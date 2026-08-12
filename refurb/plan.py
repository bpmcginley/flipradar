"""90-day improvement plan generator for an acquired micro-SaaS.

generate_plan(asset, audit_md=None) returns a weekly-granularity markdown plan.
The plan adapts to what the audit found missing (no tests -> week-1 smoke
tests, secrets found -> day-1 rotation, no annual plan info -> pricing work,
heavy TODO debt -> a cleanup week) and points at the ready-to-paste Claude Code
prompts in refurb/prompts/ for each automatable job.

`asset` is a dict shaped like a row from the assets table (name, repo_path,
mrr_current, purchase_price, ...) or a listings row (title, mrr, tech_stack).

CLI:
    python -m refurb.plan --name "widgetapp" [--mrr 400] [--price 1500]
        [--tech "python/flask"] [--audit report.md] [--asset-id N] [--out plan.md]
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys

log = logging.getLogger("flipradar.refurb.plan")

REFURB_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(REFURB_DIR)
PROMPTS_REL = "refurb/prompts"


def _parse_audit(audit_md: str | None) -> dict:
    """Extract signals from a refurb.audit report (see its Health checks format)."""
    signals = {
        "has_tests": None,      # None = unknown (no audit supplied)
        "has_ci": None,
        "has_license": None,
        "has_readme": None,
        "has_docker": None,
        "todo_count": None,
        "secret_count": 0,
    }
    if not audit_md:
        return signals

    def check(label: str) -> bool | None:
        m = re.search(rf"(?m)^- {label}: (present|missing)\b", audit_md)
        return None if m is None else m.group(1) == "present"

    signals["has_tests"] = check("Tests")
    signals["has_ci"] = check("CI")
    signals["has_license"] = check("LICENSE")
    signals["has_readme"] = check("README")
    signals["has_docker"] = check("Dockerfile")

    m = re.search(r"TODO/FIXME/HACK/XXX: (\d+)", audit_md)
    if m:
        signals["todo_count"] = int(m.group(1))
    m = re.search(r"(\d+) potential secret\(s\) found", audit_md)
    if m:
        signals["secret_count"] = int(m.group(1))
    return signals


def _prompt(name: str) -> str:
    return f"`{PROMPTS_REL}/{name}`"


def generate_plan(asset: dict, audit_md: str | None = None) -> str:
    """Build a 90-day (13-week) improvement plan as markdown.

    Accepts an assets-table dict (name, repo_path, mrr_current, mrr_at_purchase,
    purchase_price) or a listings dict (title, mrr, asking_price, tech_stack).
    Missing keys are handled gracefully. audit_md, if given, should be output
    of refurb.audit.audit_repo for the acquired repo.
    """
    name = asset.get("name") or asset.get("title") or "the product"
    mrr = asset.get("mrr_current") or asset.get("mrr_at_purchase") or asset.get("mrr")
    price = asset.get("purchase_price") or asset.get("asking_price")
    tech = asset.get("tech_stack")
    repo_path = asset.get("repo_path")
    s = _parse_audit(audit_md)

    # None (unknown) is treated as "assume missing" -- cheap to verify, costly to skip.
    no_tests = s["has_tests"] is not True
    no_ci = s["has_ci"] is not True
    no_readme = s["has_readme"] is not True
    no_license = s["has_license"] is not True
    heavy_debt = (s["todo_count"] or 0) >= 20
    secrets = s["secret_count"] or 0

    lines: list[str] = []
    add = lines.append

    add(f"# 90-Day Refurb Plan: {name}")
    add("")
    if mrr is not None:
        add(f"- MRR at plan time: ${float(mrr):,.0f}/mo")
    if price is not None:
        add(f"- Purchase price: ${float(price):,.0f}")
    if tech:
        add(f"- Stack: {tech}")
    if repo_path:
        add(f"- Repo: `{repo_path}`")
    add(f"- Audit input: {'refurb.audit report supplied' if audit_md else 'none -- unknowns assumed missing'}")
    add("")
    add("Goal for the 90 days: stabilize, then stop the leaks, then grow. Do not")
    add("start growth work until weeks 1-2 (stabilize) are actually done.")
    add("")
    add("Each week lists at most ~5 hours of owner work. Jobs marked **[prompt]**")
    add(f"have a ready-to-paste Claude Code prompt in `{PROMPTS_REL}/` -- run Claude")
    add("Code inside the acquired repo and paste the prompt.")
    add("")

    # ---- Phase 1: stabilize (weeks 1-2) ----
    add("## Phase 1: Stabilize (weeks 1-2)")
    add("")
    add("### Week 1 -- own it safely")
    if secrets:
        add(f"- Day 1: rotate the {secrets} secret(s) flagged in the audit -- API keys,")
        add("  DB passwords, webhook signing secrets. The seller has seen all of them.")
    else:
        add("- Day 1: rotate every credential anyway (API keys, DB, SMTP, Stripe")
        add("  webhook secrets) -- the audit heuristic finding nothing proves little.")
    add("- Transfer lockdown: confirm you solely control domain, DNS, hosting,")
    add("  Stripe, email sender, error tracker, analytics. Enable 2FA everywhere.")
    add("- Set up uptime monitoring (any free pinger) + error alerting to your inbox.")
    if no_tests:
        add("- **[prompt]** Add smoke tests so you can deploy without fear: "
            f"{_prompt('add-smoke-tests.md')}")
    else:
        add("- Run the existing test suite; record how to run it and current pass rate.")
    add("")
    add("### Week 2 -- know how it runs")
    add("- Write (or verify) a deploy runbook: how to ship a change end to end.")
    if no_ci:
        add("- Add minimal CI: run the smoke tests on every push (GitHub Actions or")
        add("  equivalent). Green check before deploy, always.")
    else:
        add("- Review existing CI; make sure it runs the tests and you get failures.")
    if no_readme:
        add("- Write a README: what it is, how to run locally, how to deploy.")
    add("- Baseline metrics snapshot: MRR, subscriber count, churn (last 3 mo),")
    add("  signups/week, traffic. Record them -- these are your before numbers.")
    if no_license:
        add("- Decide licensing posture (proprietary is fine; just be explicit) and")
        add("  check dependency licenses for anything viral.")
    add("")

    # ---- Phase 2: stop the leaks (weeks 3-6) ----
    add("## Phase 2: Stop the leaks (weeks 3-6)")
    add("")
    add("### Week 3 -- onboarding")
    add("- Sign up as a new customer with a fresh email. Time it. Note every")
    add("  confusion point between landing page and first value.")
    add(f"- **[prompt]** Fix the worst friction: {_prompt('fix-onboarding.md')}")
    add("")
    add("### Week 4 -- pricing and billing")
    add("- Map the current plans. If there is no annual option, that's free LTV:")
    add(f"  **[prompt]** {_prompt('add-annual-billing.md')} (Stripe)")
    add("- Check for failed-payment (dunning) handling; enable Stripe smart retries")
    add("  + card-update emails if off.")
    add("- Compare price against 3 competitors; queue a considered price change for")
    add("  Phase 3 (never change price in the same week as other churn work).")
    add("")
    add("### Week 5 -- churn rescue")
    add("- Compute real churn from Stripe, not memory: cancels / starting customers.")
    add(f"- **[prompt]** Cancellation flow + win-back emails: {_prompt('churn-rescue-emails.md')}")
    add("- Add a one-question cancellation survey (\"what made you cancel?\").")
    add("")
    add("### Week 6 -- support and code debt")
    add("- Answer every open support thread; harvest the top 3 complaints into a")
    add("  fix list. Complaints are a free roadmap.")
    if heavy_debt:
        add(f"- Audit found {s['todo_count']} TODO/FIXME/HACK markers -- triage them:")
        add("  fix the ones guarding real bugs, delete the stale ones.")
    else:
        add("- Light debt pass: fix any TODO/FIXME markers that guard real bugs.")
    add(f"- **[prompt]** Patch known-vulnerable deps: {_prompt('dependency-upgrade.md')}")
    add("")

    # ---- Phase 3: grow (weeks 7-12) ----
    add("## Phase 3: Grow (weeks 7-12)")
    add("")
    add("### Weeks 7-8 -- SEO and landing page")
    add(f"- **[prompt]** Landing/SEO pass: {_prompt('seo-landing-pass.md')}")
    add("- Identify the 5 search queries a buyer of this product types; make sure a")
    add("  page exists that answers each one.")
    add("- Set up Search Console if not already; submit sitemap.")
    add("")
    add("### Weeks 9-10 -- ship one visible improvement")
    add("- Pick the #1 harvested complaint from week 6 and ship the fix. Announce it")
    add("  to the mailing list (\"under new management, here's what's new\").")
    add("- Execute the price change queued in week 4, if still warranted --")
    add("  grandfather existing customers.")
    add("")
    add("### Weeks 11-12 -- distribution experiments")
    add("- Run two small acquisition experiments (directory listings, integration")
    add("  marketplace, a comparison post, a partnership). Measure signups/week")
    add("  against the week-2 baseline.")
    add("- Double down on whichever moved the number; kill the other.")
    add("")

    # ---- Week 13 ----
    add("## Week 13 -- retro and re-value")
    add("- Update FlipRadar: `assets` row -- hours_invested, mrr_current, notes.")
    add("- Re-run `python -m refurb.audit` on the repo; diff against the day-1 report.")
    add("- Re-value the asset (dd.valuation) with the new MRR/churn. Decide: hold,")
    add("  keep improving, or list it for sale with your now-clean books.")
    add("")
    add("---")
    add("*Generated by FlipRadar refurb.plan. A plan is a hypothesis -- rewrite it")
    add("when reality disagrees.*")
    add("")
    return "\n".join(lines)


def _load_asset(asset_id: int) -> dict | None:
    sys.path.insert(0, REPO_ROOT)
    import db  # noqa: E402

    conn = db.get_conn()
    try:
        row = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(
        prog="python -m refurb.plan",
        description="Generate a 90-day improvement plan for an acquired micro-SaaS.",
    )
    parser.add_argument("--asset-id", type=int, default=None,
                        help="load the asset from the assets table in deals.db")
    parser.add_argument("--name", default=None, help="asset/product name")
    parser.add_argument("--mrr", type=float, default=None, help="current MRR ($)")
    parser.add_argument("--price", type=float, default=None, help="purchase price ($)")
    parser.add_argument("--tech", default=None, help="tech stack description")
    parser.add_argument("--repo", default=None, help="path to the acquired repo")
    parser.add_argument("--audit", default=None,
                        help="path to a refurb.audit markdown report to drive the plan")
    parser.add_argument("--out", default=None, help="write plan to this file instead of stdout")
    args = parser.parse_args(argv)

    if args.asset_id is not None:
        asset = _load_asset(args.asset_id)
        if asset is None:
            print(f"error: no asset with id {args.asset_id} in deals.db", file=sys.stderr)
            return 1
    elif args.name:
        asset = {}
    else:
        parser.error("provide --asset-id or at least --name")

    # CLI flags override / fill in loaded values.
    for key, val in (("name", args.name), ("mrr_current", args.mrr),
                     ("purchase_price", args.price), ("tech_stack", args.tech),
                     ("repo_path", args.repo)):
        if val is not None:
            asset[key] = val

    audit_md = None
    if args.audit:
        with open(args.audit, encoding="utf-8") as fh:
            audit_md = fh.read()

    plan = generate_plan(asset, audit_md=audit_md)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(plan)
        print(args.out)
    else:
        print(plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
