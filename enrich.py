"""FlipRadar detail-page enrichment.

Index pages/APIs give thin data (often no tech stack, verification status, or
real financials). This module fetches each listing's detail page and upgrades
the DB row, then callers rescore.

Sources:
- flippa: public v3 per-listing endpoint https://flippa.com/v3/listings/<id>
  (same politeness rules as the index adapter). Adds verified-revenue/traffic
  flags, sale method, bid/watcher counts, business model, and closes out
  listings that are no longer open (sold=1).
- microns: listing detail HTML at the stored URL. The page renders
  value/label metric pairs ("$35,000 | ARR", "28 | Customers", "2021 |
  Launched") plus an Overview description and an "Already Sold" marker.

Public API:
  enrich_all(limit=40, source=None, force=False) -> dict summary
"""

from __future__ import annotations

import html as html_mod
import json
import logging
import re
from datetime import datetime, timezone

import db
from adapters.flippa import FlippaAdapter
from adapters.microns import MicronsAdapter

log = logging.getLogger("flipradar.enrich")

FLIPPA_DETAIL = "https://flippa.com/v3/listings/{id}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _num(v) -> float | None:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return None


# ---- flippa ---------------------------------------------------------------

def enrich_flippa(listing: dict, adapter: FlippaAdapter) -> dict | None:
    """Return column updates for one flippa listing, or None if unavailable."""
    text = adapter.polite_get(FLIPPA_DETAIL.format(id=listing["source_id"]))
    if text is None:
        return None
    try:
        record = json.loads(text).get("data") or {}
    except json.JSONDecodeError:
        return None
    if not isinstance(record, dict) or not record:
        return None

    mrr = _num(record.get("revenue_per_month"))
    monthly_profit = _num(record.get("profit_per_month")) or _num(record.get("average_profit"))
    updates: dict = {
        "sale_method": record.get("sale_method"),
        "verified_revenue": 1 if record.get("has_verified_revenue") else 0,
        "verified_traffic": 1 if record.get("has_verified_traffic") else 0,
        "watchers": record.get("watching") if isinstance(record.get("watching"), int) else None,
        "bids": record.get("bid_count") if isinstance(record.get("bid_count"), int) else None,
        "sold": 0 if record.get("status") == "open" else 1,
        "raw_json": json.dumps(record, ensure_ascii=False),
    }
    if mrr is not None:
        updates["mrr"] = mrr
        updates["arr"] = mrr * 12
    if monthly_profit is not None:
        updates["annual_profit"] = monthly_profit * 12
    summary = (record.get("summary") or "").strip()
    if summary and len(summary) > len(listing.get("description") or ""):
        updates["description"] = summary
    # business_model / turnkey flag ride along in raw_json for the scorer.
    return updates


# ---- microns --------------------------------------------------------------

_MONEY = r"\$([\d,]+(?:\.\d+)?)\s*(k)?"


def _parse_money(m: re.Match) -> float:
    val = float(m.group(1).replace(",", ""))
    return val * 1000 if m.group(2) else val


def enrich_microns(listing: dict, adapter: MicronsAdapter) -> dict | None:
    page = adapter.polite_get(listing["url"])
    if page is None:
        return None
    # Strip scripts/tags into a pipe-separated token stream (matches how the
    # site lays out value/label metric pairs).
    txt = re.sub(r"<script[\s\S]*?</script>", " ", page)
    txt = re.sub(r"<[^>]+>", "|", txt)
    txt = html_mod.unescape(txt)
    txt = re.sub(r"[|\s]+", " | ", txt)

    updates: dict = {"sold": 1 if re.search(r"Already \| Sold", txt) else 0}

    m = re.search(_MONEY + r" \| Asking \| Price", txt, re.I)
    if m:
        updates["asking_price"] = _parse_money(m)
    m = re.search(_MONEY + r" \| ARR\b", txt, re.I)
    if m:
        arr = _parse_money(m)
        updates["arr"] = arr
        updates["mrr"] = round(arr / 12, 2)
    m = re.search(_MONEY + r" \| MRR\b", txt, re.I)
    if m:
        mrr = _parse_money(m)
        updates["mrr"] = mrr
        updates["arr"] = mrr * 12
    m = re.search(_MONEY + r" \| (?:Monthly \| )?Profit\b", txt, re.I)
    if m:
        updates["annual_profit"] = _parse_money(m) * 12
    m = re.search(r"(\d[\d,]*) \| Customers\b", txt, re.I)
    if m:
        updates["users_count"] = int(m.group(1).replace(",", ""))
    m = re.search(r"(19|20)(\d{2}) \| Launched\b", txt)
    if m:
        year = int(m.group(1) + m.group(2))
        months = (datetime.now(timezone.utc).year - year) * 12
        if 0 <= months <= 600:
            updates["age_months"] = float(months)

    # Overview description: first long prose block after "Startup description".
    m = re.search(r"Startup \| description \| (.{80,1200}?) \| ", txt)
    if m:
        desc = re.sub(r"\s*\|\s*", " ", m.group(1)).strip()
        if len(desc) > len(listing.get("description") or ""):
            updates["description"] = desc
    return updates


# ---- driver ---------------------------------------------------------------

ENRICHERS = {
    "flippa": (FlippaAdapter, enrich_flippa),
    "microns": (MicronsAdapter, enrich_microns),
}


def enrich_all(limit: int = 40, source: str | None = None, force: bool = False) -> dict:
    """Enrich up to `limit` listings, best-scored first. Returns a summary."""
    conn = db.get_conn()
    summary = {"enriched": 0, "sold": 0, "failed": 0, "skipped": 0}
    try:
        where = ["source IN (%s)" % ",".join("?" for _ in ENRICHERS)]
        params: list = list(ENRICHERS)
        if source:
            where = ["source = ?"]
            params = [source]
        if not force:
            where.append("enriched_at IS NULL")
        where.append("COALESCE(sold, 0) = 0")
        rows = conn.execute(
            f"SELECT * FROM listings WHERE {' AND '.join(where)} "
            f"ORDER BY score DESC NULLS LAST LIMIT ?",
            params + [limit],
        ).fetchall()

        adapters: dict = {}
        consecutive_failures: dict = {}
        for row in rows:
            listing = dict(row)
            src = listing["source"]
            if src not in ENRICHERS:
                summary["skipped"] += 1
                continue
            # Rate-limited sources 429 for the rest of the window; stop that
            # source after 3 straight failures (rows stay unenriched for the
            # next run rather than being wasted).
            if consecutive_failures.get(src, 0) >= 3:
                summary["skipped"] += 1
                continue
            cls, fn = ENRICHERS[src]
            if src not in adapters:
                adapters[src] = cls()
            try:
                updates = fn(listing, adapters[src])
            except Exception as exc:  # keep going; one bad page shouldn't stop the run
                log.warning("%s/%s: enrich failed (%s)", src, listing["source_id"], exc)
                updates = None
            if not updates:
                summary["failed"] += 1
                consecutive_failures[src] = consecutive_failures.get(src, 0) + 1
                continue
            consecutive_failures[src] = 0
            updates["enriched_at"] = _now()
            sets = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(
                f"UPDATE listings SET {sets} WHERE id = ?",
                list(updates.values()) + [listing["id"]],
            )
            conn.commit()
            summary["enriched"] += 1
            if updates.get("sold"):
                summary["sold"] += 1
            log.info("%s/%s: enriched%s", src, listing["source_id"],
                     " (SOLD)" if updates.get("sold") else "")
        return summary
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    print(enrich_all(limit=5))
