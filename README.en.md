<div align="center">

<a href="https://news.dinosaurliu.com/"><img src="assets/logo.svg" alt="AI Signal" width="120" height="120"></a>

</div>

<h1 align="center">AI Signal</h1>

<div align="center">

[![live](https://img.shields.io/badge/live-AI%20Signal-b8412c?style=flat-square&labelColor=2e4a62)](https://news.dinosaurliu.com/) [![update](https://img.shields.io/github/actions/workflow/status/Andrew-liu/ai-signal/update-news.yml?branch=main&label=update&style=flat-square&labelColor=2e4a62&color=b8412c)](https://github.com/Andrew-liu/ai-signal/actions/workflows/update-news.yml) [![license](https://img.shields.io/badge/license-MIT-b8412c?style=flat-square&labelColor=2e4a62)](LICENSE) [![stars](https://img.shields.io/github/stars/Andrew-liu/ai-signal?style=flat-square&labelColor=2e4a62&color=b8412c)](https://github.com/Andrew-liu/ai-signal/stargazers)<br>
[![python](https://img.shields.io/badge/Python-3.11+-b8412c?style=flat-square&labelColor=2e4a62&logo=python&logoColor=white)](https://www.python.org/) [![static](https://img.shields.io/badge/site-static%20HTML-b8412c?style=flat-square&labelColor=2e4a62)](#tech-stack)

</div>

<p align="center"><b>AI news by lane: the 24 hours that are actually worth reading.</b></p>

<p align="center">
  <a href="https://news.dinosaurliu.com/">Live site</a> ·
  <a href="README.md">中文</a> ·
  <a href="docs/SOURCE_COVERAGE.md">Source strategy</a> ·
  <a href="docs/CONFIG_REFERENCE.md">Config reference</a>
</p>

<div align="center">

![AI Signal lane board](docs/images/board.png)

</div>

## Introduction

**AI Signal is an open-source AI news aggregator built for Chinese-speaking AI practitioners and content creators.** It collects updates from official blogs, tech media, RSS feeds, developer communities, and optional social sources. Every item goes through AI-relevance filtering, Chinese title processing, deduplication, same-event merging, and heat ranking. The result is a static website you can deploy as is.

The whole site is static pages plus a few JSON files. There is no backend and no account system, and nothing is collected about visitors. GitHub Actions refreshes the data on a schedule, and new data is published only after it passes the quality gate.

If you find this project useful, a Star is appreciated.

## Why AI Signal

AI news is scattered across dozens of places: vendor blogs, researchers on X, Hacker News, Chinese media, GitHub Trending, and a long list of newsletters. The same story gets reposted by a dozen outlets, and the updates that matter get buried under reposts and marketing copy.

AI Signal pulls this together. Explainable rules first drop content unrelated to AI. Coverage of the same event is then merged into one entry that keeps every original link. Finally, events are sorted by lane and by heat. One screen tells you what happened in each area today, and when you want more you can follow the sources back to the originals.

## Features

- Lane board: six lanes covering models, dev tools, open source, chips and robotics, funding and earnings, and safety and products. Each lane is sorted by heat and can be filtered to "Hot" or "New"
- Same-event merging: when several sources cover the same story, they become one entry with an independent-source count, and you can expand it to see every report
- Open-source Rising Stars: GitHub Trending daily, weekly, and monthly boards, with the champion and dark horses highlighted, plus Chinese project intros and per-board commentary written by DeepSeek
- All updates and search: every item in the last 24 hours, with keyword search, per-site filters, and Official / Chinese / English toggles
- Chinese first: English titles are translated automatically, with optional LLM title rewriting and "why it matters" lines
- Six themes: Newspaper, Terminal, Doodle Journal, Market Terminal, Color-Block Poster, and Lab Notebook. Your choice is saved locally
- Source health: each run records every source's success rate, item count, and duration, so problems are visible at a glance
- Publish gate: secret scanning, schema checks, minimum counts, and drop protection. Data that fails never replaces the live version

## Four Sections

| Section       | What it is for                                        | Key capabilities                                                        |
| ------------- | ----------------------------------------------------- | ----------------------------------------------------------------------- |
| Lane board    | Scan today's AI headlines by area                     | Six lanes, heat score, same-event merging, Hot/New filters, ← → keys    |
| All updates   | Miss nothing, or find one specific story              | Keyword search, per-site filters, AI-only vs. full, Official/ZH/EN      |
| Open source   | See which GitHub projects are gaining stars right now | Daily/weekly/monthly boards, category filters, champion and dark horses, Chinese intros, commentary |
| Community     | Follow recent posts from the Chinese AI community     | WaytoAGI updates from the last 7 days, by latest day or full week       |

## Screenshots

<div align="center">

|                  Open-source Rising Stars                  |              All updates and search              |
| :--------------------------------------------------------: | :----------------------------------------------: |
| ![Open-source Rising Stars](docs/images/opensource.png)    | ![All updates](docs/images/all.png)              |

|              Terminal theme               |                 Community                  |
| :---------------------------------------: | :----------------------------------------: |
| ![Terminal theme](docs/images/terminal.png) | ![Community](docs/images/community.png)  |

</div>

> Screenshots come from one local run on real public data. All titles and projects shown come from public sources.

## Feature Details

<details>
<summary><b>Lane board</b></summary>

- Six lanes: Models · Research, Dev Tools · Agents, Open Source · GitHub, Chips · Robotics, Funding · Earnings, and Safety · Products. Pure consumer news and general tech news stay out of the lanes.
- Each event gets a heat score from 0 to 100, a weighted mix of heat (sources and engagement) at 48%, importance at 22%, freshness at 18%, and velocity at 12%. The event layer is purely rule-based (`scripts/signal_events.py`) and does not depend on an LLM.
- Events carry HOT and NEW tags plus source tiers such as "Tier 1 · Official" and "Tier 2". Merged events can be expanded so you can jump to each original report.
- Filter by "All / Hot / New" at the top and switch lanes with the ← → keys. The current lane is kept in the URL so links can be shared.

</details>

<details>
<summary><b>All updates and advanced search</b></summary>

- Shows every item in the 24-hour window, newest first. Items without a publish time are labeled with their fetch time and placed at the end.
- The search box accepts several space-separated keywords and matches titles, companies, and sources.
- Scope switches between "AI-related" and "Full (including non-AI)". You can also filter by site, and the filter state is synced to the URL.
- Items that match dangerous-content rules or show several marketing signals are filtered out in the frontend.

</details>

<details>
<summary><b>Open Source · GitHub Rising Stars</b></summary>

- Each refresh fetches the GitHub Trending daily, weekly, and monthly boards and sorts them by stars gained in the period. If a board fails to load, the previous snapshot is kept and the page says so.
- The project with the most new stars is the champion. A dark horse has under 10k total stars, gains at least the threshold in the period (200 daily / 500 weekly / 1000 monthly), and grows by at least 5%.
- Projects are sorted into AI / ML, Frontend, Dev Tools, Backend / Full-stack, and Other using keywords in the repo name and description, with the language as a fallback. The page can filter by category.
- With `DEEPSEEK_API_KEY` set, DeepSeek reads each project's README and writes a 2 to 3 sentence Chinese intro, plus "Highlights / Champion / Dark horse" commentary for each board.
- DeepSeek is called at most one round per UTC day, timed to the Trending reset at 8 AM Beijing time. Later refreshes that day only read the cache, and a failed day is not retried.
- This section has no AI filter and does not enter the event layer. The "Open Source · GitHub" lane on the board still ranks the daily board for AI relevance.

</details>

<details>
<summary><b>Sources</b></summary>

- Built-in free public sources: official AI updates (OpenAI, Anthropic, Google, Hugging Face, GitHub, and more), curated AI media RSS, Follow Builders, TechURLs, Buzzing, Info Flow, BestBlogs, Zeli, Hacker News, AI HubToday, AIbase, AI HOT, NewsNow, GitHub Trending, and WaytoAGI.
- Custom subscriptions: copy `feeds/follow.example.opml` to `feeds/follow.opml` and add your own RSS feeds. That file is ignored by Git.
- Optional paid sources: X API, SocialData (X search), TikHub (Douyin, Xiaohongshu), AGI HUNT, and AgentMail newsletters. Each one turns on only when you set its key, and paid sources have a daily interval gate to keep costs down.
- Source priority: official RSS/Atom and OPML first, then stable public JSON or static pages, and custom scrapers last. See the [source strategy](docs/SOURCE_COVERAGE.md).

</details>

<details>
<summary><b>Chinese processing and LLM enrichment</b></summary>

- English titles are translated with DeepSeek first. Without it, a public translation endpoint is used as the fallback. Product, company, and model names stay in English, and `translation-glossary.txt` fixes common mistranslations.
- With DeepSeek configured, items in the curated AI pool get rewritten titles, and the original article is fetched to write a one-line recommendation.
- All LLM output is cached in `data/title-zh-cache.json`, and cache hits never call the API again. Each kind of enrichment has a per-run limit.
- Ranking for the hot list and the latest list is fully rule-based and does not depend on an LLM, so the site works without any keys.

</details>

<details>
<summary><b>Themes and site</b></summary>

- All six themes share one DOM and switch through `body[data-skin]`. The default is "Newspaper", and your choice is saved in the browser.
- The privacy and content/copyright pages are views inside the home page and follow the current theme.
- The page builds the DOM safely (no `innerHTML`), reads data only from allowlisted domains, opens external links with `noopener noreferrer`, and ships a strict CSP.

</details>

<details>
<summary><b>Publish gate</b></summary>

- Before publishing, `scripts/quality_gate.py` checks that at least 5 sources reported, the success rate is at least 70%, there are at least 5 events and at least 20 items in the AI pool, the item count did not drop more than 70% from the last version, and the event layer and item snapshot were generated within 1 hour of each other.
- Every JSON file is scanned for key patterns, sensitive fields, and URLs with credentials. Any hit blocks the release.
- `scripts/build_public_site.py` copies only allowlisted files into `dist/`, so raw development data and caches are never published.

</details>

## Run Locally

Requirement: Python 3.11 or later.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# Refresh one round of data (free public sources + example OPML)
python scripts/update_news.py --output-dir data --window-hours 24 --archive-days 21 --rss-opml feeds/follow.example.opml
python scripts/signal_events.py --data-dir data
python scripts/quality_gate.py --data-dir data

# Build and preview
python scripts/build_public_site.py --data-dir data --output-dir dist
python -m http.server 8080 --directory dist
```

Then open `http://<your-host>:8080/`. To refresh only the open-source section, run `python scripts/github_rising_stars.py` on its own.

> Without `DEEPSEEK_API_KEY`, title translation falls back to a public translation endpoint, which can stall for a long time if your network is rate-limited. Add `--translate-max-new 0 --translate-max-new-broad 0` to skip new translations. Existing translations are still read from the cache.

## Optional Configuration

These features are enabled through environment variables or GitHub Secrets. The site runs fully without any of them:

| Variable                                    | Purpose                                                                 |
| ------------------------------------------- | ----------------------------------------------------------------------- |
| `DEEPSEEK_API_KEY`                          | Chinese translation, title rewriting, recommendation lines, plus project intros and commentary in the open-source section |
| `RISING_AI_MAX_PER_RUN`                     | Max number of new project intros in the daily open-source round, default 60 |
| `SOCIALDATA_API_KEY`                        | X search and account lists                                              |
| `TIKHUB_API_KEY`                            | Douyin and Xiaohongshu search                                           |
| `X_BEARER_TOKEN`                            | Official X API                                                          |
| `AGIHUNT_API_KEY`                           | AGI HUNT source                                                         |
| `AGENTMAIL_API_KEY`, `AGENTMAIL_INBOX_ID`   | Newsletter inbox digest                                                 |
| `FOLLOW_OPML_B64`                           | Private OPML for GitHub Actions                                         |

See the [config reference](docs/CONFIG_REFERENCE.md) for every parameter, refresh frequency, and how to stop things in an emergency. Never put keys in code, public OPML files, or `data/*.json`.

## Deployment

The workflow at `.github/workflows/update-news.yml` refreshes data on the schedule set by its cron, then deploys to GitHub Pages after the gate passes. Configure Pages as:

```text
Settings → Pages → Source → GitHub Actions
```

You can also import the repo into Vercel. `vercel.json` already sets the build command, publishes only `dist/`, and adds security headers.

## Tests

```sh
python -m pytest -q
```

The tests cover source parsing, AI-relevance scoring, event clustering and lane assignment, publish-time validation, translation and title rewriting, open-source fetching and the DeepSeek call frequency, the home page contract, and security sanitization.

## Tech Stack

| Layer       | Choice                                                                  |
| ----------- | ----------------------------------------------------------------------- |
| Collection  | Python, requests, BeautifulSoup, feedparser                             |
| Processing  | Rule-based AI-relevance scoring, event clustering, and heat ranking (no LLM) |
| Enrichment  | DeepSeek (optional): translation, title rewriting, recommendations, open-source project write-ups |
| Data        | Static JSON: `latest-24h`, `events`, `github-rising-stars`, `waytoagi-7d`, and more |
| Frontend    | Vanilla HTML / CSS / JavaScript, no build step, six themes              |
| Publishing  | GitHub Actions + GitHub Pages, or Vercel                                |
| Testing     | pytest                                                                  |

## Data and Privacy

- The public site needs no sign-up and collects no names, emails, or login data. The browser only stores your theme and filter preferences.
- Only titles, short summaries, sources, times, public engagement numbers, and original links are published. API keys, cookies, email addresses, and private email bodies are never made public.
- When an external model is enabled, some public article snippets and GitHub READMEs are sent to the configured model service. Check that service's privacy terms yourself.
- For corrections, removals, or privacy concerns, open an [issue](https://github.com/Andrew-liu/ai-signal/issues) with the exact URL and the reason.

## Project Structure

```text
ai-signal/
├── scripts/         # Collection (update_news.py), event layer (signal_events.py), open-source boards (github_rising_stars.py), gate and publishing
├── assets/          # Frontend: board.js, board.css, icons
├── data/            # Static JSON and caches read by the site
├── feeds/           # OPML example; private subscriptions go in follow.opml (ignored)
├── tests/           # Pipeline, frontend contract, and security tests
├── docs/            # Source strategy, config reference, and screenshots
├── index.html       # The single page entry
└── vercel.json      # Vercel build and security headers
```

## Contributing

Bug reports and source suggestions are welcome in [Issues](https://github.com/Andrew-liu/ai-signal/issues). Read the [source strategy](docs/SOURCE_COVERAGE.md) before adding a source, and read the development conventions in [AGENTS.md](AGENTS.md) before submitting code.

## License

This project is released under the [MIT License](LICENSE). Third-party news, articles, posts, and images belong to their original publishers. This site shows only the necessary summaries and links to the originals.
