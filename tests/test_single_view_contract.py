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


def test_page_exposes_ai_trending_board_with_explicit_24h_rules():
    html = read("index.html")
    app = read("assets/app.js")
    assert 'aria-label="AI热榜"' in html
    assert "AI热榜" in html
    assert "HOT_WINDOW_HOURS = 24" in app
    assert "HOT_MIN_IMPORTANCE_SCORE = 82" in app
    assert "HOT_TRUSTED_IMPORTANCE_SCORE = 76" in app
    assert "function hotReferenceTimeMs()" in app
    assert "function storyHasTrustedHotSource(story)" in app
    assert "function storyQualifiesForHotBoard(story)" in app
    assert "热度" in app


def test_public_build_only_copies_single_frontend_assets():
    source = read("scripts/build_public_site.py")
    assert 'ROOT_DIRS = ("assets",)' in source
    assert '"classic"' not in source


def test_tailwind_source_preserves_visual_contract():
    source = read("assets/tailwind.css")
    package = read("package.json")
    assert '@import "tailwindcss"' in source
    assert '"tailwindcss": "4.3.3"' in package
    for token in ("#f6f5f4", "#ffffff", "#111111", "#0075de", "#e6f3fe", "#ffb110", "#f64932", "#02093a"):
        assert token in source
    assert "--page-max-width: 1280px" in source
    assert "--radius-cards: 16px" in source
    assert "--motion-duration: 200ms" in source
    for tone in ("tone-models", "tone-products", "tone-devtools", "tone-research", "tone-industry", "tone-community", "tone-creator", "tone-aggregate"):
        assert tone in source
    assert "linear-gradient" not in source


def test_tailwind_compiled_styles_are_checked_in():
    compiled = read("assets/styles.css")
    assert "tailwindcss v4.3.3" in compiled
    assert ".hot-board-wrap" in compiled
    assert ".news-card" in compiled




