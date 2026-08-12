# Operating FlipRadar: the sub-5-hour week

FlipRadar has no push notifications, and while the GitHub Actions workflow
can scan on a schedule and publish a static page, CI scans see less than
local ones (runner IPs get blocked) and nothing pings you either way. It
works only if you run it on a routine. This is that routine, sized to fit in
well under 5 hours a week — the same time budget the buyer profile assumes
for operating an acquired product, because eventually you will be doing both.

Guiding rule: **deal flow is cheap, diligence is expensive.** The routine
spends minutes on scanning and reserves the real hours for at most one deal.

## Weekly schedule

| When | What | Time |
|---|---|---|
| Mon | Scan #1 + triage alerts | ~20 min |
| Thu | Scan #2 + triage alerts | ~20 min |
| Any 1 block | Deep DD on at most ONE listing (only if one earned it) | 2-3 hrs |
| Fri | Pipeline hygiene: follow-ups, kill stale rows, update notes | ~15 min |

Total: roughly 1 hour on a quiet week, 3.5-4 hours on a week with a live deal.
If two listings both seem worth deep DD in the same week, pick one and queue
the other — running two diligences at once is how corners get cut.

### Scans (Mon and Thu, ~20 min each)

```
python cli.py scan
python cli.py list
```

- The scan itself takes 30-60s (politeness delay); repeat runs within 12h are
  mostly cached, so twice a week is the right cadence — more adds little.
- Read any `DEAL ALERT` blocks (score >= 70, new this scan). History is in
  `data/alerts.log`.
- Skim the top of `list` for anything new. For a closer look:
  `python cli.py serve`, filter with `min_score=50&revenue_positive=1`.
- Triage each candidate in under 2 minutes against `dd/red_flags.md`. The
  only decision at this stage is: does this earn a message to the seller?
  Most answers are no. Remember live listings under-score on tech stack and
  neglect signals (that data is missing from index pages), so a live 55-65
  with real MRR can be better than it looks — open the actual listing.
- Anything that survives triage goes in the pipeline immediately:
  `python cli.py pipeline set <id> watch --notes "why it's interesting"`.
  When you message the seller, `set <id> contacted`. If a listing doesn't
  earn a pipeline row, it's dead — don't keep it in your head.

### Deep DD (max one per week, 2-3 hrs)

Only for a listing where the seller has replied and the basics check out.

1. `python -m dd.checklist <listing_id>` — generates
   `dd/output/<id>_checklist.md`. Work through it on a call/screen-share with
   the seller. Revenue verification is live Stripe or it didn't happen.
2. With verified numbers: `python -m dd.valuation --mrr X --churn Y --growth Z
   --hours H`. Offer against that range, not the ask.
3. Escrow only (Escrow.com or marketplace escrow), funds released after all
   assets transfer.

If verification stalls or the seller dodges, stop. The routine's job is to
make walking away cheap.

### Friday wrap: pipeline hygiene (~15 min)

- `python cli.py pipeline show` — read the whole board, top to bottom.
- Follow up on `contacted` rows older than 3-4 days (one nudge, then
  `set <id> passed --notes "no reply"`).
- Kill stale rows honestly. A `watch` that hasn't earned a message in two
  weeks, or a `dd` where verification stalled, becomes `passed` — with a
  one-line note on **why it died**. Patterns in those notes improve your
  triage more than any scoring tweak.
- The pipeline should exit Friday with at most a handful of live rows. If
  `show` prints more `watch` entries than you can name from memory, you are
  hoarding, not triaging.

## Outreach templates

Short, specific, and asking for exactly one thing. Adapt, don't paste
verbatim.

**First contact (revenue-positive listing):**

> Hi — I saw [product] on [source]. I'm a solo developer buying small
> [stack] products in the sub-$2k range, cash via escrow, quick close.
> Two questions before I take more of your time: is the $[X] MRR verifiable
> on a live Stripe screen-share, and roughly how many hours a week does it
> take to run? If those check out I can make a decision within a week.

**First contact (users but no revenue):**

> Hi — I came across [product]. I'm interested in free products with real
> users that the owner has moved on from. Could you share current active
> user numbers and how they're measured? I buy small, pay cash via escrow,
> and close fast — happy to make this painless.

