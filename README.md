# Vision One Million — Automated Scorecard Pipeline

## What This Does

Vision One Million is an automated data pipeline and live dashboard that tracks Waterloo Region's progress toward a set of ambitious regional goals, organized across five civic domains: Housing, Transportation, Healthcare, Employment, and Placemaking. The project takes its name from the forecasted growth of the region toward one million residents, and the infrastructure investments needed to support that growth responsibly.

The pipeline fetches real data from Statistics Canada, Ontario government open data portals, CMHC, Grand River Transit, the Climate Action Waterloo Region dashboard, and other public sources on a weekly schedule. When a primary source is unavailable, a Tavily AI web search provides an automatic fallback so the dashboard always shows current figures. Every metric is rated against a defined target using a four-tier system (Needs Attention / In Progress / On Track / Achieved), and anomalous changes are flagged for analyst review.

## Architecture

```
config/sources.yaml
        │
        ▼
┌───────────────────────────────────────────┐
│         Domain Fetchers (src/ingestion/)  │
│  HousingFetcher  EmploymentFetcher        │
│  HealthcareFetcher  TransportationFetcher │
│  PlacemakingFetcher                       │
│                                           │
│  Primary: API / Web Scrape / PDF          │
│  Fallback: Tavily AI Search               │
└───────────────┬───────────────────────────┘
                │
                ▼
┌───────────────────────────┐
│  Validation Layer         │
│  (src/validation/)        │
│  Pydantic v2 models       │
│  DataCleaner + Anomaly    │
│  Detector (GPT-4o-mini)   │
└───────────────┬───────────┘
                │
                ▼
┌───────────────────────────┐       ┌──────────────────────────┐
│  SQLite Database          │ ────► │  Streamlit Dashboard     │
│  data/scorecard.db        │       │  dashboard/app.py        │
│  (src/agent/database.py)  │       │  vision-one-million      │
└───────────────────────────┘       │  .streamlit.app          │
                ▲                   └──────────────────────────┘
                │
┌───────────────────────────┐
│  GitHub Actions           │
│  Weekly cron (Sunday 6am) │
│  python main.py           │
└───────────────────────────┘
```

## Live Dashboard

**https://vision-one-million.streamlit.app**

## Data Sources

| Domain | Source | Type | Frequency | Metrics |
|---|---|---|---|---|
| Housing | Ontario Data Catalogue — Housing Supply Progress | API | Monthly | building_homes_needed, affordable_housing_units |
| Housing | CMHC Rental Market Reports | PDF / Web | Annual | balanced_rental_market |
| Housing | Waterloo Region Housing Master Plan | PDF | Annual | building_homes_needed |
| Housing | Point-in-Time Homelessness Count | PDF | Annual | homelessness_funding |
| Housing | Water & Wastewater Monitoring Report | PDF | Annual | water_wastewater_capacity |
| Transportation | Grand River Transit Performance Measures | Web Scrape | Monthly | transit_ridership_target |
| Transportation | Ontario Housing Supply Tracker | Web Scrape | Monthly | rail_transit_investment, highway_7 |
| Healthcare | Ontario LTC Locator | Web Scrape | Monthly | ltc_access |
| Healthcare | Tavily AI Search | AI Search | Weekly | er_wait_target, residents_with_doctor |
| Employment | Statistics Canada LFS (14-10-0380-01) | API | Monthly | regional_employment, unemployment_rate |
| Employment | Waterloo Region Economic Development Strategy | PDF | Annual | tech_talent, employment_lands, megasite |
| Employment | IESO Annual Planning Outlook | Web Scrape | Annual | electrical_capacity |
| Placemaking | Climate Action WR Dashboard | Web Scrape | Monthly | ghg_reduction |
| Placemaking | Statistics Canada Crime Statistics | API | Annual | community_safety |
| Placemaking | WRCF Vital Signs Report | PDF | Annual | social_infrastructure, childcare_access |
| Placemaking | WRDSB Long-Term Accommodation Plan | PDF | Annual | school_spaces |

## Tech Stack

| Tool | Purpose |
|---|---|
| Python 3.11+ | Core language |
| requests + BeautifulSoup4 | HTTP fetching and HTML scraping |
| Playwright | JavaScript-rendered pages |
| PyPDF2 + OpenAI GPT-4o-mini | PDF text extraction and structured parsing |
| Tavily Search API | Fallback web search when primary sources fail |
| Pydantic v2 | Data validation models for each domain |
| pandas | Data cleaning, deduplication, normalization |
| SQLite (sqlite3) | Lightweight persistent storage |
| LangChain + LangGraph | ReAct agent for natural language metric queries |
| LangSmith | LLM call tracing and observability |
| Streamlit | Live interactive dashboard |
| Plotly Express | Historical trend charts |
| GitHub Actions | Weekly pipeline automation |

## Setup

```bash
# 1. Clone and install
git clone https://github.com/DylanCarter16/-vision-one-million.git
cd vision-one-million
pip install -e .

# 2. Configure API keys
cp .env.example .env   # then add OPENAI_API_KEY and TAVILY_API_KEY

# 3. Run the pipeline and launch the dashboard
python main.py
python -m streamlit run dashboard/app.py
```

## How It Works

**Weekly automation:** A GitHub Actions workflow runs `python main.py` every Sunday at 6 AM UTC. Each domain fetcher tries its primary source first (a public API, web scrape, or downloaded PDF), then automatically falls back to a Tavily AI web search if the primary fails. Results are written to `data/scorecard.db`.

**Tavily fallback:** Every fetch method has a `try/except` wrapper. If a URL returns a 4xx/5xx error, times out, or yields no usable number, the fetcher calls the Tavily Search API with a targeted query (e.g. "Kitchener Cambridge Waterloo unemployment rate 2025 Statistics Canada") and parses the first numeric result in a plausible range.

**Anomaly detection:** The `AnomalyDetector` class in `src/validation/anomaly_detector.py` compares each new value against the previous month's value. If the change exceeds 50%, it calls GPT-4o-mini to assess whether the swing is a plausible real-world event or a likely data error. Flagged metrics appear with a warning banner in the dashboard and are routed to the human review queue.

**LangSmith tracing:** The `ScorecardAgent` (powered by LangGraph) wraps all LLM calls with `@traceable` from LangSmith. Every natural language query to the agent — including its tool calls to the SQLite database — is visible in the LangSmith dashboard for debugging and quality review.

## Data Quality

Each metric is rated against a fixed target value using percentage-of-target achieved:

| Rating | Threshold | Color | Meaning |
|---|---|---|---|
| **NEEDS ATTENTION** | < 40% of target | Red `#C62828` | Significant gap; requires urgent action |
| **IN PROGRESS** | 40–69% of target | Amber `#F9A825` | Work underway but well below target |
| **ON TRACK** | 70–89% of target | Green `#2E7D32` | Good progress; on trajectory to achieve |
| **ACHIEVED** | ≥ 90% of target | Teal `#00838F` | At or near target |

For metrics where lower is better (e.g. ER wait times, where the target is < 3.0 hours), the ratio is inverted before rating is applied.

Source status badges indicate data provenance:
- **Live data** (green) — fetched successfully from primary source this run
- **Tavily Search** (blue) — primary source failed; value from AI web search
- **Seed data** (red) — no live or fallback data; showing baseline seeded value
