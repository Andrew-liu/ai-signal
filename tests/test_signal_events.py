"""Tests for the rule-based hot/fresh event layer."""

from datetime import UTC, datetime, timedelta

from scripts.signal_events import (
    PRIMARY,
    REFERENCE,
    REPORT,
    SIGNAL,
    build_events,
    build_item,
    channel_for,
    cluster_items,
    noise_level,
    same_event,
)

NOW = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)


def rec(i, site_id, title, url, *, source="", hours_ago=1.0, **extra):
    ts = (NOW - timedelta(hours=hours_ago)).isoformat().replace("+00:00", "Z")
    out = {
        "id": f"id{i}",
        "site_id": site_id,
        "site_name": site_id,
        "source": source or site_id,
        "title": title,
        "url": url,
        "published_at": ts,
        "first_seen_at": ts,
    }
    out.update(extra)
    return out


def test_hn_mirrors_share_one_channel():
    a = channel_for(rec(1, "zeli", "x", "https://a.dev/x", source="Hacker News · 24h最热"))
    b = channel_for(rec(2, "techurls", "x", "https://a.dev/x", source="Hacker News"))
    c = channel_for(rec(3, "newsnow", "x", "https://a.dev/x", source="hackernews"))
    d = channel_for(rec(4, "iris", "x", "https://a.dev/x", source="Hacker News (黑客新闻)"))
    assert a == b == c == d == ("hn", SIGNAL)


def test_vendor_post_via_any_path_is_one_primary_channel():
    url = "https://openai.com/index/chatgpt-for-teens/"
    official = channel_for(rec(1, "official_ai", "t", url, source="OpenAI News"))
    via_aihot = channel_for(rec(2, "aihot", "t", url, source="OpenAI：官网动态（RSS）"))
    via_opml = channel_for(rec(3, "opmlrss", "t", url, source="OpenAI News"))
    assert official == via_aihot == via_opml == ("pub:openai.com", PRIMARY)


def test_media_reports_keyed_by_publisher_and_community_dropped():
    assert channel_for(rec(1, "curated_media", "t", "https://techcrunch.com/a", source="TechCrunch AI")) == (
        "pub:techcrunch.com",
        REPORT,
    )
    assert channel_for(rec(2, "tikhub_douyin", "t", "https://douyin.com/x"))[1] == "drop"
    assert channel_for(rec(3, "newsnow", "t", "https://producthunt.com/x", source="producthunt"))[1] == "drop"


def test_noise_levels():
    assert noise_level("LangChain4j 入门指南") == "hard"
    assert noise_level("Beat Apple Store prices: AirPods Max 2 deal at Amazon") == "hard"
    assert noise_level("Why Normal People Aren't Using AI Agents") == "soft"
    assert noise_level("Show HN: Cronloop, run Claude Code on a schedule") == "soft"
    assert noise_level("Anthropic宣布Claude Code默认启用自动模式") == "none"


def test_cross_lingual_reports_merge():
    official = build_item(rec(1, "official_ai", "Introducing ChatGPT for Teens: Built for learning",
                              "https://openai.com/index/teens/", source="OpenAI News",
                              title_zh="OpenAI 推出 ChatGPT for Teens：面向青少年的学习体验"))
    zh = build_item(rec(2, "aibase", "OpenAI推出ChatGPT for Teens，加强青少年安全与学习引导",
                        "https://www.aibase.com/news/1"))
    assert same_event(official, zh)


def test_same_product_different_stories_do_not_merge():
    design = build_item(rec(1, "curated_media", "Claude Code gets a /design command for UI mockups",
                            "https://the-decoder.com/design", source="The Decoder AI News"))
    limits = build_item(rec(2, "hackernews", "Claude Code May–August 2026 weekly limits promotion",
                            "https://claude.com/limits"))
    assert not same_event(design, limits)


def test_model_version_conflict_blocks_merge():
    a = build_item(rec(1, "aibase", "智谱 GLM-5.3 正式上线，开源第一", "https://www.aibase.com/news/2"))
    b = build_item(rec(2, "aibase", "智谱 GLM-5.2 正式上线，开源第一", "https://www.aibase.com/news/3"))
    assert not same_event(a, b)


def test_anchored_clustering_avoids_chaining():
    items = [
        build_item(rec(1, "curated_media", "Claude Code gets a /design command", "https://the-decoder.com/d",
                       source="The Decoder AI News")),
        build_item(rec(2, "aibase", "Anthropic官宣Claude Code整合/design命令", "https://www.aibase.com/news/4")),
        build_item(rec(3, "hackernews", "Claude Code weekly limits promotion", "https://claude.com/l")),
    ]
    clusters = cluster_items(items)
    sizes = sorted(len(c) for c in clusters)
    assert sizes == [1, 2]


