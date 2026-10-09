"""DeepSeek 更新日志 / 智谱发布记录两个官方源的解析与事件层折叠。"""

from datetime import UTC, datetime

from scripts.signal_events import PRIMARY, build_item, channel_for, cluster_items
from scripts.update_news import (
    parse_anthropic_news_items,
    parse_deepseek_updates_items,
    parse_meta_ai_blog_items,
    parse_meta_newsroom_feed,
    parse_xai_news_items,
    parse_zhipu_release_feed,
)

NOW = datetime(2026, 9, 11, 2, 0, tzinfo=UTC)
OCT = datetime(2026, 10, 9, 8, 0, tzinfo=UTC)

ANTHROPIC = """
<a href="/news/claude-frontier-academy" class="FeaturedGrid-module__card"><h3>Anthropic invests $100 million</h3>
<time class="FeaturedGrid-module__date">Oct 2, 2026</time></a>
<ul>
<li><a href="/news/2026-usage-policy-update" class="PublicationList-module-scss-module__KxYrHG__listItem">
<div class="PublicationList-module-scss-module__KxYrHG__meta"><time class="x__date">Oct 8, 2026</time>
<span class="PublicationList-module-scss-module__KxYrHG__subject">Announcements</span></div>
<span class="PublicationList-module-scss-module__KxYrHG__title body-3">2026 Usage Policy update</span></a></li>
<li><a href="/news/claude-frontier-academy" class="PublicationList-module__listItem"><time>Oct 2, 2026</time>
<span class="PublicationList-module__title">Anthropic invests $100 million</span></a></li>
<li><a href="/news/old-post" class="PublicationList-module__listItem"><time>Jan 2, 2025</time>
<span class="PublicationList-module__title">Old post</span></a></li>
</ul>
"""

XAI = """
<a class="group/card block" href="/news/grok-4-7"><div><span>Grok 4.7</span></div>
<div><h2>Introducing Grok 4.7</h2><p>Our smartest model.</p><div>Sep 21, 2026</div></div></a>
<a class="group/card" href="/news/designing-grok-bot"><div class="flex-1"><h3>Designing Grok Bot</h3>
<p>How we designed Grok Bot.</p></div><div class="shrink-0 text-xs">Sep 3, 2026</div></a>
<a href="/news/grok-1.5"><h3>Grok-1.5</h3><div>Mar 28, 2024</div></a>
"""

META_BLOG = """
<a class="_amcw" href="https://ai.meta.com/blog/introducing-muse-spark-meta-model-api/"><img/></a>
<div class="_amd1"><a class="_amd2" href="https://ai.meta.com/blog/introducing-muse-spark-meta-model-api/">Introducing Muse Spark 1.1 </a></div>
<div class="_amun">September 30, 2026</div>
<a class="_amd2" href="https://ai.meta.com/blog/tribe-v2/">TRIBE v2: a brain predictive model</a><div>July 09, 2026</div>
"""

