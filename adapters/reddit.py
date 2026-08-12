"""Reddit adapter: r/SaaSforSale new posts + r/SideProject 'for sale' search.

Uses Reddit's public JSON endpoints (no auth) via BaseAdapter.polite_get,
which handles the custom User-Agent, 2s throttle, robots.txt, and 12h cache.

Reddit's robots.txt currently disallows most crawling for generic agents and
the JSON endpoints often 403 unauthenticated clients. Per project policy we
do not fight this: on any block we log a warning and return whatever parsed
(possibly []); fixtures/reddit_sample.json + --fixtures keeps the pipeline
testable offline.
"""

from __future__ import annotations

import json
import logging
import re

from .base import BaseAdapter

log = logging.getLogger("flipradar.adapters.reddit")

ENDPOINTS = [
    "https://www.reddit.com/r/SaaSforSale/new.json?limit=100",
    "https://www.reddit.com/r/SideProject/search.json?q=%22for%20sale%22&restrict_sr=1&sort=new&limit=100",
]

# A money amount: $1,500 | 1500 | 1.5k | $2k
_AMOUNT = r"\$?\s*(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(k)?"

# MRR mentioned before the number: "MRR $200", "MRR: 1.5k", "MRR is $200", "MRR of 200"
_MRR_BEFORE = re.compile(r"\bmrr\b\s*(?:[:=]|is|of|at|around|about|~)?\s*" + _AMOUNT, re.I)
# MRR mentioned after the number: "$200 MRR", "$1.5k in MRR", "200/mo", "$200 a month"
_MRR_AFTER = re.compile(
    _AMOUNT + r"\s*(?:in\s+|of\s+)?(?:\bmrr\b|/\s*mo(?:nth)?\b|per\s+month\b|a\s+month\b|monthly\b)",
    re.I,
)
# Asking price: "asking $1,500", "price: 2k", "selling (it) for $500", "for sale for 1.5k", "buy it now $900"
_ASKING = re.compile(
    r"(?:\basking(?:\s+price)?\b|\bprice\b|\bselling(?:\s+it)?\s+for\b|\bfor\s+sale\s+(?:for|at)\b"
    r"|\blooking\s+for\b|\bbuy\s+it\s+now\b|\bbin\b|\bobo\b)\s*(?:[:=]|is|of|at)?\s*" + _AMOUNT,
    re.I,
)
# Fallback: any bare dollar amount, e.g. "$1,500" or "$2k"
_ANY_DOLLAR = re.compile(r"\$\s*(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(k)?", re.I)


def _to_number(num: str, k_suffix: str | None) -> float | None:
    try:
        value = float(num.replace(",", ""))
    except ValueError:
        return None
    if k_suffix:
        value *= 1000
    return value


def extract_mrr(text: str) -> float | None:
    """Best-effort MRR extraction from free text."""
    for pattern in (_MRR_BEFORE, _MRR_AFTER):
        m = pattern.search(text)
        if m:
            value = _to_number(m.group(1), m.group(2))
            if value is not None and 0 < value < 1_000_000:
                return value
    return None


def extract_asking_price(text: str, mrr: float | None = None) -> float | None:
    """Best-effort asking-price extraction from free text.

    Prefers amounts near sale keywords; falls back to the first bare dollar
    amount that isn't the MRR figure.
    """
    m = _ASKING.search(text)
    if m:
        value = _to_number(m.group(1), m.group(2))
        if value is not None and 0 < value < 10_000_000:
            return value
    for m in _ANY_DOLLAR.finditer(text):
        value = _to_number(m.group(1), m.group(2))
        if value is None or not 0 < value < 10_000_000:
            continue
        if mrr is not None and value == mrr:
            continue  # skip the MRR mention itself
        return value
    return None


class RedditAdapter(BaseAdapter):
    name = "reddit"

    def fetch(self) -> list[dict]:
        listings: list[dict] = []
        seen: set[str] = set()
        for endpoint in ENDPOINTS:
            body = self.polite_get(endpoint)
            if body is None:
                log.warning("reddit: no response from %s (blocked or robots-disallowed)", endpoint)
                continue
            for post in self._parse_posts(body, endpoint):
                if post["source_id"] not in seen:
                    seen.add(post["source_id"])
                    listings.append(post)
        if not listings:
            log.warning(
                "reddit: 0 live listings; use --fixtures (fixtures/reddit_sample.json) for offline testing"
            )
        return listings

    def _parse_posts(self, body: str, endpoint: str) -> list[dict]:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            log.warning("reddit: non-JSON response from %s", endpoint)
            return []
        children = payload.get("data", {}).get("children", []) if isinstance(payload, dict) else []
        out: list[dict] = []
        for child in children:
            data = child.get("data", {}) if isinstance(child, dict) else {}
            post_id = data.get("id")
            title = data.get("title")
            if not post_id or not title:
                continue
            selftext = (data.get("selftext") or "").strip()
            text = f"{title}\n{selftext}"
            mrr = extract_mrr(text)
            asking = extract_asking_price(text, mrr)
            permalink = data.get("permalink") or ""
            out.append(
                {
                    "source": self.name,
                    "source_id": post_id,
                    "url": f"https://www.reddit.com{permalink}" if permalink else data.get("url"),
                    "title": title,
                    "description": selftext or None,
                    "asking_price": asking,
                    "mrr": mrr,
                    "arr": mrr * 12 if mrr is not None else None,
                    "annual_profit": None,
                    "tech_stack": None,
                    "age_months": None,
                    "users_count": None,
                    "raw_json": {
                        "id": post_id,
                        "subreddit": data.get("subreddit"),
                        "title": title,
                        "selftext": selftext,
                        "permalink": permalink,
                        "created_utc": data.get("created_utc"),
                        "author": data.get("author"),
                        "url": data.get("url"),
                        "num_comments": data.get("num_comments"),
                        "score": data.get("score"),
                    },
                }
            )
        return out
