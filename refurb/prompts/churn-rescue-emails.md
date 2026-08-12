# Prompt: Churn Rescue Emails

Paste this into Claude Code running in the root of the acquired product's repo.

---

You are working in the codebase of a micro-SaaS I just acquired. Your job:
build a minimal churn-rescue system — catch failed payments and cancellations
with well-timed emails, using only what the repo already has.

**Step 1 — read before you touch.** Explore the repo first. Find: how email is
currently sent (SMTP, SendGrid, Postmark, Mailgun, whatever exists — reuse
it), how subscriptions/cancellations are processed (Stripe webhooks or other),
whether any scheduled-job mechanism exists (cron, celery, APScheduler, queue),
and where email templates live. Summarize what exists before building.

**Step 2 — implement three interventions.**
1. **Dunning (failed payment):** on `invoice.payment_failed`, email the
   customer a friendly "card didn't go through" note with a link to update
   their card (Stripe billing portal or existing update-card page). Second,
   firmer email if a retry fails again. Idempotent: never double-send for the
   same invoice.
2. **Cancellation save:** when a user cancels, send one email: acknowledge it,
   ask the single question "what made you cancel?" (reply-to me), and mention
   they keep access until period end. No dark patterns, no guilt.
3. **Win-back:** 30 days after a subscription actually ends, one email: what's
   new since they left + a resubscribe link. If no scheduler exists, implement
   the simplest reliable option the stack allows (e.g. a daily cron entry
   calling a management command) and document how to enable it.

All copy should be plain text, short, and human — write drafts, put them in
templates alongside the existing ones, and mark clearly where I should edit
tone. Sender address must come from existing config.

**Constraints:** reuse the existing email provider — do not add a new one. No
new dependencies unless the repo has no scheduler at all and the stack's
stdlib can't do it. Every send must be logged (who, which template, when) so
sends are provably idempotent.

**Acceptance criteria:**
- Simulating `invoice.payment_failed` (Stripe CLI test event) triggers exactly
  one dunning email, and a repeat delivery of the same event sends nothing.
- Cancelling a test subscription triggers the save email once.
- The win-back path is runnable manually for a given user and safe to run
  daily (no duplicate sends).
- A log/table records every rescue email sent.
- Summary: files changed, the three email drafts, how to enable the scheduler,
  and what I must configure (env vars, cron line).
