"""FlipRadar scoring engine.

Scores each listing 0-100 for a specific buyer profile:
  - budget under $2000 asking price
  - strong Python / C# / JS / TS / Rust developer
  - wants revenue-positive or user-positive neglected products
  - under 5 hrs/wk to operate

Factors (see score_listing):
  affordability, value multiple vs market averages, revenue-positive bonus,
  users-but-no-revenue bonus, tech-stack match, abandonment signals,
  red-flag penalties (hype with no revenue, crypto/gambling niches).

Public API:
  score_listing(listing) -> (score: float, reasons: str)
  rescore_all(conn=None) -> int   # number of listings rescored
"""

from __future__ import annotations

import re
import sqlite3

import config

BUDGET_MAX = getattr(config, "BUDGET_MAX", 2000)

# Multiples context: sub-$100k deals average ~1.7x annual profit; typical
# resale range is 2.5-4x. Anything under 2x is flagged underpriced.
MARKET_AVG_MULTIPLE = 1.7
UNDERPRICED_MULTIPLE = 2.0
RESALE_LOW, RESALE_HIGH = 2.5, 4.0

TECH_MATCH_PATTERNS = [
    (re.compile(r"\bpython\b|\bdjango\b|\bflask\b|\bfastapi\b", re.I), "Python"),
    (re.compile(r"\bjavascript\b|\bjs\b|\bnode(?:\.?js)?\b|\breact\b|\bvue\b|\bnext(?:\.?js)?\b", re.I), "JS"),
    (re.compile(r"\btypescript\b|\bts\b", re.I), "TS"),
    (re.compile(r"c#|\bcsharp\b|\.net\b|\bdotnet\b|\bblazor\b", re.I), "C#"),
    (re.compile(r"\brust\b", re.I), "Rust"),
]

ABANDONMENT_PATTERNS = [
    (re.compile(r"no time|don'?t have (?:the )?time|lack of time", re.I), "'no time'"),
    (re.compile(r"moving on|moved on", re.I), "'moving on'"),
    (re.compile(r"side.?project", re.I), "'side project'"),
    (re.compile(r"other projects|new job|focus(?:ing)? on other", re.I), "focus elsewhere"),
    (re.compile(r"abandon|neglect|haven'?t touched|no longer maintain", re.I), "neglected"),
    (re.compile(r"lost interest", re.I), "lost interest"),
]

HYPE_PATTERNS = [
    (re.compile(r"\btrending\b", re.I), "'trending'"),
    (re.compile(r"huge potential|massive potential|unlimited potential", re.I), "'huge potential'"),
]

# Language typical of resold clone scripts and manufactured "businesses"
# (CodeCanyon re-skins, autopilot hype, revenue gated behind NDAs/videos).
CLONE_SCRIPT_PATTERNS = [
    (re.compile(r"same foundation as|clone (?:of|script)|ready.?made|turn.?key", re.I), "clone/turnkey language"),
    (re.compile(r"codecanyon|envato|nulled", re.I), "stock-script marketplace mention"),
    (re.compile(r"newbie friendly|beginner friendly|no experience (?:needed|required)", re.I), "'newbie friendly'"),
    (re.compile(r"sign (?:an? )?nda|watch (?:the )?(?:demo|marketing|strategy) video", re.I), "NDA/video-gated claims"),
    (re.compile(r"fully automated|auto.?pilot|passive income", re.I), "'autopilot/passive income'"),
]

CHURN_PATTERN = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%\s*(?:overall\s+|monthly\s+)?churn", re.I)

RISKY_NICHE_PATTERN = re.compile(
    r"\bcrypto(?:currency)?\b|\bnft\b|\btoken\b|\bweb3\b|\bdefi\b|"
    r"\bgambling\b|\bcasino\b|\bbetting\b|\bsportsbook\b|\bpoker\b|"
    r"prop.?trading|prop.?firm|funded.?trader|\bforex\b|binary options",
    re.I,
)


