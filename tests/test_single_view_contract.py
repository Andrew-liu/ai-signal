"""Regression checks for the single responsive frontend contract."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_FILES = (
    "latest-24h.json",
    "latest-24h-all.json",
    "waytoagi-7d.json",
    "source-status.json",
    "daily-brief.json",
    "stories-merged.json",
)
REQUIRED_IDS = (
    "updatedAt",
    "sourceStatusPill",
    "sectionTabs",
    "modeSelectedBtn",
    "modeAllBtn",
    "searchInput",
    "siteSelect",
    "hotBoardWrap",
    "hotBoardList",
    "newsListWrap",
    "newsList",
    "itemTpl",
)


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_single_frontend_keeps_data_source_override_contract():
    source = read("assets/app.js")
    assert 'get("data")' in source
    assert 'localStorage.getItem("dataBaseUrl")' in source
    assert "function dataUrl(path)" in source
    for filename in DATA_FILES:
        assert filename in source


def test_single_frontend_keeps_last_mile_content_safety_gate():
    source = read("assets/app.js")
    assert "UNSAFE_HARD_PATTERNS" in source
    assert "UNSAFE_PROMO_PATTERNS" in source
    assert "function safeItems(items)" in source
    assert "function isUnsafeStory(story)" in source


def test_page_exposes_only_one_responsive_surface():
    source = read("index.html")
    assert "view-mode.js" not in source
    assert "view-switch.css" not in source
    assert "data-radar-view-target" not in source
    assert 'href="./classic/' not in source
    assert "data-radar-view=" not in source
    assert not (ROOT / "classic" / "index.html").exists()


def test_page_preserves_required_runtime_dom_contract():
    source = read("index.html")
    for element_id in REQUIRED_IDS:
        assert f'id="{element_id}"' in source
    assert 'class="news-card"' in source
    assert 'class="meta-row"' in source
    assert 'class="title"' in source
    assert 'class="news-summary"' in source
    assert 'class="why-box"' in source


def test_public_build_only_copies_single_frontend_assets():
    source = read("scripts/build_public_site.py")
    assert 'ROOT_DIRS = ("assets",)' in source
    assert '"classic"' not in source


def test_design_tokens_follow_editorial_reference():
    source = read("assets/styles.css")
    for token in ("#202020", "#efefef", "#f5f5f5", "#ebe6dd", "#ff682c", "#816729"):
        assert token in source
    assert "box-shadow:" not in source
    assert "linear-gradient" not in source
