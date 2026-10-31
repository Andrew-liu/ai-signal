"""Tests for the lane board: open-source lane, GitHub Trending, AIbase times, category and clustering fixes."""

from datetime import UTC, datetime, timedelta

from scripts import update_news
from scripts.signal_events import (
    LANES,
    SIGNAL,
    build_events,
    build_item,
    channel_for,
    cluster_items,
    same_event,
)

NOW = datetime(2026, 10, 9, 8, 0, tzinfo=UTC)


def iso(hours_ago: float) -> str:
    return (NOW - timedelta(hours=hours_ago)).isoformat().replace("+00:00", "Z")


def rec(i, site_id, title, url, *, source="", hours_ago=1.0, **extra):
    out = {
        "id": f"lane{i}",
        "site_id": site_id,
        "site_name": site_id,
        "source": source or site_id,
        "title": title,
        "url": url,
        "published_at": iso(hours_ago),
        "first_seen_at": iso(hours_ago),
    }
    out.update(extra)
    return out


def gh_rec(i, repo, desc, *, stars_today=500, rank=1):
    return rec(
        i, "github_trending", f"{repo}: {desc}", f"https://github.com/{repo}",
        source="GitHub Trending · 日榜", hours_ago=0,
        github_repo=repo, github_stars_today=stars_today, github_stars=12000,
        github_language="Python", github_trending_rank=rank, summary=desc,
    )


# ---------------------------------------------------------------------------
# Category fixes
# ---------------------------------------------------------------------------


def test_versioned_model_beats_open_source_keyword():
    item = build_item(rec(1, "aihot", "GLM-5.3上线：AA智能指数60分并列开源第一，成本更低", "https://aihot.dev/glm"))
    assert item.category == "model"


def test_incidental_chips_mention_is_not_chip_lane():
    item = build_item(rec(
        2, "curated_media",
        "Anthropic CEO says AI centralizes by nature and open models just shift power to whoever owns the chips",
        "https://the-decoder.com/anthropic-ceo",
    ))
    assert item.category != "chip"


def test_real_chip_news_stays_in_chip_lane():
    item = build_item(rec(3, "aibase", "阿里5nm RISC-V芯片成功原生跑通270亿大模型", "https://www.aibase.com/news/1"))
    assert item.category == "chip"


def test_github_repo_and_trending_go_to_opensource():
    trending = build_item(gh_rec(4, "vllm-project/vllm", "A high-throughput inference engine for LLMs"))
    show_hn = build_item(rec(5, "hackernews", "Show HN: Local agent memory for LLM apps",
                             "https://github.com/acme/agent-memory"))
    blog = build_item(rec(6, "official_ai", "GitHub Copilot coding agent is now generally available",
                          "https://github.blog/changelog/copilot-agent"))
    assert trending.category == "opensource"
    assert show_hn.category == "opensource"
    assert blog.category != "opensource"


def test_github_trending_is_signal_channel_shared_with_newsnow():
    a = channel_for(gh_rec(7, "acme/x", "LLM agent toolkit"))
    b = channel_for(rec(8, "newsnow", "acme / x", "https://github.com/acme/x", source="github"))
    assert a == b == ("github_trending", SIGNAL)


# ---------------------------------------------------------------------------
# Clustering: same org + same rare action concept
# ---------------------------------------------------------------------------


def test_openai_slowdown_reports_merge_across_wording():
    records = [
        rec(10, "official_ai", "Pacing model development in an era of cyber-critical capabilities",
            "https://openai.com/index/pacing-model-development", source="OpenAI", hours_ago=10,
            title_zh="OpenAI 在“关键网络能力”时代放缓模型开发节奏"),
        rec(11, "hackernews", "OpenAI announces slowing pace of development after hack by rogue agent",
            "https://www.theinformation.com/openai-slow", source="Hacker News", hours_ago=4),
        rec(12, "zeli", "OpenAI pauses frontier model training", "https://www.wsj.com/openai-pause",
            source="Hacker News · 24h最热", hours_ago=6),
        rec(13, "aibase", "AI模型“越狱”偷袭Hugging Face，OpenAI已暂停部分AI训练工作长达两周",
            "https://www.aibase.com/news/2", hours_ago=3),
    ]
    clusters = cluster_items([build_item(r) for r in records])
    assert len(clusters) == 1


