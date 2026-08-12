"""FlipRadar CLI.

Subcommands:
  scan      - run all adapters, upsert listings into the DB, then score
  score     - rescore all listings
  list      - print top deals
  export    - write static dashboard (docs/) for GitHub Pages
  serve     - run the web dashboard
  pipeline  - track deal status per listing (watch/contacted/dd/offer/owned/passed)
  portfolio - track acquired assets (price, MRR, hours, rough ROI estimates)
  package   - build a resale listing package for an owned asset

Modules for scoring/adapters/dashboard are imported lazily so a missing or
broken module only affects its own command.
"""

from __future__ import annotations

import argparse
import importlib
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("flipradar.cli")


def _load_adapters(use_fixtures: bool) -> list:
    import config

    adapters = []
    for name in config.TARGET_SOURCES:
        try:
            mod = importlib.import_module(f"adapters.{name}")
            cls = getattr(mod, f"{name.capitalize()}Adapter")
            adapters.append(cls(use_fixtures=use_fixtures))
        except (ImportError, AttributeError) as exc:
            log.warning("skipping adapter '%s': %s", name, exc)
    return adapters


def cmd_scan(args: argparse.Namespace) -> int:
    from datetime import datetime, timezone

    import db

    scan_start = datetime.now(timezone.utc).isoformat(timespec="seconds")
    total = 0
    failed: list[str] = []
    for adapter in _load_adapters(use_fixtures=args.fixtures):
        try:
            listings = adapter.run()
        except Exception as exc:  # one broken adapter must never kill the scan
            log.error("%s: adapter failed (%s); continuing", adapter.name, exc)
            failed.append(adapter.name)
            continue
        log.info("%s: %d listings", adapter.name, len(listings))
        for listing in listings:
            try:
                db.upsert_listing(listing)
                total += 1
            except Exception as exc:
                log.warning("%s: skipped listing (%s)", adapter.name, exc)
    if failed:
        log.warning("adapters that failed this scan: %s", ", ".join(failed))
    print(f"scan complete: {total} listings upserted")
    rc = cmd_score(args)
    try:
        import alerts

        alerts.alert_new_high_scores(since=scan_start)
    except ImportError:
        log.warning("alerts module not available; skipping alerts")
    return rc


def cmd_score(args: argparse.Namespace) -> int:
    try:
        scoring = importlib.import_module("scoring")
    except ImportError:
        log.warning("scoring module not available yet; skipping score step")
        return 0
    n = scoring.rescore_all()
    print(f"scored {n} listings")
    return 0


def cmd_enrich(args: argparse.Namespace) -> int:
    import enrich

    summary = enrich.enrich_all(limit=args.limit, source=args.source, force=args.force)
    print(f"enrich complete: {summary}")
    return cmd_score(args)


def cmd_export(args: argparse.Namespace) -> int:
    import export_static

    summary = export_static.export(out_dir=args.out)
    print(f"export complete: {summary}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    import config
    import db

    filters = {"exclude_sold": True}
    if not args.all:
        filters["max_price"] = config.BUDGET_MAX
    rows = db.get_listings(filters=filters, order_by="score DESC", limit=args.limit)
    if not rows:
        print("no listings yet -- run 'python cli.py scan' (or scan --fixtures)")
        return 0
    headers = ["#", "SCORE", "PRICE", "MRR", "SOURCE", "TITLE"]
    table = []
    for i, r in enumerate(rows, 1):
        table.append([
            str(i),
            f"{r['score']:.0f}" if r["score"] is not None else "-",
            f"${r['asking_price']:,.0f}" if r["asking_price"] is not None else "?",
            f"${r['mrr']:,.0f}/mo" if r["mrr"] is not None else "-",
            r["source"],
            (r["title"] or "(untitled)")[:60],
        ])
    widths = [max(len(h), *(len(row[c]) for row in table)) for c, h in enumerate(headers)]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*headers))
    print(fmt.format(*("-" * w for w in widths)))
    for row, r in zip(table, rows):
        print(fmt.format(*row))
        print(f"{'':>{widths[0]}}  url: {r['url']}")
    return 0


def _print_table(headers: list[str], rows: list[list[str]]) -> None:
    widths = [
        max(len(h), *(len(row[c]) for row in rows)) if rows else len(h)
        for c, h in enumerate(headers)
    ]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*headers))
    print(fmt.format(*("-" * w for w in widths)))
    for row in rows:
        print(fmt.format(*row))


