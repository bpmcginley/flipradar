# FlipRadar

A micro-SaaS deal-flow scanner and due-diligence toolkit for a solo buyer.

It scrapes small-acquisition marketplaces, stores listings in a local SQLite
database, scores each one against a fixed buyer profile, and gives you a CLI
table, a local web dashboard, and DD tools (checklist generator, valuation
calculator, red-flags reference, 90-day flip playbook). v2 adds the rest of
the lifecycle: a deal pipeline tracker, a portfolio of owned assets, a refurb
toolkit for auditing and planning work on an acquired codebase, a resale
packager, a static export for GitHub Pages, and an optional desktop window.

The buyer profile it scores for:

- Budget: under **$2,000** asking price.
- Skills: strong Python / C# / JS / TS / Rust developer (can rescue neglected code).
- Wants: revenue-positive or user-positive products the seller has stopped caring about.
- Time: under **5 hrs/wk** to operate after purchase.

This is a personal research tool, not a marketplace client. It is polite by
design (single-threaded, 2s between requests, honors robots.txt, 12h response
cache) and it does not fight anti-bot measures — sites that block it simply
return nothing.

## Quickstart

Requires Python 3.11+.

```
cd flipradar
python -m pip install -r requirements.txt   # requests, beautifulsoup4, flask

python cli.py scan          # scrape live sources, upsert into DB, score
python cli.py list          # print top deals within budget
python cli.py serve         # dashboard at http://127.0.0.1:5057
```

No network, or just want to see it work? `python cli.py scan --fixtures` loads
hand-written sample listings from `fixtures/` instead of hitting any site.

The database is created automatically at `data/deals.db`. A live scan takes
roughly 30-60 seconds because of the 2-second politeness delay; repeat scans
within 12 hours mostly hit the cache in `data/cache/`.

## Commands

### `python cli.py scan [--fixtures]`

Runs every adapter listed in `config.TARGET_SOURCES`, upserts results into
`data/deals.db` (keyed on `source + source_id`, so re-scans update rather than
duplicate), then rescores everything. A failing adapter is logged and skipped;
it never kills the scan. After scoring, any **new** listing scoring >= 70
prints a deal-alert block and is appended to `data/alerts.log`.

`--fixtures` uses the offline sample data in `fixtures/` for every adapter.

### `python cli.py score`

Rescores all listings without scraping. Useful after editing `scoring.py`.

### `python cli.py enrich [--limit N] [--source S] [--force]`

Fetches detail pages for the top listings (default 40) to fill in fields the
index pages don't expose (tech stack, seller story), then rescores. Same
politeness rules as `scan`.

### `python cli.py list [--limit N] [--all]`

Prints the top deals (default 20) as an aligned table: rank, score, price,
MRR, source, title, URL. By default only listings within the $2,000 budget
are shown; `--all` removes that filter.

### `python cli.py export [--out DIR]`