def test_concept_merge_needs_shared_org():
    a = build_item(rec(14, "curated_media", "OpenAI pauses frontier model training", "https://a.com/1"))
    b = build_item(rec(15, "curated_media", "Waymo pauses robotaxi service in Austin", "https://b.com/2"))
    assert not same_event(a, b)


def test_concept_merge_respects_time_window():
    a = build_item(rec(16, "curated_media", "OpenAI pauses frontier model training", "https://a.com/1", hours_ago=1))
    b = build_item(rec(17, "curated_media", "OpenAI slows rollout of voice mode", "https://b.com/2", hours_ago=30))
    assert not same_event(a, b)


# ---------------------------------------------------------------------------
# Unknown publish time
# ---------------------------------------------------------------------------


def test_unknown_publish_time_is_archive_only():
    # 旧文不刷屏：没有可信发布时间、也没有当前热榜背书 → 不进热榜/最新/赛道。
    records = [
        rec(20, "aibase", "OpenAI 发布 GPT-6 mini 推理模型", "https://www.aibase.com/news/20",
            hours_ago=0, published_at=None, published_estimated=True),
    ]
    payload = build_events(records, NOW)
    assert payload["stories"] == []
    assert all(not lane["stories"] for lane in payload["lanes"])


def test_unknown_publish_time_with_hot_list_backing_is_never_fresh():
    records = [
        rec(21, "aihot", "OpenAI 发布 GPT-6 mini 推理模型", "https://aihot.news/s/21",
            hours_ago=0, published_estimated=True, aihot_hot_rank=2, aihot_category="ai-models"),
        rec(22, "aibase", "OpenAI 发布 GPT-6 mini 推理模型", "https://www.aibase.com/news/22",
            hours_ago=0, published_at=None, published_estimated=True),
    ]
    payload = build_events(records, NOW)
    story = payload["stories"][0]
    assert story["time_known"] is False
    assert not story["is_fresh"]
    assert story["freshness"] <= 0.35


def test_future_publish_time_is_untrusted():
    seen = (NOW - timedelta(hours=1)).isoformat()
    future = (NOW + timedelta(hours=3)).isoformat()
    records = [
        rec(23, "curated_media", "OpenAI launches GPT-6 mini reasoning model", "https://techcrunch.com/a",
            published_at=future, first_seen_at=seen),
    ]
    assert build_events(records, NOW)["stories"] == []


# ---------------------------------------------------------------------------
# Lanes payload
# ---------------------------------------------------------------------------


def test_lanes_payload_groups_events_and_ranks_by_heat():
    records = [
        gh_rec(30, "acme/agent-kit", "Open-source LLM agent framework", stars_today=2400, rank=1),
        gh_rec(31, "acme/rag-lite", "Tiny RAG library for LLM apps", stars_today=150, rank=7),
        gh_rec(32, "acme/stock-bot", "Daily stock analysis scripts", stars_today=900, rank=3),  # not AI
        rec(33, "curated_media", "Etched raises $500M at $21B valuation", "https://techcrunch.com/etched"),
        rec(34, "official_ai", "Introducing Qwen4 open weights", "https://qwen.ai/blog/qwen4", source="Qwen"),
    ]
    payload = build_events(records, NOW)
    assert [lane["key"] for lane in payload["lanes"]] == [key for key, _, _ in LANES]
    by_id = {s["story_id"]: s for s in payload["stories"]}
    lanes = {lane["key"]: lane for lane in payload["lanes"]}

    oss = [by_id[sid] for sid in lanes["opensource"]["stories"]]
    assert [s["github"]["repo"] for s in oss] == ["acme/agent-kit", "acme/rag-lite"]
    assert oss[0]["github"]["stars_today"] == 2400
    assert all(not s["is_hot"] and not s["is_fresh"] for s in oss)

    assert [by_id[sid]["lane"] for sid in lanes["business"]["stories"]] == ["business"]
    assert [by_id[sid]["lane"] for sid in lanes["model"]["stories"]] == ["model"]
    assert payload["total_stories"] == len(payload["stories"])
    for lane in payload["lanes"]:
        assert set(lane["stories"]) <= set(by_id)


