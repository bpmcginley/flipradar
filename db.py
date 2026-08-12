"""FlipRadar SQLite layer.

Creates data/deals.db on first use and exposes upsert/query helpers.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(REPO_ROOT, "data")
DB_PATH = os.path.join(DATA_DIR, "deals.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    url TEXT,
    title TEXT,
    description TEXT,
    asking_price REAL,
    mrr REAL,
    arr REAL,
    annual_profit REAL,
    tech_stack TEXT,
    age_months REAL,
    users_count INTEGER,
    first_seen TEXT,
    last_seen TEXT,
    raw_json TEXT,
    score REAL,
    score_reasons TEXT,
    UNIQUE(source, source_id)
);

CREATE TABLE IF NOT EXISTS pipeline (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER UNIQUE REFERENCES listings(id),
    status TEXT CHECK(status IN ('watch','contacted','dd','offer','owned','passed')),
    notes TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER REFERENCES listings(id),
    name TEXT,
    acquired_at TEXT,
    purchase_price REAL,
    hours_invested REAL DEFAULT 0,
    mrr_at_purchase REAL,
    mrr_current REAL,
    repo_path TEXT,
    notes TEXT
);
"""

PIPELINE_STATUSES = ("watch", "contacted", "dd", "offer", "owned", "passed")

# Columns an asset dict may supply.
ASSET_FIELDS = [
    "listing_id",
    "name",
    "acquired_at",
    "purchase_price",
    "hours_invested",
    "mrr_at_purchase",
    "mrr_current",
    "repo_path",
    "notes",
]

# Columns an adapter dict may supply (besides source/source_id).
LISTING_FIELDS = [
    "url",
    "title",
    "description",
    "asking_price",
    "mrr",
    "arr",
    "annual_profit",
    "tech_stack",
    "age_months",
    "users_count",
    "raw_json",
    "score",
    "score_reasons",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# Columns added after the initial schema; applied idempotently on connect.
MIGRATION_COLUMNS = [
    ("enriched_at", "TEXT"),        # when detail-page enrichment last ran
    ("sale_method", "TEXT"),        # auction / classified (flippa)
    ("verified_revenue", "INTEGER"),  # platform-verified revenue flag (0/1)
    ("verified_traffic", "INTEGER"),
    ("watchers", "INTEGER"),
    ("bids", "INTEGER"),
    ("sold", "INTEGER"),            # 1 = no longer available
]


def get_conn(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Open a connection, creating the data dir and schema if needed."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(listings)")}
    for col, typ in MIGRATION_COLUMNS:
        if col not in existing:
            conn.execute(f"ALTER TABLE listings ADD COLUMN {col} {typ}")
    conn.commit()
    return conn


def upsert_listing(listing: dict, conn: sqlite3.Connection | None = None) -> int:
    """Insert or update a listing keyed on (source, source_id).

    Returns the row id. first_seen is preserved on update; last_seen refreshed.
    """
    if "source" not in listing or "source_id" not in listing:
        raise ValueError("listing requires 'source' and 'source_id'")

    own_conn = conn is None
    if own_conn:
        conn = get_conn()
    try:
        now = _now()
        raw = listing.get("raw_json")
        if raw is not None and not isinstance(raw, str):
            raw = json.dumps(raw, default=str)

        values = {f: listing.get(f) for f in LISTING_FIELDS}
        values["raw_json"] = raw
        values["source"] = str(listing["source"])
        values["source_id"] = str(listing["source_id"])
        values["first_seen"] = now
        values["last_seen"] = now

        cols = ", ".join(values.keys())
        placeholders = ", ".join(":" + k for k in values)
        # Never clobber an existing score with NULL from an adapter re-scan;
        # scores are owned by scoring.rescore_all().
        update_cols = [f for f in LISTING_FIELDS if f not in ("score", "score_reasons")]
        update_cols.append("last_seen")
        update_clause = ", ".join(f"{c}=excluded.{c}" for c in update_cols)

        cur = conn.execute(
            f"INSERT INTO listings ({cols}) VALUES ({placeholders}) "
            f"ON CONFLICT(source, source_id) DO UPDATE SET {update_clause}",
            values,
        )
        conn.commit()
        if cur.lastrowid:
            return cur.lastrowid
        row = conn.execute(
            "SELECT id FROM listings WHERE source=? AND source_id=?",
            (values["source"], values["source_id"]),
        ).fetchone()
        return row["id"]
    finally:
        if own_conn:
            conn.close()


