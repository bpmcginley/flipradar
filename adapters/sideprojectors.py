"""SideProjectors adapter (https://www.sideprojectors.com).

Public marketplace of side projects for sale. Project pages live at
/project/<id>/<slug>; robots.txt explicitly allows /project/. As of 2026-08
the whole site (including /rss) sits behind a Cloudflare JS challenge that
returns 403 to plain HTTP clients. Per project policy we do not fight bot
protection: live scans log a warning and return [] -- use
fixtures/sideprojectors_sample.json via --fixtures.
"""

from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

from .base import BaseAdapter

log = logging.getLogger("flipradar.adapters.sideprojectors")

BASE_URL = "https://www.sideprojectors.com"
# Browse/search pages to scan, tried in order; duplicates are de-duped by id.
LISTING_PAGES = [BASE_URL + "/search/project", BASE_URL + "/"]

_MONEY_RE = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)\s*([kKmM]?)")
_PROJECT_HREF_RE = re.compile(r"/project/(\d+)(?:/([^/?#]*))?")


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


class SideprojectorsAdapter(BaseAdapter):
    name = "sideprojectors"

    def fetch(self) -> list[dict]:
        listings: list[dict] = []
        seen: set[str] = set()
        got_any_html = False

        for page in LISTING_PAGES:
            html = self.polite_get(page)
            if not html:
                continue
            got_any_html = True
            for item in self._parse_project_cards(html):
                if item["source_id"] in seen:
                    continue
                seen.add(item["source_id"])
                listings.append(item)

        if not got_any_html:
            log.warning(
                "sideprojectors: blocked (Cloudflare challenge) or unreachable; "
                "returning []. Use 'scan --fixtures' for offline data."
            )
            return []
        if not listings:
            log.warning("sideprojectors: pages fetched but no project cards parsed")
        return listings

    # ---- parsing --------------------------------------------------------

    def _parse_project_cards(self, html: str) -> list[dict]:
        """Parse anchors to /project/<id>/<slug> and their surrounding card."""
        soup = BeautifulSoup(html, "html.parser")
        listings = []
        seen: set[str] = set()

        for a in soup.select("a[href*='/project/']"):
            href = a.get("href", "")
            m = _PROJECT_HREF_RE.search(href)
            if not m:
                continue
            project_id = m.group(1)
            if project_id in seen:
                continue

            # The anchor may wrap the whole card or just the title; climb to
            # the card container to catch price/description, but never past a
            # wrapper that holds other projects' cards too.
            card = a
            for _ in range(3):
                parent = card.parent
                if parent is None or len(parent.select("a[href*='/project/']")) > 1:
                    break
                card = parent
            card_text = card.get_text(" ", strip=True)

            heading = a.find(["h2", "h3", "h4"]) or card.find(["h2", "h3", "h4"])
            title = (heading.get_text(strip=True) if heading
                     else a.get_text(" ", strip=True))
            if not title:
                continue
            seen.add(project_id)

            para = card.find("p")
            listings.append(
                {
                    "source": self.name,
                    "source_id": project_id,
                    "url": BASE_URL + m.group(0),
                    "title": title[:200],
                    "description": para.get_text(" ", strip=True) if para else None,
                    "asking_price": _parse_money(card_text),
                    "mrr": None,
                    "arr": None,
                    "annual_profit": None,
                    "tech_stack": None,
                    "age_months": None,
                    "users_count": None,
                    "raw_json": {"card_text": card_text[:1000], "href": href},
                }
            )
        return listings
