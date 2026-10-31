import json
import re
from datetime import datetime, timedelta, timezone

import scripts.github_rising_stars as rs
from scripts.github_rising_stars import (
    SCHEMA,
    build_payload,
    classify,
    parse_trending,
    summarize_period,
)

NOW = datetime(2026, 10, 31, 8, 0, tzinfo=timezone.utc)


def _row(repo: str, desc: str, lang: str, stars: str, forks: str, gained: str, unit: str = "today") -> str:
    lang_html = f'<span itemprop="programmingLanguage">{lang}</span>' if lang else ""
    return f"""
    <article class="Box-row">
      <h2><a href="/{repo}"> {repo.split('/')[0]} / {repo.split('/')[1]} </a></h2>
      <p> {desc} </p>
      <div>{lang_html}
        <a class="Link--muted" href="/{repo}/stargazers">{stars}</a>
        <a class="Link--muted" href="/{repo}/forks">{forks}</a>
        <span class="d-inline-block float-sm-right">{gained} stars {unit}</span>
      </div>
    </article>"""


HTML = "".join([
    _row("acme/agent-kit", "Build LLM agents with MCP tools", "Python", "52,100", "3,000", "1,200"),
    _row("tiny/rocket", "A blazing fast terminal file manager", "Rust", "4,000", "120", "600"),
    _row("web/ui", "React component library with Tailwind", "TypeScript", "20,000", "900", "300"),
    '<article class="Box-row"><h2><a href="/broken">x</a></h2></article>',
])


def test_parse_trending_sorts_and_marks_dark_horse():
    projects = parse_trending(HTML, "daily")
    assert [p["repo"] for p in projects] == ["acme/agent-kit", "tiny/rocket", "web/ui"]
    assert [p["rank"] for p in projects] == [1, 2, 3]
    top = projects[0]
    assert top["stars"] == 52100 and top["forks"] == 3000 and top["stars_gained"] == 1200
    assert top["category"] == "ai" and top["category_label"] == "AI / ML"
    assert top["url"] == "https://github.com/acme/agent-kit"
    rocket = projects[1]
    assert rocket["category"] == "devtools"
    assert rocket["growth_rate"] == 15.0
    assert rocket["is_dark_horse"] is True
    assert top["is_dark_horse"] is False


def test_classify_avoids_short_keyword_false_positives():
    assert classify("Go", "Maintain rapid deployments") == "backend"
    assert classify("", "Rapid prototyping playground") == "other"
    assert classify("Python", "本地运行的大模型推理框架") == "ai"


def test_summarize_period_stats():
    period = summarize_period("daily", "今日", parse_trending(HTML, "daily"))
    assert period["total"] == 3
    assert period["champion"] == "acme/agent-kit"
    assert period["dark_horses"] == ["tiny/rocket"]
    assert [c["key"] for c in period["categories"]] == ["ai", "frontend", "devtools"]
    assert period["languages"][0]["count"] == 1


def test_build_payload_reuses_previous_snapshot_on_partial_failure():
    previous = {"periods": [{"since": "monthly", "label": "本月", "total": 0, "projects": [], "categories": []}]}

    def fetch(since):
        if since == "monthly":
            raise RuntimeError("HTTP 429")
        return HTML

    payload = build_payload(NOW, fetch, previous)
    assert payload["schema"] == SCHEMA
    assert payload["generated_at"] == "2026-10-31T08:00:00Z"
    assert [p["since"] for p in payload["periods"]] == ["daily", "weekly", "monthly"]
    assert payload["periods"][2]["stale"] is True
    assert payload["has_error"] is False
    assert "monthly" in payload["error"]


def test_build_payload_flags_total_failure():
    def fetch(since):
        raise RuntimeError("offline")

    payload = build_payload(NOW, fetch)
    assert payload["has_error"] is True
    assert all(p["total"] == 0 for p in payload["periods"])


def _payload():
    return build_payload(NOW, lambda since: HTML)