def _num(val) -> float | None:
    """Coerce to float if possible, treating non-positive placeholders as-is."""
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def score_listing(listing: dict) -> tuple[float, str]:
    """Score one listing dict (adapter/DB shape) for the buyer profile.

    Returns (score 0-100, human-readable reasons joined by '; ').
    """
    if listing.get("sold"):
        return 0.0, "no longer available (sold/closed)"

    reasons: list[str] = []
    score = 0.0

    price = _num(listing.get("asking_price"))
    mrr = _num(listing.get("mrr"))
    arr = _num(listing.get("arr"))
    annual_profit = _num(listing.get("annual_profit"))
    users = _num(listing.get("users_count"))

    text = " ".join(
        str(listing.get(k) or "") for k in ("title", "description")
    )
    tech_text = " ".join(
        str(listing.get(k) or "") for k in ("tech_stack", "title", "description")
    )

    has_revenue = any(v is not None and v > 0 for v in (mrr, arr, annual_profit))

    # --- Affordability (up to +25, heavy scaled penalty over budget) ---
    if price is None:
        score += 5
        reasons.append("price unknown (+5)")
    elif price <= BUDGET_MAX:
        score += 25
        reasons.append(f"within ${BUDGET_MAX:,.0f} budget (+25)")
    else:
        over = price / BUDGET_MAX  # 1.0 at budget
        pts = max(-35.0, 25.0 - 30.0 * (over - 1.0))
        score += pts
        reasons.append(
            f"over budget: ${price:,.0f} is {over:.1f}x the ${BUDGET_MAX:,.0f} cap ({pts:+.0f})"
        )

    # --- Value multiple vs annual profit (up to +25) ---
    if price is not None and annual_profit is not None and annual_profit > 0:
        multiple = price / annual_profit
        if price <= 100:
            pts = 0
            reasons.append(
                f"price ${price:,.0f} looks like an auction starting bid; profit multiple not meaningful (+0)"
            )
        elif multiple < 0.5:
            pts = -25
            reasons.append(
                f"implausibly cheap: {multiple:.2f}x annual profit — real businesses don't sell under 0.5x; "
                f"classic fake-revenue pattern ({pts})"
            )
        elif multiple < 1.0:
            pts = 15
            reasons.append(
                f"very cheap: {multiple:.1f}x annual profit — plausible only for distressed sales, verify revenue hard (+{pts})"
            )
        elif multiple < MARKET_AVG_MULTIPLE:
            pts = 22
            reasons.append(
                f"underpriced: {multiple:.1f}x profit vs ~{MARKET_AVG_MULTIPLE}x sub-$100k average (+{pts})"
            )
        elif multiple < UNDERPRICED_MULTIPLE:
            pts = 18
            reasons.append(
                f"underpriced: {multiple:.1f}x profit, below the {UNDERPRICED_MULTIPLE}x line (+{pts})"
            )
        elif multiple <= RESALE_LOW:
            pts = 12
            reasons.append(f"fair value: {multiple:.1f}x profit (+{pts})")
        elif multiple <= RESALE_HIGH:
            pts = 6
            reasons.append(
                f"priced in {RESALE_LOW}-{RESALE_HIGH}x resale range: {multiple:.1f}x (+{pts})"
            )
        else:
            pts = -5
            reasons.append(f"expensive: {multiple:.1f}x profit, above resale range ({pts})")
        score += pts

    # --- Revenue-positive bonus (+15) / users-but-no-revenue (+8) ---
    if has_revenue:
        score += 15
        bits = []
        if mrr:
            bits.append(f"${mrr:,.0f} MRR")
        if arr and not mrr:
            bits.append(f"${arr:,.0f} ARR")
        if annual_profit:
            bits.append(f"${annual_profit:,.0f}/yr profit")
        reasons.append(f"revenue-positive: {', '.join(bits) or 'yes'} (+15)")
    elif users is not None and users > 0:
        score += 8
        reasons.append(f"{users:,.0f} users but no revenue: monetization upside (+8)")

    # --- Tech-stack match (up to +12) ---
    matches = [label for pat, label in TECH_MATCH_PATTERNS if pat.search(tech_text)]
    if matches:
        pts = min(12, 6 + 3 * (len(matches) - 1))
        score += pts
        reasons.append(f"tech match ({'/'.join(matches)}) (+{pts})")

    # --- Abandonment / neglect signals (up to +10) ---
    signals = [label for pat, label in ABANDONMENT_PATTERNS if pat.search(text)]
    if signals:
        pts = min(10, 5 * len(signals))
        score += pts
        reasons.append(f"seller neglect signals: {', '.join(signals[:3])} (+{pts})")

    # --- Red flags ---
    hype = [label for pat, label in HYPE_PATTERNS if pat.search(text)]
    if hype and not has_revenue:
        pts = -min(15, 10 * len(hype))
        score += pts
        reasons.append(f"hype with no revenue: {', '.join(hype)} ({pts})")

    # --- Enrichment signals (platform verification, turnkey flag) ---
    verified = listing.get("verified_revenue")
    if has_revenue and verified is not None:
        if verified:
            score += 8
            reasons.append("platform-verified revenue (+8)")
        else:
            score -= 8
            reasons.append("revenue claimed but NOT platform-verified (-8)")

    raw = listing.get("raw_json") or ""
    if '"turnkey_listing": true' in raw or '"turnkey_listing":true' in raw:
        score -= 15
        reasons.append("platform-flagged turnkey listing (-15)")

    clone_hits = [label for pat, label in CLONE_SCRIPT_PATTERNS if pat.search(text)]
    if clone_hits:
        pts = -min(30, 12 * len(clone_hits))
        score += pts
        reasons.append(f"clone-script/scam language: {', '.join(clone_hits[:3])} ({pts})")

    churn_m = CHURN_PATTERN.search(text)
    if churn_m:
        churn = float(churn_m.group(1))
        if churn >= 15:
            score -= 15
            reasons.append(f"disclosed churn {churn:.0f}% — retention is broken (-15)")

    if RISKY_NICHE_PATTERN.search(text):
        score -= 20
        reasons.append("crypto/gambling niche (-20)")

    score = max(0.0, min(100.0, score))
    return round(score, 1), "; ".join(reasons)


