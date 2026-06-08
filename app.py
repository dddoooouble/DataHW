from __future__ import annotations

import json
import logging
import mimetypes
import os
import threading
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from src.analytics import build_correlation, build_history, build_leaders, build_summary
from src.db import DashboardRepository
from src.market_feeds import MarketFeedService
from src.pipeline import PipelineService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATABASE_PATH = Path(os.environ.get("DATABASE_PATH", BASE_DIR / "data" / "crypto_pulse.db"))
REFRESH_INTERVAL_MINUTES = int(os.environ.get("REFRESH_INTERVAL_MINUTES", "360"))
PORT = int(os.environ.get("PORT", "8000"))
PIPELINE_MONITOR_LIMIT = 6
VISUAL_ASSET_IDS = {"bitcoin", "ethereum", "ripple", "solana", "cardano", "dogecoin"}
CORRELATION_ASSET_IDS = {"bitcoin", "ethereum", "ripple", "solana", "cardano", "dogecoin"}

repository = DashboardRepository(DATABASE_PATH)
pipeline = PipelineService(repository)
market_feeds = MarketFeedService()


def serialize_run(row: dict[str, object] | None) -> dict[str, object] | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "status": row["status"],
        "source": row["source"],
        "message": row["message"],
        "run_started_at": row["run_started_at"],
        "run_finished_at": row["run_finished_at"],
        "records_loaded": row["records_loaded"],
    }


def pipeline_status_payload() -> dict[str, object]:
    latest = repository.latest_run()
    successful = repository.latest_successful_run()
    recent_runs = [serialize_run(dict(row)) for row in repository.recent_runs(PIPELINE_MONITOR_LIMIT)]
    age_minutes = None
    next_refresh_due_at = None
    freshness = "empty"
    if successful is not None:
        finished_at = datetime.fromisoformat(successful["run_finished_at"])
        age_minutes = round((datetime.now(UTC) - finished_at).total_seconds() / 60, 1)
        next_refresh_due_at = (finished_at + timedelta(minutes=REFRESH_INTERVAL_MINUTES)).isoformat()
        if successful["source"] == "sample":
            freshness = "sample"
        elif age_minutes < REFRESH_INTERVAL_MINUTES / 2:
            freshness = "fresh"
        elif age_minutes < REFRESH_INTERVAL_MINUTES:
            freshness = "aging"
        else:
            freshness = "stale"
    return {
        "last_run_id": None if latest is None else latest["id"],
        "last_status": None if latest is None else latest["status"],
        "last_message": None if latest is None else latest["message"],
        "last_finished_at": None if successful is None else successful["run_finished_at"],
        "source": None if successful is None else successful["source"],
        "records_loaded": None if successful is None else successful["records_loaded"],
        "refresh_interval_minutes": REFRESH_INTERVAL_MINUTES,
        "age_minutes": age_minutes,
        "freshness": freshness,
        "next_refresh_due_at": next_refresh_due_at,
        "recent_runs": recent_runs,
        "server_time": datetime.now(UTC).isoformat(),
    }


def refresh_in_background() -> None:
    while True:
        try:
            pipeline.refresh_if_stale(REFRESH_INTERVAL_MINUTES)
        except Exception as error:  # noqa: BLE001
            logging.exception("Scheduled refresh failed: %s", error)
        threading.Event().wait(60)


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._serve_file(STATIC_DIR / "index.html")
            return
        if parsed.path.startswith("/static/"):
            file_path = STATIC_DIR / parsed.path.removeprefix("/static/")
            self._serve_file(file_path)
            return
        if parsed.path == "/health":
            self._send_json({"status": "ok", "time": datetime.now(UTC).isoformat()})
            return
        if parsed.path == "/api/summary":
            snapshot_rows = [dict(row) for row in repository.latest_snapshot_rows()]
            summary = build_summary(snapshot_rows, repository.latest_successful_run())
            self._send_json(summary)
            return
        if parsed.path == "/api/history":
            history_rows = [
                dict(row)
                for row in repository.latest_history_rows()
                if row["asset_id"] in VISUAL_ASSET_IDS
            ]
            self._send_json(build_history(history_rows))
            return
        if parsed.path == "/api/leaders":
            snapshot_rows = [dict(row) for row in repository.latest_snapshot_rows()]
            self._send_json(build_leaders(snapshot_rows))
            return
        if parsed.path == "/api/correlation":
            history_rows = [
                dict(row)
                for row in repository.latest_history_rows()
                if row["asset_id"] in CORRELATION_ASSET_IDS
            ]
            self._send_json(build_correlation(history_rows))
            return
        if parsed.path == "/api/pipeline/status":
            self._send_json(pipeline_status_payload())
            return
        if parsed.path == "/api/benchmarks":
            self._send_json(market_feeds.load_benchmarks())
            return
        if parsed.path == "/api/news":
            limit = parse_qs(parsed.query).get("limit", ["10"])[0]
            try:
                news_limit = max(1, min(20, int(limit)))
            except ValueError:
                news_limit = 10
            self._send_json(market_feeds.load_news(limit=news_limit))
            return
        if parsed.path == "/api/assets":
            snapshot_rows = [dict(row) for row in repository.latest_snapshot_rows()]
            symbol = parse_qs(parsed.query).get("symbol", [None])[0]
            if symbol:
                filtered = [row for row in snapshot_rows if row["symbol"].lower() == symbol.lower()]
            else:
                filtered = snapshot_rows
            self._send_json({"assets": filtered})
            return
        self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/pipeline/run":
            try:
                result = pipeline.run_pipeline()
                self._send_json(result, HTTPStatus.ACCEPTED)
            except Exception as error:  # noqa: BLE001
                logging.exception("Manual refresh failed: %s", error)
                self._send_json(
                    {"status": "failed", "message": f"Manual refresh failed: {error}"},
                    HTTPStatus.BAD_GATEWAY,
                )
            return
        self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: object) -> None:
        logging.info("%s - %s", self.address_string(), format % args)

    def _serve_file(self, file_path: Path) -> None:
        if not file_path.exists() or not file_path.is_file():
            self._send_json({"error": "File not found"}, HTTPStatus.NOT_FOUND)
            return
        mime_type, _ = mimetypes.guess_type(file_path.name)
        content_type = mime_type or "application/octet-stream"
        payload = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def bootstrap() -> None:
    repository.initialize()
    try:
        pipeline.seed_or_refresh()
    except Exception as error:  # noqa: BLE001
        logging.exception("Startup pipeline failed: %s", error)


def main() -> None:
    bootstrap()
    scheduler = threading.Thread(target=refresh_in_background, daemon=True)
    scheduler.start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), DashboardHandler)
    logging.info("Crypto Pulse server running on port %s", PORT)
    server.serve_forever()


if __name__ == "__main__":
    main()
