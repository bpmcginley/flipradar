# The Flip Playbook

Template for taking an acquired micro-SaaS from "neglected" to "resellable"
in one quarter, then relisting it with verified metrics. Copy this file per
deal and fill in the blanks.

Target profile: bought under $2k, operated under 5 hrs/wk, flipped at a
higher multiple because the asset is now clean, growing, and documented.

---

## Part 1: 90-Day Improvement Plan

### Days 0-7: Stabilize and baseline

- [ ] Complete all transfers (domain, repo, hosting, Stripe/customers, email).
- [ ] Rotate every secret and API key; remove seller access everywhere.
- [ ] Get the app deploying from YOUR machine — do one trivial deploy to prove it.
- [ ] Set up uptime monitoring (UptimeRobot free tier) and error tracking
  (Sentry free tier).
- [ ] Record baseline metrics in a spreadsheet — this becomes your "verified
  metrics" story at relist time:
  - MRR, customer count, churn %, signups/mo, traffic/mo, conversion %,
    infra cost/mo, support tickets/wk, owner hrs/wk.
- [ ] Email existing customers: friendly ownership announcement, nothing
  changes, here's how to reach support. (Cuts transition churn.)

### Days 8-30: Fix onboarding (biggest cheap win)

Neglected products bleed signups between "created account" and "got value".

- [ ] Walk through signup yourself as a new user; write down every point of
  confusion. Fix the top 3.
- [ ] Add a single clear "first success" path: one action the new user should
  take, surfaced immediately after signup (checklist, sample data, or wizard).
- [ ] Add a 3-5 email onboarding drip (welcome -> how to get value -> case
  use -> nudge to upgrade). Any transactional email service's free tier works.
- [ ] Kill or hide half-broken features the seller left rotting — fewer,
  working features convert better.
- [ ] Instrument the funnel (signup -> activation -> paid) so improvement is
  measurable at relist.

### Days 31-60: Pricing and revenue mechanics

- [ ] **Add an annual plan** at 10x monthly (2 months free). Annual prepays
  improve cash, cut effective churn, and look great at relist. Email existing
  monthly customers a one-time switch offer.
- [ ] Review price point: neglected products are almost always underpriced.
  A modest raise for NEW customers only (grandfather existing) is low-risk.
- [ ] **Churn email flows:**
  - [ ] Failed-payment dunning (Stripe Smart Retries + reminder emails) —
    recovers 20-40% of involuntary churn, often the single highest-ROI fix.
  - [ ] Cancellation flow: one-question exit survey + pause option +
    downgrade option before the cancel button.
  - [ ] Win-back email 30 days after cancellation with a small incentive.
- [ ] Verify Stripe billing hygiene: correct statement descriptor (cuts
  disputes), receipts on, tax settings sane.

### Days 61-90: SEO basics and steady growth

Goal is a visible upward trend line at relist, not a growth miracle.

- [ ] Fix technical SEO: titles/descriptions on every page, sitemap.xml,
  robots.txt, no broken links, fast LCP (compress images, cache).
- [ ] Register Google Search Console; fix any indexing errors it reports.
- [ ] Write 4-6 bottom-of-funnel pages: "[product category] for [niche]",
  "X vs [competitor]", "how to [job the product does]". These convert far
  better than blog fluff at this size.
- [ ] Get 5-10 legitimate backlinks: listings in relevant directories,
  integration partners' pages, one or two guest mentions.
- [ ] Ask 5 happy customers for testimonials/reviews (G2/Capterra if
  applicable); put them on the landing page.
- [ ] Final metrics snapshot; compute deltas vs Day-0 baseline.

### Weekly operating rhythm (whole 90 days, budget ~5 hrs/wk)

- 1 hr: support and monitoring triage.
- 2 hrs: the current phase's checklist items.
- 1 hr: one growth/content task.
- 30 min: update the metrics spreadsheet (Mondays, same time — clean weekly
  series is gold at relist).

---

## Part 2: Relist Strategy

### Where to relist, by size

| Exit price | Venue | Notes |
|---|---|---|
| < $5k | Flippa, Little Exits, Twitter/X + IndieHackers | Low fees, fast, buyers expect scrappy. |
| $5k-$25k | Acquire.com, Flippa, Little Exits | Acquire.com buyers pay better multiples for clean SaaS. |
| $25k-$100k | Acquire.com, Empire Flippers (if it qualifies), broker-assisted | EF vetting itself raises buyer trust and price. |
| $100k+ | Empire Flippers, FE International, Quiet Light | Brokered; longer process, best multiples. |

Also consider a direct approach: competitors and adjacent tool owners often
pay more than marketplace buyers because of strategic fit.

### How to present verified metrics

The entire flip premium comes from being the seller who is easy to diligence.
Be the anti-pattern of every red flag in `red_flags.md`:

- [ ] **Offer the Stripe screen-share before being asked.** Put "live Stripe
  walkthrough available on any call" in the listing itself.
- [ ] Show the weekly metrics spreadsheet: MRR, churn, signups since Day 0.
  A hand-kept, dated series is far more credible than one screenshot.
- [ ] Present churn honestly with the calculation shown
  (cancels / customers-at-start, 6-month average).
- [ ] Rebuilt P&L with ALL expenses (hosting, APIs, email, fees). Buyers
  find hidden costs anyway; volunteering them buys trust and speed.
- [ ] Document the operation: a runbook covering deploy, common support
  answers, and the weekly rhythm. "Under 5 hrs/wk, here's the runbook"
  justifies the top of the multiple band.
- [ ] Disclose the story: "Acquired [date], fixed onboarding, added annual
  plans and dunning, grew MRR from $X to $Y." Flipping openly with receipts
  reads as competence, not as a pump-and-dump.
- [ ] Pre-package transfer logistics: asset list, migration plan for Stripe
  customers, 30-day support offer, Escrow.com. Every friction you remove
  shows up in the price.

### Pricing the relist

- Run `python -m dd.valuation` with the NEW numbers; ask near the top of the
  adjusted band — you have earned it if the checklist above is done.
- Expect to justify the multiple with: 3+ months of your ownership data,
  improving trend, documented sub-5-hr/wk operation, clean transfer package.
- Leave 10-15% negotiation room; serious buyers always want a concession.
- Do not chase the last dollar against a slow close: at this size, time is
  the biggest cost. A clean 1.68x -> 2.5x+ multiple uplift on improved MRR is
  the win condition.
