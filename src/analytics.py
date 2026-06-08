from __future__ import annotations

from collections import defaultdict
from typing import Any

import pandas as pd


def _round_or_none(value: Any, digits: int = 2) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), digits)


def _sorted_non_null(frame: pd.DataFrame, column: str, ascending: bool) -> pd.DataFrame:
    return frame[frame[column].notna()].sort_values(column, ascending=ascending)


def build_summary(snapshot_rows: list[dict[str, Any]], run_info: dict[str, Any] | None) -> dict[str, Any]:
    if not snapshot_rows:
        return {
            "title": "Crypto Pulse",
            "cards": [],
            "assets": [],
            "insights": {"tiles": []},
            "last_updated": None,
            "source": None,
        }

    frame = pd.DataFrame(snapshot_rows)
    total_market_cap = float(frame["market_cap"].fillna(0).sum())
    avg_change_24h = float(frame["price_change_pct_24h"].fillna(0).mean())
    avg_return_30d = (
        float(frame["return_pct_30d"].dropna().mean()) if frame["return_pct_30d"].notna().any() else 0.0
    )
    avg_volatility_30d = (
        float(frame["volatility_pct_30d"].dropna().mean()) if frame["volatility_pct_30d"].notna().any() else 0.0
    )
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
        "insights": build_market_intel(snapshot_rows),
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


def build_market_intel(snapshot_rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not snapshot_rows:
        return {"tiles": []}

    frame = pd.DataFrame(snapshot_rows)
    non_stable_frame = frame[~frame["asset_id"].isin(["tether"])]
    total_assets = int(len(frame))
    positive_assets = int((frame["price_change_pct_24h"].fillna(0) > 0).sum())
    negative_assets = int((frame["price_change_pct_24h"].fillna(0) < 0).sum())
    neutral_assets = total_assets - positive_assets - negative_assets
    positive_share_pct = (positive_assets / total_assets) * 100 if total_assets else 0.0

    total_market_cap = float(frame["market_cap"].fillna(0).sum())
    top_three_market_cap = float(frame.sort_values("market_cap", ascending=False)["market_cap"].fillna(0).head(3).sum())
    top_three_share_pct = (top_three_market_cap / total_market_cap) * 100 if total_market_cap else 0.0
    bitcoin_share_pct = 0.0
    bitcoin_rows = frame[frame["asset_id"] == "bitcoin"]
    if total_market_cap and not bitcoin_rows.empty:
        bitcoin_share_pct = float(bitcoin_rows.iloc[0]["market_cap"] or 0) / total_market_cap * 100

    volatility_source = non_stable_frame if not non_stable_frame.empty else frame
    volatility_leaders = _sorted_non_null(volatility_source, "volatility_pct_30d", ascending=False)
    avg_return_30d = float(frame["return_pct_30d"].dropna().mean()) if frame["return_pct_30d"].notna().any() else 0.0

    if avg_return_30d >= 5 and positive_share_pct >= 60:
        regime_label = "Risk-on"
        regime_tone = "positive"
    elif avg_return_30d <= -5 and positive_share_pct <= 45:
        regime_label = "Risk-off"
        regime_tone = "negative"
    else:
        regime_label = "Mixed tape"
        regime_tone = "neutral"

    volatility_label = "Unavailable"
    volatility_detail = "No 30-day volatility reading yet."
    if not volatility_leaders.empty:
        volatility_leader = volatility_leaders.iloc[0]
        volatility_label = f"{volatility_leader['name']} ({volatility_leader['symbol'].upper()})"
        volatility_detail = f"30d daily return stdev {format_percent_number(volatility_leader['volatility_pct_30d'])}."

    return {
        "tiles": [
            {
                "label": "24h Breadth",
                "value": f"{positive_assets} / {total_assets} green",
                "detail": f"{positive_share_pct:.1f}% positive, {negative_assets} red, {neutral_assets} flat.",
                "tone": "positive" if positive_assets >= negative_assets else "negative",
            },
            {
                "label": "Top-3 Concentration",
                "value": format_percent_number(top_three_share_pct),
                "detail": f"BTC alone is {bitcoin_share_pct:.1f}% of basket market cap.",
                "tone": "neutral",
            },
            {
                "label": "Volatility Leader",
                "value": volatility_label,
                "detail": volatility_detail,
                "tone": "neutral",
            },
            {
                "label": "Regime Signal",
                "value": regime_label,
                "detail": f"Basket 30d return {format_signed_number(avg_return_30d)} with {positive_share_pct:.1f}% breadth.",
                "tone": regime_tone,
            },
        ]
    }


def format_percent_number(value: Any) -> str:
    rounded = _round_or_none(value)
    return "-" if rounded is None else f"{rounded:.2f}%"


def format_signed_number(value: Any) -> str:
    rounded = _round_or_none(value)
    if rounded is None:
        return "-"
    prefix = "+" if rounded >= 0 else ""
    return f"{prefix}{rounded:.2f}%"
