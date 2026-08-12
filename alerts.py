"""FlipRadar alerts.

After a scan, any NEW listing (first seen during that scan) scoring at or
above ALERT_THRESHOLD is printed as a highlighted block and appended to
data/alerts.log.

Public API:
  alert_new_high_scores(since=None, conn=None) -> list[dict]
    since: ISO timestamp (UTC) marking the start of the scan; listings with
    first_seen >= since count as new. If None, falls back to listings whose
    first_seen == last_seen (i.e. inserted, never updated).
"""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timezone

ALERT_THRESHOLD = 70.0
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
ALERTS_LOG = os.path.join(REPO_ROOT, "data", "alerts.log")

log = logging.getLogger("flipradar.alerts")

BAR = "=" * 66


def _format_alert(listing: dict) -> str:
    price = listing.get("asking_price")
    mrr = listing.get("mrr")
    lines = [
        BAR,
        f"  *** DEAL ALERT: score {listing.get('score', 0):.0f}/100 ***",
        f"  {listing.get('title') or '(untitled)'}",
        f"  {listing.get('source', '?')} | "
        f"ask {'$%s' % format(price, ',.0f') if price is not None else '?'} | "
        f"mrr {'$%s/mo' % format(mrr, ',.0f') if mrr is not None else '?'}",
        f"  {listing.get('url') or '(no url)'}",
        f"  why: {listing.get('score_reasons') or '-'}",
        BAR,
    ]
    return "\n".join(lines)


def _log_line(listing: dict) -> str:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return (
        f"{ts}\tscore={listing.get('score')}\t"
        f"{listing.get('source')}/{listing.get('source_id')}\t"
        f"{listing.get('title') or '(untitled)'}\t{listing.get('url') or '-'}\t"
        f"{listing.get('score_reasons') or '-'}\n"
    )


def alert_new_high_scores(
    since: str | None = None,
    conn: sqlite3.Connection | None = None,
    log_path: str = ALERTS_LOG,
) -> list[dict]:
    """Print + log alerts for new listings scoring >= ALERT_THRESHOLD.

    Returns the alerted listings.
    """
    import db

    own_conn = conn is None
    if own_conn:
        conn = db.get_conn()
    try:
        if since is not None:
            rows = conn.execute(
                "SELECT * FROM listings WHERE score >= ? AND first_seen >= ? "
                "ORDER BY score DESC",
                (ALERT_THRESHOLD, since),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM listings WHERE score >= ? AND first_seen = last_seen "
                "ORDER BY score DESC",
                (ALERT_THRESHOLD,),
            ).fetchall()
        alerted = [dict(r) for r in rows]
    finally:
        if own_conn:
            conn.close()

    if not alerted:
        return []

    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as fh:
        for listing in alerted:
            print(_format_alert(listing))
            log.info(
                "ALERT %s/%s score=%s",
                listing.get("source"), listing.get("source_id"), listing.get("score"),
            )
            fh.write(_log_line(listing))
    return alerted


if __name__ == "__main__":
    # Smoke test: seed a temp DB with one high and one low scorer, run alerts.
    import tempfile

    import db
    import scoring

    tmpdir = tempfile.mkdtemp(prefix="flipradar_alerts_")
    db_path = os.path.join(tmpdir, "test.db")
    log_path = os.path.join(tmpdir, "alerts.log")

    conn = db.get_conn(db_path)
    db.upsert_listing(
        {
            "source": "test", "source_id": "hi", "url": "http://x/hi",
            "title": "Python SaaS uptime monitor",
            "description": "Profitable side project, no time, moving on.",
            "asking_price": 1500, "mrr": 120, "annual_profit": 1400,
            "tech_stack": "Python, Flask",
        },
        conn=conn,
    )
    db.upsert_listing(
        {
            "source": "test", "source_id": "lo", "url": "http://x/lo",
            "title": "Recipe blog", "description": "A blog.",
        },
        conn=conn,
    )
    scoring.rescore_all(conn=conn)
    hits = alert_new_high_scores(conn=conn, log_path=log_path)
    conn.close()

    assert len(hits) == 1 and hits[0]["source_id"] == "hi", hits
    assert os.path.exists(log_path) and "hi" in open(log_path, encoding="utf-8").read()
    print("alerts smoke test passed")
