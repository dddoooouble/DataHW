# Crypto Pulse Dashboard

Crypto Pulse is a deployable market dashboard that tracks a curated basket of major cryptocurrencies with a refreshable ETL pipeline. The app extracts live market data from CoinGecko, transforms it into 24-hour, 7-day, and 30-day indicators, stores the results in SQLite, and serves a custom dashboard without relying on BI tools.

## Why this project fits the assignment

- Dashboard front-end: custom HTML/CSS/JavaScript with Chart.js charts.
- Data pipeline back-end: Python ETL that extracts, transforms, and loads market data.
- Storage layer: SQLite database for snapshots, daily history, and pipeline run logs.
- Refresh mechanism: automatic startup load, recurring background freshness checks, and a manual refresh button.
- Deployment-ready: runs as a public web service on Render with a real URL.

## Project structure

- `app.py`: web server, API routes, and background refresh scheduler.
- `src/pipeline.py`: ETL logic, public API integration, and offline fallback seeding.
- `src/db.py`: SQLite schema and repository methods.
- `src/analytics.py`: summary, leaders, history, and correlation payload builders.
- `static/`: dashboard UI.
- `EXECUTIVE_SUMMARY.md`: one-page submission artifact.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:8000`.

## Deploy on Render

1. Push this project to a GitHub repository.
2. Create a new Render Web Service from that repository.
3. Use the included `render.yaml` or set:
   - Build command: `pip install -r requirements.txt`
   - Start command: `python app.py`
4. After deployment, Render will provide a public URL for the class demo.

## Data model

- `pipeline_runs`: tracks run status, timestamps, record counts, and data source.
- `asset_snapshots`: stores the latest transformed metrics for the curated 12-asset basket.
- `daily_prices`: stores 30-day histories for tracked assets used in line charts and correlation analysis.

## Notes

- When live API access is unavailable on the very first run, the app seeds deterministic sample data so the dashboard still loads.
- On subsequent failures, the dashboard keeps serving the last successful dataset instead of replacing it with degraded data.
