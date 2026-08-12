# Red Flags: Top Scam Patterns in Micro-SaaS Sales

Static reference. Read before every negotiation. If two or more of these show
up on one deal, walk.

## 1. Inflated MRR via refunds (the classic)

Seller charges friends' cards (or their own) in the months before listing to
pump the Stripe revenue graph, then refunds after closing.

**Detect:** In the Stripe screen-share, open the refunds list for the last
6 months and compare charge dates vs listing date. A cluster of new
"customers" 30-60 days before listing, especially at round amounts, is the
tell. Also check disputes/chargebacks. Cross-check payouts against bank
statements — refunded money never lands.

## 2. Bought traffic dressed up as organic growth

"10k visitors/month, growing!" — from a $200 Fiverr traffic package, cheap ad
blasts, or bot traffic. Traffic dies the day the spend stops, and none of it
converts.

**Detect:** Live analytics screen-share (GA4/Plausible). Check acquisition
channels: real products show search + direct + referral mix. 90% "direct" or
one weird referrer = bought. Check bounce rate and session duration on the
spike periods. Ask for the ad account: if there is paid spend, it must appear
in the expense numbers.

## 3. Single-customer concentration

MRR is real but one customer (often a friendly company or the seller's other
business) is 40-80% of it. You are buying one relationship that can cancel
with one email — sometimes the day after closing.

**Detect:** In the Stripe screen-share, sort customers by revenue. Any
customer >30% of MRR gets named, and you discount the deal accordingly (or
require them on an annual contract that survives the transfer).

## 4. Unlicensed code and dependencies

The "asset" contains GPL code in a proprietary product, a nulled/pirated
theme or plugin, assets ripped from stock sites without a license, or — the
modern flavor — large chunks copied from a competitor. You inherit the legal
exposure.

**Detect:** Repo review before closing. Run a license scan on dependencies
(`pip-licenses`, `license-checker`, `cargo license`). Search for copyright
headers that don't match the seller. Ask directly: "Did you write all of
this? What's licensed, and can you show the licenses?" Get an IP warranty
clause in the purchase agreement.

## 5. Seller won't screen-share Stripe

Every excuse — "privacy", "I'll send screenshots", "here's a CSV", "my
accountant handles it", "Stripe is linked to my other businesses" — means the
numbers are fake or worse than claimed. Screenshots and CSVs are trivially
forged; there are literally paid tools for faking Stripe dashboards.

**Detect:** This one detects itself. The rule is absolute: **no live
screen-share of the payment processor, no deal.** A seller with real revenue
has zero reason to refuse 15 minutes of read-only screen-sharing.

## Bonus patterns (cheaper, still common)

- **The urgency script.** "Two other buyers ready to wire today." Real
  micro-SaaS deals take weeks. Urgency exists to stop your DD.
- **Off-platform escape.** Seller pushes to leave the marketplace and pay by
  direct wire/PayPal F&F "to save fees" — this removes escrow and any
  recourse.
- **Expense amnesia.** "Profit" quoted as revenue minus hosting, omitting
  ads, APIs, email service, contractors, and payment fees. Rebuild the P&L
  yourself from the processor and hosting bills.
- **Serial flipper polish.** Same seller lists many near-identical products
  with beautiful landing pages and 3 months of history. They manufacture
  listings, not businesses. Search the seller's history on the marketplace.
- **Annual-plan cash grab.** Seller runs a 50%-off annual deal right before
  listing: cash and "MRR" look great, but you owe 12 months of service to
  customers who already paid the seller.
