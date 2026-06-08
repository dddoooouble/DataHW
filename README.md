# Crypto Pulse Dashboard

Crypto Pulse is a deployable crypto market dashboard built for a data engineering and visualization assignment. It combines a custom front-end dashboard with a Python ETL pipeline, persistent storage, a refresh mechanism, and a cloud deployment path that avoids localhost-only demos.

## Assignment fit

- `Dashboard front-end`: custom HTML/CSS/JavaScript plus Chart.js. No Tableau, Power BI, or other BI tools.
- `Data pipeline back-end`: Python ETL extracts live market data from CoinGecko, transforms it into derived indicators, and loads it into SQLite.
- `Database layer`: SQLite stores run logs, latest snapshot rows, and 30-day history rows.
- `Refresh mechanism`: startup load, scheduled freshness checks, and a manual refresh button for demos.
- `Public deployment`: packaged for Render so the app can be shown through a public URL instead of localhost.
- `Communication artifact`: [`EXECUTIVE_SUMMARY.md`](/Users/ss/Documents/Codex/2026-06-08/dddoooouble-datahw-https-github-com-dddoooouble/EXECUTIVE_SUMMARY.md) and [`EXECUTIVE_SUMMARY.pdf`](/Users/ss/Documents/Codex/2026-06-08/dddoooouble-datahw-https-github-com-dddoooouble/EXECUTIVE_SUMMARY.pdf).

## What the dashboard shows

- KPI cards for basket market cap, average 30-day return, and best/worst 24-hour performers.
- A 30-day normalized performance chart comparing major crypto assets with Nasdaq and the Dow.
- ETL-derived insight tiles for breadth, concentration, momentum, and regime signal.
- Leaders and laggards, a crypto correlation heatmap, a live news feed, and a full asset table.
- A pipeline monitor panel that proves refresh behavior with run history, record counts, and freshness status.

## Architecture

`CoinGecko API -> ETL transform -> SQLite -> Python API -> Dashboard UI`

- [`app.py`](/Users/ss/Documents/Codex/2026-06-08/dddoooouble-datahw-https-github-com-dddoooouble/app.py): HTTP server, API routes, and background freshness loop.
- [`src/pipeline.py`](/Users/ss/Documents/Codex/2026-06-08/dddoooouble-datahw-https-github-com-dddoooouble/src/pipeline.py): extract, transform, load, plus offline fallback seeding.
- [`src/db.py`](/Users/ss/Documents/Codex/2026-06-08/dddoooouble-datahw-https-github-com-dddoooouble/src/db.py): schema and repository methods.
- [`src/analytics.py`](/Users/ss/Documents/Codex/2026-06-08/dddoooouble-datahw-https-github-com-dddoooouble/src/analytics.py): summary cards, insight tiles, leaders, history, and correlation payload builders.
- [`static/index.html`](/Users/ss/Documents/Codex/2026-06-08/dddoooouble-datahw-https-github-com-dddoooouble/static/index.html), [`static/app.js`](/Users/ss/Documents/Codex/2026-06-08/dddoooouble-datahw-https-github-com-dddoooouble/static/app.js), [`static/style.css`](/Users/ss/Documents/Codex/2026-06-08/dddoooouble-datahw-https-github-com-dddoooouble/static/style.css): dashboard presentation layer.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:8000`.

## Deploy on Render

1. Push this repository to GitHub.
2. In Render, create a new Web Service from the GitHub repo.
3. Use the included [`render.yaml`](/Users/ss/Documents/Codex/2026-06-08/dddoooouble-datahw-https-github-com-dddoooouble/render.yaml), which sets:
   - Build command: `pip install -r requirements.txt`
   - Start command: `python app.py`
   - Health check: `/health`
4. After deployment, Render will generate a public URL such as `https://your-service-name.onrender.com`.
5. Put that URL into your slides or demo notes for the in-class presentation.

## Demo flow

1. Open the public Render URL.
2. Show the top summary cards and explain the curated crypto basket.
3. Scroll to the insight tiles and pipeline monitor to prove ETL logic and refresh behavior.
4. Click `Refresh Market Data` to demonstrate an on-demand pipeline run.
5. Finish with the benchmark comparison, heatmap, and executive summary.

## Data model

- `pipeline_runs`: pipeline status, timestamps, message, source, and records loaded.
- `asset_snapshots`: latest transformed snapshot for each dashboard asset.
- `daily_prices`: 30-day history rows for the focus assets used in line charts and correlation analysis.

## Notes

- If live API access fails on the first run, the app seeds deterministic sample data so the dashboard still renders.
- If live refresh later fails, the dashboard preserves the last successful dataset instead of overwriting it with degraded data.
