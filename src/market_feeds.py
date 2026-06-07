from __future__ import annotations

import html
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

GOOGLE_FINANCE_QUOTES = [
    {
        "id": "nasdaq",
        "name": "Nasdaq Composite",
        "symbol": "IXIC",
        "url": "https://www.google.com/finance/quote/.IXIC:INDEXNASDAQ",
    },
    {
        "id": "dow",
        "name": "Dow Jones Industrial Average",
        "symbol": "DJI",
        "url": "https://www.google.com/finance/quote/.DJI:INDEXDJX",
    },
]
COINDESK_RSS_URL = "https://www.coindesk.com/arc/outboundfeeds/rss/"
COINTELEGRAPH_RSS_URL = "https://cointelegraph.com/rss"
NEWS_FEEDS = [
    {
        "label": "CoinDesk RSS",
        "url": COINDESK_RSS_URL,
        "default_source": "CoinDesk",
    },
    {
        "label": "Cointelegraph RSS",
        "url": COINTELEGRAPH_RSS_URL,
        "default_source": "Cointelegraph",
    },
]


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    without_tags = re.sub(r"<[^>]+>", " ", value)
    unescaped = html.unescape(without_tags)
    return re.sub(r"\s+", " ", unescaped).strip()


class MarketFeedService:
    def __init__(self) -> None:
        self._benchmark_cache: dict[str, Any] | None = None
        self._news_cache: dict[str, Any] | None = None

    def load_benchmarks(self) -> dict[str, Any]:
        try:
            benchmarks = []
            series = []
            fetched_at = datetime.now(UTC).isoformat()

            for quote in GOOGLE_FINANCE_QUOTES:
                html_payload = self._fetch_text(quote["url"])
                summary = self._parse_google_finance_summary(html_payload)
                history_points = self._parse_google_finance_history(html_payload)
                if not history_points:
                    continue

                first_price = history_points[0]["price"]
                last_price = history_points[-1]["price"]
                change_30d = ((last_price / first_price) - 1) * 100 if first_price else 0.0
                range_low = min(point["price"] for point in history_points)
                range_high = max(point["price"] for point in history_points)

                benchmarks.append(
                    {
                        "id": quote["id"],
                        "symbol": quote["symbol"],
                        "name": quote["name"],
                        "price": summary["price"],
                        "change_1d": summary["change_1d"],
                        "change_30d": round(change_30d, 2),
                        "previous_close": summary["previous_close"],
                        "day_low": summary["day_low"],
                        "day_high": summary["day_high"],
                        "range_30d_low": round(range_low, 2),
                        "range_30d_high": round(range_high, 2),
                        "last_trading_date": history_points[-1]["date"],
                    }
                )
                series.append(
                    {
                        "id": quote["id"],
                        "symbol": quote["symbol"],
                        "label": quote["name"],
                        "points": history_points,
                    }
                )

            payload = {
                "benchmarks": benchmarks,
                "series": series,
                "source": "Google Finance public page data",
                "last_updated": fetched_at,
            }
            self._benchmark_cache = payload
            return payload
        except Exception as error:  # noqa: BLE001
            if self._benchmark_cache is not None:
                cached = dict(self._benchmark_cache)
                cached["warning"] = f"Live benchmark refresh failed: {error}"
                return cached
            return {
                "benchmarks": [],
                "series": [],
                "source": "Google Finance public page data",
                "last_updated": datetime.now(UTC).isoformat(),
                "warning": f"Live benchmark refresh failed: {error}",
            }

    def load_news(self, limit: int = 10) -> dict[str, Any]:
        failures: list[str] = []
        try:
            for feed in NEWS_FEEDS:
                try:
                    items = self._fetch_news_from_rss(feed["url"], feed["default_source"], limit)
                except Exception as error:  # noqa: BLE001
                    failures.append(f"{feed['label']}: {error}")
                    continue

                payload = {
                    "items": items,
                    "source": feed["label"],
                    "last_updated": datetime.now(UTC).isoformat(),
                    "is_live": True,
                }
                self._news_cache = payload
                if failures:
                    payload["warning"] = f"Primary source fallback used after: {'; '.join(failures)}"
                return payload

            raise ValueError("; ".join(failures) or "No news feed returned any items")
        except Exception as error:  # noqa: BLE001
            if self._news_cache is not None:
                cached = dict(self._news_cache)
                cached["warning"] = f"Live news refresh failed: {error}"
                cached["is_live"] = False
                return cached
            return {
                "items": [],
                "source": "Crypto RSS feeds",
                "last_updated": datetime.now(UTC).isoformat(),
                "warning": f"Live news refresh failed: {error}",
                "is_live": False,
            }

    def _fetch_news_from_rss(self, url: str, default_source: str, limit: int) -> list[dict[str, Any]]:
        xml_payload = self._fetch_text(url)
        root = ET.fromstring(xml_payload)

        items = []
        for item in root.findall("./channel/item")[:limit]:
            description = _clean_text(item.findtext("description"))
            published_at = item.findtext("pubDate")
            author = item.findtext("{http://purl.org/dc/elements/1.1/}creator")
            media = item.find("{http://search.yahoo.com/mrss/}content")
            image = None if media is None else media.attrib.get("url")

            published_iso = None
            if published_at:
                parsed = parsedate_to_datetime(published_at)
                published_iso = parsed.astimezone(UTC).isoformat()

            items.append(
                {
                    "title": _clean_text(item.findtext("title")),
                    "link": item.findtext("link"),
                    "summary": description,
                    "source": author or default_source,
                    "published_at": published_iso,
                    "image": image,
                }
            )

        if not items:
            raise ValueError(f"No items found in RSS feed: {url}")
        return items

    def _fetch_text(self, url: str) -> str:
        response = subprocess.run(
            [
                "curl",
                "-A",
                "Mozilla/5.0",
                "-L",
                "--silent",
                "--show-error",
                "--retry",
                "2",
                "--retry-delay",
                "1",
                "--retry-all-errors",
                "--max-time",
                "20",
                url,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=25,
        )
        if not response.stdout.strip():
            raise ValueError(f"Empty response from {url}")
        return response.stdout

    def _parse_google_finance_summary(self, html_payload: str) -> dict[str, float]:
        ds7_payload = self._extract_dataset(html_payload, "7")
        entry = ds7_payload[0][0]
        return {
            "open": round(float(entry[2]), 2),
            "day_low": round(float(entry[4]), 2),
            "day_high": round(float(entry[5]), 2),
            "price": round(float(entry[6]), 2),
            "change_abs": round(float(entry[8]), 2),
            "change_1d": round(float(entry[10]), 2),
            "previous_close": round(float(entry[15]), 2),
        }

    def _parse_google_finance_history(self, html_payload: str) -> list[dict[str, float | str]]:
        ds10_payload = self._extract_dataset(html_payload, "10")
        entry = ds10_payload[0][0]
        raw_points = entry[3][0][1]

        deduped_by_date: dict[str, dict[str, float | str]] = {}
        for point in raw_points:
            date_info, price_info = point
            date_key = f"{date_info[0]:04d}-{date_info[1]:02d}-{date_info[2]:02d}"
            deduped_by_date[date_key] = {
                "date": date_key,
                "price": round(float(price_info[0]), 2),
            }

        return [deduped_by_date[key] for key in sorted(deduped_by_date)]

    def _extract_dataset(self, html_payload: str, dataset_key: str) -> Any:
        pattern = re.compile(
            rf'<script class="ds:{dataset_key}"[^>]*>AF_initDataCallback\(\{{key: \'ds:{dataset_key}\'.*?data:(.*?), sideChannel:',
            re.S,
        )
        match = pattern.search(html_payload)
        if match is None:
            raise ValueError(f"Unable to locate Google Finance dataset ds:{dataset_key}")
        return json.loads(match.group(1))
