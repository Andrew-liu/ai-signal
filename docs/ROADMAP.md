# AI News Radar Roadmap

## Removed — 三口味 persona / 每日精选 / 旧故事层（2026-10-09）

v0.8–v0.9 的「今日 TOP3 · 三口味锐评」、精选卡片锐评行、`daily-brief.json` 精选池、`stories-merged.json` 故事层与前端二次热度打分已整体删除，不再保留开关或兜底。

- 替代：`scripts/signal_events.py` 生成 `data/events.json`（`hot` / `fresh` 双通道），热点榜读 `hot`，「最新」页读 `fresh`。
- 删除的产物：`personas/`、`scripts/persona_score.py`、`data/daily-brief.json`、`data/stories-merged.json`、`data/top3-personas.json`、`data/merge-log.json`。
- 无兜底的代价：`events.json` 结构异常或与 `latest-24h.json` 生成时间相差超过 1 小时，`quality_gate.py` 会直接拦下该轮发布。

## v0.3.0 — Source Overlap Check

Goal: before adding a new public default source, evaluate whether its recent items are mostly duplicates of the existing source set.

Status: implemented as a maintainer-facing intake tool.

### What ships

- `scripts/evaluate_source_overlap.py`
  - Fetches a candidate RSS/Atom source.
  - Compares recent candidate items against `data/archive.json` or another baseline JSON.
  - Reports hard duplicates, possible duplicates, unique items, top overlapping sources, and a recommendation.
- `tests/test_source_overlap.py`
  - Covers URL exact matches, title similarity, duplicate-rate statistics, threshold recommendations, and the small-sample guard.

### Default decision thresholds

- `< 35%` duplicate rate: `accept_default`
- `35%–65%` duplicate rate: `watchlist`
- `>= 65%` duplicate rate: `skip_duplicate`
- `< 5` recent candidate items: always `watchlist`, because the sample is too small for automatic rejection.

### Example

```bash
python scripts/evaluate_source_overlap.py \
  --source-url https://aihot.virxact.com/feed.xml \
  --source-name "AI HOT" \
  --site-id aihot_candidate \
  --baseline data/archive.json \
  --lookback-days 7 \
  --output /tmp/aihot-overlap.json
```

The tool is advisory only. It does not change `update_news.py`, does not remove any items, and does not publish the report to GitHub Pages by default.

## v0.4.0 — Explainable AI Relevance Scoring

Goal: move beyond a black-box boolean topic filter and make every AI relevance decision inspectable, testable, and tunable.

Status: implemented as the default topic-filtering layer.

### What ships

- `scripts/ai_relevance.py`
  - Scores each normalized record with `score_ai_relevance(record)`.
  - Emits `is_ai_related`, `score`, `label`, `reason`, `signals`, and `noise`.
  - Keeps `is_ai_related_record(record)` as a backward-compatible boolean wrapper.
- `scripts/update_news.py`
  - Uses the new scorer before writing the 24h Signal payload.
  - Adds AI relevance fields to kept records so downstream UI and audits can explain why an item passed.
  - Publishes the filter metadata as `topic_filter=ai_relevance_scoring_v0_4` and `ai_relevance_threshold=0.65`.
- `scripts/audit_ai_relevance.py`
  - Generates a Markdown audit report from `latest-24h.json` and `latest-24h-all.json`.
  - Summarizes raw keep rate, label distribution, source keep rate, top kept samples, high-score dropped samples, and review-band candidates.
- `tests/test_ai_relevance.py`
  - Covers strong AI signals, broad AI terms with tech context, trusted AI-source priors, noise suppression, structured output fields, and boolean compatibility.

### Default decision thresholds

- `score >= 0.65`: keep in the AI Signal view.
- `0.45 <= score < 0.65`: review band for future manual or LLM second-pass review.
- `< 0.45`: keep only in all-mode/archive data.

### Audit example

```bash
python scripts/update_news.py \
  --output-dir /tmp/ai-news-radar-v0.4-preview \
  --window-hours 24 \
  --rss-opml feeds/follow.opml

python scripts/audit_ai_relevance.py \
  --data-dir /tmp/ai-news-radar-v0.4-preview \
  --output reports/ai-relevance-audit/v0.4.0-YYYY-MM-DD.md
```

### Non-goals for v0.4.0

- No LLM classifier in the default GitHub Actions path.
- No full-body semantic reading; the default scorer remains title/source/url based.
- No automatic source deletion based on keep rate.
- No public page layout redesign.

## v0.5.0 — Story Merge / Event Cluster

Goal: move beyond per-item filtering and represent the same event as one story with multiple source references.

### Planned direction

- Keep the current filter-first behavior as the safe default.
- Add a story clustering layer after source normalization and before page payload generation.
- Preserve one primary title plus secondary source references, instead of randomly choosing one duplicated item.
- Show repeated coverage as a trust signal: "多个来源报道了这件事".

### Non-goals for v0.5.0

- No LLM semantic clustering in the first pass.
- No cross-language deep semantic matching unless the rule-based event merge proves insufficient.
- No automatic deletion of sources based only on overlap score.
- No change to the public page layout unless the story data model is stable.