META_FEED = b"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
<item><title>Why Data Centers Are Such a Big Part of Meta&#8217;s AI Approach</title>
<link>https://about.fb.com/news/2026/10/meta-data-centers-ai-approach/</link>
<pubDate>Wed, 07 Oct 2026 23:19:00 +0000</pubDate><category><![CDATA[Meta]]></category><category><![CDATA[AI]]></category></item>
<item><title>Measures to Fight Child Exploitation</title><link>https://about.fb.com/news/2026/10/x/</link>
<pubDate>Wed, 07 Oct 2026 10:00:00 +0000</pubDate><category><![CDATA[India Newsroom]]></category></item>
</channel></rss>"""

DEEPSEEK_ZH = """
<article><div class="theme-doc-markdown markdown"><h1>更新日志</h1><hr>
<h2 id="时间-2026-09-10">时间: 2026-09-10<a class="hash-link">\u200b</a></h2>
<h3 id="deepseek-v41-flash-发布">DeepSeek-V4.1-Flash 发布<a class="hash-link">\u200b</a></h3>
<p>今天，我们正式发布 DeepSeek-V4.1-Flash 模型。</p>
<ul><li>GPQA Diamond: 90.9</li></ul>
<h2 id="时间-2026-08-21">时间: 2026-08-21</h2>
<h3 id="deepseek-v4-flash-vision-exp-发布">DeepSeek-V4-Flash-Vision-Exp 发布</h3>
<h2 id="时间-2025-12-01">时间: 2025-12-01</h2>
<h3 id="deepseek-v32">DeepSeek-V3.2</h3>
</div></article>
"""

DEEPSEEK_EN = """
<article><div class="theme-doc-markdown markdown">
<h2 id="date-2026-09-10">Date: 2026-09-10</h2>
<h3 id="deepseek-v41-flash-release">DeepSeek-V4.1-Flash Release</h3>
<p>Introducing DeepSeek-V4.1-Flash.</p>
</div></article>
"""

ZHIPU_ZH = """<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:content="http://purl.org/rss/1.0/modules/content/" version="2.0"><channel>
<title><![CDATA[模型与产品发布记录]]></title>
<item>
<title><![CDATA[2026-09-10]]></title>
<link>https://docs.bigmodel.cn/cn/update/new-releases#2026-09-10</link>
<pubDate>Thu, 10 Sep 2026 13:39:25 GMT</pubDate>
<content:encoded><![CDATA[<p>👀 <a href="https://docs.bigmodel.cn/cn/guide/models/vlm/glm-5.3-flash"><strong>GLM-5.3-Flash</strong></a></p>
<ul><li>原生融入视觉能力，使模型能够主动观察界面</li><li>极致高效混合架构</li></ul>]]></content:encoded>
</item>
<item>
<title><![CDATA[2026-04-07]]></title>
<link>https://docs.bigmodel.cn/cn/update/new-releases#2026-04-07</link>
<pubDate>Tue, 07 Apr 2026 10:00:00 GMT</pubDate>
<content:encoded><![CDATA[<p><strong>GLM-5</strong></p>]]></content:encoded>
</item>
</channel></rss>
""".encode()

ZHIPU_EN = """<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:content="http://purl.org/rss/1.0/modules/content/" version="2.0"><channel>
<item>
<title><![CDATA[2026-09-10]]></title>
<link>https://docs.z.ai/release-notes/new-released#2026-09-10</link>
<pubDate>Thu, 10 Sep 2026 14:16:05 GMT</pubDate>
<content:encoded><![CDATA[<ul>
<li><p>Native visual capabilities enable the model to observe interfaces, rendering results, and feedback.</p></li>
<li><p>Beyond coding. Learn more in our <a href="https://docs.z.ai/guides/vlm/glm-5.3-flash">documentation</a>.</p></li>
</ul>]]></content:encoded>
</item>
</channel></rss>
""".encode()


def as_record(i, raw):
    ts = raw.published_at.isoformat().replace("+00:00", "Z")
    return {
        "id": f"v{i}",
        "site_id": raw.site_id,
        "site_name": raw.site_name,
        "source": raw.source,
        "title": raw.title,
        "url": raw.url,
        "published_at": ts,
        "first_seen_at": ts,
    }


def test_deepseek_updates_parse_h3_releases_with_dates():
    page = "https://api-docs.deepseek.com/zh-cn/updates"
    items = parse_deepseek_updates_items(DEEPSEEK_ZH, NOW, page, "DeepSeek 更新日志")
    assert [it.title for it in items] == ["DeepSeek-V4.1-Flash 发布", "DeepSeek-V4-Flash-Vision-Exp 发布"]
    first = items[0]
    assert first.site_id == "official_ai"
    assert first.url == f"{page}#deepseek-v41-flash-发布"
    # 只有日期：按北京时间当天中午估计（UTC 04:00），超过 45 天的 V3.2 被丢弃。
    assert first.published_at == datetime(2026, 9, 10, 4, 0, tzinfo=UTC)
    assert first.meta["summary"].startswith("今天，我们正式发布")


def test_zhipu_feed_builds_title_from_content():
    zh = parse_zhipu_release_feed(ZHIPU_ZH, NOW, "智谱发布记录", "zh")
    en = parse_zhipu_release_feed(ZHIPU_EN, NOW, "Z.ai Release Notes", "en")
    assert [it.title for it in zh] == ["智谱发布 GLM-5.3-Flash：原生融入视觉能力"]
    assert zh[0].url == "https://docs.bigmodel.cn/cn/guide/models/vlm/glm-5.3-flash"
    assert en[0].title == (
        "Z.ai releases GLM-5.3-Flash: Native visual capabilities enable the model to observe interfaces"
    )
    assert en[0].url == "https://docs.z.ai/guides/vlm/glm-5.3-flash"


def test_vendor_bilingual_pages_count_as_one_primary_channel():
    ds = parse_deepseek_updates_items(DEEPSEEK_ZH, NOW, "https://api-docs.deepseek.com/zh-cn/updates", "DeepSeek 更新日志")
    ds += parse_deepseek_updates_items(DEEPSEEK_EN, NOW, "https://api-docs.deepseek.com/updates", "DeepSeek Updates")
    zp = parse_zhipu_release_feed(ZHIPU_ZH, NOW, "智谱发布记录", "zh")
    zp += parse_zhipu_release_feed(ZHIPU_EN, NOW, "Z.ai Release Notes", "en")
    ds_records = [as_record(i, r) for i, r in enumerate(ds)]
    zp_records = [as_record(10 + i, r) for i, r in enumerate(zp)]

    assert {channel_for(r) for r in ds_records} == {("pub:deepseek.com", PRIMARY)}
    assert {channel_for(r) for r in zp_records} == {("pub:z.ai", PRIMARY)}
    # 官网主站与 API 文档子域也归到同一发布方。
    assert channel_for(as_record(99, ds[0]) | {"url": "https://www.deepseek.com/news/x/"})[0] == "pub:deepseek.com"

    clusters = cluster_items([build_item(r) for r in ds_records + zp_records])
    titles = sorted(sorted(it.title for it in c) for c in clusters)
    assert ["DeepSeek-V4.1-Flash Release", "DeepSeek-V4.1-Flash 发布"] in titles
    assert any(len(c) == 2 and all("GLM-5.3-Flash" in it.title for it in c) for c in clusters)


def test_anthropic_list_rows_use_title_span_and_dedupe():
    items = parse_anthropic_news_items(ANTHROPIC, OCT)
    assert [it.title for it in items] == ["Anthropic invests $100 million", "2026 Usage Policy update"]
    assert items[1].url == "https://www.anthropic.com/news/2026-usage-policy-update"
    assert items[1].published_at == datetime(2026, 10, 8, 19, 0, tzinfo=UTC)  # 太平洋时间中午


def test_xai_news_cards():
    items = parse_xai_news_items(XAI, OCT)
    assert [(it.title, it.url) for it in items] == [
        ("Introducing Grok 4.7", "https://x.ai/news/grok-4-7"),
        ("Designing Grok Bot", "https://x.ai/news/designing-grok-bot"),
    ]
    assert items[0].meta["summary"] == "Our smartest model."
    assert channel_for({"site_id": "official_ai", "source": "xAI News", "url": items[0].url}) == ("pub:x.ai", PRIMARY)


def test_meta_blog_and_newsroom_ai_only():
    blog = parse_meta_ai_blog_items(META_BLOG, OCT)
    assert [it.title for it in blog] == ["Introducing Muse Spark 1.1"]  # July 已超 45 天
    assert blog[0].url == "https://ai.meta.com/blog/introducing-muse-spark-meta-model-api"
    feed = parse_meta_newsroom_feed(META_FEED, OCT)
    assert [it.title for it in feed] == ["Why Data Centers Are Such a Big Part of Meta\u2019s AI Approach"]
    rec = {"site_id": "official_ai", "source": "Meta Newsroom", "url": feed[0].url}
    assert channel_for(rec) == ("pub:about.fb.com", PRIMARY)
