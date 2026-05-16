from __future__ import annotations

import json
import math
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from src.db import DashboardRepository

API_BASE = "https://api.coingecko.com/api/v3"
DASHBOARD_ASSETS = [
    "bitcoin",
    "ethereum",
    "tether",
    "binancecoin",
    "ripple",
    "solana",
    "cardano",
    "dogecoin",
    "chainlink",
    "avalanche-2",
    "tron",
    "sui",
]
TRACKED_ASSETS = ["bitcoin", "ethereum", "solana", "dogecoin", "cardano"]


class PipelineService:
    def __init__(self, repository: DashboardRepository) -> None:
        self.repository = repository

    def seed_or_refresh(self) -> dict[str, Any]:
        latest = self.repository.latest_successful_run()
        if latest is None:
            return self.run_pipeline()
        return {"status": "skipped", "message": "Existing data is already available."}

    def refresh_if_stale(self, max_age_minutes: int) -> dict[str, Any]:
        latest = self.repository.latest_successful_run()
        if latest is None:
            return self.run_pipeline()

        finished = datetime.fromisoformat(latest["run_finished_at"])
        if datetime.now(UTC) - finished >= timedelta(minutes=max_age_minutes):
            return self.run_pipeline()
        return {"status": "skipped", "message": "Pipeline data is still fresh."}

    def run_pipeline(self) -> dict[str, Any]:
        started_at = datetime.now(UTC)
        run_id = self.repository.start_run(started_at.isoformat(), "live")
        try:
            try:
                payload = self._fetch_live_payload()
                source = "live"
            except (HTTPError, URLError, TimeoutError, ValueError) as error:
                if self.repository.latest_successful_run() is not None:
                    self.repository.finish_run(
                        run_id,
                        "failed",
                        datetime.now(UTC).isoformat(),
                        f"Live refresh failed: {error}",
                        0,
                    )
                    raise
                payload = self._build_offline_payload()
                source = "sample"

            snapshot_rows, history_rows = self._transform_payload(run_id, payload)
            self.repository.save_run_payload(run_id, snapshot_rows, history_rows)
            self.repository.finish_run(
                run_id,
                "success",
                datetime.now(UTC).isoformat(),
                f"Loaded {len(snapshot_rows)} assets and {len(history_rows)} daily records.",
                len(snapshot_rows) + len(history_rows),
            )
        except Exception as error:  # noqa: BLE001
            latest = self.repository.latest_run()
            if latest is not None and latest["id"] == run_id and latest["status"] == "running":
                self.repository.finish_run(
                    run_id,
                    "failed",
                    datetime.now(UTC).isoformat(),
                    f"Unexpected pipeline error: {error}",
                    0,
                )
            raise

        latest = self.repository.latest_run()
        if latest is None:
            raise RuntimeError("Pipeline run did not persist correctly.")

        if source != "live":
            with self.repository.connect() as connection:
                connection.execute(
                    "UPDATE pipeline_runs SET source = ? WHERE id = ?",
                    (source, run_id),
                )

        return {
            "status": "success",
            "message": latest["message"],
            "run_id": run_id,
            "source": source,
        }

    def _fetch_live_payload(self) -> dict[str, Any]:
        market_data = self._fetch_json(
            "/coins/markets",
            {
                "ids": ",".join(DASHBOARD_ASSETS),
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": str(len(DASHBOARD_ASSETS)),
                "page": "1",
                "sparkline": "false",
                "price_change_percentage": "24h,7d",
            },
        )

        available_assets = {asset["id"] for asset in market_data}
        history_data: dict[str, Any] = {}
        for asset_id in TRACKED_ASSETS:
            if asset_id not in available_assets:
                continue
            try:
                history_data[asset_id] = self._fetch_json(
                    f"/coins/{asset_id}/market_chart",
                    {
                        "vs_currency": "usd",
                        "days": "30",
                        "interval": "daily",
                    },
                )
            except (HTTPError, URLError, TimeoutError, ValueError):
                continue

        return {"markets": market_data, "history": history_data}

    def _fetch_json(self, endpoint: str, params: dict[str, str]) -> Any:
        url = f"{API_BASE}{endpoint}?{urlencode(params)}"
        try:
            response = subprocess.run(
                ["curl", "-L", "--silent", "--show-error", url],
                check=True,
                capture_output=True,
                text=True,
                timeout=20,
            )
            payload = json.loads(response.stdout)
            return self._validate_payload(payload)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError):
            pass

        request = Request(
            url,
            headers={
                "User-Agent": "CryptoPulseDashboard/1.0",
                "Accept": "application/json",
            },
        )
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return self._validate_payload(payload)

    def _validate_payload(self, payload: Any) -> Any:
        if isinstance(payload, dict):
            status = payload.get("status")
            if isinstance(status, dict) and status.get("error_message"):
                raise ValueError(status["error_message"])
            if payload.get("error"):
                raise ValueError(str(payload["error"]))
        return payload

    def _transform_payload(
        self, run_id: int, payload: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        history_metrics: dict[str, dict[str, float | None]] = {}
        history_rows: list[dict[str, Any]] = []

        market_index = {asset["id"]: asset for asset in payload["markets"]}
        for asset_id, history_payload in payload["history"].items():
            if not isinstance(history_payload, dict) or "prices" not in history_payload:
                continue
            asset = market_index[asset_id]
            metrics, rows = self._history_records_for_asset(run_id, asset, history_payload)
            history_metrics[asset_id] = metrics
            history_rows.extend(rows)

        snapshot_rows = []
        updated_at = datetime.now(UTC).isoformat()
        for asset in payload["markets"]:
            metrics = history_metrics.get(asset["id"], {})
            snapshot_rows.append(
                {
                    "run_id": run_id,
                    "asset_id": asset["id"],
                    "symbol": asset["symbol"],
                    "name": asset["name"],
                    "market_cap_rank": asset.get("market_cap_rank"),
                    "current_price": asset.get("current_price"),
                    "market_cap": asset.get("market_cap"),
                    "total_volume": asset.get("total_volume"),
                    "circulating_supply": asset.get("circulating_supply"),
                    "price_change_pct_24h": asset.get("price_change_percentage_24h_in_currency"),
                    "price_change_pct_7d": asset.get("price_change_percentage_7d_in_currency"),
                    "return_pct_30d": metrics.get("return_pct_30d"),
                    "volatility_pct_30d": metrics.get("volatility_pct_30d"),
                    "avg_volume_30d": metrics.get("avg_volume_30d"),
                    "ath": asset.get("ath"),
                    "ath_change_pct": asset.get("ath_change_percentage"),
                    "updated_at": updated_at,
                }
            )

        return snapshot_rows, history_rows

    def _history_records_for_asset(
        self, run_id: int, asset: dict[str, Any], history_payload: dict[str, Any]
    ) -> tuple[dict[str, float | None], list[dict[str, Any]]]:
        price_frame = pd.DataFrame(history_payload["prices"], columns=["timestamp", "price"])
        market_cap_frame = pd.DataFrame(history_payload["market_caps"], columns=["timestamp", "market_cap"])
        volume_frame = pd.DataFrame(history_payload["total_volumes"], columns=["timestamp", "total_volume"])
        frame = price_frame.merge(market_cap_frame, on="timestamp").merge(volume_frame, on="timestamp")
        frame["price_date"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True).dt.strftime("%Y-%m-%d")
        frame["return_pct"] = frame["price"].pct_change() * 100

        history_rows = []
        for row in frame.to_dict(orient="records"):
            history_rows.append(
                {
                    "run_id": run_id,
                    "asset_id": asset["id"],
                    "symbol": asset["symbol"],
                    "name": asset["name"],
                    "price_date": row["price_date"],
                    "price": float(row["price"]),
                    "market_cap": float(row["market_cap"]),
                    "total_volume": float(row["total_volume"]),
                    "return_pct": None if pd.isna(row["return_pct"]) else float(row["return_pct"]),
                }
            )

        start_price = float(frame["price"].iloc[0])
        end_price = float(frame["price"].iloc[-1])
        return_pct_30d = ((end_price / start_price) - 1) * 100
        volatility_pct_30d = float(frame["return_pct"].dropna().std()) if frame["return_pct"].dropna().size else None
        avg_volume_30d = float(frame["total_volume"].mean())
        return (
            {
                "return_pct_30d": return_pct_30d,
                "volatility_pct_30d": volatility_pct_30d,
                "avg_volume_30d": avg_volume_30d,
            },
            history_rows,
        )

    def _build_offline_payload(self) -> dict[str, Any]:
        seeds = [
            {
                "id": "bitcoin",
                "symbol": "btc",
                "name": "Bitcoin",
                "current_price": 103250,
                "market_cap": 2035000000000,
                "market_cap_rank": 1,
                "total_volume": 38400000000,
                "circulating_supply": 19700000,
                "price_change_percentage_24h_in_currency": 1.82,
                "price_change_percentage_7d_in_currency": 5.64,
                "ath": 109114,
                "ath_change_percentage": -5.37,
            },
            {
                "id": "ethereum",
                "symbol": "eth",
                "name": "Ethereum",
                "current_price": 4875,
                "market_cap": 586000000000,
                "market_cap_rank": 2,
                "total_volume": 19200000000,
                "circulating_supply": 120100000,
                "price_change_percentage_24h_in_currency": 2.14,
                "price_change_percentage_7d_in_currency": 6.01,
                "ath": 4891,
                "ath_change_percentage": -0.33,
            },
            {
                "id": "tether",
                "symbol": "usdt",
                "name": "Tether",
                "current_price": 1.0,
                "market_cap": 143000000000,
                "market_cap_rank": 3,
                "total_volume": 76300000000,
                "circulating_supply": 143200000000,
                "price_change_percentage_24h_in_currency": 0.01,
                "price_change_percentage_7d_in_currency": 0.02,
                "ath": 1.32,
                "ath_change_percentage": -24.24,
            },
            {
                "id": "solana",
                "symbol": "sol",
                "name": "Solana",
                "current_price": 244.5,
                "market_cap": 118000000000,
                "market_cap_rank": 4,
                "total_volume": 5200000000,
                "circulating_supply": 482000000,
                "price_change_percentage_24h_in_currency": 4.93,
                "price_change_percentage_7d_in_currency": 14.21,
                "ath": 260.7,
                "ath_change_percentage": -6.21,
            },
            {
                "id": "binancecoin",
                "symbol": "bnb",
                "name": "BNB",
                "current_price": 841.2,
                "market_cap": 121000000000,
                "market_cap_rank": 5,
                "total_volume": 2600000000,
                "circulating_supply": 144000000,
                "price_change_percentage_24h_in_currency": 0.88,
                "price_change_percentage_7d_in_currency": 2.45,
                "ath": 875.0,
                "ath_change_percentage": -3.86,
            },
            {
                "id": "dogecoin",
                "symbol": "doge",
                "name": "Dogecoin",
                "current_price": 0.32,
                "market_cap": 47000000000,
                "market_cap_rank": 6,
                "total_volume": 4100000000,
                "circulating_supply": 147000000000,
                "price_change_percentage_24h_in_currency": -1.45,
                "price_change_percentage_7d_in_currency": 7.62,
                "ath": 0.73,
                "ath_change_percentage": -56.16,
            },
            {
                "id": "ripple",
                "symbol": "xrp",
                "name": "XRP",
                "current_price": 2.58,
                "market_cap": 150000000000,
                "market_cap_rank": 7,
                "total_volume": 3900000000,
                "circulating_supply": 58100000000,
                "price_change_percentage_24h_in_currency": 1.17,
                "price_change_percentage_7d_in_currency": 4.55,
                "ath": 3.4,
                "ath_change_percentage": -24.12,
            },
            {
                "id": "usd-coin",
                "symbol": "usdc",
                "name": "USDC",
                "current_price": 1.0,
                "market_cap": 61000000000,
                "market_cap_rank": 8,
                "total_volume": 10600000000,
                "circulating_supply": 60900000000,
                "price_change_percentage_24h_in_currency": 0.0,
                "price_change_percentage_7d_in_currency": 0.01,
                "ath": 1.17,
                "ath_change_percentage": -14.53,
            },
            {
                "id": "cardano",
                "symbol": "ada",
                "name": "Cardano",
                "current_price": 1.02,
                "market_cap": 36000000000,
                "market_cap_rank": 9,
                "total_volume": 1300000000,
                "circulating_supply": 35300000000,
                "price_change_percentage_24h_in_currency": 3.2,
                "price_change_percentage_7d_in_currency": 8.94,
                "ath": 3.1,
                "ath_change_percentage": -67.1,
            },
            {
                "id": "avalanche-2",
                "symbol": "avax",
                "name": "Avalanche",
                "current_price": 48.7,
                "market_cap": 20100000000,
                "market_cap_rank": 10,
                "total_volume": 880000000,
                "circulating_supply": 412000000,
                "price_change_percentage_24h_in_currency": 2.55,
                "price_change_percentage_7d_in_currency": 6.23,
                "ath": 144.96,
                "ath_change_percentage": -66.4,
            },
            {
                "id": "chainlink",
                "symbol": "link",
                "name": "Chainlink",
                "current_price": 28.4,
                "market_cap": 17900000000,
                "market_cap_rank": 11,
                "total_volume": 940000000,
                "circulating_supply": 631000000,
                "price_change_percentage_24h_in_currency": -0.34,
                "price_change_percentage_7d_in_currency": 5.17,
                "ath": 52.7,
                "ath_change_percentage": -46.11,
            },
            {
                "id": "sui",
                "symbol": "sui",
                "name": "Sui",
                "current_price": 2.34,
                "market_cap": 7200000000,
                "market_cap_rank": 12,
                "total_volume": 580000000,
                "circulating_supply": 3080000000,
                "price_change_percentage_24h_in_currency": 5.41,
                "price_change_percentage_7d_in_currency": 12.2,
                "ath": 2.5,
                "ath_change_percentage": -6.4,
            },
        ]

        history_payload: dict[str, Any] = {}
        today = datetime.now(UTC).date()
        sample_profiles = {
            "bitcoin": {"trend": 0.10, "amplitude": 0.03, "phase": 0.2, "volume_bias": 1.0},
            "ethereum": {"trend": 0.07, "amplitude": 0.05, "phase": 0.8, "volume_bias": 1.15},
            "solana": {"trend": 0.15, "amplitude": 0.08, "phase": 1.4, "volume_bias": 1.35},
            "dogecoin": {"trend": 0.18, "amplitude": 0.11, "phase": 2.1, "volume_bias": 1.55},
            "cardano": {"trend": 0.12, "amplitude": 0.07, "phase": 2.7, "volume_bias": 1.2},
        }
        for asset in seeds:
            if asset["id"] not in TRACKED_ASSETS:
                continue
            profile = sample_profiles[asset["id"]]
            prices = []
            market_caps = []
            total_volumes = []
            for offset in range(30):
                day = today - timedelta(days=29 - offset)
                timestamp = int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp() * 1000)
                slope = (offset - 14.5) / 18
                seasonality = math.sin((offset / 3.1) + profile["phase"]) * profile["amplitude"]
                pullback = math.cos((offset / 5.4) + profile["phase"] / 2) * 0.015
                multiplier = 1 + slope * profile["trend"] + seasonality + pullback
                price = asset["current_price"] * multiplier
                market_cap = asset["market_cap"] * multiplier
                volume = asset["total_volume"] * (
                    0.7
                    + profile["volume_bias"] * 0.16
                    + (math.cos((offset / 4.1) + profile["phase"]) + 1) * 0.12
                )
                prices.append([timestamp, round(price, 6)])
                market_caps.append([timestamp, round(market_cap, 2)])
                total_volumes.append([timestamp, round(volume, 2)])
            history_payload[asset["id"]] = {
                "prices": prices,
                "market_caps": market_caps,
                "total_volumes": total_volumes,
            }

        return {"markets": seeds, "history": history_payload}
