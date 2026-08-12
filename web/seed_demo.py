"""Seed 3 synthetic demo listings into data/deals.db for dashboard testing.

Usage: python web/seed_demo.py  (from repo root)
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db

DEMO_LISTINGS = [
    {
        "source": "demo",
        "source_id": "demo-001",
        "url": "https://example.com/listings/pyform-widgets",
        "title": "PyForm Widgets - embeddable form builder",
        "description": "Small Flask SaaS, embeddable forms, 60 paying users, founder moved on.",
        "asking_price": 1500.0,
        "mrr": 120.0,
        "arr": 1440.0,
        "annual_profit": 1100.0,
        "tech_stack": "Python/Flask, SQLite, vanilla JS",
        "age_months": 26.0,
        "users_count": 60,
        "raw_json": json.dumps({"demo": True}),
        "score": 87.5,
        "score_reasons": "+30 revenue-positive ($120 MRR)\n+25 under budget ($1,500)\n+20 Python stack matches buyer\n+12 neglected but stable (26 months old)\n+0.5 small user base",
    },
    {
        "source": "demo",
        "source_id": "demo-002",
        "url": "https://example.com/listings/rustping",
        "title": "RustPing - uptime monitor CLI + web",
        "description": "Rust-based uptime monitor with 900 free users, no monetization yet.",
        "asking_price": 800.0,
        "mrr": 0.0,
        "arr": 0.0,
        "annual_profit": None,
        "tech_stack": "Rust, Actix, Postgres",
        "age_months": 14.0,
        "users_count": 900,
        "raw_json": json.dumps({"demo": True}),
        "score": 64.0,
        "score_reasons": "+25 user-positive (900 users)\n+25 well under budget ($800)\n+14 Rust stack matches buyer\n-0 no revenue yet",
    },
    {
        "source": "demo",
        "source_id": "demo-003",
        "url": "https://example.com/listings/sheetsync-pro",
        "title": "SheetSync Pro - Google Sheets CRM sync",
        "description": "PHP legacy codebase, $45 MRR, high support load reported by seller.",
        "asking_price": 1950.0,
        "mrr": 45.0,
        "arr": 540.0,
        "annual_profit": 300.0,
        "tech_stack": "PHP/Laravel, MySQL",
        "age_months": 48.0,
        "users_count": 25,
        "raw_json": json.dumps({"demo": True}),
        "score": 41.0,
        "score_reasons": "+20 revenue-positive ($45 MRR)\n+10 within budget ($1,950)\n-10 PHP stack outside buyer languages\n-5 seller reports high support load (>5 hrs/wk risk)",
    },
]


def main() -> None:
    conn = db.get_conn()
    try:
        for listing in DEMO_LISTINGS:
            row_id = db.upsert_listing(listing, conn=conn)
            print(f"upserted id={row_id}: {listing['title']}")
    finally:
        conn.close()
    print(f"done: {len(DEMO_LISTINGS)} demo listings in {db.DB_PATH}")


if __name__ == "__main__":
    main()
