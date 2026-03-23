# Vision One Million — Automated Scorecard Pipeline

## Overview

Vision One Million is an automated data pipeline and live dashboard for Waterloo Region's Ready 1 Million Scorecard. The project replaces manual spreadsheet updates with a fully automated system that fetches live data weekly from Statistics Canada, Ontario open data portals, CMHC, Grand River Transit, the Climate Action Waterloo Region dashboard, and other public sources. Results are validated, stored in a SQLite database, and displayed on a Streamlit dashboard with ratings calculated against defined targets.

When a primary data source is unavailable — due to a URL change, API limit, or page restructuring — the pipeline automatically falls back to a Tavily AI web search to find the most recent publicly available figure. Every metric is rated on a four-tier system (Needs Attention / In Progress / On Track / Achieved) based on percentage of target achieved. Anomalous changes are detected using OpenAI GPT-4o-mini and flagged for human review.

## Live Dashboard

🌐 https://vision-one-million.streamlit.app

## Architecture

```
Data Sources          Pipeline              Output
─────────────         ────────              ──────
Statistics Canada ──► Employment Fetcher ──►
Ontario Open Data ──► Housing Fetcher    ──► SQLite DB ──► Streamlit Dashboard
GRT Performance   ──► Transport Fetcher  ──►                    │
CMHC Reports      ──► Healthcare Fetcher ──►          GitHub Actions (weekly)
Climate Dashboard ──► Placemaking Fetcher──►
         │
         └──► Tavily Search (fallback if primary source fails)
```

## Scorecard Domains

| Domain | Key Metrics | Primary Source | Update Frequency |
|---|---|---|---|
| Housing | Homes built, affordable units, vacancy rate | Ontario Data Catalogue, CMHC | Monthly / Annual |
| Transportation | Transit ridership, rail investment, highway progress | Grand River Transit, Ontario tracker | Monthly |
| Healthcare | ER wait times, LTC access, doctor access | Ontario Health, Tavily | Monthly |
| Employment | Employment rate, jobs secured, tech talent | Statistics Canada LFS | Monthly |
| Placemaking | GHG reduction, childcare, school spaces, safety | Climate Action WR, StatCan crime | Monthly / Annual |

## Rating System

| Status | Threshold | Color |
|--------|-----------|-------|
| NEEDS ATTENTION | < 40% of target | Red `#C62828` |
| IN PROGRESS | 40–69% of target | Amber `#F9A825` |
| ON TRACK | 70–89% of target | Green `#2E7D32` |
| ACHIEVED | 90%+ of target | Teal `#00838F` |

For metrics where lower is better (e.g. ER wait times targeting < 3.0 hours), the ratio is inverted before the rating is applied.

## Tech Stack

| Tool | Purpose |
|------|---------|
| Python 3.11+ | Core pipeline language |
| requests + BeautifulSoup4 | HTTP fetching and HTML scraping |
| PyPDF2 | PDF text extraction |
| LangChain + LangSmith | Agent orchestration and LLM call tracing |
| OpenAI GPT-4o-mini | PDF data extraction and anomaly detection |
| Tavily Search API | Fallback data sourcing when primary sources fail |
| Pydantic v2 | Data validation models for each domain |
| pandas | Data cleaning and transformation |
| SQLite | Lightweight persistent historical storage |
| Streamlit | Interactive live dashboard |
| Plotly Express | Historical trend charts |
| GitHub Actions | Weekly pipeline automation (`cron: 0 0 * * 0`) |

## Running Locally

```bash
git clone https://github.com/DylanCarter16/-vision-one-million
pip install -r requirements.txt
cp .env.example .env  # add your API keys
python main.py        # run the full pipeline
python -m streamlit run dashboard/app.py  # launch the dashboard
```

## Automation

GitHub Actions runs the full pipeline every Sunday at midnight UTC via `.github/workflows/pipeline.yml`. The workflow checks out the repository, installs dependencies, runs `python main.py` using secrets stored in the repository, commits any updated database artifacts, and pushes. The Streamlit Cloud deployment pulls from `main` automatically on each push.

## Data Quality

Every fetcher follows a three-step fallback chain:

1. **Primary source** — structured API call or targeted web scrape against the official source (e.g. Ontario Data Catalogue API, StatCan WDS, CMHC page, GRT performance measures).
2. **Tavily Search** — if the primary source returns a non-200 response, times out, or yields no parseable number, a Tavily AI web search is performed with a specific query and a numeric range filter to reject implausible values.
3. **Human review flag** — if both primary and fallback fail, the metric is marked `failed` and the previous seeded/historical value is retained. Anomaly detection (`src/validation/anomaly_detector.py`) compares each new value against historical data; changes > 50% trigger a GPT-4o-mini assessment to distinguish real-world events from data errors. Flagged metrics appear with a warning banner in the dashboard.
