#!/usr/bin/env python3
"""GitHub Rising Stars：开源栏目数据（日 / 周 / 月 Trending 榜）。

移植自 github-rising-stars skill 的确定性部分：抓取 github.com/trending，
按描述关键词 + 语言做分类，标出冠军和「黑马」（总星少但涨得猛），统计语言分布。
配置了 DEEPSEEK_API_KEY 时，再用 DeepSeek 给每个项目写中文介绍、给每期榜单写点评
（enrich_with_ai，带缓存）。输出 data/github-rising-stars.json 给首页「开源」视图使用。

和 update_news.py 里的 github_trending 源的区别：那个源只取日榜，进入事件层
参与 AI 赛道排序；这里保留完整的日/周/月三张榜，单独成栏，不做 AI 过滤。
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests
from bs4 import BeautifulSoup

try:
    from scripts.safe_io import atomic_write_json
except ModuleNotFoundError:
    from safe_io import atomic_write_json

TRENDING_URL = "https://github.com/trending"
SCHEMA = "github_rising_stars_v1"
PERIODS = (("daily", "今日"), ("weekly", "本周"), ("monthly", "本月"))
DESC_MAX = 240
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# 分类顺序即优先级；key 给程序用，label 给页面用。
CATEGORIES = (
    ("ai", "AI / ML"),
    ("frontend", "前端"),
    ("devtools", "开发工具"),
    ("backend", "后端 / 全栈"),
    ("other", "其他"),
)
CATEGORY_LABELS = dict(CATEGORIES)

AI_KEYWORDS = (
    "ai", "llm", "gpt", "agent", "agents", "machine learning", "deep learning",
    "neural", "model", "models", "diffusion", "transformer", "embedding",
    "rag", "langchain", "openai", "anthropic", "claude", "inference",
    "fine-tun", "training", "dataset", "nlp", "computer vision",
    "mcp", "a2a", "chatbot", "copilot", "voice ai", "vllm", "ollama",
    "text-to", "speech-to", "image generation", "大模型", "智能体",
)
FRONTEND_KEYWORDS = (
    "react", "vue", "svelte", "next.js", "nuxt", "angular", "ui component",
    "css", "tailwind", "frontend", "front-end", "browser", "dom",
    "web app", "dashboard", "visualization",
)
DEVTOOLS_KEYWORDS = (
    "cli", "terminal", "editor", "linter", "formatter", "bundler",
    "compiler", "debugger", "profiler", "devtool", "build tool",
    "package manager", "shell", "vscode", "neovim", "dotfiles",
)
BACKEND_KEYWORDS = (
    "server", "api", "backend", "back-end", "database", "microservice",
    "http", "grpc", "rest", "graphql", "auth", "queue", "cache",
    "web framework", "full-stack", "fullstack",
)
LANGUAGE_FALLBACK = {
    "frontend": {"javascript", "typescript", "vue", "svelte", "css", "html", "scss", "less"},
    "backend": {"go", "java", "kotlin", "ruby", "php", "elixir", "scala", "clojure"},
    "devtools": {"rust", "zig", "shell", "powershell", "makefile", "dockerfile", "lua", "vim script"},
}

# 黑马：总星不到 1 万、本期新增够多且增长率够高。
DARK_HORSE_MAX_STARS = 10_000
DARK_HORSE_MIN_GAINED = {"daily": 200, "weekly": 500, "monthly": 1000}
DARK_HORSE_MIN_RATE = 5.0

_GAINED_RE = re.compile(r"([\d,]+)\s+stars?\s+(?:today|this week|this month)", re.I)


def _match(text: str, keywords: tuple[str, ...]) -> bool:
    low = text.lower()
    for kw in keywords:
        # 短词用词边界，避免 "ai" 命中 "maintain"、"api" 命中 "rapid"。
        if len(kw) <= 3 and kw.isascii():
            if re.search(rf"\b{re.escape(kw)}\b", low):
                return True
        elif kw in low:
            return True
    return False


def classify(language: str, description: str, repo: str = "") -> str:
    text = f"{repo.replace('/', ' ').replace('-', ' ')} {description or ''}"
    if _match(text, AI_KEYWORDS):
        return "ai"
    if _match(text, FRONTEND_KEYWORDS):
        return "frontend"
    if _match(text, DEVTOOLS_KEYWORDS):
        return "devtools"
    if _match(text, BACKEND_KEYWORDS):
        return "backend"
    lang = (language or "").lower()
    for key, langs in LANGUAGE_FALLBACK.items():
        if lang in langs:
            return key
    return "other"


def _int(text: str) -> int:
    raw = str(text or "").strip().lower().replace(",", "")
    try:
        if raw.endswith("k"):
            return int(float(raw[:-1]) * 1000)
        return int(re.sub(r"[^\d]", "", raw) or 0)
    except ValueError:
        return 0


def parse_trending(html: str, since: str = "daily") -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    projects: list[dict[str, Any]] = []
    for row in soup.select("article.Box-row"):
        link = row.select_one("h2 a[href]")
        if not link:
            continue
        repo = re.sub(r"\s+", "", link.get("href", "")).strip("/")
        if repo.count("/") != 1:
            continue
        desc_tag = row.select_one("p")
        desc = re.sub(r"\s+", " ", desc_tag.get_text(" ", strip=True)).strip() if desc_tag else ""
        lang_tag = row.select_one("[itemprop='programmingLanguage']")
        language = lang_tag.get_text(strip=True) if lang_tag else ""
        stars_tag = row.select_one("a[href$='/stargazers']")
        forks_tag = row.select_one("a[href$='/forks']")
        gained = _GAINED_RE.search(row.get_text(" ", strip=True))
        stars = _int(stars_tag.get_text(strip=True)) if stars_tag else 0
        stars_gained = _int(gained.group(1)) if gained else 0
        category = classify(language, desc, repo)
        rate = round(stars_gained / stars * 100, 1) if stars else 0.0
        projects.append({
            "repo": repo,
            "owner": repo.split("/")[0],
            "name": repo.split("/")[1],
            "url": f"https://github.com/{repo}",
            "description": desc[:DESC_MAX],
            "language": language,
            "stars": stars,
            "forks": _int(forks_tag.get_text(strip=True)) if forks_tag else 0,
            "stars_gained": stars_gained,
            "growth_rate": rate,
            "category": category,
            "category_label": CATEGORY_LABELS[category],
            "is_dark_horse": (
                0 < stars < DARK_HORSE_MAX_STARS
                and stars_gained >= DARK_HORSE_MIN_GAINED.get(since, 200)
                and rate >= DARK_HORSE_MIN_RATE
            ),
        })
    projects.sort(key=lambda p: p["stars_gained"], reverse=True)
    for rank, p in enumerate(projects, start=1):
        p["rank"] = rank
    return projects


def summarize_period(since: str, label: str, projects: list[dict[str, Any]]) -> dict[str, Any]:
    languages: dict[str, dict[str, int]] = {}
    for p in projects:
        stat = languages.setdefault(p["language"] or "Unknown", {"count": 0, "stars_gained": 0})
        stat["count"] += 1
        stat["stars_gained"] += p["stars_gained"]
    categories = []
    for key, cat_label in CATEGORIES:
        members = [p for p in projects if p["category"] == key]
        if members:
            categories.append({
                "key": key,
                "label": cat_label,
                "count": len(members),
                "stars_gained": sum(p["stars_gained"] for p in members),
            })
    return {
        "since": since,
        "label": label,
        "total": len(projects),
        "champion": projects[0]["repo"] if projects else None,
        "dark_horses": [p["repo"] for p in projects if p["is_dark_horse"]],
        "categories": categories,
        "languages": [
            {"language": name, **stat}
            for name, stat in sorted(languages.items(), key=lambda kv: (-kv[1]["count"], -kv[1]["stars_gained"]))
        ],
        "projects": projects,
    }


def fetch_page(session: requests.Session, since: str) -> str:
    resp = session.get(
        TRENDING_URL,
        params={"since": since},
        headers={"User-Agent": USER_AGENT, "Accept": "text/html", "Accept-Language": "en-US,en;q=0.9"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.text


def build_payload(
    now: datetime,
    fetch: Callable[[str], str],
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """逐个周期抓取；单个周期失败时沿用上一轮快照，全部失败才标记 has_error。"""
    prev_periods = {p.get("since"): p for p in (previous or {}).get("periods", []) if isinstance(p, dict)}
    periods: list[dict[str, Any]] = []
    errors: list[str] = []
    for since, label in PERIODS:
        try:
            projects = parse_trending(fetch(since), since)
            if not projects:
                raise RuntimeError("no repositories parsed (layout changed?)")
            periods.append(summarize_period(since, label, projects))
        except Exception as exc:  # noqa: BLE001 - 单个周期失败不影响其它周期
            errors.append(f"{since}: {exc}")
            stale = prev_periods.get(since)
            if stale:
                periods.append({**stale, "stale": True})
            else:
                periods.append(summarize_period(since, label, []))
    fresh = len(PERIODS) - len(errors)
    return {
        "schema": SCHEMA,
        "generated_at": now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": "GitHub Trending",
        "source_url": TRENDING_URL,
        "periods": periods,
        "has_error": fresh == 0,
        "error": "; ".join(errors) if errors else None,
    }


def fetch_rising_stars(
    session: requests.Session,
    now: datetime,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return build_payload(now, lambda since: fetch_page(session, since), previous)


# ---------- DeepSeek 解读 ----------
# 两类内容，都缓存在 title-zh-cache.json（与标题翻译、推荐理由共用一个文件，不同前缀）：
#   rs1|<sha1(repo|description)>  单个项目的中文介绍：是什么、给谁用、亮点
#   rsb1|<since>|<sha1(榜单仓库列表)>  每期榜单点评（JSON 字符串）：总览 / 冠军 / 黑马
# 项目描述不变就不重算；榜单成员不变就不重算点评。没有 DEEPSEEK_API_KEY 时整体跳过。
PROJECT_CACHE_PREFIX = "rs1|"
BRIEF_CACHE_PREFIX = "rsb1|"
PROJECT_BATCH = 8
README_MAX = 2500
SUMMARY_MIN, SUMMARY_MAX = 30, 260
BRIEF_FIELDS = ("overview", "champion", "dark_horse")


def _deepseek_config() -> tuple[str, str, str] | None:
    key = str(os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    if not key:
        return None
    base = str(os.environ.get("DEEPSEEK_API_BASE_URL") or "https://api.deepseek.com").strip().rstrip("/")
    model = str(os.environ.get("DEEPSEEK_MODEL") or "deepseek-v4-flash").strip()
    return key, base, model


def deepseek_json(system: str, user: str, timeout: int = 90) -> dict[str, Any] | None:
    """调用 DeepSeek chat，要求返回 JSON 对象；任何失败都返回 None。"""
    cfg = _deepseek_config()
    if not cfg:
        return None
    key, base, model = cfg
    try:
        r = requests.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "temperature": 0.3,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            },
            timeout=timeout,
        )
        if r.status_code != 200:
            return None
        content = str(((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content)
        data = json.loads(content)
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def _clean_text(value: Any, max_len: int) -> str:
    text = re.sub(r"<[^>]+>", "", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip().strip("\"'“”「」")
    return text[:max_len]


def _readme_excerpt(markdown: str) -> str:
    text = re.sub(r"```.*?```", " ", markdown, flags=re.S)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = html.unescape(text).replace("\xa0", " ")
    # 丢掉只有符号/空白的行（徽章残留、语言切换栏的 • 分隔符等）。
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if len(re.sub(r"[\W_]+", "", line)) >= 3]
    return "\n".join(lines)[:README_MAX]


README_NAMES = ("README.md", "readme.md", "Readme.md", "README.MD", "README.rst", "README")


def fetch_readme(session: requests.Session, repo: str) -> str:
    """取仓库 README 开头作为上下文，减少模型只凭一句描述瞎猜。失败返回空串。"""
    for name in README_NAMES:
        try:
            r = session.get(
                f"https://raw.githubusercontent.com/{repo}/HEAD/{name}",
                headers={"User-Agent": USER_AGENT},
                timeout=12,
            )
        except Exception:  # noqa: BLE001
            return ""
        if r.status_code == 200:
            return _readme_excerpt(r.text)
        if r.status_code != 404:
            return ""
    return ""


def project_cache_key(project: dict[str, Any]) -> str:
    raw = f"{project.get('repo')}|{project.get('description') or ''}"
    return PROJECT_CACHE_PREFIX + hashlib.sha1(raw.encode("utf-8")).hexdigest()


def brief_cache_key(period: dict[str, Any]) -> str:
    repos = ",".join(p["repo"] for p in period.get("projects") or [])
    return f"{BRIEF_CACHE_PREFIX}{period.get('since')}|" + hashlib.sha1(repos.encode("utf-8")).hexdigest()


PROJECT_SYSTEM = (
    "你是开源技术编辑，为 GitHub Trending 上的项目写中文介绍，读者大多没听说过这些项目。"
    "每个项目写 2 到 3 句、60 到 150 字，讲清楚：它是什么、解决什么问题；适合谁用；和同类相比有什么特别之处。"
    "只根据给出的描述和 README 写，不确定的地方宁可不写，不要编造 star 数、公司背景或功能。"
    "项目名、产品名、公司名、技术名词保留英文原样。不要用营销腔，不要以「该项目」开头堆砌套话。"
    '输出 JSON 对象：{"items": [{"repo": "owner/name", "summary": "中文介绍"}]}，repo 必须与输入一致。'
)

BRIEF_SYSTEM = (
    "你是开源趋势分析师，根据一期 GitHub Trending 榜单写中文点评。"
    "overview：2 到 3 句，概括这期榜单的整体趋势，例如哪类项目占多数、出现了什么共同主题，可以引用榜单里的数字。"
    "champion：2 到 3 句，分析新增星数第一的项目为什么在这时候火、面向谁。"
    "dark_horse：如果有黑马项目（总星少但增长快），用 1 到 2 句说明为什么值得关注；没有就返回空字符串。"
    "只依据给出的数据，不编造数字。项目名保留英文原样。纯文本，不要 Markdown 或 HTML。"
    '输出 JSON 对象：{"overview": "...", "champion": "...", "dark_horse": "..."}。'
)


def summarize_projects(session: requests.Session, projects: list[dict[str, Any]]) -> dict[str, str]:
    with ThreadPoolExecutor(max_workers=8) as pool:
        readmes = list(pool.map(lambda p: fetch_readme(session, p["repo"]), projects))
    blocks = []
    for p, readme in zip(projects, readmes):
        block = (
            f"### {p['repo']}\n语言：{p.get('language') or '未知'}；分类：{p.get('category_label')}；"
            f"总星 {p.get('stars')}，本期新增 {p.get('stars_gained')}\n描述：{p.get('description') or '（无）'}"
        )
        if readme:
            block += f"\nREADME 摘录：\n{readme}"
        blocks.append(block)
    data = deepseek_json(PROJECT_SYSTEM, "\n\n".join(blocks))
    wanted = {p["repo"] for p in projects}
    out: dict[str, str] = {}
    for item in (data or {}).get("items") or []:
        if not isinstance(item, dict):
            continue
        repo = str(item.get("repo") or "").strip()
        summary = _clean_text(item.get("summary"), SUMMARY_MAX)
        if repo in wanted and _has_cjk(summary) and len(summary) >= SUMMARY_MIN:
            out[repo] = summary
    return out


def brief_period(period: dict[str, Any]) -> dict[str, str] | None:
    lines = [f"榜单：GitHub Trending {period.get('label')}（{period.get('since')}），共 {period.get('total')} 个项目"]
    cats = "、".join(f"{c['label']} {c['count']} 个" for c in period.get("categories") or [])
    langs = "、".join(f"{l['language']} {l['count']}" for l in (period.get("languages") or [])[:6])
    lines.append(f"分类分布：{cats}")
    lines.append(f"语言分布：{langs}")
    lines.append(f"冠军：{period.get('champion')}")
    lines.append(f"黑马：{'、'.join(period.get('dark_horses') or []) or '无'}")
    lines.append("项目（按本期新增星数排序）：")
    for p in period.get("projects") or []:
        intro = p.get("summary_zh") or p.get("description") or ""
        lines.append(
            f"{p['rank']}. {p['repo']} | {p.get('category_label')} | {p.get('language') or '-'} | "
            f"总星 {p.get('stars')} | 新增 {p.get('stars_gained')} | 增速 {p.get('growth_rate')}% | {intro}"
        )
    data = deepseek_json(BRIEF_SYSTEM, "\n".join(lines))
    if not data:
        return None
    brief = {field: _clean_text(data.get(field), 400) for field in BRIEF_FIELDS}
    if not _has_cjk(brief["overview"]):
        return None
    if not period.get("dark_horses"):
        brief["dark_horse"] = ""
    return brief


AI_GATE_KEY = "rsgate|last_ai_date"
BRIEF_LATEST_PREFIX = "rsb_latest|"


def ai_day(now: datetime) -> str:
    """按 UTC 日期计天：GitHub Trending 日榜在 UTC 0 点（北京 8 点）换榜，和它对齐。"""
    return now.astimezone(timezone.utc).date().isoformat()


def seed_cache_from_previous(cache: dict[str, str], previous: dict[str, Any] | None) -> None:
    """从上一版 github-rising-stars.json 恢复闸门日期和已生成的解读。

    CI 里 data/title-zh-cache.json 被 .gitignore 忽略、每轮都从空缓存开始，
    只有 github-rising-stars.json 会被提交并在下一轮 checkout 回来。
    不做这一步的话，线上每小时都会把「今天还没调用过」当真，再调一轮 DeepSeek。
    """
    if not isinstance(previous, dict):
        return
    last_day = str((previous.get("ai") or {}).get("last_run_date") or "")
    if last_day and last_day > cache.get(AI_GATE_KEY, ""):
        cache[AI_GATE_KEY] = last_day
    for period in previous.get("periods") or []:
        if not isinstance(period, dict):
            continue
        projects = [p for p in period.get("projects") or [] if isinstance(p, dict) and p.get("repo")]
        for p in projects:
            summary = p.get("summary_zh")
            if summary:
                cache.setdefault(project_cache_key(p), str(summary))
        brief = period.get("brief_zh")
        if isinstance(brief, dict) and brief.get("overview"):
            dumped = json.dumps(brief, ensure_ascii=False)
            # 只按点评生成时的榜单指纹恢复；当天沿用的旧点评不能挂到新成员上，否则第二天不会重写。
            if brief.get("key"):
                cache.setdefault(str(brief["key"]), dumped)
            cache.setdefault(BRIEF_LATEST_PREFIX + str(period.get("since")), dumped)


def enrich_with_ai(
    payload: dict[str, Any],
    session: requests.Session,
    cache: dict[str, str],
    max_new_projects: int | None = None,
    now: datetime | None = None,
    previous: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    """给每个项目补 summary_zh、给每期补 brief_zh。

    调用频率：每个 UTC 日最多一轮 DeepSeek 调用。闸门日期存在缓存的 AI_GATE_KEY 里，
    在发出第一个请求前就写入，所以当天这一轮即使失败也不会在后续刷新里重试，
    不管是 update_news.py 的定时任务还是手动跑本脚本，只要共用同一个缓存文件就共享这道闸门。
    当天其余刷新只读缓存：新上榜的项目先显示 GitHub 原始描述，点评沿用最近一次生成的版本。
    """
    cfg = _deepseek_config()
    seed_cache_from_previous(cache, previous)
    today = ai_day(now or datetime.now(timezone.utc))
    last_day = cache.get(AI_GATE_KEY, "")
    gate_open = bool(cfg) and last_day != today
    if max_new_projects is None:
        try:
            max_new_projects = int(os.environ.get("RISING_AI_MAX_PER_RUN") or 60)
        except ValueError:
            max_new_projects = 60
    requests_made = 0

    def claim_gate() -> None:
        cache[AI_GATE_KEY] = today

    # 1) 项目介绍：三期榜单的项目去重后一起处理。
    unique: dict[str, dict[str, Any]] = {}
    for period in payload.get("periods") or []:
        for p in period.get("projects") or []:
            unique.setdefault(project_cache_key(p), p)
    pending = [p for key, p in unique.items() if key not in cache][: max(0, max_new_projects)]
    if gate_open and pending:
        claim_gate()
        for start in range(0, len(pending), PROJECT_BATCH):
            batch = pending[start:start + PROJECT_BATCH]
            requests_made += 1
            result = summarize_projects(session, batch)
            for p in batch:
                if p["repo"] in result:
                    cache[project_cache_key(p)] = result[p["repo"]]
    for period in payload.get("periods") or []:
        for p in period.get("projects") or []:
            summary = cache.get(project_cache_key(p)) or p.get("summary_zh") or ""
            if summary:
                p["summary_zh"] = summary

    # 2) 每期点评：放在项目介绍之后，让点评能引用中文介绍。
    for period in payload.get("periods") or []:
        if not period.get("projects"):
            continue
        since = str(period.get("since"))
        key = brief_cache_key(period)
        cached = cache.get(key)
        if cached is None and gate_open:
            claim_gate()
            requests_made += 1
            brief = brief_period(period)
            if brief:
                brief["date"] = today
                brief["key"] = key
                cached = json.dumps(brief, ensure_ascii=False)
                cache[key] = cached
                cache[BRIEF_LATEST_PREFIX + since] = cached
        if cached is None:
            # 当天闸门已关、榜单成员又变了：沿用这一期最近一次的点评，不再调用模型。
            cached = cache.get(BRIEF_LATEST_PREFIX + since)
        if cached:
            try:
                period["brief_zh"] = json.loads(cached)
            except json.JSONDecodeError:
                pass

    payload["ai"] = {
        "provider": "deepseek",
        "enabled": bool(cfg),
        "policy": "once_per_utc_day",
        "last_run_date": cache.get(AI_GATE_KEY) or None,
        "requests_this_run": requests_made,
    }
    return payload, cache


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch GitHub Rising Stars (daily/weekly/monthly trending)")
    parser.add_argument("--output", type=Path, default=Path("data/github-rising-stars.json"))
    parser.add_argument("--cache", type=Path, default=Path("data/title-zh-cache.json"),
                        help="DeepSeek 解读缓存文件（与标题翻译缓存共用）")
    parser.add_argument("--no-ai", action="store_true", help="跳过 DeepSeek 解读")
    args = parser.parse_args()
    previous = None
    if args.output.is_file():
        try:
            previous = json.loads(args.output.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous = None
    session = requests.Session()
    payload = fetch_rising_stars(session, datetime.now(timezone.utc), previous)
    if not args.no_ai:
        cache: dict[str, str] = {}
        if args.cache.is_file():
            try:
                loaded = json.loads(args.cache.read_text(encoding="utf-8"))
                cache = {str(k): str(v) for k, v in loaded.items()} if isinstance(loaded, dict) else {}
            except json.JSONDecodeError:
                cache = {}
        payload, cache = enrich_with_ai(payload, session, cache, previous=previous)
        atomic_write_json(args.cache, cache, indent=2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(args.output, payload, indent=2)
    counts = ", ".join(f"{p['since']}={p['total']}" for p in payload["periods"])
    with_ai = sum(1 for per in payload["periods"] for p in per["projects"] if p.get("summary_zh"))
    briefs = sum(1 for per in payload["periods"] if per.get("brief_zh"))
    ai = payload.get("ai") or {}
    print(
        f"Wrote: {args.output} ({counts}; ai summaries={with_ai}, briefs={briefs}, "
        f"deepseek requests this run={ai.get('requests_this_run', 0)}, last ai day={ai.get('last_run_date')})"
    )
    return 1 if payload["has_error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
