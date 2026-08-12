"""Microns.io adapter.

Scrapes public listing cards from microns.io browse pages (Webflow site,
server-rendered HTML). Cards expose title, slug URL, short description,
category tag, and infoblocks like "Asking Price" / "Annual Revenue" /
"Monthly Revenue". Full financials are gated behind login; we only take
what is public.
"""

from __future__ import annotations

import json
import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from adapters.base import BaseAdapter

log = logging.getLogger("flipradar.adapters.microns")

BASE_URL = "https://www.microns.io"
START_PAGES = [
    "https://www.microns.io/online-businesses/price/under-10k",
    "https://www.microns.io/",  # homepage shows the latest listings
]
MAX_PAGES_PER_START = 3  # first page + up to 2 "next" pages, politely capped

_MONEY_RE = re.compile(r"\$?\s*([\d,]+(?:\.\d+)?)\s*([kKmM]?)")


def _parse_money(text: str | None) -> float | None:
    """'$10,000' -> 10000.0, '$1.2k' -> 1200.0. None if unparseable."""
    if not text:
        return None
    m = _MONEY_RE.search(text)
    if not m:
        return None
    value = float(m.group(1).replace(",", ""))
    suffix = m.group(2).lower()
    if suffix == "k":
        value *= 1_000
    elif suffix == "m":
        value *= 1_000_000
    return value


class MicronsAdapter(BaseAdapter):
    name = "microns"

    def fetch(self) -> list[dict]:
        listings: dict[str, dict] = {}  # source_id -> listing (dedupe across pages)
        for start in START_PAGES:
            url: str | None = start
            for _ in range(MAX_PAGES_PER_START):
                if url is None:
                    break
                html = self.polite_get(url)
                if html is None:
                    log.warning("microns: no HTML for %s (blocked or error)", url)
                    break
                page_listings, next_url = self._parse_page(html, url)
                for item in page_listings:
                    listings.setdefault(item["source_id"], item)
                url = next_url
        if not listings:
            log.warning(
                "microns: 0 listings parsed from live pages; "
                "site may have changed or blocked us. Use --fixtures for offline testing."
            )
        return list(listings.values())

    # ---- parsing --------------------------------------------------------

    def _parse_page(self, html: str, page_url: str) -> tuple[list[dict], str | None]:
        """Return (listings, next_page_url_or_None) for one browse page."""
        soup = BeautifulSoup(html, "html.parser")
        listings = []
        for card in soup.select("div.listing-card"):
            item = self._parse_card(card)
            if item is not None:
                listings.append(item)

        next_url = None
        next_link = soup.select_one("a.w-pagination-next[href]") or next(
            (a for a in soup.select("a[href]") if "_page=" in a["href"]), None
        )
        if next_link is not None:
            next_url = urljoin(page_url, next_link["href"])
            if next_url == page_url:
                next_url = None
        return listings, next_url

    def _parse_card(self, card) -> dict | None:
        link = card.select_one("a[href^='/startup-listings/']")
        if link is None:
            return None
        href = link["href"]
        source_id = href.rstrip("/").rsplit("/", 1)[-1]
        url = urljoin(BASE_URL, href)

        title_el = card.select_one(".listing-card-headings h5")
        title = title_el.get_text(strip=True) if title_el else None
        if not title:
            return None

        desc_el = card.select_one(".listing-card-headings .body-text")
        description = desc_el.get_text(strip=True) if desc_el else None

        tag_el = card.select_one(".tag-mc div:not([class])") or card.select_one(".tag-mc")
        category = tag_el.get_text(" ", strip=True) if tag_el else None

        asking_price = mrr = arr = None
        for block in card.select(".listing-card-infoblock"):
            value_el = block.select_one("h5")
            label_el = block.select_one(".body-text")
            if value_el is None or label_el is None:
                continue
            value = _parse_money(value_el.get_text(strip=True))
            label = label_el.get_text(strip=True).lower()
            if value is None:
                continue
            if "asking" in label or "price" in label:
                asking_price = value
            elif "annual" in label:
                arr = value
            elif "monthly" in label or "mrr" in label:
                mrr = value
        if mrr is None and arr is not None:
            mrr = round(arr / 12.0, 2)
        if arr is None and mrr is not None:
            arr = mrr * 12.0

        return {
            "source": self.name,
            "source_id": source_id,
            "url": url,
            "title": title,
            "description": description,
            "asking_price": asking_price,
            "mrr": mrr,
            "arr": arr,
            "annual_profit": None,  # not shown on public cards
            "tech_stack": None,
            "age_months": None,
            "users_count": None,
            "raw_json": json.dumps({"category": category}) if category else None,
        }
