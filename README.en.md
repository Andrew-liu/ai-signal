# AI Signal

[![GitHub stars](https://img.shields.io/github/stars/Andrew-liu/ai-signal?style=flat-square&color=f5c542)](https://github.com/Andrew-liu/ai-signal/stargazers)
[![Live](https://img.shields.io/badge/Live-AI%20Signal-green?style=flat-square)](https://andrew-liu.github.io/ai-signal/)
[![Actions](https://img.shields.io/github/actions/workflow/status/Andrew-liu/ai-signal/update-news.yml?branch=main&label=update&style=flat-square)](https://github.com/Andrew-liu/ai-signal/actions/workflows/update-news.yml)
[![Agent Skill](https://img.shields.io/badge/Agent%20Skill-AI%20News%20Radar-blueviolet?style=flat-square)](skills/ai-news-radar/README.md)
[![License](https://img.shields.io/badge/license-MIT-green.svg?style=flat-square)](LICENSE)

An open-source AI information aggregator for Chinese AI practitioners and creators.

AI Signal collects public updates from official blogs, technical media, RSS feeds, developer communities, and optional social sources. It filters AI-relevant items, normalizes titles, removes duplicates, merges coverage of the same event, ranks importance, and publishes a static responsive website.

[Live site](https://andrew-liu.github.io/ai-signal/) · [中文](README.md) · [Source strategy](docs/SOURCE_COVERAGE.md)

## Features

- Official updates, AI media, RSS/OPML, Hacker News, GitHub, and optional social sources
- Explainable AI-relevance scoring
- Same-event clustering with original source links
- Chinese titles, concise summaries, review lines, and daily picks
- Source health and AI-signal-density reporting
- Hourly GitHub Actions refresh and GitHub Pages deployment
- Tests, sanitization, and quality gates before publication

## Architecture

```text
Public sources / RSS / optional APIs
              ↓
Fetch and normalize RawItem
              ↓
AI relevance and content enrichment
              ↓
Deduplicate, cluster, and rank
              ↓
Static data/*.json
              ↓
Responsive website / Agent Skill
```

```text
scripts/        ingestion, clustering, scoring, and publishing
assets/         the single responsive frontend
data/           static JSON consumed by the site
feeds/          OPML examples and private subscription entry
personas/       persona prompts
tests/          pipeline and security tests
skills/         Agent consumer and maintainer Skills
```

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q
python scripts/quality_gate.py --data-dir data
python scripts/build_public_site.py --data-dir data --output-dir dist
python -m http.server 8080 --directory dist
```

Open `http://127.0.0.1:8080/`.

## Refresh data

```bash
python scripts/update_news.py \
  --output-dir data \
  --window-hours 24 \
  --archive-days 21 \
  --rss-opml feeds/follow.example.opml \
  --rss-max-feeds 10

python scripts/persona_score.py --data-dir data
python scripts/sanitize_public_data.py --data-dir data
python scripts/quality_gate.py --data-dir data --max-age-hours 6
python scripts/build_public_site.py --data-dir data --output-dir dist
```

Copy `feeds/follow.example.opml` to `feeds/follow.opml` for private subscriptions. The private file is ignored by Git.

## Optional integrations

- `DEEPSEEK_API_KEY`: translation, title enhancement, review lines, and persona scoring
- `SOCIALDATA_API_KEY`: X search and curated account lists
- `TIKHUB_API_KEY`: Douyin and Xiaohongshu search
- `X_BEARER_TOKEN`: official X API
- `AGENTMAIL_API_KEY`, `AGENTMAIL_INBOX_ID`: newsletter inbox summaries
- `FOLLOW_OPML_B64`: private OPML in GitHub Actions

Never commit credentials, private OPML files, or secret-bearing JSON.

## Deployment

`.github/workflows/update-news.yml` runs at minute 17 of every hour. Configure GitHub Pages with:

```text
Settings → Pages → Source → GitHub Actions
```

Vercel is also supported; only the allowlisted `dist/` artifact is published.

## License

[MIT](LICENSE). Third-party articles, posts, and media remain the property of their original publishers. AI Signal exposes only necessary excerpts and source links.
