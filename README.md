# Bina.az Real Estate Data Pipeline

A fully automated batch data pipeline for monitoring the Baku real estate market (bina.az). The system scrapes the market every hour, cleans and structures the data, automatically detects price anomalies and suspicious seller behavior, and visualizes the results in a Power BI dashboard.

## Contents

- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [How It Works — Step by Step](#how-it-works--step-by-step)
- [Data Lake Layers](#data-lake-layers)
- [Anomaly & Fraud Detection](#anomaly--fraud-detection)
- [Batch Scheduling](#batch-scheduling)
- [Power BI Dashboard](#power-bi-dashboard)
- [Setup](#setup)
- [Lessons Learned / Challenges](#lessons-learned--challenges)
- [Future Improvements](#future-improvements)

---

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌─────────────┐     ┌───────────┐
│  bina.az    │────▶│   BRONZE     │────▶│   SILVER    │────▶│    GOLD     │────▶│ Power BI  │
│  GraphQL    │     │  (raw JSON)  │     │ (cleaned,   │     │(aggregates, │     │ Dashboard │
│  API        │     │              │     │  unique)    │     │  insights)  │     │           │
└─────────────┘     └──────────────┘     └─────────────┘     └─────────────┘     └───────────┘
      ▲
      │              Playwright (browser-driven scraping)
      │              Hourly trigger: Windows Task Scheduler
      └─────────────────────────────────────────────────────────────────────────────────
```

Data flows through a classic **Medallion Architecture** (Bronze/Silver/Gold) — each layer is cleaner, more structured, and more analysis-ready than the last.

---

## Tech Stack

| Layer | Tool | Why |
|---|---|---|
| Scraping | Python, Playwright | Real browser emulation was required to bypass bina.az's anti-bot (Cloudflare/WAF) protection |
| Data Lake | Local file system (Bronze/Silver/Gold) | No Docker/cloud storage available; conceptually identical architecture |
| Format | JSON (Bronze), Parquet (Silver/Gold) | Parquet is compressed, type-safe, and fast to read |
| ETL / Analytics | pandas, numpy | Cleaning, aggregation, statistical anomaly detection |
| Scheduling | Windows Task Scheduler + `.bat` | Local automation without Docker/Airflow |
| Visualization | Power BI Desktop | Dashboard, slicers, drill-through analysis |
| Version control | Git / GitHub | Code history and sharing |

---

## Project Structure

```
real_estate_batch_pipeline/
├── src/
│   ├── scrape.py                # Scrapes bina.az via Playwright (produces Bronze)
│   ├── bronze_to_silver.py      # Cleaning, deduplication, type fixes
│   ├── silver_to_gold.py        # Aggregation (district/room/KPI summaries)
│   ├── gold_insights.py         # Anomaly / fraud detection
│   ├── config.py                # Centralized configuration
│   └── main.py                  # Entry point — runs all steps sequentially
├── data_lake/
│   ├── bronze/                  # Raw, timestamped JSON files (historical archive)
│   ├── silver/                  # Cleaned, deduplicated listings (Parquet + CSV)
│   └── gold/                    # Aggregates + insight tables (Parquet)
├── dashboard/                   # Power BI (.pbix) file
├── logs/
│   └── pipeline.log             # Success/failure log for every run
├── run_pipeline.bat             # Script invoked by Task Scheduler
├── requirements.txt
└── README.md
```

---

## How It Works — Step by Step

### 1. Finding the Data Source (Reverse Engineering)

bina.az has no public/official API. Using Chrome DevTools → Network tab, I identified the site's internal **GraphQL API** (the `SearchItems` operation) and analyzed its request structure (persisted query hash, cursor-based pagination, filter parameters).

### 2. Scraping (`scrape.py`)

The first version sent requests directly to the GraphQL endpoint via the `requests` library, but the site's anti-bot protection (Cloudflare) blocked it with a 400 error. Solution: use **Playwright** to open a real Chromium browser, load the page, and programmatically scroll (which triggers the site's own JavaScript to fire the next GraphQL request), capturing every `SearchItems` response at the network level (`page.on("response")`).

### 3. Bronze → Silver ETL (`bronze_to_silver.py`)

- Merges all Bronze files (each hourly run produces a separate file).
- Deduplicates — if the same listing (`id`) was captured at different times, only the version with the **latest `updated_at`** is kept.
- Splits `property_type` based on `area_unit` (`m²` = building, `sot` = land) to avoid mixing them in price/m² calculations.
- The result is cumulative — Silver grows over time, since each scraping run only sees a slice of the market.

### 4. Silver → Gold (`silver_to_gold.py`)

Produces aggregation tables by district, room count, and overall market KPIs. Additionally, **`district_history.csv`/`kpi_history.csv`** are append-only (never overwritten), enabling time-based trend analysis in Power BI.

### 5. Gold Insights (`gold_insights.py`) — Analytical Value Layer

Goes beyond simple aggregation to run 4 distinct statistical/behavioral analyses (detailed below).

### 6. Orchestration (`main.py`)

Calls all the above steps sequentially, logs every step (`logs/pipeline.log`), and exits with a proper error code (`exit code 1`) on failure so Task Scheduler can flag the run as unsuccessful.

---

## Data Lake Layers

| Layer | Behavior | Example files |
|---|---|---|
| **Bronze** | New file every run (never deleted or overwritten) | `listings_20260713_140000.json` |
| **Silver** | Fixed filename, overwritten each run, content grows cumulatively | `listings.parquet` |
| **Gold — summaries** | Fixed filename, overwritten ("current state") | `district_summary.parquet`, `kpi_summary.parquet` |
| **Gold — history** | Fixed filename, append-only (never overwritten) | `district_history.csv`, `kpi_history.csv` |
| **Gold — insights** | Fixed filename, overwritten, central enriched table | `listings_enriched.parquet` |

---

## Anomaly & Fraud Detection

`gold_insights.py` computes the following 4 statistical/behavioral signals and merges them all into a **single central table** (`listings_enriched.parquet`) so Power BI slicers and drill-through work without relationship issues:

| Signal | Methodology |
|---|---|
| **Underpriced deal** (`deal_flag`) | Bottom 15th percentile of price/m² within the district |
| **Overpriced** (`overpriced_flag`) | Top 15th percentile of price/m² within the district |
| **Duplicate / spam** (`is_duplicate`) | Same price + area + rooms + district combination, different IDs |
| **Bot pattern** (`is_burst_listing`) | Same seller updating/posting 3+ listings in the **same minute** — inconsistent with human behavior |
| **Suspicious seller** (`is_suspicious_seller`) | Listed as "individual" (not an agency), but has 4+ listings |
| **Overall risk score** (`risk_flag_count`) | Count of how many of the above signals overlap on the same listing (0–4) |

> **Note:** These are statistical probabilities, not proof — confirming actual fraud/spam requires human review.

---

## Batch Scheduling

Due to the lack of a Docker environment, automation is handled via **Windows Task Scheduler**:

- `run_pipeline.bat` activates the venv and runs `main.py`.
- Task Scheduler trigger: **hourly, repeating indefinitely**.
- Due to Windows account password requirements for "Run whether user is logged on or not," the **"Run only when user is logged on"** option is used instead.
- Every run's outcome (success/failure, duration) is logged to `logs/pipeline.log`.

---

## Power BI Dashboard

Consists of 5 pages:

1. **Overview** — KPI cards, property type breakdown, top districts
2. **Price Analysis** — price distribution (histogram), price by room count, price vs. area scatter plot with trend line, price/m² comparisons
3. **Geographic Analysis** — district-level price comparisons, scatter plot (price/area/listing count by district), district slicers
4. **Anomalies & Risk** — table sorted by risk score, KPI cards (deal/overpriced/duplicate/bot counts), conditional formatting (heatmap), outlier scatter chart
5. **Detail** — drill-through page showing full listing-level data for any selected data point

Data source: `data_lake/gold/listings_enriched.parquet`.

---

## Setup

```bash
git clone <this-repo-url>
cd real_estate_batch_pipeline
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

For a one-off manual test run:
```bash
python src/main.py
```

Open the `.pbix` file in the `dashboard/` folder with Power BI Desktop, then use **Get Data** to connect to the files in `data_lake/gold/`.

---

## Lessons Learned / Challenges

- **Anti-bot protection:** raw `requests` calls were blocked with a 400 error — switching to a Playwright browser-driven approach was necessary.
- **Pandas `groupby` NaN behavior:** by default, `groupby` drops `NaN` group keys — this silently excluded individual sellers (`company_type=None`) from the statistics, fixed with `dropna=False`.
- **Windows path/scheduling quirks:** folder names with spaces require quoting in Task Scheduler; hidden file extensions (`.bat.txt`) are a common pitfall.
- **Cumulative Silver logic:** each scraping run only sees a slice of the market — Silver's append-and-dedup logic builds the full picture over time.

---

## Future Improvements

- Automatic retention/cleanup policy for old Bronze files
- Scheduled Refresh in Power BI Service (via On-premises Data Gateway)
- Migration to Airflow once a Docker environment is available (better monitoring/retry logic)
- Calibration of anomaly percentile thresholds (currently 15%) against real-world data
