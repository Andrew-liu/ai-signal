"""主体名录、同主体发布方归并、分类边界（参考 AIHOT industry/taxonomy.ts）。"""

from datetime import UTC, datetime, timedelta

from scripts.signal_events import (
    PRIMARY,
    build_events,
    build_item,
    channel_for,
    classify_category,
    extract_entities,
    find_entities,
)

NOW = datetime(2026, 10, 10, 8, 0, tzinfo=UTC)


def rec(i, site_id, title, url, *, source="", hours_ago=1.0, **extra):
    ts = (NOW - timedelta(hours=hours_ago)).isoformat().replace("+00:00", "Z")
    out = {
        "id": f"tax{i}",
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


def cat(text: str, **kw) -> str:
    return classify_category(text, extract_entities(text), **kw)


# --- 主体名录 ---------------------------------------------------------------


def test_find_entities_orders_by_position_and_respects_word_boundaries():
    assert find_entities("ChatGPT 接入 Claude 与 Gemini") == ["openai", "anthropic", "google"]
    assert find_entities("GitHub Copilot adds Opus 5 support") == ["microsoft", "anthropic"]
    assert find_entities("metadata for portrait apps") == []  # 不误中 Meta / trae / Apple
    assert find_entities("Meta 发布 Llama 5") == ["meta"]
    assert find_entities("智谱 GLM-5.3 上线") == ["zhipu"]


def test_same_company_official_channels_collapse_to_one_publisher():
    blog = channel_for(rec(1, "official_ai", "t", "https://www.anthropic.com/news/x", source="Anthropic News"))
    claude = channel_for(rec(2, "official_ai", "t", "https://claude.com/blog/x", source="Claude Blog"))
    deepmind = channel_for(rec(3, "official_ai", "t", "https://deepmind.google/discover/blog/x", source="DeepMind"))
    google = channel_for(rec(4, "official_ai", "t", "https://blog.google/technology/ai/x", source="Google AI"))
    x_account = channel_for(rec(5, "aihot", "t", "https://x.com/OpenAIDevs/status/1", source="X：OpenAI Developers"))
    assert blog == claude == ("pub:anthropic.com", PRIMARY)
    assert deepmind == google == ("pub:blog.google", PRIMARY)
    assert x_account == ("pub:openai.com", PRIMARY)


def test_event_subject_prefers_title_then_publisher_then_repo_owner():
    records = [
        rec(10, "official_ai", "Introducing Operator, an agent that uses a browser", "https://openai.com/index/operator",
            source="OpenAI News"),
        rec(11, "curated_media", "Hugging Face 上线 Gemma 5 微调服务", "https://www.36kr.com/p/11"),
        rec(12, "curated_media", "Hugging Face launches Gemma 5 fine-tuning", "https://techcrunch.com/hf-gemma"),
        rec(13, "github_trending", "anthropics/claude-cookbooks: Recipes", "https://github.com/anthropics/claude-cookbooks",
            github_repo="anthropics/claude-cookbooks", github_stars_today=900),
    ]
    payload = build_events(records, NOW)
    by_title = {s["title_en"] or s["title"]: s for s in payload["stories"]}
    subjects = {k: (v["subject"] or {}).get("name") for k, v in by_title.items()}
    assert subjects.get("Introducing Operator, an agent that uses a browser") == "OpenAI"
    hf = next(v for k, v in by_title.items() if "Gemma" in k)
    assert hf["subject"]["name"] == "Hugging Face"
    assert hf["entities"][:2] == ["huggingface", "google"]
    repo = next(v for v in payload["stories"] if v.get("github"))
    assert repo["subject"] == {"id": "github:anthropics", "name": "anthropics"}


# --- 分类边界 ---------------------------------------------------------------


def test_incidents_and_lawsuits_are_safety_even_with_model_names():
    assert cat("Claude Code vulnerability lets attackers run commands") == "safety"
    assert cat("OpenAI sued over GPT-4o suicide case") == "safety"
    assert cat("ChatGPT 宕机两小时") == "safety"
    # AI 找到漏洞是能力新闻
    assert cat("GPT-5.5 在 Linux 内核中发现 12 个漏洞") == "model"
    assert cat("Anthropic 现在为开源软件提供免费的漏洞查找服务") != "safety"


def test_red_team_studies_are_research():
    assert cat("Anthropic red-teams Claude Opus 5 for sabotage risk") == "research"
    assert cat("研究发现大模型会在评测中隐藏能力") == "research"


def test_new_benchmark_is_research_but_scores_are_model():
    assert cat("OpenAI introduces HealthBench, a new benchmark for medical agents") == "research"
    assert cat("Gemini 4 tops SWE-bench Verified with 82%") == "model"
    assert cat("Meta 开源 Llama 5，附带训练数据集说明") == "model"


def test_engineering_components_are_devtool_unless_model_leads():
    assert cat("vLLM 0.12 adds day-0 support for Qwen3.6") == "devtool"
    assert cat("DeepSeek open-sources an attention kernel library for H800") == "devtool"
    assert cat("Qwen3.6 发布，vLLM 首日支持") == "model"


def test_market_commentary_without_money_is_not_business():
    assert cat("Altman says AI valuations are a bubble") != "business"
    assert cat("Anthropic raises $13B at $183B valuation") == "business"
    assert cat("英伟达称将收购一家推理芯片公司") == "business"


def test_official_post_with_attitude_is_not_soft_noise():
    item = build_item(rec(30, "official_ai", "Why we're open-sourcing our agent runtime",
                          "https://openai.com/index/open-agent-runtime", source="OpenAI News"))
    assert item.role == PRIMARY and item.noise == "none"
    media = build_item(rec(31, "curated_media", "Why we're open-sourcing our agent runtime",
                           "https://techcrunch.com/why"))
    assert media.noise == "soft"
