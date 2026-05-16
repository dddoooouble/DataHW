from __future__ import annotations

import json
import logging
import mimetypes
import os
import threading
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from src.analytics import build_correlation, build_history, build_leaders, build_summary
from src.db import DashboardRepository
from src.pipeline import PipelineService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATABASE_PATH = Path(os.environ.get("DATABASE_PATH", BASE_DIR / "data" / "crypto_pulse.db"))
REFRESH_INTERVAL_MINUTES = int(os.environ.get("REFRESH_INTERVAL_MINUTES", "360"))
PORT = int(os.environ.get("PORT", "8000"))

repository = DashboardRepository(DATABASE_PATH)
pipeline = PipelineService(repository)


def pipeline_status_payload() -> dict[str, str | int | None]:
    latest = repository.latest_run()
    successful = repository.latest_successful_run()
    return {
        "last_run_id": None if latest is None else latest["id"],
        "last_status": None if latest is None else latest["status"],
        "last_message": None if latest is None else latest["message"],
        "last_finished_at": None if successful is None else successful["run_finished_at"],
        "source": None if successful is None else successful["source"],
        "refresh_interval_minutes": REFRESH_INTERVAL_MINUTES,
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
            history_rows = [dict(row) for row in repository.latest_history_rows()]
            self._send_json(build_history(history_rows))
            return
        if parsed.path == "/api/leaders":
            snapshot_rows = [dict(row) for row in repository.latest_snapshot_rows()]
            self._send_json(build_leaders(snapshot_rows))
            return
        if parsed.path == "/api/correlation":
            history_rows = [dict(row) for row in repository.latest_history_rows()]
            self._send_json(build_correlation(history_rows))
            return
        if parsed.path == "/api/pipeline/status":
            self._send_json(pipeline_status_payload())
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

    def _send_json(self, payload: dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
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