def rescore_all(conn: sqlite3.Connection | None = None) -> int:
    """Recompute score + score_reasons for every listing in the DB."""
    import db

    own_conn = conn is None
    if own_conn:
        conn = db.get_conn()
    try:
        rows = conn.execute("SELECT * FROM listings").fetchall()
        n = 0
        for row in rows:
            listing = dict(row)
            score, reasons = score_listing(listing)
            conn.execute(
                "UPDATE listings SET score = ?, score_reasons = ? WHERE id = ?",
                (score, reasons, listing["id"]),
            )
            n += 1
        conn.commit()
        return n
    finally:
        if own_conn:
            conn.close()


if __name__ == "__main__":
    # Unit test: 5 synthetic listings covering the main scoring paths.
    tests = [
        (
            "dream deal: cheap, profitable, python, neglected",
            {
                "title": "Python SaaS uptime monitor",
                "description": "Profitable side project, I have no time and am moving on.",
                "asking_price": 1500,
                "mrr": 120,
                "annual_profit": 1400,
                "tech_stack": "Python, Flask",
            },
        ),
        (
            "over budget, fairly priced, no stack match",
            {
                "title": "Shopify analytics app",
                "description": "Steady revenue, well maintained.",
                "asking_price": 6000,
                "annual_profit": 2000,
                "tech_stack": "Ruby on Rails",
            },
        ),
        (
            "users but no revenue, JS stack",
            {
                "title": "React habit tracker",
                "description": "Free app, 4000 signed-up users. Built as a side project.",
                "asking_price": 900,
                "users_count": 4000,
                "tech_stack": "JavaScript, React, Node",
            },
        ),
        (
            "red flags: hype, no revenue, crypto",
            {
                "title": "Trending crypto portfolio tracker",
                "description": "Huge potential! NFT and token support coming.",
                "asking_price": 1800,
                "tech_stack": "TypeScript",
            },
        ),
        (
            "no price, no revenue, no signals",
            {
                "title": "Recipe blog",
                "description": "A blog about recipes.",
            },
        ),
        (
            "scam pattern: clone script, impossible multiple, high churn",
            {
                "title": "Turnkey marketplace built on the same foundation as Fiverr",
                "description": "Newbie friendly, fully automated passive income. 35% churn.",
                "asking_price": 1400,
                "mrr": 388,
                "annual_profit": 4656,
            },
        ),
        (
            "legit auction: $1 starting bid with revenue",
            {
                "title": "Small Python SaaS at auction",
                "description": "Auction starts at $1, reserve applies.",
                "asking_price": 1,
                "mrr": 100,
                "annual_profit": 1100,
                "tech_stack": "Python",
            },
        ),
    ]

    results = {}
    for name, listing in tests:
        score, reasons = score_listing(listing)
        results[name] = score
        print(f"{score:5.1f}  {name}")
        print(f"       {reasons}")

    s = results
    assert s["dream deal: cheap, profitable, python, neglected"] >= 70, "dream deal should alert"
    assert s["over budget, fairly priced, no stack match"] < 50, "over-budget deal should score low"
    assert 30 <= s["users but no revenue, JS stack"] <= 70, "user-positive deal should be mid-range"
    assert s["red flags: hype, no revenue, crypto"] < s["users but no revenue, JS stack"], (
        "red-flagged listing must score below the clean user-positive one"
    )
    assert s["no price, no revenue, no signals"] <= 15, "empty listing should score near zero"
    assert s["scam pattern: clone script, impossible multiple, high churn"] < 40, (
        "clone-script scam listing must score below 40"
    )
    assert s["scam pattern: clone script, impossible multiple, high churn"] < s[
        "dream deal: cheap, profitable, python, neglected"
    ] - 30, "scam listing must sit far below a clean deal"
    assert s["legit auction: $1 starting bid with revenue"] >= 40, (
        "auction starting bid should not be punished as fake revenue"
    )
    assert all(0 <= v <= 100 for v in s.values()), "scores must stay within 0-100"
    print(f"all {len(tests)} scoring tests passed")