def cmd_pipeline_set(args: argparse.Namespace) -> int:
    import db

    try:
        db.set_pipeline_status(args.listing_id, args.status, notes=args.notes)
    except ValueError as exc:
        log.error("%s", exc)
        return 1
    print(f"listing {args.listing_id} -> {args.status}")
    return 0


def cmd_pipeline_show(args: argparse.Namespace) -> int:
    import db

    rows = db.get_pipeline(status=args.status)
    if not rows:
        print("pipeline is empty -- add with 'python cli.py pipeline set <listing_id> <status>'")
        return 0
    table = []
    for r in rows:
        table.append([
            str(r["listing_id"]),
            r["status"],
            f"{r['score']:.0f}" if r["score"] is not None else "-",
            f"${r['asking_price']:,.0f}" if r["asking_price"] is not None else "?",
            f"${r['mrr']:,.0f}/mo" if r["mrr"] is not None else "-",
            (r["title"] or "(untitled)")[:50],
            (r["notes"] or "")[:40],
        ])
    _print_table(["LISTING", "STATUS", "SCORE", "PRICE", "MRR", "TITLE", "NOTES"], table)
    return 0


def cmd_portfolio_add(args: argparse.Namespace) -> int:
    import db

    asset_id = db.add_asset({
        "name": args.name,
        "purchase_price": args.price,
        "listing_id": args.listing_id,
        "mrr_at_purchase": args.mrr,
        "mrr_current": args.mrr,
        "repo_path": args.repo_path,
        "notes": args.notes,
    })
    print(f"asset {asset_id} added: {args.name}")
    return 0


def _months_held(acquired_at: str | None) -> float | None:
    from datetime import datetime, timezone

    if not acquired_at:
        return None
    try:
        start = datetime.fromisoformat(acquired_at)
    except ValueError:
        return None
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return max((datetime.now(timezone.utc) - start).days / 30.44, 0.0)


def cmd_portfolio_list(args: argparse.Namespace) -> int:
    import db

    rows = db.get_assets()
    if not rows:
        print("portfolio is empty -- add with 'python cli.py portfolio add --name X --price N'")
        return 0
    table = []
    for r in rows:
        months = _months_held(r["acquired_at"])
        mrr = r["mrr_current"]
        price = r["purchase_price"]
        # ROI is a rough ESTIMATE, not an accounting figure:
        #   est resale value  = current MRR x 12 x 2.5 (a common small-SaaS multiple)
        #   est revenue taken = current MRR x months held (assumes flat MRR, 100% margin)
        #   ROI = (est value + est revenue - purchase price) / purchase price
        roi = None
        if mrr is not None and price and months is not None:
            est_value = mrr * 12 * 2.5
            est_revenue = mrr * months
            roi = (est_value + est_revenue - price) / price * 100
        table.append([
            str(r["id"]),
            (r["name"] or "?")[:30],
            f"${price:,.0f}" if price is not None else "?",
            f"${mrr:,.0f}/mo" if mrr is not None else "-",
            f"{months:.1f}" if months is not None else "-",
            f"{r['hours_invested']:.0f}h" if r["hours_invested"] is not None else "-",
            f"{roi:+.0f}%" if roi is not None else "-",
        ])
    _print_table(["ID", "NAME", "PAID", "MRR", "MONTHS", "HOURS", "EST ROI"], table)
    print(
        "\nEST ROI is a rough estimate: (MRR x 12 x 2.5 resale multiple + MRR x months held"
        " as collected revenue - purchase price) / purchase price. It assumes flat MRR,"
        " 100% margin, and a 2.5x ARR exit -- treat it as a directional gut-check only."
    )
    return 0


def cmd_portfolio_update(args: argparse.Namespace) -> int:
    import db

    updates = {
        "mrr_current": args.mrr,
        "hours_invested": args.hours,
        "notes": args.notes,
    }
    if all(v is None for v in updates.values()):
        log.error("nothing to update -- pass --mrr, --hours, and/or --notes")
        return 1
    try:
        db.update_asset(args.id, updates)
    except ValueError as exc:
        log.error("%s", exc)
        return 1
    print(f"asset {args.id} updated")
    return 0


