# Prompt: SEO / Landing Page Pass

Paste this into Claude Code running in the root of the acquired product's repo.

---

You are working in the codebase of a micro-SaaS I just acquired. Your job: a
technical SEO and landing-page conversion pass. Content strategy is mine;
you fix what code can fix.

**Step 1 — read before you touch.** Explore the repo first. Find every public
(logged-out) page and how pages are rendered (templates, SSG, SPA). List the
public URLs. Note the framework's idiomatic way to set per-page meta tags.
Summarize before changing anything.

**Step 2 — technical SEO fixes.** For every public page:
1. Unique, descriptive `<title>` (product + benefit, under ~60 chars) and
   `<meta name="description">` (under ~155 chars). Draft the copy from what
   the codebase says the product does; mark drafts for my review.
2. Exactly one `<h1>` per page; heading hierarchy sane.
3. Canonical URL tags; `og:` and `twitter:` card tags with a real image if one
   exists in the repo.
4. `robots.txt` (allow public, disallow app/admin/api) and an XML `sitemap`
   listing the public pages — generated, not hand-maintained, if the stack
   allows.
5. `alt` text on images; `loading="lazy"` below the fold.
6. Cheap performance wins only: compress oversized images found in the repo,
   add missing width/height to prevent layout shift, defer non-critical
   scripts. Do not swap frameworks or build systems.
7. If the site is a client-rendered SPA with no server rendering, do not
   retrofit SSR — flag it as a finding with options instead.

**Step 3 — landing page conversion pass.** On the main landing page only:
- Headline states what the product does and for whom (not a slogan). Draft it.
- One primary call to action above the fold; secondary CTAs de-emphasized.
- Add or fix: social proof section placeholder (testimonials if any exist in
  the repo/site already — never invent testimonials), pricing link, FAQ block
  with schema.org `FAQPage` markup if FAQs exist.

**Constraints:** no new dependencies, no paid services, no invented claims,
numbers, or testimonials — copy drafts may only state what the code shows the
product actually does. Match existing template style.

**Acceptance criteria:**
- Every public page has unique title + description; no page shares either.
- `robots.txt` and sitemap resolve locally; sitemap covers all public pages.
- Landing page renders correctly (screenshot or local check) and total page
  weight did not increase.
- A findings list: anything needing my decision (SSR, content strategy,
  missing OG image), with your recommendation for each.
- Summary: files changed, draft copy written (flagged for review), before/after
  of title/description per page.
