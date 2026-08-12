# Prompt: Dependency Upgrade

Paste this into Claude Code running in the root of the acquired product's repo.

---

You are working in the codebase of a micro-SaaS I just acquired. Dependencies
are likely stale. Your job: a risk-ordered upgrade pass — security patches
first, convenience upgrades last, nothing that silently changes behavior.

**Step 1 — read before you touch.** Explore the repo first. Find every
dependency manifest and lockfile (requirements.txt / pyproject.toml /
package.json + lock / Gemfile.lock / go.mod / Cargo.toml ...). Note the
runtime version pinned (python version, node engines field, .tool-versions,
Dockerfile base image). Determine how the app is tested (if a test suite
exists, it is your safety net; if not, say so and be more conservative).

**Step 2 — inventory and classify.** Produce a table of every direct
dependency: current version, latest version, and a class:
- **A — security:** known CVE or advisory affecting the installed version
  (use the ecosystem's audit tool offline output: `pip-audit`, `npm audit`,
  `cargo audit` — whichever applies and is available; if none is available,
  classify from the changelog and say the audit tool was unavailable).
- **B — safe bump:** patch/minor within the same major, actively used API
  unchanged per changelog.
- **C — major/breaking:** requires code changes or has known breaking notes.
- **D — unused:** imported nowhere — candidate for removal.

**Step 3 — execute in order.**
1. Remove class D (prove unused via grep of imports, then remove).
2. Upgrade all of class A. If a security fix is only in a new major, do the
   minimal code migration needed and flag it.
3. Upgrade class B in one batch.
4. For class C, upgrade only those with a concrete benefit (security backports
   ending, blocking another fix); list the rest as findings with effort
   estimates — do not upgrade for the sake of it.
5. Regenerate lockfiles properly; never hand-edit them.

Run the app and the test suite after each numbered step, not just at the end.
If a step breaks something you cannot fix within the step, revert that step
and record it as a finding.

**Constraints:** no framework swaps, no runtime major-version bumps (python 3
minor, node major) unless class A forces it — flag those for my decision
instead. Keep each step a separately revertable set of file changes.

**Acceptance criteria:**
- Zero known security advisories remain against installed versions (or each
  remaining one is listed with why it can't be fixed now).
- App boots and test suite passes at the end (state pass/fail per step).
- Lockfile and manifest are consistent (fresh install from lockfile works).
- The dependency table (before/after/class) is in your summary, plus findings:
  class-C upgrades deferred, unused deps removed, anything reverted.
