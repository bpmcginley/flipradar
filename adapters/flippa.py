"""Flippa adapter: SaaS listings under $5,000 via Flippa's public v3 JSON API.

What was investigated (2026-08-12) and what worked:

- https://flippa.com/robots.txt allows /search and /v3/ paths (only /users/
  and a few auction action sub-paths are disallowed). It also points at a
  sitemap: http://flippa-filestore-production.s3.amazonaws.com/sitemaps/sitemap.xml.gz
- https://flippa.com/search?filter[property_type]=saas returns HTTP 200, but
  the page is a client-side JS app: the HTML contains NO listing data (only
  FAQ ld+json blocks), so scraping the search page directly is a dead end.
- WORKED: Flippa exposes a public JSON:API endpoint used by that search page:
      https://flippa.com/v3/listings
  It accepts JSON:API style query params, returns 200 with no auth, e.g.:
      /v3/listings?filter[property_type]=saas&filter[status]=open
                  &filter[price][max]=5000&page[size]=50&page[number]=1
  The response has meta.page_number / meta.total_results, links.next for
  pagination, and rich per-listing fields: id, title, summary, html_url,
  display_price, buy_it_now_price, current_price, revenue_per_month,
  profit_per_month, established_at, uniques_per_month, property_type,
  sale_method, status, industry, seller_location, has_verified_revenue, etc.
  Note: filter[price][max] is applied server-side but a few auction rows leak
  through above the cap, so we re-filter client-side.

This adapter therefore fetches from the v3 API (politely: 2s delay, custom
UA, robots.txt check, 12h response cache via BaseAdapter.polite_get). If
Flippa ever locks the endpoint down (403/429/JS challenge), polite_get
returns None and fetch() returns [] with a warning — use --fixtures mode
with fixtures/flippa_sample.json to keep the pipeline testable offline.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from urllib.parse import urlencode

from .base import BaseAdapter

log = logging.getLogger("flipradar.adapters.flippa")

API_BASE = "https://flippa.com/v3/listings"
MAX_PRICE = 5000  # target: SaaS under $5,000
PAGE_SIZE = 50
MAX_PAGES = 10  # safety cap; ~400 matching listings as of Aug 2026


class FlippaAdapter(BaseAdapter):
    name = "flippa"

    def fetch(self) -> list[dict]:
        listings: list[dict] = []
        url = self._search_url(page_number=1)
        for _ in range(MAX_PAGES):
            text = self.polite_get(url)
            if text is None:
                log.warning("flippa: no response for %s; stopping (use --fixtures offline)", url)
                break
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                log.warning("flippa: non-JSON response at %s (blocked or changed API); stopping", url)
                break
            for record in payload.get("data", []):
                item = self._to_listing(record)
                if item is not None:
                    listings.append(item)
            next_url = (payload.get("links") or {}).get("next")
            if not next_url:
                break
            url = next_url
        log.info("flippa: %d listings under $%d", len(listings), MAX_PRICE)
        return listings

    # ---- helpers --------------------------------------------------------

    @staticmethod
    def _search_url(page_number: int) -> str:
        params = {
            "filter[property_type]": "saas",
            "filter[status]": "open",
            "filter[price][max]": str(MAX_PRICE),
            "page[size]": str(PAGE_SIZE),
            "page[number]": str(page_number),
        }
        return f"{API_BASE}?{urlencode(params)}"

    def _to_listing(self, record: dict) -> dict | None:
        source_id = str(record.get("id") or "").strip()
        url = record.get("html_url")
        if not source_id or not url:
            return None

        price = self._first_number(
            record.get("display_price"),
            record.get("buy_it_now_price"),
            record.get("current_price"),
        )
        # Server-side price filter lets some auction rows leak above the cap.
        if price is not None and price > MAX_PRICE:
            return None

        mrr = self._first_number(record.get("revenue_per_month"))
        monthly_profit = self._first_number(
            record.get("profit_per_month"), record.get("average_profit")
        )
        title = (record.get("title") or record.get("property_name") or "").strip()

        return {
            "source": self.name,
            "source_id": source_id,
            "url": url,
            "title": title or "(untitled)",
            "description": (record.get("summary") or "").strip() or None,
            "asking_price": price,
            "mrr": mrr,
            "arr": mrr * 12 if mrr is not None else None,
            "annual_profit": monthly_profit * 12 if monthly_profit is not None else None,
            "tech_stack": None,  # not exposed by the v3 listing index
            "age_months": self._age_months(record.get("established_at")),
            "users_count": self._first_int(record.get("uniques_per_month")),
            "raw_json": json.dumps(record, ensure_ascii=False),
        }

    @staticmethod
    def _first_number(*values) -> float | None:
        for v in values:
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return float(v)
        return None

    @staticmethod
    def _first_int(value) -> int | None:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return int(value)
        return None

    @staticmethod
    def _age_months(established_at: str | None) -> float | None:
        if not established_at:
            return None
        try:
            dt = datetime.fromisoformat(established_at)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta_days = (datetime.now(timezone.utc) - dt).days
        return round(max(delta_days, 0) / 30.44, 1)
