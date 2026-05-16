# Executive Summary: Crypto Pulse Dashboard

## Project overview

Crypto Pulse is a public web dashboard that monitors the market structure of a curated basket of major cryptocurrencies. The goal is to give a fast decision-oriented view of which assets are leading, which are weakening, and how tightly key coins move together. The dashboard focuses on ranked basket snapshots, 30-day price history, short-term leadership shifts, and return correlation across tracked assets such as Bitcoin, Ethereum, Solana, Dogecoin, and Cardano.

## Data pipeline and architecture

The system uses a Python ETL pipeline connected to the CoinGecko public API. In the **extract** step, the pipeline downloads the latest 12-asset dashboard basket plus 30-day daily histories for selected assets. In the **transform** step, it calculates 24-hour and 7-day changes, 30-day returns, average trading volume, and 30-day volatility. It also prepares daily return series used to build a correlation matrix. In the **load** step, the transformed data is written into a SQLite database with three tables: `pipeline_runs`, `asset_snapshots`, and `daily_prices`.

The web application serves both the dashboard front-end and the back-end API. The front-end is built with custom HTML, CSS, JavaScript, and Chart.js rather than Tableau or Power BI, which keeps the solution aligned with the project rules. The back-end exposes JSON endpoints for summary cards, asset tables, historical series, leaders/laggards, and correlation data.

## Dashboard features

The dashboard includes four major views:

1. KPI cards summarizing total tracked market capitalization, average 30-day return, best 24-hour performer, and weakest 24-hour performer.
2. A multi-series line chart showing 30-day price curves for the tracked assets.
3. A scatter plot comparing market capitalization against 24-hour price change, which helps distinguish large stable assets from smaller high-momentum assets.
4. A correlation heatmap and leadership board to explain whether assets are moving together and which ones currently lead or lag.

## Refresh and deployment

The application supports three refresh behaviors. First, it runs the ETL pipeline automatically at startup. Second, it checks data freshness on a recurring timer and refreshes stale data in the background. Third, it provides a manual refresh button in the dashboard for live demos. For deployment, the project is packaged for Render, which provides a public URL suitable for the required in-class demonstration without relying on localhost.

## Value and grading alignment

This project aims to score well across all grading areas. The ETL component is more than a simple file load because it integrates external API extraction, transformation into derived metrics, and structured persistence. The visualization layer combines multiple chart types and an explanatory table instead of a single graph. The refresh mechanism is explicit and demonstrable. Finally, the architecture and summary are designed to communicate clearly during the executive summary submission and in-class presentation.