def test_hot_requires_independent_channels_and_fresh_requires_reporter():
    records = [
        # Event A: official + media + HN -> hot and fresh
        rec(1, "official_ai", "Introducing GLM-5.3 open weights", "https://z.ai/blog/glm-5-3", source="Z.ai"),
        rec(2, "curated_media", "Zhipu releases GLM-5.3 with open weights", "https://techcrunch.com/glm",
            source="TechCrunch AI"),
        rec(3, "zeli", "Zhipu releases GLM-5.3 with open weights", "https://news.ycombinator.com/item?id=1",
            source="Hacker News · 24h最热"),
        # Event B: same HN story mirrored 3 times -> one channel, not hot, not fresh
        rec(4, "zeli", "Docker Sandboxes for AI agents", "https://docker.com/sandboxes",
            source="Hacker News · 24h最热"),
        rec(5, "techurls", "Docker Sandboxes for AI agents", "https://docker.com/sandboxes", source="Hacker News"),
        rec(6, "iris", "Docker Sandboxes for AI agents", "https://docker.com/sandboxes",
            source="Hacker News (黑客新闻)"),
        # Event C: tutorial -> dropped
        rec(7, "aibase", "Claude Code 入门指南：从零上手", "https://www.aibase.com/news/9"),
    ]
    payload = build_events(records, NOW)
    by_title = {s["primary_item"]["title_original"]: s for s in payload["stories"]}
    glm = next(s for s in payload["stories"] if "GLM-5.3" in s["title"])
    assert glm["is_hot"] and glm["is_fresh"]
    assert glm["source_count"] == 3
    assert payload["hot"][0] == glm["story_id"]
    docker = by_title.get("Docker Sandboxes for AI agents")
    if docker is not None:
        # 单一 HN 渠道：只能出现在赛道看板，不能进热榜/最新。
        assert not docker["is_hot"] and not docker["is_fresh"]
        assert docker["story_id"] not in payload["hot"] + payload["fresh"]
        assert any(docker["story_id"] in lane["stories"] for lane in payload["lanes"])
    assert not any("入门指南" in s["title"] for s in payload["stories"])
    assert payload["schema"] == "events_v1"
    assert payload["total_stories"] == len(payload["stories"])


def test_event_times_never_lead_now():
    future = (NOW + timedelta(hours=8)).isoformat().replace("+00:00", "Z")
    records = [
        rec(1, "official_ai", "Introducing GLM-5.3 open weights", "https://z.ai/blog/glm-5-3", source="Z.ai"),
        rec(2, "curated_media", "Zhipu releases GLM-5.3 with open weights", "https://techcrunch.com/glm",
            source="TechCrunch AI", published_at=future),
    ]
    payload = build_events(records, NOW)
    assert payload["stories"]
    for story in payload["stories"]:
        for field in ("earliest_at", "latest_at"):
            parsed = datetime.fromisoformat(story[field].replace("Z", "+00:00"))
            assert parsed <= NOW


def test_fresh_lane_uses_publish_time_not_fetch_time():
    # CI has no persisted archive, so every record's first_seen_at equals "this run".
    now_ts = NOW.isoformat().replace("+00:00", "Z")
    records = [
        rec(1, "official_ai", "Introducing GLM-5.3 open weights", "https://z.ai/blog/glm-5-3", source="Z.ai",
            hours_ago=20, first_seen_at=now_ts),
        rec(2, "official_ai", "Introducing Qwen4 open weights", "https://qwen.ai/blog/qwen4", source="Qwen",
            hours_ago=2, first_seen_at=now_ts),
        rec(3, "official_ai", "Introducing Kimi K3 open weights", "https://moonshot.ai/blog/k3", source="Moonshot",
            hours_ago=5, first_seen_at=now_ts),
    ]
    payload = build_events(records, NOW)
    by_id = {s["story_id"]: s for s in payload["stories"]}
    fresh_titles = [by_id[sid]["title"] for sid in payload["fresh"]]
    assert not any("GLM-5.3" in t for t in fresh_titles)
    assert len(fresh_titles) == 2
    assert "Qwen4" in fresh_titles[0] and "Kimi K3" in fresh_titles[1]


def test_hot_list_is_not_forced_to_half_chinese():
    """中文来源少时热榜不硬凑中英各半：更热的英文事件不会被挤掉。"""
    records = []
    for i in range(4):
        model = f"Qwen{5 + i}"
        records += [
            rec(10 * i, "official_ai", f"Introducing {model} open weights", f"https://qwen.ai/{model}", source="Qwen Blog"),
            rec(10 * i + 1, "curated_media", f"{model} launches with open weights", f"https://techcrunch.com/{model}",
                source="TechCrunch AI"),
            rec(10 * i + 2, "hackernews", f"{model} open weights released", f"https://news.ycombinator.com/item?id={i}",
                source="Hacker News"),
        ]
    payload = build_events(records, NOW)
    hot = [s for s in payload["stories"] if s["is_hot"]]
    assert len(hot) == 4
    assert all(s["lang"] == "en" for s in hot)


def test_waytoagi_is_tier3_reference_not_independent_source():
    way = rec(1, "waytoagi", "GLM-5.3 实测：编程能力大幅提升", "https://waytoagi.feishu.cn/wiki/abc")
    assert channel_for(way) == ("ref:waytoagi", REFERENCE)
    official = rec(2, "official_ai", "GLM-5.3 released with stronger coding", "https://z.ai/blog/glm-5.3",
                   source="Z.ai Blog")
    payload = build_events([official, way], NOW)
    story = next(s for s in payload["stories"] if "glm" in (s["title"] + (s["title_en"] or "")).lower())
    assert story["tier"] == 1
    assert story["source_count"] == 1  # 参考源不算独立来源
    assert {r["tier"] for r in story["sources"]} == {1, 3}
