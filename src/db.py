from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class DashboardRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS pipeline_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_started_at TEXT NOT NULL,
                    run_finished_at TEXT,
                    status TEXT NOT NULL,
                    source TEXT NOT NULL,
                    message TEXT,
                    records_loaded INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS asset_snapshots (
                    run_id INTEGER NOT NULL,
                    asset_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    name TEXT NOT NULL,
                    market_cap_rank INTEGER,
                    current_price REAL,
                    market_cap REAL,
                    total_volume REAL,
                    circulating_supply REAL,
                    price_change_pct_24h REAL,
                    price_change_pct_7d REAL,
                    return_pct_30d REAL,
                    volatility_pct_30d REAL,
                    avg_volume_30d REAL,
                    ath REAL,
                    ath_change_pct REAL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, asset_id),
                    FOREIGN KEY (run_id) REFERENCES pipeline_runs(id)
                );

                CREATE TABLE IF NOT EXISTS daily_prices (
                    run_id INTEGER NOT NULL,
                    asset_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    name TEXT NOT NULL,
                    price_date TEXT NOT NULL,
                    price REAL NOT NULL,
                    market_cap REAL,
                    total_volume REAL,
                    return_pct REAL,
                    PRIMARY KEY (run_id, asset_id, price_date),
                    FOREIGN KEY (run_id) REFERENCES pipeline_runs(id)
                );
                """
            )

    def start_run(self, started_at: str, source: str) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO pipeline_runs (run_started_at, status, source)
                VALUES (?, 'running', ?)
                """,
                (started_at, source),
            )
            return int(cursor.lastrowid)

    def save_run_payload(
        self,
        run_id: int,
        snapshot_rows: list[dict[str, Any]],
        history_rows: list[dict[str, Any]],
    ) -> None:
        with self.connect() as connection:
            connection.executemany(
                """
                INSERT OR REPLACE INTO asset_snapshots (
                    run_id, asset_id, symbol, name, market_cap_rank, current_price,
                    market_cap, total_volume, circulating_supply, price_change_pct_24h,
                    price_change_pct_7d, return_pct_30d, volatility_pct_30d,
                    avg_volume_30d, ath, ath_change_pct, updated_at
                ) VALUES (
                    :run_id, :asset_id, :symbol, :name, :market_cap_rank, :current_price,
                    :market_cap, :total_volume, :circulating_supply, :price_change_pct_24h,
                    :price_change_pct_7d, :return_pct_30d, :volatility_pct_30d,
                    :avg_volume_30d, :ath, :ath_change_pct, :updated_at
                )
                """,
                snapshot_rows,
            )
            connection.executemany(
                """
                INSERT OR REPLACE INTO daily_prices (
                    run_id, asset_id, symbol, name, price_date, price, market_cap,
                    total_volume, return_pct
                ) VALUES (
                    :run_id, :asset_id, :symbol, :name, :price_date, :price,
                    :market_cap, :total_volume, :return_pct
                )
                """,
                history_rows,
            )

    def finish_run(
        self,
        run_id: int,
        status: str,
        finished_at: str,
        message: str,
        records_loaded: int,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE pipeline_runs
                SET status = ?, run_finished_at = ?, message = ?, records_loaded = ?
                WHERE id = ?
                """,
                (status, finished_at, message, records_loaded, run_id),
            )

    def latest_successful_run(self) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute(
                """
                SELECT *
                FROM pipeline_runs
                WHERE status = 'success'
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()

    def latest_run(self) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute(
                """
                SELECT *
                FROM pipeline_runs
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()

    def latest_snapshot_rows(self) -> list[sqlite3.Row]:
        latest = self.latest_successful_run()
        if latest is None:
            return []
        with self.connect() as connection:
            return connection.execute(
                """
                SELECT *
                FROM asset_snapshots
                WHERE run_id = ?
                ORDER BY market_cap_rank ASC, market_cap DESC
                """,
                (latest["id"],),
            ).fetchall()

    def latest_history_rows(self) -> list[sqlite3.Row]:
        latest = self.latest_successful_run()
        if latest is None:
            return []
        with self.connect() as connection:
            return connection.execute(
                """
                SELECT *
                FROM daily_prices
                WHERE run_id = ?
                ORDER BY price_date ASC
                """,
                (latest["id"],),
            ).fetchall()