**Follow-up (3-4 days later, send once):**

> Just bumping this once in case it got buried — still interested in
> [product] if you're open to the Stripe walkthrough. If it's sold or
> you've changed your mind, no worries, just let me know.

**Opening an offer (after DD):**

> Thanks for the walkthrough. Based on the verified numbers ($[MRR] MRR,
> ~[churn]% monthly churn), comparable sub-$100k deals close around
> [multiple]x annual profit, which puts fair value near $[Y]. I can offer
> $[Z] via Escrow.com, with a simple asset-transfer checklist I'll provide,
> and close within [N] days. Open to it?

Notes on tone: never pressure, never bluff a competing offer, and put the
escrow + fast close in the first message — for a burned-out seller of a $1.5k
asset, low friction is worth more than a higher number from a flaky buyer.

## After you buy: the acquisition -> refurb -> resell lifecycle

The moment a deal closes, the tooling changes. The lifecycle, in order:

1. **Close the loop in the DB.** `python cli.py pipeline set <id> owned`,
   then register the asset:
   ```
   python cli.py portfolio add --name widgetapp --price 1500 --mrr 400 \
       --listing-id <id> --repo-path C:/src/widgetapp
   ```
   Record the MRR you *verified* during DD, not the listing's claim.
2. **Day 0-1: audit the repo.** As soon as you have the code:
   `python -m refurb.audit C:/src/widgetapp --out audit.md`. It is offline
   and read-only. Anything in its secrets section gets rotated *today* —
   the seller had those values, and so does anyone they ever pasted them to.
3. **Generate the plan.** `python -m refurb.plan --asset-id 1 --audit
   audit.md --out plan.md`. This is `dd/playbook.md`'s 90-day shape
   (transfer/rotate, onboarding, pricing mechanics, SEO) adapted to what
   the audit actually found — no tests means week-1 smoke tests, heavy TODO
   debt means a cleanup week.
4. **Work the plan with the prompts.** The plan points at ready-to-paste
   Claude Code prompts in `refurb/prompts/` (smoke tests, dependency
   upgrade, onboarding fix, annual billing, churn-rescue emails, SEO pass).
   Open the acquired repo in Claude Code, paste the prompt for the current
   week's job, review the result yourself. The prompts automate the typing,
   not the judgment.
5. **Track MRR monthly.** First of the month, from live Stripe (the same
   standard you held the seller to):
   ```
   python cli.py portfolio update 1 --mrr 450 --hours 22
   ```
   `--hours` is the running total, not an increment. `portfolio list` shows
   months held, hours, and an EST ROI column — that ROI assumes a 2.5x ARR
   exit, flat MRR, and 100% margin, so read it as a gut-check, not a P&L.
   If MRR is flat or down two months in a row, revisit the plan before
   sinking more hours.
6. **Package when ready to sell.** When the metrics story is real (the
   playbook says ~day 90, with verified weekly metrics in hand):
   `python cli.py package 1`. It writes listing copy, a metrics sheet, a
   buyer FAQ, and a where-to-list guide to `resale/output/1/` — using only
   numbers the DB actually has. Fill every `[FILL: ...]` yourself before
   posting; the package never invents a metric, and neither should you.
   After the sale, `portfolio update 1 --notes "sold $X on <venue>, <date>"`
   so the record survives.

While operating an acquired product, drop FlipRadar scanning to once a week
and skip deep DD entirely — the refurb plan's own rhythm is ~4.5 hrs/wk, and
one asset at a time is the whole point of the under-$2k, under-5-hrs profile.
The pipeline keeps running at `watch`-only depth so the next candidate is
already queued when this one sells.

## Honest expectations

- Two live sources (flippa, microns) is thin coverage. Expect most weeks to
  produce zero deals worth DD; that is the routine working, not failing.
- Scores triage, they don't verify. A 75 with fake MRR is worth less than
  nothing; the checklist is the actual filter.
- Good sub-$2k deals are rare and go fast — which is exactly why the routine
  is two scans a week and a same-week close capability, not a daily grind.
