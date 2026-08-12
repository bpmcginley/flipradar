# Prompt: Add Annual Billing (Stripe)

Paste this into Claude Code running in the root of the acquired product's repo.

---

You are working in the codebase of a micro-SaaS I just acquired that bills
customers monthly through Stripe. Your job: add an annual plan option at a
discount (2 months free — annual price = 10x monthly) without breaking
existing monthly subscribers.

**Step 1 — read before you touch.** Explore the repo first. Find: how Stripe
is integrated (Checkout, Payment Links, Elements, or raw API), where price/
plan IDs live (env vars, config, DB, hardcoded), how the webhook handler
processes subscription events, and how the app decides a user is "paid".
Summarize the current billing architecture for me before changing anything.

**Step 2 — plan the price objects.** Do NOT create Stripe objects yourself and
do NOT touch live keys. Instead, output the exact Stripe CLI or dashboard
steps for me to create the annual Price(s) (one per existing monthly price),
and make the code read the new price ID(s) from configuration the same way the
existing ones are read.

**Step 3 — implement.**
1. Add the annual option to the pricing/upgrade UI with a monthly/annual
   toggle showing the savings ("2 months free").
2. Route checkout to the annual price when selected, reusing the existing
   checkout path — do not build a parallel flow.
3. Make entitlement logic interval-agnostic: a user is paid if they have an
   active subscription, regardless of interval. Audit every place that checks
   plan/price ID and fix any that would treat annual as unpaid.
4. Handle webhook events for the annual price identically to monthly
   (created, updated, deleted, invoice.paid, invoice.payment_failed).
5. Support monthly -> annual upgrade for existing subscribers via Stripe's
   subscription update (proration on, unless the code shows a house style).

Match existing code style. No new dependencies. Use Stripe test mode for all
verification.

**Acceptance criteria:**
- With test keys, a new customer can subscribe annually end to end and the app
  marks them paid; a monthly customer can switch to annual.
- Existing monthly checkout is untouched and still works (verify it).
- No live Stripe objects created or modified by you; the manual steps I must
  run are listed clearly at the end.
- All price IDs come from config/env, none hardcoded.
- Summary: files changed, webhook events handled, the manual Stripe steps, and
  any edge case you deferred.
