"""FlipRadar Flask dashboard.

Run via `python cli.py serve` (127.0.0.1:5057) or `python -m web.app`.
"""

from __future__ import annotations

import importlib
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

from flask import Flask, redirect, render_template, request

# Allow running both as package (web.app) and as a script from repo root.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import config
import db

log = logging.getLogger("flipradar.web")

app = Flask(__name__)


def _parse_float(value: str | None) -> float | None:
    if value is None or value.strip() == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _is_revenue_positive(row: dict) -> bool:
    for key in ("mrr", "arr", "annual_profit"):
        val = row.get(key)
        if val is not None and val > 0:
            return True
    return False


def _summary(conn) -> dict:
    total = conn.execute("SELECT COUNT(*) AS n FROM listings").fetchone()["n"]
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(
        timespec="seconds"
    )
    new_24h = conn.execute(
        "SELECT COUNT(*) AS n FROM listings WHERE first_seen >= ?", (cutoff,)
    ).fetchone()["n"]
    top = conn.execute(
        "SELECT MAX(score) AS s FROM listings WHERE score IS NOT NULL"
    ).fetchone()["s"]
    return {"total": total, "new_24h": new_24h, "top_score": top}


@app.route("/")
def index():
    raw_max_price = request.args.get("max_price")
    # Default budget filter unless the field was explicitly cleared.
    if raw_max_price is None:
        max_price = float(config.BUDGET_MAX)
    else:
        max_price = _parse_float(raw_max_price)

    source = (request.args.get("source") or "").strip() or None
    min_score = _parse_float(request.args.get("min_score"))
    revenue_only = request.args.get("revenue_positive") == "1"

    filters: dict = {"exclude_sold": True}
    if max_price is not None:
        filters["max_price"] = max_price
    if source:
        filters["source"] = source
    if min_score is not None:
        filters["min_score"] = min_score

    conn = db.get_conn()
    try:
        rows = db.get_listings(filters=filters, order_by="score DESC", conn=conn)
        if revenue_only:
            rows = [r for r in rows if _is_revenue_positive(r)]
        sources = [
            r["source"]
            for r in conn.execute(
                "SELECT DISTINCT source FROM listings ORDER BY source"
            ).fetchall()
        ]
        summary = _summary(conn)
        pipeline_map = {
            r["listing_id"]: r["status"]
            for r in conn.execute("SELECT listing_id, status FROM pipeline").fetchall()
        }
    finally:
        conn.close()

    return render_template(
        "index.html",
        rows=rows,
        sources=sources,
        summary=summary,
        pipeline_map=pipeline_map,
        f_max_price="" if max_price is None else ("%g" % max_price),
        f_source=source or "",
        f_min_score="" if min_score is None else ("%g" % min_score),
        f_revenue=revenue_only,
    )


def _find_checklist_fn():
    """Locate a checklist generator in the dd package, if one exists."""
    candidates = []
    try:
        dd_pkg = importlib.import_module("dd")
        candidates.append(dd_pkg)
    except ImportError:
        return None
    try:
        candidates.insert(0, importlib.import_module("dd.checklist"))
    except ImportError:
        pass
    for mod in candidates:
        for name in ("checklist", "generate", "generate_checklist"):
            fn = getattr(mod, name, None)
            if callable(fn):
                return fn
    return None


@app.route("/dd/<int:listing_id>")
def dd_checklist(listing_id: int):
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM listings WHERE id = ?", (listing_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return render_template(
            "index.html", dd_error="Listing not found.", **_empty_ctx()
        ), 404

    listing = dict(row)
    fn = _find_checklist_fn()
    if fn is None:
        body = (
            "Due-diligence module not available yet (dd.checklist not found).\n"
            "This feature degrades gracefully; check back once dd/ ships."
        )
    else:
        try:
            result = fn(listing)
            if isinstance(result, (list, tuple)):
                body = "\n".join(f"- {item}" for item in result)
            else:
                body = str(result)
        except Exception as exc:  # degrade gracefully, never 500
            body = f"Checklist generation failed: {exc}"

    return render_template(
        "checklist.html", listing=listing, body=body
    )


def _months_held(acquired_at: str | None) -> float | None:
    """Whole-ish months between acquisition and now; None if unparseable."""
    if not acquired_at:
        return None
    try:
        acquired = datetime.fromisoformat(acquired_at)
    except ValueError:
        return None
    if acquired.tzinfo is None:
        acquired = acquired.replace(tzinfo=timezone.utc)
    days = (datetime.now(timezone.utc) - acquired).days
    return max(days, 0) / 30.44


@app.route("/pipeline")
def pipeline():
    conn = db.get_conn()
    try:
        rows = db.get_pipeline(conn=conn)
    finally:
        conn.close()

    columns = {status: [] for status in db.PIPELINE_STATUSES}
    for row in rows:
        columns.setdefault(row["status"], []).append(row)

    return render_template(
        "pipeline.html",
        columns=columns,
        statuses=db.PIPELINE_STATUSES,
        total=len(rows),
    )


@app.route("/pipeline/set", methods=["POST"])
def pipeline_set():
    try:
        listing_id = int(request.form.get("listing_id", ""))
    except ValueError:
        return "invalid listing_id", 400
    status = (request.form.get("status") or "").strip()
    if status not in db.PIPELINE_STATUSES:
        return "invalid status", 400
    notes = request.form.get("notes")
    if notes is not None and notes.strip() == "":
        notes = None  # blank form field must not clobber existing notes

    try:
        db.set_pipeline_status(listing_id, status, notes=notes)
    except ValueError as exc:
        log.warning("pipeline_set rejected: %s", exc)
        return str(exc), 400

    next_url = request.form.get("next") or "/pipeline"
    if not next_url.startswith("/"):
        next_url = "/pipeline"  # only allow same-site redirects
    return redirect(next_url)


@app.route("/portfolio")
def portfolio():
    assets = db.get_assets()
    total_mrr = 0.0
    total_invested = 0.0
    for a in assets:
        a["months_held"] = _months_held(a.get("acquired_at"))
        if a.get("mrr_current") is not None:
            total_mrr += a["mrr_current"]
        if a.get("purchase_price") is not None:
            total_invested += a["purchase_price"]

    return render_template(
        "portfolio.html",
        assets=assets,
        total_mrr=total_mrr,
        total_invested=total_invested,
    )


def _empty_ctx() -> dict:
    return {
        "rows": [],
        "sources": [],
        "summary": {"total": 0, "new_24h": 0, "top_score": None},
        "pipeline_map": {},
        "f_max_price": "",
        "f_source": "",
        "f_min_score": "",
        "f_revenue": False,
    }


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5057, debug=False)