# ---------------------------------------------------------------------------
# Collectors
# ---------------------------------------------------------------------------

TRENDING_HTML = """
<article class="Box-row">
  <h2 class="h3 lh-condensed"><a class="Link" href="/vllm-project/vllm">
    <span class="text-normal">vllm-project /</span> vllm</a></h2>
  <p class="col-9 color-fg-muted my-1">  A high-throughput and memory-efficient inference engine for LLMs </p>
  <div class="f6 color-fg-muted mt-2">
    <span itemprop="programmingLanguage">Python</span>
    <a class="Link" href="/vllm-project/vllm/stargazers"> 61,234</a>
    <span class="d-inline-block float-sm-right">1,024 stars today</span>
  </div>
</article>
<article class="Box-row">
  <h2 class="h3 lh-condensed"><a class="Link" href="/acme/no-desc"><span>acme /</span> no-desc</a></h2>
</article>
"""


def test_parse_github_trending_extracts_repo_metrics():
    items = update_news.parse_github_trending(TRENDING_HTML, NOW)
    assert [it.url for it in items] == ["https://github.com/vllm-project/vllm", "https://github.com/acme/no-desc"]
    first = items[0]
    assert first.site_id == "github_trending"
    assert first.title.startswith("vllm-project/vllm: A high-throughput")
    assert first.meta["github_stars"] == 61234
    assert first.meta["github_stars_today"] == 1024
    assert first.meta["github_language"] == "Python"
    assert first.meta["github_trending_rank"] == 1
    assert first.published_at == NOW
    assert items[1].title == "acme/no-desc"
    assert "github_stars_today" not in items[1].meta


AIBASE_HTML = (
    '<script>self.__next_f.push([1,"{\\"Id\\":31509,\\"title\\":\\"OpenAI 年化收入\\",\\"description\\":\\"x\\",'
    '\\"addtime\\":\\"2026-10-09 16:56:50\\",\\"updtime\\":\\"2026-10-09 16:56:50\\"}'
    '{\\"Id\\":31507,\\"title\\":\\"谷歌云发布 Gemini Agent\\",\\"addtime\\":\\"2026-10-09 16:05:56\\"}"])</script>'
)


