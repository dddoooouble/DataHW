from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd


def _round_or_none(value: Any, digits: int = 2) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), digits)


def build_summary(snapshot_rows: list[dict[str, Any]], run_info: dict[str, Any] | None) -> dict[str, Any]:
    if not snapshot_rows:
        return {
            "title": "Crypto Pulse",
            "cards": [],
            "assets": [],
            "last_updated": None,
            "source": None,
        }

    frame = pd.DataFrame(snapshot_rows)
    total_market_cap = float(frame["market_cap"].fillna(0).sum())
    avg_change_24h = float(frame["price_change_pct_24h"].fillna(0).mean())
    avg_return_30d = float(frame["return_pct_30d"].fillna(0).mean())
    avg_volatility_30d = float(frame["volatility_pct_30d"].dropna().mean()) if frame["volatility_pct_30d"].notna().any() else 0.0
    best_asset = frame.sort_values("price_change_pct_24h", ascending=False).iloc[0]
    weakest_asset = frame.sort_values("price_change_pct_24h", ascending=True).iloc[0]

    cards = [
        {
            "label": "Basket Market Cap",
            "value": total_market_cap,
            "format": "currency_compact",
            "delta": avg_change_24h,
            "delta_label": "avg 24h move",
        },
        {
            "label": "Average 30d Return",
            "value": avg_return_30d,
            "format": "percent",
            "delta": avg_volatility_30d,
            "delta_label": "avg volatility",
        },
        {
            "label": "Best 24h Performer",
            "value": f"{best_asset['name']} ({best_asset['symbol'].upper()})",
            "format": "text",
            "delta": float(best_asset["price_change_pct_24h"]),
            "delta_label": "24h change",
        },
        {
            "label": "Weakest 24h Performer",
            "value": f"{weakest_asset['name']} ({weakest_asset['symbol'].upper()})",
            "format": "text",
            "delta": float(weakest_asset["price_change_pct_24h"]),
            "delta_label": "24h change",
        },
    ]

    asset_rows = []
    for row in frame.sort_values("market_cap_rank").to_dict(orient="records"):
        asset_rows.append(
            {
                "name": row["name"],
                "symbol": row["symbol"].upper(),
                "price": _round_or_none(row["current_price"], 4),
                "market_cap": _round_or_none(row["market_cap"], 2),
                "volume": _round_or_none(row["total_volume"], 2),
                "market_cap_rank": int(row["market_cap_rank"]) if row["market_cap_rank"] is not None else None,
                "change_24h": _round_or_none(row["price_change_pct_24h"]),
                "change_7d": _round_or_none(row["price_change_pct_7d"]),
                "return_30d": _round_or_none(row["return_pct_30d"]),
                "volatility_30d": _round_or_none(row["volatility_pct_30d"]),
            }
        )

    return {
        "title": "Crypto Pulse",
        "subtitle": "A market structure dashboard powered by a refreshable ETL pipeline.",
        "cards": cards,
        "assets": asset_rows,
        "last_updated": run_info["run_finished_at"] if run_info else None,
        "source": run_info["source"] if run_info else None,
    }


def build_history(history_rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not history_rows:
        return {"series": []}

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in history_rows:
        grouped[row["asset_id"]].append(
            {
                "date": row["price_date"],
                "price": _round_or_none(row["price"], 4),
                "return_pct": _round_or_none(row["return_pct"]),
                "symbol": row["symbol"].upper(),
                "name": row["name"],
            }
        )

    series = []
    for asset_id, points in grouped.items():
        label = f"{points[0]['name']} ({points[0]['symbol']})"
        series.append(
            {
                "asset_id": asset_id,
                "label": label,
                "symbol": points[0]["symbol"],
                "points": points,
            }
        )

    return {"series": series}


def build_leaders(snapshot_rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not snapshot_rows:
        return {"gainers": [], "laggards": []}

    frame = pd.DataFrame(snapshot_rows)
    gainers = []
    laggards = []

    for row in frame.sort_values("price_change_pct_24h", ascending=False).head(5).to_dict(orient="records"):
        gainers.append(
            {
                "name": row["name"],
                "symbol": row["symbol"].upper(),
                "change_24h": _round_or_none(row["price_change_pct_24h"]),
                "return_30d": _round_or_none(row["return_pct_30d"]),
                "market_cap": _round_or_none(row["market_cap"], 2),
            }
        )

    for row in frame.sort_values("price_change_pct_24h", ascending=True).head(5).to_dict(orient="records"):
        laggards.append(
            {
                "name": row["name"],
                "symbol": row["symbol"].upper(),
                "change_24h": _round_or_none(row["price_change_pct_24h"]),
                "return_30d": _round_or_none(row["return_pct_30d"]),
                "market_cap": _round_or_none(row["market_cap"], 2),
            }
        )

    return {"gainers": gainers, "laggards": laggards}


def build_correlation(history_rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not history_rows:
        return {"labels": [], "matrix": []}

    frame = pd.DataFrame(history_rows)
    pivot = frame.pivot(index="price_date", columns="symbol", values="return_pct").dropna(how="all")
    correlation = pivot.corr().fillna(0)
    labels = correlation.columns.tolist()
    matrix = []
    for row_label in labels:
        row_values = []
        for col_label in labels:
            row_values.append(_round_or_none(correlation.loc[row_label, col_label], 3))
        matrix.append(row_values)
    return {"labels": labels, "matrix": matrix}
