# Prompt: Add Smoke Tests

Paste this into Claude Code running in the root of the acquired product's repo.

---

You are working in the codebase of a micro-SaaS I just acquired that has no
(or unknown) test coverage. Your job: a small smoke-test suite that lets me
deploy without fear. Breadth over depth — I want "the app is not on fire"
coverage of the money paths, not unit-test purity.

**Step 1 — read before you touch.** Explore the repo first. Identify: the
stack and its idiomatic test runner (pytest, jest/vitest, go test, rspec...),
how the app boots, how the database is configured (and how to point tests at a
throwaway one), and the routes/handlers for the money paths: signup, login,
the core product action, billing/webhooks, and any public pages.

**Step 2 — set up the harness.** Use the stack's standard test runner —
introduce it as a dev dependency only if nothing is present. Tests must run
against a throwaway database (in-memory, temp file, or transaction-rollback),
never a real one, and must not call external services: stub or fake Stripe,
email, and any third-party APIs at the boundary the codebase already has.

**Step 3 — write the smoke tests.** Target roughly 10-20 tests:
1. App boots / test client constructs without error.
2. Every public page returns 200 (parametrize over the route list).
3. Signup happy path creates a user; duplicate signup fails cleanly.
4. Login happy path + wrong-password rejection.
5. Auth-required routes redirect or 401 when logged out.
6. The core product action succeeds for a logged-in user (the single most
   important feature — pick it from the code and say why you picked it).
7. Billing webhook endpoint: accepts a well-formed test event, rejects a bad
   signature (if signature checking exists — if it does NOT exist, add that to
   findings, do not silently add it).
8. Health/status endpoint if one exists.

**Step 4 — make it runnable.** One command runs everything (`make test`,
`npm test`, `pytest` — whatever is idiomatic). Document it in the README. If a
CI config exists, wire the tests in; if not, add a minimal GitHub Actions
workflow that runs them on push.

**Constraints:** do not refactor app code to make it testable except minimal
seams (e.g. extracting an app factory) — list any such change explicitly. No
new runtime dependencies; dev/test dependencies only.

**Acceptance criteria:**
- Full suite passes locally from a fresh checkout with one documented command.
- Suite runs in under ~60 seconds and touches no real database or external
  service (prove it: run with network unavailable or assert on stubs).
- A failing money path actually fails the suite (demonstrate by breaking one
  route temporarily and showing the red run, then restore it).
- Summary: test list with one line each on what it protects, seams changed in
  app code, findings (e.g. missing webhook signature verification).
