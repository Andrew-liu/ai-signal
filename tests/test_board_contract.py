"""Contract checks for the lane board homepage (index.html + assets/board.*)."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKINS = ("terminal", "editorial", "doodle", "ticker", "poster", "notebook")


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_homepage_is_lane_board_with_inline_views():
    html = read("index.html")
    assert "./assets/board.js" in html
    assert "./assets/board.css" in html
    assert "./assets/app.js" not in html
    for element_id in ("lanes", "feed", "skin", "skin-menu", "seg", "views", "view-name", "view-stat", "more", "stamp"):
        assert f'id="{element_id}"' in html
    # 全部动态和社区在首页内切换，跟随当前主题；旧版 archive 页已删除。
    for view in ("board", "all", "community"):
        assert f'data-view="{view}"' in html
    assert "archive.html" not in html
    assert 'href="./privacy.html"' not in html
    assert 'href="./content-policy.html"' not in html
    # 高级检索、隐私说明、内容与版权都并入首页视图，跟随当前主题。
    assert 'data-view="all" data-focus="q">高级检索<' in html
    assert 'data-view="privacy">隐私说明<' in html
    assert 'data-view="policy">内容与版权<' in html
    for element_id in ("tools", "q", "range", "sites", "doc-privacy", "doc-policy"):
        assert f'id="{element_id}"' in html
    js = read("assets/board.js")
    assert 'ITEMS_PATH = "data/latest-24h.json"' in js
    assert 'FULL_PATH = "data/latest-24h-all.json"' in js
    assert 'COMMUNITY_PATH = "data/waytoagi-7d.json"' in js
    assert '"privacy", "policy"' in js
    assert "UNSAFE_HARD_PATTERNS" in js


def test_legacy_policy_pages_redirect_into_homepage():
    for page, view in (("privacy.html", "privacy"), ("content-policy.html", "policy")):
        html = read(page)
        assert f'url=./?view={view}"' in html
        assert "<script" not in html


def test_skin_picker_offers_six_skins_without_instrument():
    html = read("index.html")
    assert "<select" not in html
    assert ">主题<" in html
    options = re.findall(r'<li role="option" data-theme="([a-z]+)"', html)
    assert tuple(options) == SKINS
    assert "instrument" not in html
    # 默认报纸头版；主题名前不再带 01/02 序号。
    assert '<body data-skin="editorial">' in html
    assert '<li role="option" data-theme="editorial" aria-selected="true">报纸头版</li>' in html
    assert "opt-code" not in html
    css = read("assets/board.css")
    js = read("assets/board.js")
    assert 'DEFAULT_SKIN = "editorial"' in js
    assert "opt-code" not in css
    assert "instrument" not in css
    for skin in SKINS:
        assert f'body[data-skin="{skin}"]' in css
        assert f'"{skin}"' in js
        # 每个主题都给主题菜单定义了自己的配色，避免下拉框和页面风格不一致。
        assert re.search(rf'body\[data-skin="{skin}"\] \{{[^}}]*--menu-bg', css), skin


def test_board_reads_events_lanes_with_safe_dom_only():
    js = read("assets/board.js")
    assert 'EVENTS_PATH = "data/events.json"' in js
    assert "d.lanes" in js
    assert "innerHTML" not in js
    assert "insertAdjacentHTML" not in js
    assert "TRUSTED_DATA_HOSTS" in js
    assert 'rel = "noopener noreferrer"' in js


def test_board_csp_only_allows_google_fonts_as_extra_origin():
    html = read("index.html")
    csp = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', html).group(1)
    assert "script-src 'self';" in csp
    assert "style-src 'self' https://fonts.googleapis.com;" in csp
    assert "font-src 'self' https://fonts.gstatic.com;" in csp
    vercel = read("vercel.json")
    assert "https://fonts.googleapis.com" in vercel
    assert "https://fonts.gstatic.com" in vercel


def test_legacy_frontend_and_tailwind_chain_are_removed():
    for rel in (
        "archive.html",
        "assets/app.js",
        "assets/styles.css",
        "assets/shell.css",
        "assets/tailwind.css",
        "package.json",
        "legacy",
        "assets/screenshots",
    ):
        assert not (ROOT / rel).exists(), rel
    assert "archive.html" not in read("scripts/build_public_site.py")
    workflow = read(".github/workflows/update-news.yml")
    assert "npm" not in workflow
    assert "tailwind" not in workflow.lower()
    for page in ("index.html", "privacy.html", "content-policy.html"):
        html = read(page)
        for legacy in ("app.js", "styles.css", "shell.css", "archive.html"):
            assert legacy not in html, (page, legacy)
