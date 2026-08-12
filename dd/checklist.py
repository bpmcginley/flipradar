"""Due-diligence checklist generator.

generate_checklist(listing_dict) returns a markdown checklist customized to the
listing (revenue verification, churn calc, code review, transfer logistics,
escrow, why-selling probe).

CLI:
    python -m dd.checklist <listing_id>
writes dd/output/<id>_checklist.md using the listing from data/deals.db.
"""

from __future__ import annotations

import argparse
import os
import sys

DD_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(DD_DIR)
OUTPUT_DIR = os.path.join(DD_DIR, "output")


def _fmt_money(v) -> str:
    try:
        return f"${float(v):,.0f}"
    except (TypeError, ValueError):
        return "unknown"


def generate_checklist(listing: dict) -> str:
    """Build a markdown DD checklist customized to one listing dict.

    Expects keys matching the listings table (title, url, asking_price, mrr,
    annual_profit, tech_stack, age_months, users_count, ...). Missing keys are
    handled gracefully.
    """
    title = listing.get("title") or "Untitled listing"
    url = listing.get("url") or "n/a"
    source = listing.get("source") or "unknown"
    asking = listing.get("asking_price")
    mrr = listing.get("mrr")
    arr = listing.get("arr")
    profit = listing.get("annual_profit")
    tech = listing.get("tech_stack")
    age = listing.get("age_months")
    users = listing.get("users_count")

    mrr_known = mrr is not None and float(mrr or 0) > 0
    has_revenue = mrr_known or (arr or 0) or (profit or 0)

    lines: list[str] = []
    add = lines.append

    add(f"# Due-Diligence Checklist: {title}")
    add("")
    add(f"- Source: {source}")
    add(f"- URL: {url}")
    add(f"- Asking price: {_fmt_money(asking)}")
    add(f"- Claimed MRR: {_fmt_money(mrr) if mrr is not None else 'not stated'}")
    if arr:
        add(f"- Claimed ARR: {_fmt_money(arr)}")
    if profit:
        add(f"- Claimed annual profit: {_fmt_money(profit)}")
    if tech:
        add(f"- Tech stack: {tech}")
    if age:
        add(f"- Age: {age:.0f} months")
    if users:
        add(f"- Users: {users:,}")
    add("")

    # ---- Revenue verification ----
    add("## 1. Revenue verification")
    add("")
    if has_revenue:
        add("- [ ] Live Stripe (or payment processor) **screen-share** — never accept "
            "screenshots or CSV exports. Seller shares screen and navigates in real time.")
        add("- [ ] In the screen-share, view: Balance > Payouts (last 6 months), "
            "Customers list, and the Revenue graph on the Home tab.")
        add("- [ ] Cross-check payout totals against bank statements for at least "
            "3 months.")
        if mrr_known:
            add(f"- [ ] Verify claimed MRR ({_fmt_money(mrr)}) against Stripe's own "
                "MRR / Billing analytics — not the seller's spreadsheet.")
        add("- [ ] Check **refund rate** for the last 6 months. A spike in charges "
            "followed by refunds after the listing date = inflated MRR scam.")
        add("- [ ] Check for a single customer contributing >30% of revenue "
            "(concentration risk).")
        add("- [ ] Confirm no self-purchases: look for customer emails matching the "
            "seller's domain or name.")
        add("- [ ] Identify subscription mix: monthly vs annual. Annual prepays booked "
            "recently inflate cash but pull forward revenue you must service.")
    else:
        add("- [ ] Listing claims no (or unknown) revenue — treat any revenue talk in "
            "negotiation as unverified until a Stripe screen-share happens.")
        add("- [ ] If pre-revenue, verify user/traffic claims instead (below) and "
            "value on asset quality, not promises.")
    add("")

    # ---- Churn & growth ----
    add("## 2. Churn and growth")
    add("")
    add("- [ ] Compute monthly customer churn from Stripe data: "
        "`churn % = cancels_in_month / customers_at_start_of_month * 100`.")
    add("- [ ] Average it over the last 6 months; ignore the seller's quoted number.")
    add("- [ ] Compute net revenue retention: are upgrades offsetting cancels?")
    add("- [ ] Plot new signups per month for 12 months. Flat or declining while the "
        "seller says \"growing\" is a red flag.")
    add("- [ ] Ask where customers come from. If it's mostly paid ads, check ad spend "
        "is included in the profit number and whether traffic survives without it.")
    if users:
        add(f"- [ ] Verify the {users:,} users claim: request read-only analytics "
            "access (Plausible/GA) — again live screen-share, not screenshots.")
    add("")

    # ---- Code & asset review ----
    add("## 3. Code and asset review")
    add("")
    if tech:
        add(f"- [ ] Stack is **{tech}** — confirm you can actually maintain it "
            "(buyer strengths: Python / C# / JS / Rust).")
    else:
        add("- [ ] Identify the actual stack (ask for repo tour) and confirm you can "
            "maintain it (buyer strengths: Python / C# / JS / Rust).")
    add("- [ ] Request a read-only repo invite (or screen-share code tour) before "
        "closing.")
    add("- [ ] Check licenses of all dependencies — no GPL contamination of a "
        "proprietary product, no pirated themes/plugins/assets.")
    add("- [ ] Search for hard-coded secrets, third-party API keys that belong to the "
        "seller, and services billed to the seller's accounts.")
    add("- [ ] Confirm the code actually deploys: ask the seller to run the deploy in "
        "front of you, or get a staging environment.")
    add("- [ ] Estimate monthly infra cost (hosting, APIs, email) and verify it "
        "matches the seller's expense claims.")
    add("- [ ] Check for critical dependence on a platform that could revoke access "
        "(marketplace app, API ToS risk, single supplier).")
    add("- [ ] Ask about known bugs, support ticket backlog, and average weekly "
        "maintenance hours (target: under 5 hrs/wk).")
    add("")

    # ---- Why selling ----
    add("## 4. Why is the seller selling?")
    add("")
    add("- [ ] Ask directly, then ask again later in a different way — inconsistent "
        "answers are a red flag.")
    add("- [ ] Plausible good answers: shiny new project, burnout, needs cash, "
        "portfolio pruning. Bad signs: vague, defensive, \"no time\" while listing "
        "5 other products.")
    add("- [ ] Ask: \"What would you do with this product if you kept it?\" — sellers "
        "of healthy products have a ready answer.")
    add("- [ ] Search the seller's name/handle: prior flips, disputes, reputation on "
        "the marketplace, Twitter/X history.")
    add("- [ ] Ask what they tried that did NOT work (marketing channels, features). "
        "Honest sellers have a list.")
    add("")

    # ---- Transfer logistics ----
    add("## 5. Transfer logistics")
    add("")
    add("- [ ] Written asset list: domain(s), repo, hosting account or migration, "
        "Stripe account or customer migration plan, email lists, social handles, "
        "docs, trademarks.")
    add("- [ ] Stripe cannot be \"handed over\" casually — plan either a Stripe "
        "account transfer (support ticket, both parties) or customer re-subscription "
        "migration, and know the churn cost of the latter.")
    add("- [ ] Domain transfer: unlock + auth code into YOUR registrar account, "
        "verified before final payment release.")
    add("- [ ] DNS, email deliverability (SPF/DKIM), and OAuth app ownership "
        "transferred and tested.")
    add("- [ ] Customer notification plan agreed (who announces the change, when).")
    add("- [ ] 30 days of post-sale seller support in writing (Slack/email, response "
        "time expectations).")
    add("- [ ] Non-compete clause: seller won't launch a clone for 2-3 years.")
    add("")

    # ---- Escrow & closing ----
    add("## 6. Escrow and closing")
    add("")
    add("- [ ] Use **Escrow.com** (or the marketplace's built-in escrow) — never "
        "direct wire/PayPal for the full amount.")
    add("- [ ] Structure: funds in escrow -> assets transferred -> inspection period "
        "(3-7 days to verify everything works) -> release.")
    add("- [ ] Simple asset purchase agreement in writing, even for small deals: "
        "assets included, price, transfer steps, support period, non-compete.")
    if asking is not None:
        add(f"- [ ] Escrow.com fees on a {_fmt_money(asking)} deal are small — do not "
            "let the seller talk you out of escrow to \"save fees\".")
    add("- [ ] Agree who pays escrow fees before opening the transaction (commonly "
        "split 50/50).")
    add("")

    add("---")
    add("*Generated by FlipRadar dd.checklist. Verify everything yourself; this is a "
        "process aid, not legal or financial advice.*")
    add("")
    return "\n".join(lines)


def _load_listing(listing_id: int) -> dict | None:
    sys.path.insert(0, REPO_ROOT)
    import db  # noqa: E402

    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM listings WHERE id = ?", (listing_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m dd.checklist",
        description="Generate a due-diligence checklist for a listing in deals.db.",
    )
    parser.add_argument("listing_id", type=int, help="listings.id from deals.db")
    args = parser.parse_args(argv)

    listing = _load_listing(args.listing_id)
    if listing is None:
        print(f"error: no listing with id {args.listing_id} in deals.db", file=sys.stderr)
        return 1

    md = generate_checklist(listing)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, f"{args.listing_id}_checklist.md")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(md)
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
