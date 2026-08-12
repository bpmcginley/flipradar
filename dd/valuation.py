"""Micro-SaaS valuation calculator.

Inputs: MRR, monthly churn %, monthly growth %, owner hours/week.
Outputs: SDE and a fair-value range built from SDE multiples.

Heuristics (documented so future-me can argue with them):

* Base multiple band is 1.5x-4.0x annual SDE. Public marketplace data
  (Flippa/Empire Flippers/Acquire.com aggregate reports) shows sub-$100k
  deals actually close around ~1.68x SDE on average, while clean,
  well-documented, transferable SaaS resales command roughly 2.5x-4.5x.
  So: scruffy micro deals cluster near the bottom of the band, and only
  genuinely clean assets earn the top.
* Churn: monthly churn under ~3% is good for micro-SaaS, 3-6% is normal,
  >6% means the revenue is melting — each band shifts the multiple.
* Growth: flat-to-declining products are priced as annuities in run-off;
  >5%/mo growth is rare at this size and earns a premium.
* Owner dependency: every hour of required owner time is a liability the
  buyer purchases. <5 hrs/wk is semi-passive (premium); >15 hrs/wk means
  you are buying a job (discount).
* Age: products under 12 months have unproven retention (discount);
  2+ years of history de-risks the revenue (small premium).

The adjusted multiple is clamped to [1.0, 4.5] — below 1x nobody sells,
above 4.5x nobody sane buys a micro-SaaS.

Usage as a library:
    from dd.valuation import valuate
    result = valuate(mrr=500, churn_pct=4, growth_pct=1, hours_per_week=3)

CLI:
    python -m dd.valuation --mrr 500 --churn 4 --growth 1 --hours 3 \
        [--expenses 50] [--age-months 24]
"""

from __future__ import annotations

import argparse


BASE_LOW = 1.5   # bottom of the SDE multiple band
BASE_HIGH = 4.0  # top of the band before adjustments
CLAMP_LOW = 1.0
CLAMP_HIGH = 4.5


def _churn_adj(churn_pct: float) -> tuple[float, str]:
    """Multiple adjustment for monthly customer churn %."""
    if churn_pct < 0:
        churn_pct = 0.0
    if churn_pct <= 2.0:
        return +0.4, f"low churn ({churn_pct:.1f}%/mo): +0.4x"
    if churn_pct <= 3.0:
        return +0.2, f"good churn ({churn_pct:.1f}%/mo): +0.2x"
    if churn_pct <= 6.0:
        return 0.0, f"average churn ({churn_pct:.1f}%/mo): +0.0x"
    if churn_pct <= 10.0:
        return -0.5, f"high churn ({churn_pct:.1f}%/mo): -0.5x"
    return -1.0, f"severe churn ({churn_pct:.1f}%/mo): -1.0x"


def _growth_adj(growth_pct: float) -> tuple[float, str]:
    """Multiple adjustment for monthly revenue growth %."""
    if growth_pct >= 5.0:
        return +0.5, f"strong growth ({growth_pct:.1f}%/mo): +0.5x"
    if growth_pct >= 2.0:
        return +0.25, f"moderate growth ({growth_pct:.1f}%/mo): +0.25x"
    if growth_pct >= 0.0:
        return 0.0, f"flat/slow growth ({growth_pct:.1f}%/mo): +0.0x"
    if growth_pct >= -3.0:
        return -0.4, f"declining ({growth_pct:.1f}%/mo): -0.4x"
    return -0.8, f"steep decline ({growth_pct:.1f}%/mo): -0.8x"


def _owner_adj(hours_per_week: float) -> tuple[float, str]:
    """Multiple adjustment for owner-dependency (hours/week to operate)."""
    if hours_per_week < 0:
        hours_per_week = 0.0
    if hours_per_week <= 2.0:
        return +0.3, f"near-passive ({hours_per_week:.0f} hrs/wk): +0.3x"
    if hours_per_week <= 5.0:
        return +0.1, f"semi-passive ({hours_per_week:.0f} hrs/wk): +0.1x"
    if hours_per_week <= 15.0:
        return -0.2, f"hands-on ({hours_per_week:.0f} hrs/wk): -0.2x"
    return -0.6, f"buying a job ({hours_per_week:.0f} hrs/wk): -0.6x"