def test_aibase_addtimes_maps_article_id_to_utc():
    times = update_news.aibase_addtimes(AIBASE_HTML)
    assert times["31509"] == datetime(2026, 10, 9, 8, 56, 50, tzinfo=UTC)
    assert times["31507"] == datetime(2026, 10, 9, 8, 5, 56, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Regressions found on live data (2026-10-09)
# ---------------------------------------------------------------------------


def test_github_repo_never_merges_with_news_about_same_org():
    news = build_item(rec(40, "aihot", "Claude 九月回顾：Chat 与 Cowork 合一，Claude 5.5 系列模型上线",
                          "https://www.youtube.com/shorts/x"))
    repo = build_item(gh_rec(41, "anthropics/knowledge-work-plugins", "Plugins for Claude Cowork"))
    mirror = build_item(rec(42, "newsnow", "anthropics /      knowledge-work-plugins",
                            "https://github.com/anthropics/knowledge-work-plugins", source="github"))
    assert not same_event(news, repo)
    assert same_event(repo, mirror)
    assert mirror.title == "anthropics/knowledge-work-plugins"


def test_github_repo_title_is_not_machine_translated():
    item = build_item(rec(43, "newsnow", "thedotmack / claude-mem", "https://github.com/thedotmack/claude-mem",
                          source="github", title_zh="塞多马克 / Claude·梅姆"))
    assert item.title_zh == ""


def test_revenue_policy_and_valuation_reports_merge():
    revenue = [
        rec(50, "aibase", "OpenAI 年化营收被曝接近 500 亿美元", "https://www.ithome.com/1"),
        rec(51, "curated_media", "OpenAI's revenue is reportedly $20 billion less than projected", "https://techcrunch.com/1"),
    ]
    policy = [
        rec(52, "aibase", "Anthropic更新使用政策，首次明令禁止“虐待”Claude", "https://www.aibase.com/news/52"),
        rec(53, "curated_media", "Anthropic bans abusive or cruel behavior towards Claude", "https://engadget.com/1"),
        rec(54, "curated_media", "Being mean to Claude can now get your account suspended under Anthropic rules", "https://verge.com/1"),
    ]
    arena = [
        rec(55, "aihot", "Arena 完成 2 亿美元 B 轮融资，估值 31 亿美元", "https://x.com/arena/status/1"),
        rec(56, "curated_media", "Popular AI leaderboard Arena nearly doubles valuation to $3.1B", "https://techcrunch.com/2"),
    ]
    for group in (revenue, policy, arena):
        assert len(cluster_items([build_item(r) for r in group])) == 1


def test_cross_lingual_entity_phrase_merges():
    a = build_item(rec(60, "aibase", "谷歌云重磅发布Gemini Agent，全面杀入企业级AI办公赛道", "https://www.aibase.com/news/60"))
    b = build_item(rec(61, "curated_media", "Google Cloud Launches Gemini Agent for the enterprise", "https://marktechpost.com/1"))
    c = build_item(rec(62, "curated_media", "Gemini app adds offline mode", "https://9to5google.com/1"))
    assert same_event(a, b)
    assert not same_event(b, c)


def test_classification_fixes_from_live_data():
    gpu_free = build_item(rec(70, "aibase", "网页端 46MB 抠图模型升级，不要显卡也能跑", "https://www.aibase.com/news/70"))
    lawsuit = build_item(rec(71, "aibase", "AI陪伴机器人诱导自残，Character.AI遭美肯塔基州起诉", "https://www.aibase.com/news/71"))
    hardware = build_item(rec(72, "agihunt", "Odyssey 发布世界模型 Odyssey-3", "https://x.com/o/status/1",
                              agihunt_channel="hardware", agihunt_sort="hot", agihunt_rank=1))
    report = build_item(rec(73, "agihunt", "Contra 发布 Creative Intelligence 2026 报告", "https://x.com/c/status/1",
                            agihunt_channel="funding", agihunt_sort="hot", agihunt_rank=2))
    seed = build_item(rec(74, "agihunt", "Phinity 出隐身：AI 芯片设计获 520 万美元种子轮", "https://x.com/p/status/1",
                          agihunt_channel="funding", agihunt_sort="hot", agihunt_rank=3))
    assert gpu_free.category != "chip"
    assert lawsuit.category == "safety"
    assert hardware.category == "robotics"
    assert report.category != "business"
    assert seed.category == "business"


def test_lane_skips_single_source_opinion_posts():
    records = [
        rec(80, "agihunt", "博主吐槽：让 Opus 5.5 仿我声音做视频", "https://x.com/b/status/1",
            agihunt_channel="models", agihunt_sort="new", agihunt_rank=9),
        rec(81, "aibase", "智谱发布 GLM-5.3 推理模型", "https://www.aibase.com/news/81"),
    ]
    payload = build_events(records, NOW)
    by_id = {s["story_id"]: s for s in payload["stories"]}
    model_lane = next(lane for lane in payload["lanes"] if lane["key"] == "model")
    titles = [by_id[sid]["title"] for sid in model_lane["stories"]]
    assert all("吐槽" not in t for t in titles)
    assert any("GLM-5.3" in t for t in titles)