def get_listings(
    filters: dict | None = None,
    order_by: str = "score DESC",
    limit: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[dict]:
    """Fetch listings as dicts.

    filters supports:
      source, max_price, min_mrr, min_score, min_users (numeric comparisons),
      plus any exact-match on a real column name.
    order_by is validated against a small whitelist.
    """
    allowed_order = {
        "score DESC", "score ASC",
        "asking_price ASC", "asking_price DESC",
        "mrr DESC", "last_seen DESC", "first_seen DESC", "id ASC",
    }
    if order_by not in allowed_order:
        order_by = "score DESC"

    where = []
    params: list = []
    f = dict(filters or {})

    special = {
        "max_price": ("asking_price <= ?", None),
        "min_mrr": ("mrr >= ?", None),
        "min_score": ("score >= ?", None),
        "min_users": ("users_count >= ?", None),
    }
    for key, (clause, _) in special.items():
        if key in f and f[key] is not None:
            where.append(clause)
            params.append(f.pop(key))

    if f.pop("exclude_sold", None):
        where.append("COALESCE(sold, 0) = 0")

    valid_cols = {"source", "source_id", "url", "title", "tech_stack"} | set(LISTING_FIELDS)
    for key, val in f.items():
        if key in valid_cols and val is not None:
            where.append(f"{key} = ?")
            params.append(val)

    sql = "SELECT * FROM listings"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += f" ORDER BY {order_by} NULLS LAST" if "score" in order_by else f" ORDER BY {order_by}"
    if limit:
        sql += " LIMIT ?"
        params.append(int(limit))

    own_conn = conn is None
    if own_conn:
        conn = get_conn()
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        if own_conn:
            conn.close()


def set_pipeline_status(
    listing_id: int,
    status: str,
    notes: str | None = None,
    conn: sqlite3.Connection | None = None,
    db_path: str | None = None,
) -> int:
    """Set (or update) the pipeline status for a listing. One row per listing.

    Passing notes=None preserves any existing notes. Returns the pipeline row id.
    """
    if status not in PIPELINE_STATUSES:
        raise ValueError(f"status must be one of {PIPELINE_STATUSES}, got {status!r}")

    own_conn = conn is None
    if own_conn:
        conn = get_conn(db_path or DB_PATH)
    try:
        row = conn.execute(
            "SELECT id FROM listings WHERE id = ?", (listing_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"no listing with id {listing_id}")
        conn.execute(
            "INSERT INTO pipeline (listing_id, status, notes, updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(listing_id) DO UPDATE SET "
            "status=excluded.status, "
            "notes=COALESCE(excluded.notes, pipeline.notes), "
            "updated_at=excluded.updated_at",
            (listing_id, status, notes, _now()),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id FROM pipeline WHERE listing_id = ?", (listing_id,)
        ).fetchone()
        return row["id"]
    finally:
        if own_conn:
            conn.close()


def get_pipeline(
    status: str | None = None,
    conn: sqlite3.Connection | None = None,
    db_path: str | None = None,
) -> list[dict]:
    """Fetch pipeline rows joined with their listings, newest update first."""
    sql = (
        "SELECT p.id AS pipeline_id, p.listing_id, p.status, p.notes, p.updated_at, "
        "l.title, l.url, l.source, l.asking_price, l.mrr, l.score "
        "FROM pipeline p JOIN listings l ON l.id = p.listing_id"
    )
    params: list = []
    if status is not None:
        sql += " WHERE p.status = ?"
        params.append(status)
    sql += " ORDER BY p.updated_at DESC"

    own_conn = conn is None
    if own_conn:
        conn = get_conn(db_path or DB_PATH)
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        if own_conn:
            conn.close()


def add_asset(
    asset: dict,
    conn: sqlite3.Connection | None = None,
    db_path: str | None = None,
) -> int:
    """Insert a portfolio asset. acquired_at defaults to now. Returns row id."""
    if not asset.get("name"):
        raise ValueError("asset requires 'name'")

    values = {f: asset.get(f) for f in ASSET_FIELDS}
    if values["acquired_at"] is None:
        values["acquired_at"] = _now()
    if values["hours_invested"] is None:
        values["hours_invested"] = 0

    own_conn = conn is None
    if own_conn:
        conn = get_conn(db_path or DB_PATH)
    try:
        cols = ", ".join(values.keys())
        placeholders = ", ".join(":" + k for k in values)
        cur = conn.execute(
            f"INSERT INTO assets ({cols}) VALUES ({placeholders})", values
        )
        conn.commit()
        return cur.lastrowid
    finally:
        if own_conn:
            conn.close()


def update_asset(
    asset_id: int,
    updates: dict,
    conn: sqlite3.Connection | None = None,
    db_path: str | None = None,
) -> None:
    """Update the given ASSET_FIELDS keys on one asset; other keys are ignored."""
    fields = {k: v for k, v in updates.items() if k in ASSET_FIELDS and v is not None}
    if not fields:
        return

    own_conn = conn is None
    if own_conn:
        conn = get_conn(db_path or DB_PATH)
    try:
        row = conn.execute("SELECT id FROM assets WHERE id = ?", (asset_id,)).fetchone()
        if row is None:
            raise ValueError(f"no asset with id {asset_id}")
        set_clause = ", ".join(f"{k} = :{k}" for k in fields)
        fields["asset_id"] = asset_id
        conn.execute(f"UPDATE assets SET {set_clause} WHERE id = :asset_id", fields)
        conn.commit()
    finally:
        if own_conn:
            conn.close()


def get_assets(
    conn: sqlite3.Connection | None = None,
    db_path: str | None = None,
) -> list[dict]:
    """Fetch all portfolio assets, oldest acquisition first."""
    own_conn = conn is None
    if own_conn:
        conn = get_conn(db_path or DB_PATH)
    try:
        rows = conn.execute("SELECT * FROM assets ORDER BY acquired_at ASC").fetchall()
        return [dict(r) for r in rows]
    finally:
        if own_conn:
            conn.close()


if __name__ == "__main__":
    c = get_conn()
    n = c.execute("SELECT COUNT(*) AS n FROM listings").fetchone()["n"]
    c.close()
    print(f"OK: {DB_PATH} ready ({n} listings)")
