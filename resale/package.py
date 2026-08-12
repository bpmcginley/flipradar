"""FlipRadar resale packager.

Turns an owned asset (assets table) plus its linked listing into a
ready-to-post listing package under resale/output/<asset_id>/:

  listing_copy.md   - headline + description, filled from real fields only
  metrics_sheet.md  - P&L snapshot: MRR then vs now, hours/week, costs
  buyer_faq.md      - transfer logistics, escrow, what's included
  where_to_list.md  - marketplace guidance with fee notes

Rule: no invented numbers. Any metric we do not actually have renders as
[FILL: metric] for the seller to complete before posting. The suggested
price range comes from dd.valuation and its assumptions are spelled out
inline wherever a required input had to be assumed rather than measured.

Usage:
    python cli.py package <asset_id>
    from resale.package import build_package
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import db
from dd.valuation import valuate

log = logging.getLogger("flipradar.resale")

OUTPUT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

# Assumed monthly churn when the seller has not measured it. 4.5%/mo sits in
# dd.valuation's "average" band and contributes a 0.0x multiple adjustment,
# so the assumption is neutral rather than flattering.
ASSUMED_CHURN_PCT = 4.5

PACKAGE_FILES = (
    "listing_copy.md",
    "metrics_sheet.md",
    "buyer_faq.md",
    "where_to_list.md",
)


def _fill(label: str) -> str:
    return f"[FILL: {label}]"


def _money(value: float | None, label: str) -> str:
    """Format a dollar amount, or a FILL placeholder when we have no data."""
    if value is None:
        return _fill(label)
    return f"${value:,.0f}"


def _months_between(start_iso: str | None, end: datetime) -> float | None:
    if not start_iso:
        return None
    try:
        start = datetime.fromisoformat(start_iso)
    except ValueError:
        log.warning("could not parse acquired_at %r", start_iso)
        return None
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    days = (end - start).total_seconds() / 86400.0
    return max(days / 30.44, 0.0)


def _get_asset(conn, asset_id: int) -> dict:
    row = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
    if row is None:
        raise ValueError(f"no asset with id {asset_id}")
    return dict(row)


def _get_listing(conn, listing_id: int | None) -> dict | None:
    if listing_id is None:
        return None
    row = conn.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
    return dict(row) if row else None


def _derive_metrics(asset: dict, listing: dict | None) -> dict:
    """Compute owned-months, hours/week, monthly growth, and total age.

    Everything here is derived from stored fields; anything underivable is None.
    """
    now = datetime.now(timezone.utc)
    months_owned = _months_between(asset.get("acquired_at"), now)

    hours_per_week = None
    hours_invested = asset.get("hours_invested")
    if hours_invested is not None and months_owned and months_owned > 0:
        hours_per_week = hours_invested / (months_owned * 4.345)

    growth_pct = None
    mrr_then = asset.get("mrr_at_purchase")
    mrr_now = asset.get("mrr_current")
    if mrr_then and mrr_now and mrr_then > 0 and months_owned and months_owned >= 1:
        growth_pct = ((mrr_now / mrr_then) ** (1.0 / months_owned) - 1.0) * 100.0

    age_months = None
    if listing and listing.get("age_months") is not None:
        age_months = listing["age_months"] + (months_owned or 0.0)
    elif months_owned is not None:
        age_months = months_owned  # lower bound: at least as old as our ownership

    return {
        "months_owned": months_owned,
        "hours_per_week": hours_per_week,
        "growth_pct": growth_pct,
        "age_months": age_months,
    }


def _run_valuation(asset: dict, derived: dict) -> tuple[dict | None, list[str]]:
    """Run dd.valuation if we have MRR; return (result, assumption notes)."""
    mrr = asset.get("mrr_current")
    if mrr is None:
        return None, ["No current MRR on record - valuation skipped. "
                      "Update the asset's mrr_current and re-run."]

    assumptions = [f"Churn assumed at {ASSUMED_CHURN_PCT}%/mo (industry-average band, "
                   "neutral multiple adjustment) - replace with measured churn if known."]

    growth = derived["growth_pct"]
    if growth is None:
        growth = 0.0
        assumptions.append("Growth assumed flat (0%/mo) - MRR-at-purchase or "
                           "ownership dates were missing, so growth could not be derived.")
    hours = derived["hours_per_week"]
    if hours is None:
        hours = 5.0
        assumptions.append("Owner time assumed at 5 hrs/wk - hours_invested or "
                           "acquisition date missing, so it could not be derived.")
    assumptions.append("Operating expenses assumed $0/mo - fill in real costs "
                       "in metrics_sheet.md and re-run if material.")

    result = valuate(
        mrr=mrr,
        churn_pct=ASSUMED_CHURN_PCT,
        growth_pct=growth,
        hours_per_week=hours,
        monthly_expenses=0.0,
        age_months=derived["age_months"],
    )
    return result, assumptions


def _render_listing_copy(asset: dict, listing: dict | None,
                         derived: dict, val: dict | None,
                         assumptions: list[str]) -> str:
    name = asset.get("name") or _fill("product name")
    listing = listing or {}
    mrr_now = asset.get("mrr_current")
    tech = listing.get("tech_stack") or _fill("tech stack")
    users = listing.get("users_count")
    age = derived["age_months"]

    lines = [
        f"# {name} - "
        + (f"${mrr_now:,.0f}/mo " if mrr_now is not None else "")
        + _fill("one-line hook, e.g. 'profitable niche SaaS, near-passive'"),
        "",
        "## Overview",
        "",
        f"{listing.get('description') or _fill('2-3 paragraph description: what it does, who pays for it, why it exists')}",
        "",
        "## Key numbers",
        "",
        f"- **MRR:** {_money(mrr_now, 'current MRR')}",
        f"- **Age:** " + (f"{age:.0f} months" if age is not None else _fill("product age")),
        f"- **Customers/users:** " + (f"{users:,}" if users is not None else _fill("paying customer count")),
        f"- **Tech stack:** {tech}",
        f"- **Owner time:** "
        + (f"~{derived['hours_per_week']:.1f} hrs/week" if derived["hours_per_week"] is not None
           else _fill("hours per week to operate")),
        f"- **Monthly growth:** "
        + (f"{derived['growth_pct']:+.1f}%/mo over the ownership period"
           if derived["growth_pct"] is not None else _fill("monthly growth rate")),
        f"- **Monthly costs:** " + _fill("hosting + API + tool costs per month"),
        f"- **Churn:** " + _fill("monthly customer churn %"),
        "",
        "## Why I'm selling",
        "",
        _fill("honest one-paragraph reason - buyers discount vague answers"),
        "",
        "## Suggested asking price",
        "",
    ]

    if val is not None:
        lines += [
            f"**${val['value_low']:,.0f} - ${val['value_high']:,.0f}** "
            f"(mid ${val['value_mid']:,.0f}), from SDE ${val['sde']:,.0f} at "
            f"{val['multiple_low']:.2f}x-{val['multiple_high']:.2f}x "
            f"(mid {val['multiple_mid']:.2f}x).",
            "",
            "Multiple adjustments:",
        ]
        lines += [f"- {r}" for r in val["reasons"]]
        lines += ["", "Assumptions behind this range:"]
        lines += [f"- {a}" for a in assumptions]
    else:
        lines += [_fill("suggested price - valuation skipped: " + assumptions[0])]

    lines += [
        "",
        "## What's included",
        "",
        "See buyer_faq.md - trim this list to what actually transfers:",
        "- Source code" + (f" ({asset['repo_path']})" if asset.get("repo_path") else ""),
        "- Domain(s): " + _fill("domains included"),
        "- Customer/user data: " + _fill("what customer data transfers"),
        "- " + _fill("anything else: social accounts, email list, content, licenses"),
        "",
    ]
    return "\n".join(lines)


def _render_metrics_sheet(asset: dict, listing: dict | None, derived: dict) -> str:
    mrr_then = asset.get("mrr_at_purchase")
    mrr_now = asset.get("mrr_current")
    delta = None
    if mrr_then is not None and mrr_now is not None:
        delta = mrr_now - mrr_then

    lines = [
        f"# Metrics sheet - {asset.get('name') or _fill('product name')}",
        "",
        "Fill every [FILL] before sharing with a buyer. Serious buyers will ask",
        "for Stripe/payment-processor screenshots to verify each revenue line.",
        "",
        "## Revenue",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| MRR at purchase | {_money(mrr_then, 'MRR when acquired')} |",
        f"| MRR current | {_money(mrr_now, 'current MRR')} |",
        "| MRR change since purchase | "
        + (f"{'+' if delta >= 0 else '-'}${abs(delta):,.0f}/mo" if delta is not None
           else _fill("change - needs both MRR figures")) + " |",
        "| Monthly growth (avg over ownership) | "
        + (f"{derived['growth_pct']:+.2f}%/mo" if derived["growth_pct"] is not None
           else _fill("growth rate")) + " |",
        f"| Annual run rate | "
        + (f"${mrr_now * 12:,.0f}" if mrr_now is not None else _fill("ARR")) + " |",
        f"| Monthly churn | {_fill('measured churn %')} |",
        "",
        "## Costs (monthly)",
        "",
        "| Line item | $/mo |",
        "|---|---|",
        f"| Hosting | {_fill('hosting cost')} |",
        f"| Third-party APIs | {_fill('API costs')} |",
        f"| Tools/other | {_fill('other recurring costs')} |",
        f"| **Total** | {_fill('total monthly costs')} |",
        "",
        "## Owner time",
        "",
        "| Metric | Value |",
        "|---|---|",
        "| Hours invested since purchase | "
        + (f"{asset['hours_invested']:.0f}" if asset.get("hours_invested") is not None
           else _fill("total hours")) + " |",
        "| Average hours/week | "
        + (f"~{derived['hours_per_week']:.1f}" if derived["hours_per_week"] is not None
           else _fill("hours per week")) + " |",
        f"| What the time goes to | {_fill('support / content / maintenance breakdown')} |",
        "",
        "## Cost basis (private - do not share; for your own floor price)",
        "",
        f"- Purchase price: {_money(asset.get('purchase_price'), 'what you paid')}",
        "- Months owned: "
        + (f"{derived['months_owned']:.1f}" if derived["months_owned"] is not None
           else _fill("ownership duration")),
        "",
    ]
    return "\n".join(lines)


def _render_buyer_faq(asset: dict, listing: dict | None) -> str:
    name = asset.get("name") or _fill("product name")
    tech = (listing or {}).get("tech_stack")
    return "\n".join([
        f"# Buyer FAQ - {name}",
        "",
        "Answers a serious buyer will expect. Fill the [FILL]s with real",
        "specifics - vague answers here are the #1 reason deals stall.",
        "",
        "## What exactly is included in the sale?",
        "",
        "- Full source code" + (f" ({tech})" if tech else "")
        + (f", currently at `{asset['repo_path']}`" if asset.get("repo_path") else ""),
        "- " + _fill("domains, and where they're registered"),
        "- " + _fill("customer database / user accounts - and the legal basis for transferring them"),
        "- " + _fill("email list, social accounts, content, brand assets, licenses"),
        "",
        "## What is NOT included?",
        "",
        "- " + _fill("anything retained: personal accounts, shared infrastructure, other projects on the same server"),
        "",
        "## How does the transfer work?",
        "",
        "1. **Code:** repository transfer (GitHub supports full repo transfer with issues/history) "
        "or a clean export. " + _fill("state which"),
        "2. **Domain:** registrar push or auth-code transfer. Allow up to 5-7 days for "
        "inter-registrar moves.",
        "3. **Payments:** Stripe accounts generally do NOT transfer between owners; the standard "
        "path is the buyer creates their own account and migrates subscriptions "
        "(Stripe supports PAN data migration between accounts on request). "
        + _fill("confirm your processor's transfer path"),
        "4. **Hosting/DNS:** " + _fill("transfer the account, or hand over a fresh deployment?"),
        "5. **Support handoff:** " + _fill("e.g. 30 days of email support / 2 calls included"),
        "",
        "## How is payment secured?",
        "",
        "- Use escrow for anything non-trivial: Escrow.com (works standalone or via Flippa), "
        "or Acquire.com's built-in escrow if selling there.",
        "- Typical flow: buyer funds escrow -> assets transfer -> buyer inspects "
        "(agree the inspection window up front, e.g. 3-7 days) -> escrow releases.",
        "- Never transfer the domain or repo before funds are in escrow.",
        "",
        "## How do you verify the revenue?",
        "",
        "- Live screen-share of the payment processor dashboard, read-only processor "
        "access, or verified-revenue integration on the marketplace. "
        + _fill("state what you'll provide"),
        "",
        "## Why are you selling?",
        "",
        "- " + _fill("same honest answer as in listing_copy.md - keep them consistent"),
        "",
        "## Is there a non-compete?",
        "",
        "- " + _fill("standard is 2-3 years within the product's niche; decide what you'll agree to"),
        "",
    ])


def _render_where_to_list(val: dict | None) -> str:
    price_note = ""
    if val is not None:
        price_note = (f"Suggested range for this asset: ${val['value_low']:,.0f} - "
                      f"${val['value_high']:,.0f} (mid ${val['value_mid']:,.0f}) - "
                      "so start with the tier that bracket falls into.")
    else:
        price_note = ("No valuation was computed (missing current MRR), so pick the tier "
                      "once you know your asking price.")

    return "\n".join([
        "# Where to list",
        "",
        price_note,
        "",
        "## Under ~$5k asking: zero-fee channels first",
        "",
        "At this size, marketplace fees eat a visible chunk of the deal, and the",
        "buyers for sub-$5k assets hang out in free channels anyway.",
        "",
        "| Channel | Fees | Notes |",
        "|---|---|---|",
        "| Microns | Free basic listing | Micro-startup focused; buyers expect $1k-$50k deals |",
        "| Reddit (r/SideProject, r/microsaas, r/EntrepreneurRideAlong) | Free | Follow each sub's self-promo rules; expect tire-kickers; still use escrow |",
        "| IndieMaker | Zero commission tiers | Side-project marketplace; listing upgrades optional |",
        "",
        "## $5k+ asking: paid marketplaces earn their fees",
        "",
        "More buyer volume, verified-revenue tooling, and built-in escrow justify",
        "the cost once the deal is big enough.",
        "",
        "| Channel | Fees (check current pricing before listing) | Notes |",
        "|---|---|---|",
        "| Flippa | Listing fee (~$29+) plus a success fee (~10% on smaller deals, tiered down as size grows) | Largest buyer pool; use verified revenue + Escrow.com integration |",
        "| Acquire.com | Free to list; paid seller tiers and/or closing fees on premium plans | SaaS-focused buyers; built-in escrow and LOI flow |",
        "",
        "## Pricing anchor",
        "",
        "Clean, well-documented, transferable micro-SaaS resales anchor around",
        "**2.5x-4x SDE**. Scruffy or owner-dependent assets close nearer 1.5x-1.7x",
        "(sub-$100k marketplace average is ~1.68x). Price at the top of your band",
        "only if churn, growth, and handoff docs genuinely support it.",
        "",
        "## Scope note",
        "",
        "FlipRadar does NOT auto-post listings to any marketplace. Posting requires",
        "your own accounts and each marketplace's terms of service restrict",
        "automated submissions - copy the package contents over manually.",
        "",
    ])


def build_package(
    asset_id: int,
    db_path: str = db.DB_PATH,
    output_dir: str | None = None,
) -> str:
    """Build the resale listing package for one asset.

    Writes the four package files to output_dir (default
    resale/output/<asset_id>/) and returns that directory path.
    Raises ValueError if the asset does not exist.
    """
    conn = db.get_conn(db_path)
    try:
        asset = _get_asset(conn, asset_id)
        listing = _get_listing(conn, asset.get("listing_id"))
    finally:
        conn.close()

    if listing is None and asset.get("listing_id") is not None:
        log.warning("asset %d references missing listing %s",
                    asset_id, asset["listing_id"])

    derived = _derive_metrics(asset, listing)
    val, assumptions = _run_valuation(asset, derived)

    out = output_dir or os.path.join(OUTPUT_ROOT, str(asset_id))
    os.makedirs(out, exist_ok=True)

    contents = {
        "listing_copy.md": _render_listing_copy(asset, listing, derived, val, assumptions),
        "metrics_sheet.md": _render_metrics_sheet(asset, listing, derived),
        "buyer_faq.md": _render_buyer_faq(asset, listing),
        "where_to_list.md": _render_where_to_list(val),
    }
    for fname, text in contents.items():
        path = os.path.join(out, fname)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        log.info("wrote %s", path)

    return out
