# ADR-0027: CI runs the mise tasks, and carries no deploy

**Status:** Accepted
**Date:** 2026-09-10
**Deciders:** Carla Cury
**Decision style:** Closing a gap that let an unverified change reach main.
**Related:** [[0005-pages-summary-redacted-and-not-yet-enabled]],
[[0024-investigation-correlates-logs-and-classifies-noise]]

## Context

The repo had one workflow, `pages.yml`, which built `site/` and deployed
it to GitHub Pages on push to `reports/**`. It had no workflow that ran
the test suite, so nothing verified a pull request: PR #21 — a change to
the agent prompt, the budget cap and the PII gate — merged on the strength
of a local `mise run test` and a claim in its own description.

The deploy it did carry cannot work. ADR-0005 records that Pages is not
enabled for this repo and will not be until it transfers to the Medprev
org, because private-repo Pages needs GitHub Enterprise Cloud. So the
workflow's `deploy-pages` step targets an environment that does not
exist, on the one path (`reports/**`) that changes most often.

It also pinned `python-version: "3.12"` and installed from
`requirements.txt`, while `mise.toml` pins Python 3.14 and `mise run
setup` installs `requirements-dev.txt`. A green run there would not have
meant the suite passes on the toolchain anyone actually uses.

## Decision

`.github/workflows/test.yml` runs on every pull request, on push to
`main`, and on demand. It resolves the toolchain with `jdx/mise-action`
and then runs `mise run setup`, `mise run lint`, `mise run test` — the
same three commands run locally, no second dependency list and no second
Python version to drift from `mise.toml`.

`pages.yml` is removed. `scripts/generate_site.py` stays, and the page
stays what ADR-0005 made it: built on demand, when someone wants it.

## Consequences

CI green now means something specific and checkable: `ruff check .` is
clean and the whole suite passes on Python 3.14 with the project's own
dev dependencies. Because CI runs the mise tasks rather than reimplementing
them, a task that changes locally changes in CI in the same commit.

Nothing publishes the incident summary. Regenerating it is
`python scripts/generate_site.py`, and whoever wants it runs that. When
this repo transfers to the Medprev org and Pages becomes available, adding
the deploy back is a decision to make then, with a working target — not a
step left in place hoping for one.

The suite is offline by construction (recorded fixtures and mocked
subprocess calls), so CI needs no Datadog credentials and no `.env`. mise
tolerates the missing file, which is what makes running the local tasks
unmodified possible.