def test_enrich_skips_without_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    payload, cache = rs.enrich_with_ai(_payload(), session=None, cache={})
    assert payload["ai"]["enabled"] is False
    assert cache == {}
    assert not any(p.get("summary_zh") for per in payload["periods"] for p in per["projects"])


def test_enrich_fills_summaries_and_briefs_and_uses_cache(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(rs, "fetch_readme", lambda session, repo: "")
    calls = {"project": 0, "brief": 0}

    def fake(system, user, timeout=90):
        if system == rs.PROJECT_SYSTEM:
            calls["project"] += 1
            repos = re.findall(r"^### (\S+)", user, re.M)
            return {"items": [{"repo": r, "summary": f"{r} 是一个面向开发者的开源工具，用来演示中文介绍的生成和缓存逻辑。"} for r in repos]}
        calls["brief"] += 1
        assert "acme/agent-kit" in user
        return {"overview": "本期 AI 项目占多数。", "champion": "冠军靠 MCP 走红。", "dark_horse": "tiny/rocket 增速很快。"}

    monkeypatch.setattr(rs, "deepseek_json", fake)
    payload, cache = rs.enrich_with_ai(_payload(), session=None, cache={}, now=NOW)
    daily = payload["periods"][0]
    assert all(p["summary_zh"].startswith(p["repo"]) for p in daily["projects"])
    assert daily["brief_zh"]["overview"] == "本期 AI 项目占多数。"
    # 三期榜单项目相同：3 个项目一个批次，三期各一条点评。
    assert calls == {"project": 1, "brief": 3}
    assert payload["ai"]["requests_this_run"] == 4
    assert payload["ai"]["last_run_date"] == "2026-10-31"

    # 同一天再跑，全部命中缓存，不再调用模型。
    payload2, _ = rs.enrich_with_ai(_payload(), session=None, cache=cache, now=NOW)
    assert calls == {"project": 1, "brief": 3}
    assert payload2["ai"]["requests_this_run"] == 0
    assert payload2["periods"][1]["brief_zh"]["champion"] == "冠军靠 MCP 走红。"


NEW_ROW = _row("fresh/newcomer", "A new LLM inference server", "Go", "1,000", "10", "900")


def test_same_day_list_change_does_not_call_again(monkeypatch):
    """同一 UTC 日内榜单变化（新项目上榜、成员变动）也不会再调 DeepSeek。"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(rs, "fetch_readme", lambda session, repo: "")
    calls = []

    def fake(system, user, timeout=90):
        calls.append(system)
        if system == rs.PROJECT_SYSTEM:
            repos = re.findall(r"^### (\S+)", user, re.M)
            return {"items": [{"repo": r, "summary": f"{r} 是一个面向开发者的开源工具，用来演示中文介绍的生成和缓存逻辑。"} for r in repos]}
        return {"overview": "第一版点评。", "champion": "c", "dark_horse": ""}

    monkeypatch.setattr(rs, "deepseek_json", fake)
    _, cache = rs.enrich_with_ai(_payload(), session=None, cache={}, now=NOW)
    first = len(calls)

    later_same_day = NOW.replace(hour=23, minute=30)
    changed = build_payload(later_same_day, lambda since: HTML + NEW_ROW)
    payload, cache = rs.enrich_with_ai(changed, session=None, cache=cache, now=later_same_day)
    assert len(calls) == first
    assert payload["ai"]["requests_this_run"] == 0
    newcomer = next(p for p in payload["periods"][0]["projects"] if p["repo"] == "fresh/newcomer")
    assert "summary_zh" not in newcomer
    # 成员变了也沿用最近一次点评，而不是空白。
    assert payload["periods"][0]["brief_zh"]["overview"] == "第一版点评。"

    # 第二天闸门重新打开，只补新项目和变化了的点评。
    next_day = (NOW + timedelta(days=1)).replace(hour=0, minute=17)
    payload, cache = rs.enrich_with_ai(build_payload(next_day, lambda since: HTML + NEW_ROW), session=None, cache=cache, now=next_day)
    assert payload["ai"]["requests_this_run"] == 4  # 1 批项目 + 3 期点评
    assert payload["ai"]["last_run_date"] == "2026-11-01"
    newcomer = next(p for p in payload["periods"][0]["projects"] if p["repo"] == "fresh/newcomer")
    assert newcomer["summary_zh"].startswith("fresh/newcomer")


def test_ci_empty_cache_still_respects_daily_gate(monkeypatch):
    """CI 每轮缓存为空，只有上一版 github-rising-stars.json 留下来；同一天不能再调。"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(rs, "fetch_readme", lambda session, repo: "")
    calls = []

    def fake(system, user, timeout=90):
        calls.append(system)
        if system == rs.PROJECT_SYSTEM:
            repos = re.findall(r"^### (\S+)", user, re.M)
            return {"items": [{"repo": r, "summary": f"{r} 是一个面向开发者的开源工具，用来演示中文介绍的生成和缓存逻辑。"} for r in repos]}
        return {"overview": "第一版点评。", "champion": "c", "dark_horse": ""}

    monkeypatch.setattr(rs, "deepseek_json", fake)
    first, _ = rs.enrich_with_ai(_payload(), session=None, cache={}, now=NOW)
    used = len(calls)
    previous = json.loads(json.dumps(first))  # 模拟提交到仓库再 checkout 回来

    later = NOW.replace(hour=22)
    changed = build_payload(later, lambda since: HTML + NEW_ROW, previous)
    payload, _ = rs.enrich_with_ai(changed, session=None, cache={}, now=later, previous=previous)
    assert len(calls) == used
    assert payload["ai"]["requests_this_run"] == 0
    assert payload["ai"]["last_run_date"] == "2026-10-31"
    acme = next(p for p in payload["periods"][0]["projects"] if p["repo"] == "acme/agent-kit")
    assert acme["summary_zh"].startswith("acme/agent-kit")
    assert payload["periods"][0]["brief_zh"]["overview"] == "第一版点评。"

    next_day = (NOW + timedelta(days=1)).replace(hour=1)
    payload, _ = rs.enrich_with_ai(build_payload(next_day, lambda since: HTML + NEW_ROW, payload), session=None, cache={}, now=next_day, previous=payload)
    # 第二天只补新项目（1 批）和成员变了的三期点评，已有介绍从上一版恢复，不重写。
    assert payload["ai"]["requests_this_run"] == 4


def test_failed_run_is_not_retried_same_day(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(rs, "fetch_readme", lambda session, repo: "")
    calls = []
    monkeypatch.setattr(rs, "deepseek_json", lambda system, user, timeout=90: calls.append(system))
    payload, cache = rs.enrich_with_ai(_payload(), session=None, cache={}, now=NOW)
    assert len(calls) == 4
    assert cache == {rs.AI_GATE_KEY: "2026-10-31"}
    payload, cache = rs.enrich_with_ai(_payload(), session=None, cache=cache, now=NOW.replace(hour=20))
    assert len(calls) == 4
    assert payload["ai"]["requests_this_run"] == 0


def test_enrich_rejects_bad_model_output(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(rs, "fetch_readme", lambda session, repo: "")
    monkeypatch.setattr(rs, "deepseek_json", lambda system, user, timeout=90: {"items": [{"repo": "acme/agent-kit", "summary": "too short"}]} if system == rs.PROJECT_SYSTEM else None)
    payload, cache = rs.enrich_with_ai(_payload(), session=None, cache={}, now=NOW)
    assert not any(p.get("summary_zh") for p in payload["periods"][0]["projects"])
    assert "brief_zh" not in payload["periods"][0]
    assert set(cache) == {rs.AI_GATE_KEY}


def test_readme_excerpt_strips_badges_and_code():
    md = "# Tool\n![badge](https://x/y.svg)\n<p align=center>hi</p>\n```bash\nrm -rf /\n```\nA [fast](https://a) tool."
    text = rs._readme_excerpt(md)
    assert "badge" not in text and "rm -rf" not in text and "<p" not in text
    assert "A fast tool." in text
