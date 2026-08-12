# Prompt: Fix Onboarding

Paste this into Claude Code running in the root of the acquired product's repo.

---

You are working in the codebase of a micro-SaaS I just acquired. I did not
write this code. Your job: reduce signup-to-first-value friction.

**Step 1 — read before you touch.** Explore the repo first: find the signup
flow, the post-signup landing state, email verification (if any), and the
first screen a new user sees. Identify the framework, template system, and how
routes are wired. Summarize the current onboarding path for me as a numbered
list of steps a new user actually walks through, before proposing any change.

**Step 2 — diagnose.** List every point of friction you can see in code:
required fields that aren't needed for first value, dead ends after signup
(blank dashboard, no next step), missing email verification handling, forms
without inline validation, steps that could be deferred until after the user
has seen the product work.

**Step 3 — fix, smallest first.** Implement, in order of impact-to-risk:
1. Cut any signup field not strictly required (name, company, phone — defer
   them to a later settings page).
2. After signup, land the user on a state with one obvious next action, not an
   empty screen. Add an empty-state with a single call to action or, better,
   pre-populate demo/sample data clearly labeled as sample.
3. Add inline validation errors on the signup form (bad email, weak password)
   instead of full-page reloads or silent failures.
4. If there is an email-verification wall before first value, let the user
   into the product immediately and verify asynchronously (banner reminder),
   unless the code shows a hard reason not to.

Do not redesign the visual style. Do not add new dependencies unless the repo
already has no way to do the job. Match the existing code style.

**Acceptance criteria:**
- A new user can go from landing on the signup page to seeing the product's
  core value with at most 2 required form fields and no dead-end screens.
- Every changed flow still works: run the app locally and walk the signup path
  yourself; paste the steps and results.
- Existing tests still pass (run the suite; if there is no suite, say so).
- No new third-party services introduced.
- Give me a bullet summary: files changed, friction removed, anything you
  found but deliberately did not change (and why).
