# ADR-0005: The Pages summary shows only structured fields, and enabling Pages is left to a human decision

**Status:** Accepted
**Date:** 2026-09-01
**Deciders:** Carla Cury
**Decision style:** Adopted mid-session when the project's goal was extended
to require a public incident summary; the exposure question was flagged
before building, not after.
**Related:** [[0003-pii-gate-from-first-commit]]

## Context

The project's goal was extended to include "a GitHub Pages page with a
summary" of the incidents this tool tracks. That is in direct tension with
an earlier, deliberate decision: the plan this repo implements explicitly
deferred any public-facing status surface to a later slice, gated on having
a measured false-positive rate first — "nothing exposed to the internet
before a false-positive rate exists."

Two separate facts make this a real decision, not a formality:
1. GitHub Pages on a private repository under a personal Free or Pro plan
   is not access-restricted — restricting Pages to signed-in viewers
   requires GitHub Enterprise Cloud. A GitHub Pages site on this repo, if
   enabled, is a public URL, full stop.
2. `docs/e0-verification.md` and every `docs/adr/*.md` file document real
   production service names, error types, and one real regression window —
   none of that is secret, but a report's **body** (E5) carries root cause,
   evidence, and recommended actions in free text, which is exactly the
   content the PII gate's documented gap (a person's name isn't
   regex-matchable) applies to.

## Decision

Two decisions, kept separate on purpose:

1. **What the page shows.** `scripts/generate_site.py` reads only
   structured front-matter fields (fingerprint, service, source, reason,
   severity, state, first-seen date, promoted issue link) and never a
   report's body. Front-matter fields are closed-vocabulary or numeric —
   the same class of content the PII gate already scans as part of the full
   rendered file in E5 — while the body is exactly the free-text surface
   ADR-0003 already flags as the gate's known gap.
2. **Whether the page goes live.** The generator and the
   `.github/workflows/pages.yml` deploy workflow are built and committed.
   Actually enabling GitHub Pages for this repository (`gh api -X POST
   .../pages`) is **not done by this change** — it publishes something to a
   public URL, on a decision this repo's owner has already made once (defer
   public exposure) and reversing it deserves the same explicit sign-off
   any other public-facing change would.

## Alternatives considered

1. **Render the full report (front-matter + body) on the page** — rejected:
   directly reintroduces the exposure the parent plan deferred, for no
   stated benefit over a structured summary.
2. **Make the repo public to unlock free-tier private Pages restriction
   moot** — rejected outright as a side effect of building a summary page;
   changing repo visibility is a separate, larger decision than adding a
   generator script.
3. **Build fully and also flip the Pages toggle on** — rejected: the
   generator is reversible (delete the file, nothing was ever public); the
   Pages toggle is not (a public URL, once live, may already be crawled or
   cached before anyone disables it).

## Consequences

### Good
- The redaction rule is enforced structurally (the generator's source
  simply never reads `body`), not by a reviewer remembering to check.
- Building the whole pipeline (generator + workflow) up front means turning
  the summary on later is a one-click Settings change, not a coding task.

### Bad
- The goal that asked for this page is not fully satisfied until a human
  explicitly enables Pages (Settings → Pages → source: GitHub Actions, or
  `gh api -X POST repos/carlacurymed/medprev-poc-houston/pages -f
  build_type=workflow`) and decides whether that requires a plan change or
  a repo-visibility change first.

### Follow-up
Revisit if `medprev-poc-houston` transfers to the Medprev org — an org on
GitHub Enterprise Cloud can restrict Pages to signed-in members, which
would remove the "public URL, full stop" constraint this ADR is built
around.
