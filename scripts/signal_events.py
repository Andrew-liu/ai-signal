#!/usr/bin/env python3
"""AI Signal event layer (rule-based, no LLM).

Pipeline (runs after ``update_news.py`` on the same data dir):

1. Source roles: every record is mapped to a *channel* and a *role*.
   - ``primary``: first-party official channels (decides "新").
   - ``report``:  AI / tech media reporting (can headline an event).
   - ``signal``:  aggregators, HN mirrors, Reddit, X builders. They only add
     heat to an event and never headline it alone.
   - ``reference``: tier-3 reference sources (WaytoAGI). Lowest weight, not an
     independent source; can only appear in lanes.
   - ``drop``:    out of scope for the hot/fresh product (creators).
2. Scope + noise: AI domain incl. chips, robotics, AI-company business news;
   tutorials, deals, digests and chatter are removed.
3. Cross-lingual clustering: entity dictionary + latin product tokens + CJK
   bigrams (using the existing ``title_zh`` translations) merge reports of the
   same event across Chinese and English sources.
4. Lanes: ``hot`` (multi-channel heat) and ``fresh`` (new hard events from
   primary/report channels). No forced zh/en ratio.

Output: ``events.json``, story-compatible so the front end can render it with
its existing story components.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.safe_io import atomic_write_json  # noqa: E402

SCHEMA_VERSION = "events_v1"
WINDOW_HOURS = 24
CLUSTER_WINDOW_HOURS = 36
FRESH_MAX_AGE_HOURS = 12
FRESH_HALF_LIFE_HOURS = 6.0
HOT_LIST_LIMIT = 30
STREAM_LIMIT = 120
HOT_MIN_CHANNELS = 2
SOFT_NOISE_MIN_CHANNELS = 3

# ---------------------------------------------------------------------------
# 1. Source roles / channels
# ---------------------------------------------------------------------------

PRIMARY, REPORT, SIGNAL, REFERENCE, DROP = "primary", "report", "signal", "reference", "drop"
ROLE_RANK = {PRIMARY: 0, REPORT: 1, SIGNAL: 2, REFERENCE: 3, DROP: 4}
# 信源分级：一级=厂商官网（定"新"），二级=媒体/聚合/热度（含 GitHub Trending），三级=参考源（WaytoAGI）。
ROLE_TIER = {PRIMARY: 1, REPORT: 2, SIGNAL: 2, REFERENCE: 3, DROP: 3}

AIHOT_FIRST_PARTY_HINTS = (
    "openai：", "anthropic：", "claude code：", "google developers", "google research",
    "mistral ai：", "hugging face：", "x：openai", "x：claude", "x：google deepmind",
    "x：ai at meta", "x：chatgpt", "x：notebooklm", "x：perplexity", "x：runway",
    "x：阿里云", "x：可灵", "deepseek", "qwen", "github releases",
)

REPORT_SITES = {"aibase", "aihubtoday", "bestblogs", "aibreakfast"}
DROP_SITES = {"tikhub_douyin", "tikhub_xiaohongshu"}
# 三级参考源：进赛道，只加一点热度，不算独立来源、不能单独上热榜或「最新」。
REFERENCE_SITES = {"waytoagi"}
X_SITES = {"followbuilders", "xapi", "socialdata_x"}
HN_SOURCE_RE = re.compile(r"hacker\s*news|hackernews|黑客新闻|news\.ycombinator\.com", re.I)

# AGI HUNT（agihunt.info）：全网 AI 信号聚簇 + 热度排序的上游。每个频道是独立渠道，
# 不按发布方域名折叠（它的入选本身就是一条热度证据）。models 频道为高权重：
# 渠道权重最高、榜单排名加热度、默认视为模型类硬事件，前排可单独上热榜。
AGIHUNT_SITE = "agihunt"
AGIHUNT_MODELS_CHANNEL = "agihunt:models"
AGIHUNT_SOLO_HOT_RANK = 5       # models 最热榜前 5：等同多一个独立渠道
AGIHUNT_BONUS_RANKS = 20        # models 最热榜前 20 才给排名加成
AGIHUNT_MAX_BONUS = 0.8         # 排名加成上限（与 hn_bonus 同量级）
GITHUB_MAX_BONUS = 0.8          # GitHub Trending 今日新增星数加成上限
UNKNOWN_TIME_FRESHNESS_CAP = 0.35

# 赛道看板：(key, 标签, 归入的事件分类)。consumer / general 不进任何赛道。
LANES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("model", "模型 · 研究", ("model", "research")),
    ("devtool", "开发工具 · Agent", ("devtool",)),
    ("opensource", "开源 · GitHub", ("opensource",)),
    ("hardware", "芯片 · 机器人", ("chip", "robotics")),
    ("business", "融资 · 财报", ("business",)),
    ("policy", "安全 · 产品", ("safety", "product")),
)
LANE_BY_CATEGORY = {cat: key for key, _, cats in LANES for cat in cats}
LANE_LIMIT = 15
# AGI HUNT 其它频道 -> (兜底分类, 可被覆盖的规则分类)。频道本身是人工主题，
# 规则只命中"模型/产品/泛类"这类宽词时，以频道主题为准。
_BROAD = ("general", "product", "consumer", "model", "devtool")
AGIHUNT_CHANNEL_CATEGORY: dict[str, tuple[str, tuple[str, ...]]] = {
    "agihunt:research": ("research", _BROAD),
    "agihunt:hardware": ("robotics", _BROAD),
    "agihunt:funding": ("business", (*_BROAD, "chip", "robotics", "opensource", "research", "safety")),
    "agihunt:coding-agents": ("devtool", ("general", "product", "consumer")),
}
# 创投频道里也有报告、论文、教程连载：只有出现资金信号才按融资归类。
MONEY_SIGNAL_RE = re.compile(
    r"(?i)(\$\s?\d|\d+(?:\.\d+)?\s?(?:m|b|bn|million|billion)\b|\bfund\w*|\binvest\w*|\bseed\b|"
    r"融资|募资|种子轮|天使轮|[a-f]\s?轮|投资|估值|基金|回购|亿美元|万美元|亿元)"
)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", str(text or "").lower()).strip("-")[:40] or "unknown"


# First-party domains: any item linking here is the vendor's own announcement,
# whichever aggregator path (official feed, aihot, OPML) delivered it.
OFFICIAL_DOMAINS = {
    "openai.com", "anthropic.com", "claude.com", "blog.google", "deepmind.google", "ai.google.dev",
    "developers.googleblog.com", "research.google", "ai.meta.com", "about.fb.com", "huggingface.co",
    "mistral.ai", "github.blog", "nvidia.com", "blogs.nvidia.com", "developer.nvidia.com",
    "qwenlm.github.io", "qwen.ai", "deepseek.com", "api-docs.deepseek.com", "x.ai", "z.ai",
    "moonshot.ai", "minimax.io", "cursor.com", "microsoft.com", "blogs.microsoft.com",
    "aws.amazon.com", "apple.com", "machinelearning.apple.com", "cohere.com", "perplexity.ai",
    "bigmodel.cn", "zhipuai.cn",
}
# 同一厂商的多个官网域名归成一个发布方（中英文档各一份，算一个来源）。
OFFICIAL_DOMAIN_ALIASES = {"bigmodel.cn": "z.ai", "zhipuai.cn": "z.ai"}
SHARED_HOSTS = {"github.com", "x.com", "twitter.com", "medium.com", "substack.com", "youtube.com", "news.ycombinator.com"}

def publisher_host(url: str) -> str:
    try:
        host = (urlparse(str(url or "")).netloc or "").lower().removeprefix("www.")
    except ValueError:
        return ""
    return host

def official_domain(host: str) -> str:
    # 取最短的匹配（api-docs.deepseek.com 与 deepseek.com 都归到 deepseek.com），结果与集合遍历顺序无关。
    matches = [d for d in OFFICIAL_DOMAINS if host == d or host.endswith("." + d)]
    if not matches:
        return ""
    domain = min(matches, key=len)
    return OFFICIAL_DOMAIN_ALIASES.get(domain, domain)


def channel_for(record: dict[str, Any]) -> tuple[str, str]:
    """Return ``(channel_id, role)``.

    Primary/report channels are keyed by the publisher (URL host), so the same
    vendor post delivered via official feed + aihot + OPML counts once.
    Signal channels are keyed by upstream community (HN mirrors share ``hn``).
    """
    channel, role = _raw_channel_for(record)
    if channel.startswith("agihunt:"):
        return channel, role
    if role in (PRIMARY, REPORT):
        host = publisher_host(str(record.get("url") or ""))
        domain = official_domain(host)
        if domain:
            return f"pub:{domain}", PRIMARY
        if host and host not in SHARED_HOSTS:
            return f"pub:{host}", role
    return channel, role


def _raw_channel_for(record: dict[str, Any]) -> tuple[str, str]:
    site = str(record.get("site_id") or "").lower()
    source = str(record.get("source") or "")
    source_l = source.lower()

    if site in DROP_SITES:
        return f"drop:{site}", DROP
    if site in REFERENCE_SITES:
        return f"ref:{site}", REFERENCE
    if site == "official_ai":
        return f"official:{_slug(source)}", PRIMARY
    if site == AGIHUNT_SITE:
        return f"agihunt:{_slug(record.get('agihunt_channel') or 'misc')}", REPORT
    if site == "aihot":
        if any(hint in source_l for hint in AIHOT_FIRST_PARTY_HINTS):
            return f"official:{_slug(source)}", PRIMARY
        return "aihot", REPORT
    if site in REPORT_SITES:
        return site, REPORT
    if site == "curated_media":
        return f"media:{_slug(source)}", REPORT
    if site.startswith("opmlrss"):
        return f"rss:{_slug(source)}", REPORT
    if site in X_SITES:
        author = source.split("·")[-1].strip() if "·" in source else source
        return f"x:{_slug(author)}", SIGNAL
    if site == "hackernews" or HN_SOURCE_RE.search(source):
        return "hn", SIGNAL
    if site == "zeli":
        return "hn", SIGNAL
    if site == "github_trending":
        return "github_trending", SIGNAL
    if site == "iris":
        return ("reddit", SIGNAL) if "reddit" in source_l else (f"iris:{_slug(source)}", SIGNAL)
    if site == "newsnow":
        if source_l in {"producthunt", "sspai"}:
            return f"drop:newsnow-{source_l}", DROP
        if source_l == "github":
            return "github_trending", SIGNAL
        return f"newsnow:{_slug(source)}", SIGNAL
    if site == "techurls":
        if "techmeme" in source_l:
            return "techmeme", SIGNAL
        # General tech media: can report an event, gated by the strict scope check.
        return f"media:{_slug(source)}", REPORT
    if site == "buzzing":
        return "buzzing", SIGNAL
    return f"other:{site}", SIGNAL


CHANNEL_WEIGHTS = {
    AGIHUNT_MODELS_CHANNEL: 1.8,
    "hn": 1.6,
    "techmeme": 1.3,
    "reddit": 1.0,
    "github_trending": 1.0,
    "buzzing": 0.4,
    "newsnow:juejin": 0.6,
}
ROLE_WEIGHTS = {PRIMARY: 1.5, REPORT: 1.0, SIGNAL: 0.6, REFERENCE: 0.3, DROP: 0.0}
X_CHANNEL_WEIGHT = 0.4
X_CHANNEL_CAP = 1.2


def channel_weight(channel: str, role: str) -> float:
    if channel in CHANNEL_WEIGHTS:
        return CHANNEL_WEIGHTS[channel]
    if channel.startswith("x:"):
        return X_CHANNEL_WEIGHT
    return ROLE_WEIGHTS.get(role, 0.5)


# ---------------------------------------------------------------------------
# 2. Scope (AI domain) and noise
# ---------------------------------------------------------------------------

# canonical entity -> aliases (lowercase). "kind" drives clustering strength.
ORG_ALIASES: dict[str, tuple[str, ...]] = {
    "openai": ("openai",),
    "anthropic": ("anthropic",),
    "google": ("google", "deepmind", "谷歌"),
    "meta": ("meta ai", "ai at meta", "meta's", "meta 的", "meta发布", "meta推出"),
    "microsoft": ("microsoft", "微软"),
    "nvidia": ("nvidia", "英伟达"),
    "apple": ("apple", "苹果"),
    "amazon": ("amazon", "aws", "亚马逊"),
    "xai": ("xai", "马斯克"),
    "deepseek": ("deepseek", "深度求索"),
    "alibaba": ("alibaba", "阿里", "通义"),
    "tencent": ("tencent", "腾讯"),
    "bytedance": ("bytedance", "字节"),
    "baidu": ("baidu", "百度"),
    "zhipu": ("zhipu", "智谱", "z.ai"),
    "moonshot": ("moonshot", "月之暗面"),
    "minimax": ("minimax",),
    "mistral": ("mistral",),
    "huggingface": ("hugging face", "huggingface"),
    "perplexity": ("perplexity",),
    "cursor": ("cursor", "anysphere"),
    "github": ("github",),
    "huawei": ("huawei", "华为"),
    "amd": ("amd",),
    "intel": ("intel", "英特尔"),
    "tsmc": ("tsmc", "台积电"),
    "unitree": ("unitree", "宇树"),
    "figure": ("figure ai",),
    "tesla": ("tesla", "特斯拉", "optimus"),
    "xiaomi": ("xiaomi", "小米"),
    "cerebras": ("cerebras",),
    "groq": ("groq",),
    "etched": ("etched",),
    "sakana": ("sakana",),
    "cohere": ("cohere",),
    "stability": ("stability ai",),
    "runway": ("runway",),
    "kuaishou": ("kuaishou", "快手", "可灵", "kling"),
}

PRODUCT_ALIASES: dict[str, tuple[str, ...]] = {
    "chatgpt": ("chatgpt",),
    "claude-code": ("claude code",),
    "claude": ("claude",),
    "codex": ("codex",),
    "copilot": ("copilot",),
    "gemini": ("gemini",),
    "gemma": ("gemma",),
    "llama": ("llama",),
    "qwen": ("qwen", "千问"),
    "glm": ("glm",),
    "kimi": ("kimi",),
    "doubao": ("doubao", "豆包"),
    "hunyuan": ("hunyuan", "混元"),
    "ernie": ("ernie", "文心"),
    "grok": ("grok",),
    "sora": ("sora",),
    "veo": ("veo",),
    "seedance": ("seedance",),
    "nemotron": ("nemotron",),
    "mcp": ("mcp", "model context protocol"),
    "ollama": ("ollama",),
    "vllm": ("vllm",),
    "sglang": ("sglang",),
    "llama-cpp": ("llama.cpp",),
    "langchain": ("langchain",),
    "openclaw": ("openclaw",),
    "notebooklm": ("notebooklm",),
    "windsurf": ("windsurf",),
    "trae": ("trae",),
    "siri": ("siri",),
    "cuda": ("cuda",),
    "blackwell": ("blackwell", "b200", "gb200", "gb300"),
    "rubin": ("rubin",),
    "ascend": ("ascend", "昇腾"),
}

MODEL_VERSION_RE = re.compile(
    r"(?i)(?<![a-z0-9])("
    r"gpt[-\s]?\d+(?:\.\d+)?(?:[-\s]?(?:mini|pro|turbo|o))?|o\d(?:-mini|-pro)?|"
    r"claude[-\s]?(?:opus|sonnet|haiku)?[-\s]?\d+(?:\.\d+)?|(?:opus|sonnet|haiku)[-\s]?\d+(?:\.\d+)?|"
    r"gemini[-\s]?\d+(?:\.\d+)?|gemma[-\s]?\d+(?:\.\d+)?|llama[-\s]?\d+(?:\.\d+)?|"
    r"qwen[-\s]?\d+(?:\.\d+)?|glm[-\s]?\d+(?:\.\d+)?|kimi[-\s]?k?\d+(?:\.\d+)?|"
    r"deepseek[-\s]?(?:v|r)\d+(?:\.\d+)?|grok[-\s]?\d+(?:\.\d+)?|minimax[-\s]?[a-z]?\d+(?:\.\d+)?|"
    r"wan\d+(?:\.\d+)?|sora[-\s]?\d+|veo[-\s]?\d+(?:\.\d+)?|seedance[-\s]?\d+(?:\.\d+)?"
    r")(?![a-z0-9])"
)
CN_MODEL_VERSION_RE = re.compile(r"(千问|豆包|混元|文心)\s*(\d+(?:\.\d+)?)")

# Every latin word inside an entity alias ("hugging", "face", "claude", "code"):
# such words are already covered by entity matching and must not count again
# as "shared distinctive tokens", otherwise any two Claude Code posts merge.
ENTITY_WORDS = {
    word
    for aliases in (*ORG_ALIASES.values(), *PRODUCT_ALIASES.values())
    for alias in aliases
    for word in re.findall(r"[a-z][a-z0-9.]*", alias)
} | {"meta", "google", "microsoft", "apple", "amazon"}

AI_CORE_RE = re.compile(
    r"(?i)(?<![a-z0-9])(ai|a\.i\.|aigc|agi|llms?|gpt|genai|agents?|agentic|chatbots?|copilot|"
    r"machine learning|deep learning|neural|transformer|diffusion|inference|fine-?tun\w*|"
    r"open[- ]weights?|foundation model|language model|reasoning model|multimodal|"
    r"text-to-(?:video|image|speech)|tts|embedding|rag|benchmark|mcp)(?![a-z0-9])"
)
AI_CORE_ZH = (
    "人工智能", "大模型", "模型", "智能体", "多模态", "推理", "算力", "具身", "机器学习",
    "深度学习", "生成式", "训练", "微调", "开源模型", "语音模型", "视频模型", "提示词",
)

CATEGORY_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("business", re.compile(
        r"(?i)(raises?\s+\$|raised|funding|series [a-f]\b|valuation|valued at|acquir\w+|acquisition|acqui-hire|"
        r"\bipo\b|earnings|revenue|quarterly results|"
        r"融资|估值|收购|上市|申购|财报|营收|季度|并购|市值)"
    )),
    ("chip", re.compile(
        r"(?i)(\bgpus?\b|\btpus?\b|\bnpus?\b|ai chips?|chipmaker|chip startup|accelerator|data ?cent(?:er|re)s?|\bhbm\b|"
        r"semiconductor|cuda|blackwell|rubin|芯片|数据中心|半导体|昇腾)"
    )),
    ("robotics", re.compile(
        r"(?i)(robot\w*|humanoid|embodied|autonomous driving|self-driving|robotaxi|"
        r"机器人|人形|具身|灵巧手|自动驾驶)"
    )),
    ("consumer", re.compile(
        r"(?i)(耳机|手机|眼镜|朋友圈|微信|酒店|租房|快递|理财|外卖|电商|购物|穿戴|"
        r"\bdating\b|earbuds|headphones|smart glasses|\bvacation\b|\bfitness\b)"
    )),
    ("opensource", re.compile(
        r"(?i)(open[- ]source[ds]?|open[- ]sourcing|\bgithub\b(?! copilot)|\brepo\b|\bstars?\b on github|"
        r"开源|仓库|star 数|星标)"
    )),
    ("devtool", re.compile(
        r"(?i)(\bapi\b|\bsdk\b|\bcli\b|\bide\b|developers?|coding|code review|agent sdk|\bmcp\b|"
        r"claude code|codex|copilot|cursor|windsurf|sandbox|framework|"
        r"changelog|vs ?code|terminal|v\d+\.\d+|\bagents?\b|agentic|"
        r"开发者|编程|代码|框架|插件|沙箱|命令行|托管平台|智能体)"
    )),
    ("model", re.compile(
        r"(?i)(open[- ]weights?|language model|reasoning model|\bllms?\b|"
        r"\bmodels?\b|checkpoint|parameters|context window|benchmark|leaderboard|"
        r"大模型|模型|参数|上下文|榜单|评测|权重)"
    )),
    ("research", re.compile(r"(?i)(paper|arxiv|research|study finds|researchers|论文|研究|科学家)")),
    ("safety", re.compile(
        r"(?i)(security|vulnerab\w+|exploit|hack\w*|breach|leak\w*|jailbreak|prompt injection|"
        r"regulat\w+|lawsuit|\bban\b|policy|safety|safeguards?|"
        r"漏洞|攻击|泄露|越狱|监管|安全|政策|新规|诉讼)"
    )),
    ("product", re.compile(
        r"(?i)(launch\w*|rolls? out|now available|feature|app\b|update|"
        r"上线|推出|功能|更新|升级|发布)"
    )),
]
CATEGORY_WEIGHTS = {
    "model": 1.0,
    "devtool": 1.0,
    "opensource": 0.9,
    "research": 0.8,
    "chip": 0.78,
    "robotics": 0.72,
    "business": 0.7,
    "safety": 0.66,
    "product": 0.62,
    "consumer": 0.45,
    "general": 0.4,
}
CATEGORY_LABELS = {
    "model": "模型",
    "devtool": "开发工具",
    "opensource": "开源",
    "research": "研究",
    "chip": "芯片算力",
    "robotics": "机器人",
    "business": "融资财报",
    "safety": "安全监管",
    "product": "产品",
    "consumer": "消费应用",
    "general": "AI 动态",
}

HARD_EVENT_RE = re.compile(
    r"(?i)(releas\w+|launch\w*|introduc\w+|unveil\w*|announc\w+|open[- ]sourc\w+|rolls? out|"
    r"now available|ships?\b|debuts?|raises?|raised|acquir\w+|\bipo\b|earnings|revenue|"
    r"leak\w*|breach|hack\w*|vulnerab\w+|banned?|sues?|lawsuit|retire[ds]?|deprecat\w+|"
    r"\bv\d+(?:\.\d+)+|"
    r"发布|推出|上线|开源|宣布|官宣|首发|升级|更新|融资|估值|收购|上市|申购|财报|营收|"
    r"泄露|曝光|漏洞|攻击|起诉|下线|停用|新规)"
)
# Version / model-name mentions make a title a hard event even without a verb.
HARD_EVENT_HINT_RE = MODEL_VERSION_RE

HARD_NOISE_PATTERNS = [
    re.compile(r"(?i)(教程|入门|指南|实战|手把手|从零|从 0|速通|踩坑|保姆级|全解析|完全指南|一文读懂|一文看懂|最佳实践)"),
    re.compile(r"(?i)\b(how to|how i|tutorial|step[- ]by[- ]step|beginner'?s guide|cheat ?sheet|tips|explained)\b"),
    re.compile(r"(?i)(本周|周报|日报|早报|晚报|精选合集|盘点|合集|top ?\d+|\d+ (?:best|essential))"),
    re.compile(r"(?i)\b(deal|deals|discount|save \$|record-low|% off|coupon|black friday|prime day)\b|at amazon|优惠|降价|券后|首发价"),
    re.compile(r"(?i)(招聘|求职|面试题|简历)"),
]
SOFT_NOISE_PATTERNS = [
    re.compile(r"(?i)^(show|ask|tell) hn\b"),
    re.compile(r"(?i)^(why|what|how|can|should|is|are|do|does|will|when|where)\b"),
    re.compile(r"[?？]\s*$"),
    re.compile(r"(?i)\b(opinion|essay|i think|my take|i've|i'm|i was|i spent|i used|we built)\b"),
    re.compile(r"(为什么|怎么看|我用|我把|我花了|我做了|我们怎样|聊了啥|聊了什么|观点|思考|复盘|心得|感受|体验了|教训|启示|反思)"),
    re.compile(r"(吐槽|博主|网友|实践分享|横评|急救卡|是个啥|到底在|到底是|别乱删|开心得)"),
    re.compile(r"(?i)(大赛|峰会|大会|aicon|报名|直播|播客|\bwebinar\b|\bpodcast\b|\binterview\b|访谈|专访)"),
    re.compile(r"(?i)\b(lessons|the case for|never about|is becoming|is dead|we need|you can'?t|should rival)\b"),
]
VERSION_ONLY_RE = re.compile(r"^\s*v?\d+(?:\.\d+){1,3}[a-z0-9.\-]*\s*$", re.I)
CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def has_cjk(text: str) -> bool:
    return len(CJK_RE.findall(str(text or ""))) >= 2


def _alias_hit(text_l: str, alias: str) -> bool:
    if CJK_RE.search(alias):
        return alias in text_l
    return re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", text_l) is not None


def extract_entities(text: str) -> dict[str, set[str]]:
    text_l = str(text or "").lower()
    orgs = {canon for canon, aliases in ORG_ALIASES.items() if any(_alias_hit(text_l, a) for a in aliases)}
    products = {canon for canon, aliases in PRODUCT_ALIASES.items() if any(_alias_hit(text_l, a) for a in aliases)}
    if "claude-code" in products:
        products.discard("claude")
    models = {re.sub(r"[\s_]+", "-", m.group(1).lower()) for m in MODEL_VERSION_RE.finditer(text_l)}
    zh_name = {"千问": "qwen", "豆包": "doubao", "混元": "hunyuan", "文心": "ernie"}
    for m in CN_MODEL_VERSION_RE.finditer(str(text or "")):
        models.add(f"{zh_name[m.group(1)]}-{m.group(2)}")
    models = {re.sub(r"-+", "-", m) for m in models}
    return {"orgs": orgs, "products": products, "models": models}


# "chips" / "算力" 常被顺带提到（"open models just shift power to whoever owns the chips"），
# 只在没有其它分类命中时才把事件归到芯片。
WEAK_CHIP_RE = re.compile(r"(?i)(\bchips?\b|算力|显卡)")
# 起诉/指控类新闻即使提到"机器人""数据中心"，主题也是安全监管（Character.AI 被诉）。
STRONG_SAFETY_RE = re.compile(r"(?i)(\bsues?\b|\bsued\b|\blawsuits?\b|\bindicted\b|起诉|指控|诉讼|立案)")
GITHUB_REPO_URL_RE = re.compile(r"(?i)^https?://(?:www\.)?github\.com/[^/\s]+/[^/\s#?]+/?(?:[#?].*)?$")
GITHUB_NON_REPO_OWNERS = {"orgs", "topics", "trending", "features", "blog", "about", "marketplace", "sponsors", "collections"}


def is_github_repo_url(url: str) -> bool:
    if not GITHUB_REPO_URL_RE.match(str(url or "")):
        return False
    owner = urlparse(str(url)).path.strip("/").split("/")[0].lower()
    return owner not in GITHUB_NON_REPO_OWNERS


def classify_category(
    text: str,
    entities: dict[str, set[str]] | None = None,
    channel: str = "",
    url: str = "",
) -> str:
    """规则分类，优先级：融资财报 > 带版本号的模型 > GitHub 仓库(开源) > 关键词顺序 > 芯片弱词兜底。"""
    business = CATEGORY_RULES[0]
    if business[1].search(text):
        return business[0]
    if entities and entities.get("models"):
        # "GLM-5.3 开源" 是模型发布，不应因"开源"落到开源/开发工具。
        return "model"
    if channel == "github_trending" or is_github_repo_url(url):
        return "opensource"
    if STRONG_SAFETY_RE.search(text):
        return "safety"
    for name, pattern in CATEGORY_RULES[1:]:
        if pattern.search(text):
            return name
    if WEAK_CHIP_RE.search(text):
        return "chip"
    return "general"


def has_ai_core(text: str, entities: dict[str, set[str]]) -> bool:
    if entities["products"] or entities["models"]:
        return True
    ai_orgs = {"openai", "anthropic", "deepseek", "zhipu", "moonshot", "minimax", "mistral",
               "huggingface", "perplexity", "cursor", "xai", "cohere", "sakana", "stability", "runway",
               "unitree", "figure", "cerebras", "groq", "etched", "nvidia"}
    if entities["orgs"] & ai_orgs:
        return True
    if AI_CORE_RE.search(text):
        return True
    return any(term in text for term in AI_CORE_ZH)


def noise_level(title: str) -> str:
    """Return ``hard`` (drop), ``soft`` (hot-only with strong heat) or ``none``."""
    if any(p.search(title) for p in HARD_NOISE_PATTERNS):
        return "hard"
    if any(p.search(title.strip()) for p in SOFT_NOISE_PATTERNS):
        return "soft"
    return "none"


# ---------------------------------------------------------------------------
# Item normalization
# ---------------------------------------------------------------------------


def parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z") if dt else None


def canonical_url(raw: str) -> str:
    try:
        p = urlparse(str(raw or "").strip())
    except ValueError:
        return ""
    if not p.netloc:
        return ""
    host = p.netloc.lower().removeprefix("www.")
    path = p.path.rstrip("/")
    if host == "news.ycombinator.com":
        return f"{host}{path}?{p.query}"
    if p.fragment and CHANGELOG_PATH_RE.search(path):
        # 更新日志单页里每个锚点是一次独立发布（DeepSeek /updates#…、Codex /changelog#…）。
        return f"{host}{path}#{p.fragment}"
    return f"{host}{path}"


CHANGELOG_PATH_RE = re.compile(r"(?i)/(?:changelog|updates|release[-_]?notes|new-released?|releases)$")


GENERIC_LATIN = {
    "the", "and", "for", "with", "from", "into", "that", "this", "its", "now", "new", "are", "was",
    "has", "have", "will", "can", "you", "your", "our", "not", "but", "all", "out", "how", "why",
    "what", "who", "more", "than", "after", "over", "about", "just", "first", "says", "said", "say",
    "ai", "a.i", "model", "models", "agent", "agents", "llm", "llms", "open", "source", "launch",
    "launches", "launched", "release", "releases", "released", "introduces", "introducing",
    "announces", "announced", "update", "updates", "available", "default", "today", "users", "user",
    "company", "startup", "report", "reports", "sources", "according", "via", "using", "use",
    "based", "new", "latest", "most", "big", "one", "two", "app", "apps", "tool", "tools", "data",
    "system", "systems", "support", "supports", "feature", "features", "free", "build", "built",
    "make", "makes", "get", "gets", "like", "here", "there", "they", "their", "them", "inc",
    "bloomberg", "techcrunch", "reuters", "verge", "wired", "times", "news", "video", "weeks", "week",
    "year", "years", "million", "billion", "per", "off", "up", "on", "in", "of", "to", "is", "be",
}
LATIN_TOKEN_RE = re.compile(r"[a-z][a-z0-9]*(?:[.\-][a-z0-9]+)*|\d+(?:\.\d+)?[a-z]+")


def latin_tokens(text: str) -> set[str]:
    out = set()
    for tok in LATIN_TOKEN_RE.findall(str(text or "").lower()):
        tok = tok.strip(".-")
        if len(tok) < 3 and not re.search(r"\d", tok):
            continue
        if tok in GENERIC_LATIN:
            continue
        out.add(tok)
    return out


ZH_STOP_BIGRAMS = {"发布", "推出", "上线", "正式", "宣布", "全新", "首款", "重磅", "官方", "消息", "今日", "最新", "支持", "已经", "进行", "实现", "可以", "通过", "成为", "一个"}


def cjk_bigrams(text: str) -> set[str]:
    grams: set[str] = set()
    for run in re.findall(r"[\u4e00-\u9fff]+", str(text or "")):
        for i in range(len(run) - 1):
            g = run[i:i + 2]
            if g not in ZH_STOP_BIGRAMS:
                grams.add(g)
    return grams


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# 同一事件不同媒体措辞差异很大（"pacing model development" / "pauses frontier model training" /
# "放缓开发" / "暂停训练"），标题词面几乎不重合。把少见、指向性强的动作归一成概念：
# 同一机构 + 同一概念 + 24h 内，视为同一事件。发布/上线这类高频动作不在此列，避免误合并。
ACTION_CONCEPTS: dict[str, re.Pattern[str]] = {
    "slowdown": re.compile(r"(?i)(\bpaus\w*|\bslow\w*|\bpacing\b|\bhalt\w*|放缓|暂停|叫停|减速)"),
    "outage": re.compile(r"(?i)(\boutages?\b|\bdegraded\b|\bdowntime\b|宕机|故障|性能下降|服务中断)"),
    "lawsuit": re.compile(r"(?i)(\bsues?\b|\bsued\b|\blawsuits?\b|起诉|诉讼|索赔)"),
    "layoff": re.compile(r"(?i)(\blayoffs?\b|\blays? off\b|裁员)"),
    "ipo": re.compile(r"(?i)(\bipo\b|首次公开募股)"),
    "acquire": re.compile(r"(?i)(\bacquir\w+|\bacquisition\b|收购|并购)"),
    "revenue": re.compile(r"(?i)(\brevenues?\b|\bearnings\b|\bannuali[sz]ed\b|营收|财报|年化收入)"),
    "funding": re.compile(r"(?i)(\bvaluations?\b|\braises?\b|\braised\b|\bfunding round\b|\bseries [a-f]\b|估值|融资|[a-f] ?轮)"),
    "ban": re.compile(r"(?i)(\bbans?\b|\bbanned\b|\bprohibit\w*|\bsuspen\w+|usage polic\w+|禁止|封禁|封号|使用政策)"),
}
CONCEPT_MERGE_HOURS = 24
SUBJECT_MERGE_CONCEPTS = {"funding", "revenue", "acquire", "ipo"}


def action_concepts(text: str) -> set[str]:
    return {name for name, pattern in ACTION_CONCEPTS.items() if pattern.search(text)}


PHRASE_STOP = {"the", "and", "for", "with", "new", "now", "via", "from", "its", "has", "ai", "is", "to", "of", "in", "on", "a", "an"}


def entity_phrases(text: str) -> set[str]:
    """实体词 + 紧邻普通词组成的短语（"gemini agent"），中英标题里常原样保留。"""
    tokens = LATIN_TOKEN_RE.findall(str(text or "").lower())
    out: set[str] = set()
    for left, right in zip(tokens, tokens[1:]):
        if left in PHRASE_STOP or right in PHRASE_STOP:
            continue
        if (left in ENTITY_WORDS) == (right in ENTITY_WORDS):
            continue
        out.add(f"{left} {right}")
    return out


@dataclass
class Item:
    record: dict[str, Any]
    id: str
    title: str
    title_zh: str
    title_en: str
    lang: str
    url: str
    curl: str
    channel: str
    role: str
    published: datetime | None
    first_seen: datetime | None
    entities: dict[str, set[str]]
    latin: set[str]
    bigrams: set[str]
    category: str
    hard_event: bool
    noise: str
    in_scope: bool
    concepts: set[str] = field(default_factory=set)
    time_known: bool = True
    phrases: set[str] = field(default_factory=set)
    github_repo: bool = False

    @property
    def time(self) -> datetime | None:
        return self.published or self.first_seen

    @property
    def strong_entities(self) -> set[str]:
        return self.entities["products"] | {f"m:{m}" for m in self.entities["models"]}


def display_title(record: dict[str, Any]) -> str:
    title = str(record.get("title_original") or record.get("title") or "").strip()
    title = re.sub(r"\s*/\s*", "/", title) if is_github_repo_url(str(record.get("url") or "")) else title
    title = re.sub(r"\s+", " ", title)
    if VERSION_ONLY_RE.match(title):
        source = str(record.get("source") or "").strip()
        source = re.sub(r"\s*(releases?|changelog|（.*?）|\(.*?\))\s*$", "", source, flags=re.I).strip()
        if source:
            title = f"{source} {title}"
    return title


def build_item(record: dict[str, Any]) -> Item | None:
    title = display_title(record)
    url = str(record.get("url") or "").strip()
    if not title or not url.startswith("http"):
        return None
    channel, role = channel_for(record)
    github_repo = channel == "github_trending" or is_github_repo_url(url)
    zh_provided = str(record.get("title_enhanced_zh") or record.get("title_zh") or record.get("provided_title_zh") or "").strip()
    if github_repo:
        # 仓库名被机翻成"塞多马克 / Claude·梅姆"没有意义：仓库条目只保留原文。
        zh_provided = ""
    lang = "zh" if has_cjk(title) else "en"
    title_zh = title if lang == "zh" else zh_provided
    title_en = title if lang == "en" else str(record.get("title_en") or record.get("provided_title_en") or "").strip()
    text = f"{title} {title_en}".strip()
    match_text = f"{text} {title_zh}"
    entities = extract_entities(match_text)
    category = classify_category(match_text, entities, channel, url)
    noise = noise_level(title)
    in_scope = has_ai_core(match_text, entities)
    # Generic chip/robotics/business words only count with an AI anchor.
    hard_event = bool(HARD_EVENT_RE.search(match_text) or HARD_EVENT_HINT_RE.search(match_text))
    if channel == AGIHUNT_MODELS_CHANNEL:
        # AGI HUNT 已按主题归入模型频道：分类以频道为准（除非规则命中更具体的开发工具/开源类）。
        # 是否"明确事件"仍走规则判断，避免观点/实践分享帖挤进"最新"。
        if category not in ("model", "devtool", "research", "opensource"):
            category = "model"
        in_scope = True
    elif channel in AGIHUNT_CHANNEL_CATEGORY:
        # 其它 AGI HUNT 频道已是人工主题：规则只落到泛类时，用频道主题兜底。
        fallback, overridable = AGIHUNT_CHANNEL_CATEGORY[channel]
        if category in overridable and (channel != "agihunt:funding" or MONEY_SIGNAL_RE.search(match_text)):
            category = fallback
        in_scope = True
    published = parse_iso(record.get("published_at"))
    time_known = published is not None and not record.get("published_estimated")
    return Item(
        record=record,
        id=str(record.get("id") or hashlib.sha1(f"{url}|{title}".encode()).hexdigest()),
        title=title,
        title_zh=title_zh,
        title_en=title_en,
        lang=lang,
        url=url,
        curl=canonical_url(url),
        channel=channel,
        role=role,
        published=published if time_known else None,
        first_seen=parse_iso(record.get("first_seen_at")),
        entities=entities,
        latin=latin_tokens(text),
        bigrams=cjk_bigrams(title_zh),
        category=category,
        hard_event=hard_event,
        noise=noise,
        in_scope=in_scope,
        concepts=action_concepts(match_text),
        time_known=time_known,
        phrases=entity_phrases(match_text),
        github_repo=github_repo,
    )


# ---------------------------------------------------------------------------
# 3. Clustering
# ---------------------------------------------------------------------------


def versions_conflict(a: Item, b: Item) -> bool:
    ma, mb = a.entities["models"], b.entities["models"]
    if not ma or not mb or ma & mb:
        return False
    fam = lambda m: re.sub(r"[-\s]?[\d.]+.*$", "", m)  # noqa: E731
    return bool({fam(m) for m in ma} & {fam(m) for m in mb})


def lead_tokens(title: str, limit: int = 5) -> set[str]:
    """标题开头几个拉丁词，通常是事件主语（"Popular AI leaderboard Arena ..."）。"""
    return set(LATIN_TOKEN_RE.findall(str(title or "").lower())[:limit])


def same_event(a: Item, b: Item) -> bool:
    if a.curl and a.curl == b.curl:
        return True
    if a.github_repo or b.github_repo:
        # 仓库条目只和同一仓库合并；"Claude 九月回顾" 不应吞掉 anthropics/knowledge-work-plugins。
        return False
    if a.time and b.time and abs((a.time - b.time).total_seconds()) > CLUSTER_WINDOW_HOURS * 3600:
        return False
    if versions_conflict(a, b):
        return False
    title_a, title_b = a.title.lower(), b.title.lower()
    if title_a == title_b:
        return True
    shared_strong = a.strong_entities & b.strong_entities
    shared_org = a.entities["orgs"] & b.entities["orgs"]
    latin_shared = (a.latin & b.latin) - ENTITY_WORDS
    bigram_sim = jaccard(a.bigrams, b.bigrams)
    latin_sim = jaccard(a.latin - ENTITY_WORDS, b.latin - ENTITY_WORDS)
    close = not (a.time and b.time) or abs((a.time - b.time).total_seconds()) <= CONCEPT_MERGE_HOURS * 3600

    if close and a.concepts & b.concepts:
        if shared_org or shared_strong:
            return True
        # 没有已知实体的公司（Arena）：同一资本概念 + 两边标题开头都出现同一个专名。
        if a.concepts & b.concepts & SUBJECT_MERGE_CONCEPTS:
            subject = {
                tok for tok in latin_shared
                if len(tok) >= 4 and not any(p.search(tok) for p in ACTION_CONCEPTS.values())
            } & lead_tokens(a.title) & lead_tokens(b.title)
            if subject:
                return True
    if close and shared_strong and a.phrases & b.phrases:
        # "谷歌云发布 Gemini Agent" / "Google Cloud Launches Gemini Agent"
        return True

    if any(s.startswith("m:") for s in shared_strong):
        # Same versioned model (e.g. GLM-5.3): one more overlap is enough.
        return bigram_sim >= 0.12 or len(latin_shared) >= 1 or latin_sim >= 0.3
    if shared_strong:
        rare_shared = {tok for tok in latin_shared if len(tok) >= 4}
        return bigram_sim >= 0.18 or len(rare_shared) >= 1 or len(latin_shared) >= 2 or latin_sim >= 0.45
    if len(shared_org) >= 2:
        return bigram_sim >= 0.12 or len(latin_shared) >= 1 or latin_sim >= 0.35
    if shared_org:
        return bigram_sim >= 0.32 or len(latin_shared) >= 2 or latin_sim >= 0.5
    return bigram_sim >= 0.5 or latin_sim >= 0.6


def cluster_items(items: list[Item]) -> list[list[Item]]:
    """Greedy anchored clustering.

    Plain union-find chains unrelated stories through shared entities
    ("Claude Code /design" -> "Claude Code weekly limits" -> ...). Here an
    item joins a cluster only if it matches the cluster anchor (the most
    authoritative, earliest item) or at least two existing members.
    """
    ordered = sorted(items, key=lambda it: (ROLE_RANK[it.role], (it.time or datetime.max.replace(tzinfo=UTC)).timestamp()))
    clusters: list[list[Item]] = []
    for item in ordered:
        target = None
        for cluster in clusters:
            if same_event(item, cluster[0]):
                target = cluster
                break
            if len(cluster) >= 2 and sum(1 for member in cluster if same_event(item, member)) >= 2:
                target = cluster
                break
        if target is None:
            clusters.append([item])
        else:
            target.append(item)
    return clusters


# ---------------------------------------------------------------------------
# 4. Scoring and lanes
# ---------------------------------------------------------------------------


@dataclass
class Event:
    items: list[Item]
    now: datetime
    channels: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for item in self.items:
            self.channels.setdefault(item.channel, item.role)

    @property
    def headline(self) -> Item:
        def key(it: Item) -> tuple[int, int, int, int, float]:
            return (
                ROLE_RANK[it.role],
                0 if it.noise == "none" else 1,
                0 if HARD_EVENT_RE.search(f"{it.title} {it.title_zh}") else 1,
                0 if it.hard_event else 1,
                (it.time or self.now).timestamp(),
            )
        return min(self.items, key=key)

    @property
    def time_known(self) -> bool:
        return any(it.time_known for it in self.items)

    def _times(self) -> list[datetime]:
        known = [it.time for it in self.items if it.time_known and it.time]
        pool = known or [it.time for it in self.items if it.time]
        return [min(t, self.now) for t in pool]

    @property
    def earliest(self) -> datetime | None:
        times = self._times()
        return min(times) if times else None

    @property
    def latest(self) -> datetime | None:
        times = self._times()
        return max(times) if times else None

    @property
    def first_seen(self) -> datetime | None:
        times = [it.first_seen for it in self.items if it.first_seen]
        return min(times) if times else self.earliest

    @property
    def langs(self) -> set[str]:
        return {it.lang for it in self.items if it.role != DROP}

    @property
    def lang(self) -> str:
        langs = self.langs
        return "both" if len(langs) > 1 else (next(iter(langs)) if langs else "en")

    @property
    def roles(self) -> set[str]:
        return set(self.channels.values())

    @property
    def category(self) -> str:
        head = self.headline.category
        if head != "general":
            return head
        cats = [it.category for it in self.items if it.category != "general"]
        if not cats:
            return "general"
        return max(set(cats), key=lambda c: (cats.count(c), CATEGORY_WEIGHTS[c]))

    @property
    def noise(self) -> str:
        levels = [it.noise for it in self.items if it.role not in (SIGNAL, REFERENCE)] or [it.noise for it in self.items]
        if all(level == "hard" for level in levels):
            return "hard"
        return "soft" if self.headline.noise != "none" else "none"

    @property
    def in_scope(self) -> bool:
        return any(it.in_scope for it in self.items)

    @property
    def known_entity(self) -> bool:
        return any(it.entities["orgs"] or it.strong_entities for it in self.items)

    @property
    def hard_event(self) -> bool:
        return any(it.hard_event for it in self.items if it.role in (PRIMARY, REPORT))

    @property
    def independent_channels(self) -> int:
        counted = [ch for ch, role in self.channels.items() if role != REFERENCE]
        x_count = sum(1 for ch in counted if ch.startswith("x:"))
        return len(counted) - x_count + min(1, x_count)

    @property
    def tier(self) -> int:
        return min((ROLE_TIER[role] for role in self.channels.values()), default=3)

    def hn_bonus(self) -> float:
        best = 0
        for it in self.items:
            try:
                best = max(best, int(it.record.get("hn_points") or 0) + 2 * int(it.record.get("hn_comments") or 0))
            except (TypeError, ValueError):
                continue
        return min(1.0, math.log10(1 + best) / 3) if best else 0.0

    @property
    def agihunt_models_rank(self) -> int | None:
        """AGI HUNT models 频道最热榜中的最佳排名（无则 None）。"""
        ranks = []
        for it in self.items:
            if it.channel != AGIHUNT_MODELS_CHANNEL or it.record.get("agihunt_sort") != "hot":
                continue
            try:
                ranks.append(int(it.record.get("agihunt_rank")))
            except (TypeError, ValueError):
                continue
        return min(ranks) if ranks else None

    def agihunt_bonus(self) -> float:
        rank = self.agihunt_models_rank
        if not rank or rank > AGIHUNT_BONUS_RANKS:
            return 0.0
        return AGIHUNT_MAX_BONUS * (1 - (rank - 1) / AGIHUNT_BONUS_RANKS)

    def github_bonus(self) -> float:
        best = 0
        for it in self.items:
            try:
                best = max(best, int(it.record.get("github_stars_today") or 0))
            except (TypeError, ValueError):
                continue
        return min(GITHUB_MAX_BONUS, math.log10(1 + best) / 4) if best else 0.0

    def heat(self) -> float:
        x_total = 0.0
        raw = 0.0
        for ch, role in self.channels.items():
            w = channel_weight(ch, role)
            if ch.startswith("x:"):
                x_total += w
            else:
                raw += w
        raw += min(X_CHANNEL_CAP, x_total) + self.hn_bonus() + self.agihunt_bonus() + self.github_bonus()
        return 1 - math.exp(-raw / 3.5)

    def velocity(self) -> float:
        # it.time = published_at (fallback first_seen). CI has no persisted archive, so
        # first_seen_at is always "this run" and cannot measure velocity on its own.
        recent = [it for it in self.items if it.time and (self.now - min(it.time, self.now)) <= timedelta(hours=3)]
        recent_channels = {it.channel for it in recent}
        return min(1.0, len(recent_channels) / 3)

    def freshness(self) -> float:
        start = self.earliest or self.first_seen
        if not start:
            return 0.0
        age = max(0.0, (self.now - start).total_seconds() / 3600)
        value = 0.5 ** (age / FRESH_HALF_LIFE_HOURS)
        # 只有抓取时间、没有真实发布时间：不能当成"刚刚发生"。
        return value if self.time_known else min(value, UNKNOWN_TIME_FRESHNESS_CAP)

    def importance(self) -> float:
        base = CATEGORY_WEIGHTS.get(self.category, 0.4)
        if PRIMARY in self.roles:
            base += 0.15
        if self.hard_event:
            base += 0.1
        if AGIHUNT_MODELS_CHANNEL in self.channels:
            base += 0.1
        if self.noise == "soft":
            base -= 0.15
        return max(0.0, min(1.0, base))

    def hot_score(self) -> float:
        score = 0.48 * self.heat() + 0.22 * self.importance() + 0.18 * self.freshness() + 0.12 * self.velocity()
        return round(100 * score, 1)

    def age_hours(self) -> float:
        latest = self.latest or self.first_seen
        return (self.now - latest).total_seconds() / 3600 if latest else float("inf")

    def eligible(self) -> bool:
        return self.in_scope and self.noise != "hard" and bool(self.roles - {DROP})

    def is_hot(self) -> bool:
        if not self.eligible() or self.age_hours() > WINDOW_HOURS:
            return False
        need = SOFT_NOISE_MIN_CHANNELS if self.noise == "soft" else HOT_MIN_CHANNELS
        channels = self.independent_channels
        rank = self.agihunt_models_rank
        if rank and rank <= AGIHUNT_SOLO_HOT_RANK:
            # AGI HUNT 的 models 热榜本身是全网多源聚簇结果，前排算一个额外的独立渠道。
            channels += 1
        if channels < need:
            return False
        # Signal-only events (e.g. HN mirrors + Reddit) need one more channel.
        if not (self.roles & {PRIMARY, REPORT}) and self.independent_channels < need + 1:
            return False
        return True

    def is_fresh(self) -> bool:
        if not self.eligible() or self.noise != "none":
            return False
        if not self.time_known:
            return False
        if not (self.roles & {PRIMARY, REPORT}) or not self.hard_event:
            return False
        if CATEGORY_WEIGHTS.get(self.category, 0) < 0.6:
            return False
        if self.category == "product" and not self.known_entity:
            return False
        start = self.earliest or self.first_seen
        if not start:
            return False
        return (self.now - start) <= timedelta(hours=FRESH_MAX_AGE_HOURS)

    def event_id(self) -> str:
        basis = sorted(it.id for it in self.items)[0]
        return "evt_" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]


def source_ref(item: Item) -> dict[str, Any]:
    rec = item.record
    return {
        "id": item.id,
        "title": item.title,
        "title_zh": item.title_zh or None,
        "title_en": item.title_en or None,
        "title_original": item.title,
        "url": item.url,
        "source": rec.get("source"),
        "source_name": rec.get("site_name"),
        "site_name": rec.get("site_name"),
        "site_id": rec.get("site_id"),
        "source_tier": rec.get("source_tier"),
        "published_at": iso(item.time),
        "first_seen_at": iso(item.first_seen),
        "channel": item.channel,
        "role": item.role,
        "tier": ROLE_TIER.get(item.role, 3),
        "lang": item.lang,
        "summary": rec.get("summary"),
    }


def event_reasons(event: Event, hot: bool, fresh: bool) -> list[str]:
    reasons = []
    if PRIMARY in event.roles:
        reasons.append("official_source")
    if event.independent_channels >= 2:
        reasons.append("multi_source")
    if event.agihunt_models_rank:
        reasons.append("agihunt_models_hot")
    if hot:
        reasons.append("hot")
    if fresh:
        reasons.append("fresh")
    if event.lang == "both":
        reasons.append("cross_lingual")
    return reasons


def github_meta(event: Event) -> dict[str, Any] | None:
    """事件里 GitHub Trending 条目的仓库指标（取今日新增星最多的一条）。"""
    best: dict[str, Any] | None = None
    for it in event.items:
        rec = it.record
        if not rec.get("github_repo"):
            continue
        cand = {
            "repo": rec.get("github_repo"),
            "language": rec.get("github_language"),
            "stars": rec.get("github_stars"),
            "stars_today": rec.get("github_stars_today"),
            "trending_rank": rec.get("github_trending_rank"),
            "description": rec.get("summary"),
        }
        if best is None or int(cand["stars_today"] or 0) > int(best["stars_today"] or 0):
            best = cand
    return best


def event_record(event: Event, hot: bool, fresh: bool) -> dict[str, Any]:
    head = event.headline
    ordered = sorted(event.items, key=lambda it: (ROLE_RANK[it.role], (it.time or event.now).timestamp()))
    zh_item = next((it for it in ordered if it.lang == "zh" and it.role != SIGNAL), None)
    en_item = next((it for it in ordered if it.lang == "en" and it.role != SIGNAL), None)
    title_zh = (head.title_zh or (zh_item.title if zh_item else "")).strip()
    title_en = (head.title_en or (en_item.title if en_item else "")).strip()
    title = title_zh or head.title
    importance = event.importance()
    hot_score = event.hot_score()
    category = event.category
    refs = [source_ref(it) for it in ordered]
    primary = source_ref(head)
    primary["title"] = title
    primary["title_zh"] = title_zh or None
    primary["title_en"] = title_en or None
    label = "官方更新" if PRIMARY in event.roles else ("多源热议" if hot else "最新动态")
    return {
        "story_id": event.event_id(),
        "title": title,
        "title_zh": title_zh or None,
        "title_en": title_en or None,
        "url": head.url,
        "primary_url": head.url,
        "source": head.record.get("source"),
        "source_name": head.record.get("site_name"),
        "sources": refs,
        "items": refs,
        "item_count": len(refs),
        "source_count": event.independent_channels,
        "duplicate_count": event.independent_channels,
        "channels": sorted(event.channels),
        "source_names": sorted({str(r.get("source") or r.get("site_name") or "") for r in refs} - {""}),
        "score": round(importance, 4),
        "importance": round(importance, 4),
        "importance_score": round(importance, 4),
        "importance_label": label,
        "hot_score": hot_score,
        "heat": round(event.heat(), 4),
        "freshness": round(event.freshness(), 4),
        "velocity": round(event.velocity(), 4),
        "category": category,
        "category_label": CATEGORY_LABELS.get(category, "AI 动态"),
        "lane": LANE_BY_CATEGORY.get(category),
        "tier": event.tier,
        "time_known": event.time_known,
        "github": github_meta(event),
        "hard_event": event.hard_event,
        "lang": event.lang,
        "is_hot": hot,
        "is_fresh": fresh,
        "reasons": event_reasons(event, hot, fresh),
        "earliest_at": iso(event.earliest),
        "latest_at": iso(event.latest),
        "first_seen_at": iso(event.first_seen),
        "primary_item": primary,
    }


# ---------------------------------------------------------------------------
# Input loading / payload
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


TRANSLATION_FIELDS = ("title_zh", "title_en", "title_enhanced_zh", "title_bilingual", "summary", "recommend_reason_zh")


def load_records(data_dir: Path) -> tuple[list[dict[str, Any]], datetime]:
    raw_payload = _load_json(data_dir / "latest-24h-all-raw.json")
    records: dict[str, dict[str, Any]] = {}
    for rec in raw_payload.get("items_all_raw") or raw_payload.get("items_all") or []:
        if isinstance(rec, dict) and rec.get("id"):
            records[str(rec["id"])] = dict(rec)
    enriched_sources = [
        (_load_json(data_dir / "latest-24h-all.json"), ("items_all_raw", "items_all")),
        (_load_json(data_dir / "latest-24h.json"), ("items", "items_ai")),
    ]
    for payload, keys in enriched_sources:
        for key in keys:
            for rec in payload.get(key) or []:
                if not isinstance(rec, dict) or not rec.get("id"):
                    continue
                base = records.setdefault(str(rec["id"]), dict(rec))
                for f in TRANSLATION_FIELDS:
                    if rec.get(f) and not base.get(f):
                        base[f] = rec[f]
    stamps = [
        parse_iso(raw_payload.get("generated_at")),
        *(parse_iso(payload.get("generated_at")) for payload, _ in enriched_sources),
    ]
    stamps = [s for s in stamps if s]
    return list(records.values()), max(stamps) if stamps else datetime.now(UTC)


def build_events(records: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    items = [it for it in (build_item(r) for r in records) if it and it.role != DROP]
    window_start = now - timedelta(hours=WINDOW_HOURS + CLUSTER_WINDOW_HOURS / 2)
    items = [it for it in items if not it.time or it.time >= window_start]
    events = [Event(group, now) for group in cluster_items(items)]

    rows: list[dict[str, Any]] = []
    lane_pool: list[dict[str, Any]] = []
    for event in events:
        hot, fresh = event.is_hot(), event.is_fresh()
        if hot or fresh:
            rows.append(event_record(event, hot, fresh))
        elif (
            event.eligible()
            and event.age_hours() <= WINDOW_HOURS
            and LANE_BY_CATEGORY.get(event.category)
            and (event.noise == "none" or event.independent_channels >= 2)
        ):
            lane_pool.append(event_record(event, False, False))

    hot_rows = sorted((r for r in rows if r["is_hot"]), key=lambda r: (-r["hot_score"], r["latest_at"] or ""))
    # 不再强制中英各半：中文来源少时就少，不为凑比例挤掉更热的事件。
    hot_rows = hot_rows[:HOT_LIST_LIMIT]
    for rank, row in enumerate(hot_rows, 1):
        row["hot_rank"] = rank
    hot_ids = {r["story_id"] for r in hot_rows}
    for row in rows:
        if row["is_hot"] and row["story_id"] not in hot_ids:
            row["is_hot"] = False
    rows = [r for r in rows if r["is_hot"] or r["is_fresh"]]
    rows.sort(key=lambda r: r.get("latest_at") or "", reverse=True)
    rows = rows[:STREAM_LIMIT]
    fresh_rows = sorted((r for r in rows if r["is_fresh"]), key=lambda r: r.get("earliest_at") or "", reverse=True)

    # 赛道看板：hot/fresh 事件 + 其余 24h 内合格事件，按赛道分组、热度排序。
    stream_ids = {r["story_id"] for r in rows}
    candidates = [r for r in rows if r.get("lane")] + [r for r in lane_pool if r["story_id"] not in stream_ids]
    lanes: list[dict[str, Any]] = []
    lane_ids: set[str] = set()
    for key, label, _cats in LANES:
        members = sorted(
            (r for r in candidates if r.get("lane") == key),
            key=lambda r: (
                not r["is_hot"],
                not (r["is_fresh"] or r["hard_event"] or r.get("github")),
                r.get("tier", 2) >= 3,
                -r["hot_score"],
                r.get("latest_at") or "",
            ),
        )
        picked = members[:LANE_LIMIT]
        lane_ids.update(r["story_id"] for r in picked)
        lanes.append({
            "key": key,
            "label": label,
            "count": len(members),
            "hot_count": sum(1 for r in members if r["is_hot"]),
            "fresh_count": sum(1 for r in members if r["is_fresh"]),
            "stories": [r["story_id"] for r in picked],
        })
    rows = rows + [r for r in lane_pool if r["story_id"] in lane_ids and r["story_id"] not in stream_ids]

    def lang_mix(sample: list[dict[str, Any]]) -> dict[str, int]:
        mix = {"zh": 0, "en": 0, "both": 0}
        for r in sample:
            mix[r["lang"]] = mix.get(r["lang"], 0) + 1
        return mix

    return {
        "schema": SCHEMA_VERSION,
        "generated_at": iso(now),
        "window_hours": WINDOW_HOURS,
        "total_stories": len(rows),
        "hot": [r["story_id"] for r in hot_rows],
        "fresh": [r["story_id"] for r in fresh_rows],
        "stats": {
            "input_items": len(records),
            "candidate_items": len(items),
            "clusters": len(events),
            "multi_channel_clusters": sum(1 for e in events if e.independent_channels >= 2),
            "hot_count": len(hot_rows),
            "fresh_count": len(fresh_rows),
            "hot_lang_mix": lang_mix(hot_rows),
            "stream_lang_mix": lang_mix(rows),
            "lane_counts": {lane["key"]: lane["count"] for lane in lanes},
        },
        "lanes": lanes,
        "stories": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build hot/fresh AI event lanes from AI Signal data")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--output", default="", help="Output path (default: <data-dir>/events.json)")
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir)
    records, now = load_records(data_dir)
    payload = build_events(records, now)
    output = Path(args.output) if args.output else data_dir / "events.json"
    atomic_write_json(output, payload, compact=True)
    stats = payload["stats"]
    print(
        f"Wrote: {output} ({payload['total_stories']} events, hot={stats['hot_count']}, "
        f"fresh={stats['fresh_count']}, clusters={stats['clusters']}, hot_lang={stats['hot_lang_mix']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