Writes a self-contained static dashboard (`docs/index.html` + `docs/data.json`)
for GitHub Pages hosting. Only listings scoring >= 30 are exported, with
descriptions truncated and no raw seller JSON — the page links out to the
original listings rather than republishing full seller text. Note that
`docs/index.html` fetches `data.json`, so it needs to be served over HTTP
(GitHub Pages, or `python -m http.server` in `docs/`) — opening the file
directly via `file://` will show an empty table. See
[Hosting on GitHub Pages](#hosting-on-github-pages).

### `python cli.py pipeline set|show`

Tracks where each candidate stands so triage decisions live in the DB instead
of your head:

```
python cli.py pipeline set 45 contacted --notes "asked for Stripe screen-share"
python cli.py pipeline show                 # all tracked listings
python cli.py pipeline show --status dd     # filter to one status
```

Statuses: `watch`, `contacted`, `dd`, `offer`, `owned`, `passed`. One row per
listing; `set` again to move it. `--notes` omitted keeps the existing notes.
The dashboard mirrors this at `/pipeline`.

### `python cli.py portfolio add|list|update`

Tracks assets you actually bought:

```
python cli.py portfolio add --name widgetapp --price 1500 --mrr 400 \
    --listing-id 45 --repo-path C:/src/widgetapp
python cli.py portfolio list
python cli.py portfolio update 1 --mrr 450 --hours 12
```

`list` prints purchase price, current MRR, months held, hours invested, and an
**EST ROI** column. That ROI is a directional gut-check, not accounting: it
assumes a 2.5x ARR resale multiple, flat MRR, and 100% margin, and it says so
every time it prints. `update --hours` sets the total, it does not add.
The dashboard mirrors this at `/portfolio`.

### `python cli.py package <asset_id>`

Builds a ready-to-post resale package for an owned asset under
`resale/output/<asset_id>/`: `listing_copy.md`, `metrics_sheet.md`,
`buyer_faq.md`, `where_to_list.md`. Hard rule: **no invented numbers** — any
metric the DB doesn't actually have renders as `[FILL: ...]` for you to
complete, and the suggested price range (from `dd.valuation`) states its
assumptions inline. Review every `[FILL: ...]` before posting anywhere.

### `python cli.py serve [--host H] [--port P]`

Runs the Flask dashboard (default `127.0.0.1:5057`). The index page shows
summary stats and a filterable listing table (`max_price`, `min_score`,
`revenue_positive` query params); `/dd/<id>` shows a per-listing DD view;
`/pipeline` and `/portfolio` mirror the CLI trackers. Local, single-user,
no auth — do not expose it to the internet.

### DD tools (run directly)

```
python -m dd.checklist <listing_id>    # writes dd/output/<id>_checklist.md
python -m dd.valuation --mrr 500 --churn 4 --growth 1 --hours 3
```

See also `dd/red_flags.md` (seller red flags to check for) and
`dd/playbook.md` (the 90-day improve-and-relist playbook).

## Refurb toolkit (after you buy)

Tools for the improve phase, in `refurb/`. All offline: no network, no code
execution.

### `python -m refurb.audit <path> [--out report.md]`

Static audit of a freshly acquired repo. Walks the tree (skipping
node_modules, build output, etc.) and reports: size and language breakdown,
health checks (tests / CI / LICENSE / README / Dockerfile), dependency
manifests with counts, TODO/FIXME/HACK debt, largest files, and secrets-ish
patterns (API keys, tokens, connection strings) that **must be rotated after
purchase** — matched values are flagged, never printed.

### `python -m refurb.plan --name "widgetapp" [--mrr 400] [--price 1500] [--tech "python/flask"] [--audit report.md] [--asset-id N] [--out plan.md]`

Generates a weekly-granularity 90-day improvement plan. Feed it the audit
report and the plan adapts: no tests -> week-1 smoke tests, secrets found ->
day-1 rotation, heavy TODO debt -> a cleanup week. `--asset-id` pulls name,
MRR, and price straight from the portfolio.

### `refurb/prompts/`

Ready-to-paste Claude Code prompts for the automatable refurb jobs the plan
references: `add-smoke-tests`, `dependency-upgrade`, `fix-onboarding`,
`add-annual-billing`, `churn-rescue-emails`, `seo-landing-pass`. Each is a
self-contained brief; open the acquired repo in Claude Code and paste one in.

## Resale toolkit

`resale/package.py` backs `python cli.py package <asset_id>` (documented
above). Output goes to `resale/output/<asset_id>/` and is deliberately
conservative: real numbers from the DB, `[FILL: ...]` placeholders for
everything else, and valuation assumptions spelled out inline. When churn
was never measured it assumes 4.5%/mo — chosen because it is multiple-neutral
in `dd.valuation`, not flattering.

## Desktop app

Optional native window instead of a browser tab. It runs the same Flask app
on `127.0.0.1:5058` (not 5057, so it can coexist with `cli.py serve`) inside
a pywebview window.

```
python -m pip install -r requirements-desktop.txt   # pywebview
python desktop.py            # open the window
python desktop.py --smoke    # headless check: boot Flask, GET /, exit 0
```

To get a double-clickable Desktop shortcut (launches with `pythonw`, no
console window), run once from the repo directory — no elevation needed:

```
powershell -ExecutionPolicy Bypass -File make_shortcut.ps1
```

It creates `FlipRadar.lnk` on your Desktop with the working directory set to
this repo.

## Hosting on GitHub Pages

`python cli.py export` writes a static dashboard to `docs/`, and
`.github/workflows/scan.yml` can keep it fresh automatically. Setup:

1. **Create a GitHub repo** and push this project to it. `data/` is
   gitignored (the DB and cache stay local); `docs/` is committed.
2. Run `python cli.py export` locally and commit `docs/` so there is
   something to serve on day one.
3. **Enable Pages:** repo Settings -> Pages -> Source: "Deploy from a
   branch" -> branch `main`, folder `/docs`. The dashboard appears at
   `https://<user>.github.io/<repo>/` a minute or two later.
4. The included workflow (`.github/workflows/scan.yml`) runs on a schedule
   (13:00 and 01:00 UTC) plus manual dispatch: it rebuilds the DB from
   scratch each run (remember, `data/` is not in git), scans, enriches the
   top 30, exports, and commits `docs/` only if it changed. Every pipeline
   step is `continue-on-error`, so one blocked source never kills the
   publish.

**Actions caveat:** GitHub-hosted runner IPs are widely known and some
sources block or degrade them — a scan that works fine from your home
connection can return fewer (or zero) listings in CI. FlipRadar does not
fight this; expect the published dashboard to be a subset of what a local
scan finds, and treat the local DB as the source of truth. Also note the
schedule only runs while the repo is active — GitHub disables scheduled
workflows on repos with no activity for 60 days.

## Adapter status

Honest picture as of the last integration pass (2026-08):

| Source | Status | Notes |
|---|---|---|
| flippa | **Live** | Uses the public `/v3/listings` JSON API; largest source by volume (~365 listings per scan). |
| microns | **Live** | HTML scrape; ~45 listings per scan. |
| reddit | Fixtures only | robots.txt disallows the JSON endpoints for generic crawlers. Legitimate live access would need Reddit OAuth script-app credentials (not implemented). Returns `[]` live with a logged warning. |
| sideprojectors | Fixtures only | Blocked by a Cloudflare JS challenge (403). robots.txt actually allows it, but FlipRadar does not fight bot management. Returns `[]` live. |
| tinyacquisitions | Fixtures only | Domain currently has no DNS record. Returns `[]` live. |

Fixtures-only sources still contribute 3 hand-written sample listings each in
`--fixtures` mode so the whole pipeline stays testable offline. Enable or
disable sources by editing `TARGET_SOURCES` in `config.py`.

**Data-quality caveat:** live flippa/microns index pages rarely expose tech
stack or the seller's "why I'm selling" story, so live listings miss those
score bonuses and cluster lower than the richer fixture samples. Treat live
scores as a triage ranking, not a verdict — the DD checklist exists because
listing data cannot be trusted at face value.

## How scoring works

`scoring.py` scores every listing 0-100 with human-readable reasons stored in
`score_reasons` (visible in the dashboard and alerts). Components:

- **Affordability** (up to +25): full points at or under $2,000; over budget
  takes a scaled penalty down to -35. Unknown price gets a token +5.
- **Value multiple** (up to +25): asking price / annual profit, compared to
  market context (sub-$100k deals average ~1.7x profit; typical resale range
  2.5-4x). Under 1x scores best; above 4x is penalized.
- **Revenue-positive** (+15) if MRR/ARR/profit > 0, else **users-but-no-revenue**
  (+8) — a free product with real users has monetization upside.
- **Tech-stack match** (up to +12) for Python/JS/TS/C#/Rust keywords in the
  stack, title, or description.
- **Neglect signals** (up to +10) for phrases like "no time", "moving on",
  "side project", "haven't touched" — the target seller psychology.
- **Red flags:** hype language ("huge potential", "trending") with no revenue
  (up to -15); crypto/gambling niches (-20).

Score >= 70 triggers a deal alert after a scan. The weights are heuristics,
not a model — read `scoring.py` (it is short and commented) and adjust to
taste, then run `python cli.py score`. Running `python scoring.py` directly
executes its built-in sanity tests.

## The DD workflow

Scoring finds candidates; it does not verify anything. The intended path from
scan to owned asset:

1. **Scan** — `python cli.py scan` (or wait for a scheduled scan). Check
   alerts and `python cli.py list`.
2. **Shortlist** — open the dashboard, filter (e.g. `min_score=50`,
   `revenue_positive=1`), and pick at most 1-2 listings worth real time.
   Skim `dd/red_flags.md` first; most listings die here. Track survivors:
   `python cli.py pipeline set <id> watch` (then `contacted`, `dd`, `offer`,
   `owned`, or `passed` as things move).
3. **Checklist** — `python -m dd.checklist <id>` generates a per-listing
   markdown checklist: revenue verification (live Stripe screen-share, not
   screenshots), churn calculation, code review, transfer logistics, and the
   why-are-you-selling probe. Work through it with the seller.
4. **Valuation** — once you have verified numbers, run
   `python -m dd.valuation --mrr ... --churn ... --growth ... --hours ...`
   to get SDE and a fair-value range from adjusted SDE multiples. Compare
   against the asking price yourself.
5. **Offer** — anchor to the valuation output, not the ask. Leave room to
   negotiate; walk away if verification was refused at step 3.
6. **Escrow** — never pay directly. Use Escrow.com (or the marketplace's
   escrow), with funds released only after all assets transfer: domain, repo,
   hosting, Stripe/customer data, email lists. Then follow `dd/playbook.md`
   Days 0-7 (rotate secrets, remove seller access, prove you can deploy).

After purchase: `python cli.py pipeline set <id> owned`, then
`python cli.py portfolio add` to start tracking it, `python -m refurb.audit`
on the repo, and `python -m refurb.plan` for the tailored 90-day plan
(`dd/playbook.md` is the generic version). `OPERATING.md` covers the weekly
routine, including the full buy -> refurb -> resell lifecycle.

## Limitations

- Only 2 of 5 sources produce live data; coverage of the actual micro-SaaS
  deal market is partial at best. Acquire.com is not implemented.
- Listing data is self-reported by sellers and often incomplete; scores
  inherit both problems.
- No push notifications — alerts print to the console and a log file. The
  GitHub Actions workflow can scan on a schedule and publish a static page,
  but CI scans see less than local ones (see the Actions caveat above); you
  still run real scans yourself (see OPERATING.md).
- The dashboard is a local, single-user tool with no auth. Do not expose it
  to the internet.
- Nothing here is financial advice; the valuation heuristics are documented
  in `dd/valuation.py` so you can argue with them.