def _age_adj(age_months: float | None) -> tuple[float, str]:
    """Multiple adjustment for product age (revenue track record)."""
    if age_months is None:
        return 0.0, "age unknown: +0.0x"
    if age_months < 12:
        return -0.3, f"young product ({age_months:.0f} mo): -0.3x"
    if age_months >= 24:
        return +0.2, f"proven track record ({age_months:.0f} mo): +0.2x"
    return 0.0, f"age {age_months:.0f} mo: +0.0x"


def valuate(
    mrr: float,
    churn_pct: float,
    growth_pct: float,
    hours_per_week: float,
    monthly_expenses: float = 0.0,
    age_months: float | None = None,
) -> dict:
    """Compute SDE and a fair-value range.

    SDE (Seller's Discretionary Earnings) for a solo micro-SaaS is annual
    revenue minus annual operating expenses, with the owner's own labor
    added back (i.e. we do NOT deduct an owner salary — standard SDE).

    Returns a dict with sde, multiples, value range, and reason strings.
    """
    annual_revenue = mrr * 12.0
    annual_expenses = monthly_expenses * 12.0
    sde = annual_revenue - annual_expenses

    adjustments = [
        _churn_adj(churn_pct),
        _growth_adj(growth_pct),
        _owner_adj(hours_per_week),
        _age_adj(age_months),
    ]
    total_adj = sum(a for a, _ in adjustments)
    reasons = [r for _, r in adjustments]

    low_mult = min(max(BASE_LOW + total_adj, CLAMP_LOW), CLAMP_HIGH)
    high_mult = min(max(BASE_HIGH + total_adj, CLAMP_LOW), CLAMP_HIGH)
    # Realism anchor: sub-$100k deals average ~1.68x, so quote a midpoint
    # weighted toward the low end rather than the arithmetic middle.
    mid_mult = low_mult + (high_mult - low_mult) * 0.35

    sde_floor = max(sde, 0.0)  # negative SDE -> value the asset at ~0 on earnings
    return {
        "mrr": mrr,
        "annual_revenue": annual_revenue,
        "annual_expenses": annual_expenses,
        "sde": sde,
        "multiple_low": round(low_mult, 2),
        "multiple_mid": round(mid_mult, 2),
        "multiple_high": round(high_mult, 2),
        "value_low": round(sde_floor * low_mult, 2),
        "value_mid": round(sde_floor * mid_mult, 2),
        "value_high": round(sde_floor * high_mult, 2),
        "reasons": reasons,
    }


def format_report(r: dict) -> str:
    lines = [
        "Valuation report",
        "----------------",
        f"MRR:               ${r['mrr']:,.0f}",
        f"Annual revenue:    ${r['annual_revenue']:,.0f}",
        f"Annual expenses:   ${r['annual_expenses']:,.0f}",
        f"SDE:               ${r['sde']:,.0f}",
        "",
        "Multiple adjustments (base band 1.5x-4.0x SDE):",
    ]
    lines += [f"  - {reason}" for reason in r["reasons"]]
    lines += [
        "",
        f"Adjusted band:     {r['multiple_low']:.2f}x - {r['multiple_high']:.2f}x"
        f" (mid {r['multiple_mid']:.2f}x, weighted low - sub-$100k deals avg ~1.68x)",
        f"Fair value range:  ${r['value_low']:,.0f} - ${r['value_high']:,.0f}",
        f"Fair value (mid):  ${r['value_mid']:,.0f}",
    ]
    if r["sde"] <= 0:
        lines.append("NOTE: SDE is non-positive; earnings-based value is ~$0. "
                     "Any price paid is for the asset/code/audience, not earnings.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m dd.valuation",
        description="Micro-SaaS valuation: SDE and fair-value range from SDE multiples.",
    )
    p.add_argument("--mrr", type=float, required=True, help="monthly recurring revenue ($)")
    p.add_argument("--churn", type=float, required=True, help="monthly customer churn (%%)")
    p.add_argument("--growth", type=float, required=True, help="monthly revenue growth (%%)")
    p.add_argument("--hours", type=float, required=True, help="owner hours per week")
    p.add_argument("--expenses", type=float, default=0.0, help="monthly operating expenses ($)")
    p.add_argument("--age-months", type=float, default=None, help="product age in months")
    a = p.parse_args(argv)

    result = valuate(
        mrr=a.mrr,
        churn_pct=a.churn,
        growth_pct=a.growth,
        hours_per_week=a.hours,
        monthly_expenses=a.expenses,
        age_months=a.age_months,
    )
    print(format_report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