def cmd_package(args: argparse.Namespace) -> int:
    from resale import package

    try:
        out_dir = package.build_package(args.asset_id)
    except ValueError as exc:
        log.error("%s", exc)
        return 1
    print(f"package written to {out_dir}:")
    for fname in package.PACKAGE_FILES:
        print(f"  {fname}")
    print("review every [FILL: ...] before posting anywhere.")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        webapp = importlib.import_module("web.app")
    except ImportError as exc:
        log.error("dashboard not available yet (%s)", exc)
        return 1
    webapp.app.run(host=args.host, port=args.port, debug=False)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="flipradar", description="FlipRadar deal scanner")
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="run all adapters, upsert, then score")
    p_scan.add_argument("--fixtures", action="store_true", help="use offline fixture data")
    p_scan.set_defaults(func=cmd_scan)

    p_score = sub.add_parser("score", help="rescore all listings")
    p_score.set_defaults(func=cmd_score)

    p_enrich = sub.add_parser("enrich", help="fetch detail pages for top listings, then rescore")
    p_enrich.add_argument("--limit", type=int, default=40, help="max listings to enrich")
    p_enrich.add_argument("--source", default=None, help="restrict to one source")
    p_enrich.add_argument("--force", action="store_true", help="re-enrich already-enriched rows")
    p_enrich.set_defaults(func=cmd_enrich)

    p_list = sub.add_parser("list", help="print top deals")
    p_list.add_argument("--limit", type=int, default=20)
    p_list.add_argument("--all", action="store_true", help="ignore budget filter")
    p_list.set_defaults(func=cmd_list)

    p_export = sub.add_parser("export", help="export static dashboard (docs/) for GitHub Pages")
    p_export.add_argument("--out", default="docs", help="output directory")
    p_export.set_defaults(func=cmd_export)

    p_pipe = sub.add_parser("pipeline", help="track deal status per listing")
    pipe_sub = p_pipe.add_subparsers(dest="pipeline_command", required=True)

    p_pset = pipe_sub.add_parser("set", help="set a listing's pipeline status")
    p_pset.add_argument("listing_id", type=int)
    p_pset.add_argument("status", choices=["watch", "contacted", "dd", "offer", "owned", "passed"])
    p_pset.add_argument("--notes", default=None, help="notes (omit to keep existing)")
    p_pset.set_defaults(func=cmd_pipeline_set)

    p_pshow = pipe_sub.add_parser("show", help="show the pipeline")
    p_pshow.add_argument("--status", default=None, help="filter to one status")
    p_pshow.set_defaults(func=cmd_pipeline_show)

    p_port = sub.add_parser("portfolio", help="track acquired assets")
    port_sub = p_port.add_subparsers(dest="portfolio_command", required=True)

    p_padd = port_sub.add_parser("add", help="add an acquired asset")
    p_padd.add_argument("--name", required=True)
    p_padd.add_argument("--price", type=float, required=True, help="purchase price (USD)")
    p_padd.add_argument("--listing-id", type=int, default=None, help="source listing id, if any")
    p_padd.add_argument("--mrr", type=float, default=None, help="MRR at purchase (USD/mo)")
    p_padd.add_argument("--repo-path", default=None)
    p_padd.add_argument("--notes", default=None)
    p_padd.set_defaults(func=cmd_portfolio_add)

    p_plist = port_sub.add_parser("list", help="list assets with rough ROI estimates")
    p_plist.set_defaults(func=cmd_portfolio_list)

    p_pupd = port_sub.add_parser("update", help="update an asset")
    p_pupd.add_argument("id", type=int)
    p_pupd.add_argument("--mrr", type=float, default=None, help="current MRR (USD/mo)")
    p_pupd.add_argument("--hours", type=float, default=None, help="total hours invested (sets, not adds)")
    p_pupd.add_argument("--notes", default=None)
    p_pupd.set_defaults(func=cmd_portfolio_update)

    p_pkg = sub.add_parser("package", help="build a resale listing package for an asset")
    p_pkg.add_argument("asset_id", type=int, help="assets table id (see 'portfolio list')")
    p_pkg.set_defaults(func=cmd_package)

    p_serve = sub.add_parser("serve", help="run web dashboard")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=5057)
    p_serve.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
