"""Tests for the AGI HUNT source: collector parsing + high-weight models channel."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import requests

from scripts import update_news
from scripts.signal_events import REPORT, build_events, channel_for

NOW = datetime(2026, 10, 9, 4, 0, tzinfo=UTC)  # 北京时间 12:00


def iso(hours_ago: float) -> str:
    return (NOW - timedelta(hours=hours_ago)).isoformat().replace("+00:00", "Z")


def ah_rec(i, title, url, *, channel="models", sort="hot", rank=1, hours_ago=1.0, **extra):
    out = {
        "id": f"ah{i}",
        "site_id": "agihunt",
        "site_name": "AGI HUNT",
        "source": f"AGI HUNT · {channel}",
        "title": title,
        "url": url,
        "published_at": iso(hours_ago),
        "first_seen_at": iso(0),
        "agihunt_channel": channel,
        "agihunt_sort": sort,
        "agihunt_rank": rank,
    }
    out.update(extra)
    return out


def test_parse_agihunt_items_keeps_rank_and_channel():
    payload = {"items": [
        {"title": "Qwen4 发布", "text": "阿里发布 Qwen4，开源权重", "url": "https://x.com/a/status/1",
         "author": "Qwen", "hot": "98.5", "cluster_id": "c1", "published_at": iso(1)},
        {"title": "", "text": "", "url": "https://x.com/a/status/2"},
        {"title": "no url", "url": "ftp://bad"},
        {"title": "Kimi K3", "url": "https://mp.weixin.qq.com/s/abc", "published_at": iso(2)},
    ]}
    items = update_news.parse_agihunt_items(payload, "models", "hot", 40, NOW)
    assert [it.title for it in items] == ["Qwen4 发布", "Kimi K3"]
    assert items[0].site_id == "agihunt"
    assert items[0].source == "AGI HUNT · 模型"
    assert items[0].meta["agihunt_rank"] == 1 and items[1].meta["agihunt_rank"] == 4
    assert items[0].meta["agihunt_hot"] == 98.5
    assert items[0].meta["agihunt_cluster"] == "c1"
    assert items[0].meta["summary"].startswith("阿里发布")


def test_merge_dedupes_same_cluster_across_urls():
    a = update_news.RawItem("agihunt", "AGI HUNT", "s", "t1", "https://x.com/a/1", None,
                            {"agihunt_channel": "models", "agihunt_sort": "new", "agihunt_rank": 1, "agihunt_cluster": "k"})
    b = update_news.RawItem("agihunt", "AGI HUNT", "s", "t2", "https://x.com/b/2", None,
                            {"agihunt_channel": "models", "agihunt_sort": "hot", "agihunt_rank": 4, "agihunt_cluster": "k"})
    merged = update_news.merge_agihunt_items([a, b])
    assert merged == [b]


def test_request_plan_is_small_and_uses_beijing_day():
    plan = update_news.agihunt_request_plan(NOW)
    assert len(plan) <= 6
    assert {day for *_, day in plan} == {"2026-10-09"}
    early = update_news.agihunt_request_plan(datetime(2026, 10, 8, 18, 0, tzinfo=UTC))  # 北京 02:00
    assert ("models", "hot", 30, "2026-10-08") in early
    assert len(early) <= 7


def test_merge_prefers_models_hot_rank():
    a = update_news.RawItem("agihunt", "AGI HUNT", "s", "t", "https://x.com/a/1", None,
                            {"agihunt_channel": "research", "agihunt_sort": "hot", "agihunt_rank": 1})
    b = update_news.RawItem("agihunt", "AGI HUNT", "s", "t", "https://x.com/a/1", None,
                            {"agihunt_channel": "models", "agihunt_sort": "new", "agihunt_rank": 3})
    c = update_news.RawItem("agihunt", "AGI HUNT", "s", "t", "https://x.com/a/1", None,
                            {"agihunt_channel": "models", "agihunt_sort": "hot", "agihunt_rank": 9})
    merged = update_news.merge_agihunt_items([a, b, c])
    assert len(merged) == 1 and merged[0] is c


def _resp(status, payload):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload
    return r


def test_fetch_stops_on_rate_limit_and_requires_key(monkeypatch):
    monkeypatch.delenv("AGIHUNT_API_KEY", raising=False)
    try:
        update_news.fetch_agihunt(MagicMock(), NOW)
        raise AssertionError("expected missing key error")
    except RuntimeError as exc:
        assert "AGIHUNT_API_KEY" in str(exc)

    monkeypatch.setenv("AGIHUNT_API_KEY", "test-key")
    session = MagicMock(spec=requests.Session)
    ok = {"items": [{"title": "GPT-6 发布", "url": "https://openai.com/index/gpt-6", "published_at": iso(1)}]}
    session.get.side_effect = [_resp(200, ok), _resp(429, {"error": {"code": "rate_limited"}})]
    items = update_news.fetch_agihunt(session, NOW)
    assert len(items) == 1
    assert session.get.call_count == 2  # 429 后不再继续请求
    headers = session.get.call_args_list[0].kwargs["headers"]
    assert headers["Authorization"] == "Bearer test-key"
    assert headers["X-AgiHunt-Skill-Version"] == update_news.AGIHUNT_SKILL_VERSION


def test_agihunt_channel_not_collapsed_into_publisher():
    rec = ah_rec(1, "GPT-6", "https://openai.com/index/gpt-6")
    assert channel_for(rec) == ("agihunt:models", REPORT)


def test_models_top_rank_is_hot_alone_and_fresh():
    records = [
        ah_rec(1, "Qwen4 正式开源，多项基准超越前代", "https://x.com/qwen/status/1", rank=2, hours_ago=1),
        ah_rec(2, "某创业公司融资 1 亿美元", "https://x.com/s/status/2", channel="funding", rank=1, hours_ago=1),
    ]
    payload = build_events(records, NOW)
    by_title = {s["title"]: s for s in payload["stories"]}
    qwen = by_title["Qwen4 正式开源，多项基准超越前代"]
    assert qwen["is_hot"] and qwen["is_fresh"]
    assert qwen["category"] in {"model", "devtool", "research"}
    assert "agihunt_models_hot" in qwen["reasons"]
    funding = by_title.get("某创业公司融资 1 亿美元")
    assert not (funding and funding["is_hot"])  # 非 models 频道单渠道不上热榜


def test_models_channel_opinion_post_not_fresh():
    records = [ah_rec(1, "博主吐槽：让 Opus 仿我声音做视频，比写人味文字容易多了", "https://x.com/u/status/9", rank=30)]
    stories = build_events(records, NOW)["stories"]
    assert not any(s["is_fresh"] for s in stories)


def test_models_channel_outweighs_other_report_channel():
    base = {"hours_ago": 2}
    model_evt = [
        ah_rec(1, "DeepSeek V4 发布", "https://x.com/ds/status/1", rank=12, **base),
        {"id": "m2", "site_id": "aibase", "site_name": "AIbase", "source": "AIbase", "title": "DeepSeek V4 正式发布",
         "url": "https://www.aibase.com/news/1", "published_at": iso(2), "first_seen_at": iso(0)},
    ]
    other_evt = [
        ah_rec(3, "Mistral Large 4 发布", "https://x.com/m/status/3", channel="research", rank=12, **base),
        {"id": "m4", "site_id": "aibase", "site_name": "AIbase", "source": "AIbase", "title": "Mistral Large 4 正式发布",
         "url": "https://www.aibase.com/news/2", "published_at": iso(2), "first_seen_at": iso(0)},
    ]
    payload = build_events(model_evt + other_evt, NOW)
    scores = {s["title_zh"] or s["title"]: s["hot_score"] for s in payload["stories"]}
    ds = next(v for k, v in scores.items() if "DeepSeek" in k)
    ms = next(v for k, v in scores.items() if "Mistral" in k)
    assert ds > ms
