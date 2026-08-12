"""Tiny Acquisitions adapter (https://tinyacquisitions.com).

Public startup listings. The site is a Next.js app; when reachable we parse
listing data out of the __NEXT_DATA__ JSON blob first and fall back to HTML
cards. As of 2026-08 the domain does not resolve, so live scans log a warning
and return [] -- use fixtures/tinyacquisitions_sample.json via --fixtures.
"""

from __future__ import annotations

import json
import logging
import re

from bs4 import BeautifulSoup

from .base import BaseAdapter

log = logging.getLogger("flipradar.adapters.tinyacquisitions")

BASE_URL = "https://tinyacquisitions.com"
# Candidate browse pages, tried in order until one returns HTML.
LISTING_PAGES = [BASE_URL + "/browse", BASE_URL + "/listings", BASE_URL + "/"]

_MONEY_RE = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)\s*([kKmM]?)")


def _parse_money(text: str | None) -> float | None:
    """'$1,500' -> 1500.0, '$1.2k' -> 1200.0. None if no dollar amount."""
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


class TinyacquisitionsAdapter(BaseAdapter):
    name = "tinyacquisitions"

    def fetch(self) -> list[dict]:
        html = None
        for page in LISTING_PAGES:
            html = self.polite_get(page)
            if html:
                break
        if not html:
            log.warning(
                "tinyacquisitions: site unreachable or blocked; returning []. "
                "Use 'scan --fixtures' for offline data."
            )
            return []

        listings = self._parse_next_data(html)
        if not listings:
            listings = self._parse_html_cards(html)
        if not listings:
            log.warning("tinyacquisitions: page fetched but no listings parsed")
        return listings

    # ---- parsing --------------------------------------------------------

    def _parse_next_data(self, html: str) -> list[dict]:
        """Pull listing objects out of Next.js __NEXT_DATA__, if present."""
        soup = BeautifulSoup(html, "html.parser")
        tag = soup.find("script", id="__NEXT_DATA__")
        if not tag or not tag.string:
            return []
        try:
            data = json.loads(tag.string)
        except json.JSONDecodeError:
            return []

        found: list[dict] = []

        def walk(node) -> None:
            if isinstance(node, dict):
                keys = {k.lower() for k in node}
                # A listing-shaped object: has a title/name plus a slug or price.
                if ({"title", "name"} & keys) and (
                    {"slug", "askingprice", "asking_price", "price"} & keys
                ):
                    found.append(node)
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)

        walk(data)

        listings = []
        for obj in found:
            get = lambda *names: next(
                (obj[n] for n in names if n in obj and obj[n] not in (None, "")), None
            )
            title = get("title", "name")
            slug = get("slug", "id")
            if not title or slug is None:
                continue
            url = f"{BASE_URL}/listing/{slug}"
            price = get("askingPrice", "asking_price", "price")
            mrr = get("mrr", "monthlyRevenue", "monthly_revenue")
            listings.append(
                {
                    "source": self.name,
                    "source_id": str(slug),
                    "url": url,
                    "title": str(title).strip(),
                    "description": get("description", "tagline", "summary"),
                    "asking_price": float(price) if isinstance(price, (int, float)) else _parse_money(str(price)),
                    "mrr": float(mrr) if isinstance(mrr, (int, float)) else _parse_money(str(mrr) if mrr else None),
                    "arr": None,
                    "annual_profit": None,
                    "tech_stack": get("techStack", "tech_stack", "stack"),
                    "age_months": None,
                    "users_count": None,
                    "raw_json": obj,
                }
            )
        return listings

    def _parse_html_cards(self, html: str) -> list[dict]:
        """Fallback: parse anchor cards linking to /listing/<slug>."""
        soup = BeautifulSoup(html, "html.parser")
        listings = []
        seen: set[str] = set()
        for a in soup.select("a[href*='/listing/']"):
            href = a.get("href", "")
            m = re.search(r"/listing/([^/?#]+)", href)
            if not m:
                continue
            slug = m.group(1)
            if slug in seen:
                continue
            seen.add(slug)

            card_text = a.get_text(" ", strip=True)
            heading = a.find(["h2", "h3", "h4"])
            title = heading.get_text(strip=True) if heading else card_text[:80]
            if not title:
                continue
            para = a.find("p")
            listings.append(
                {
                    "source": self.name,
                    "source_id": slug,
                    "url": BASE_URL + "/listing/" + slug,
                    "title": title,
                    "description": para.get_text(" ", strip=True) if para else None,
                    "asking_price": _parse_money(card_text),
                    "mrr": None,
                    "arr": None,
                    "annual_profit": None,
                    "tech_stack": None,
                    "age_months": None,
                    "users_count": None,
                    "raw_json": {"card_text": card_text, "href": href},
                }
            )
        return listings
