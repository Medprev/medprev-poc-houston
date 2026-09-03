# ADR-0021: Fix agent uses git worktree from local clone

## Status

Accepted, 2026-09-03.

## Context

The fix agent (`houston fix`) needs to work on a different repo than Houston (e.g., `medprev-rest-api`, `medprev-web-app`). It must create a branch, make changes, and push without interfering with the developer's working directory in that repo.

Options considered: (a) fresh `git clone` into tempdir, (b) `git worktree add` from the local clone, (c) work directly in the main checkout.

## Decision

Use `git worktree add` from the local clone. The worktree is created under `.houston-fix/{fingerprint}` in the target repo, branched from `origin/main` after a `git fetch origin`. Cleaned up after the agent finishes (success or failure).

## Rationale

- The repos are already cloned locally — cloning again wastes time and bandwidth.
- A worktree shares git objects with the main checkout (fast, no download).
- It isolates the fix agent's work from whatever the developer has in progress.
- `git fetch origin` before creating the worktree ensures the fix starts from current main, avoiding stale-code fixes and merge conflicts.
- Cleanup in a `finally` block prevents worktree accumulation.

## Consequences

- The `service_repos.yaml` mapping must include the local path to each repo.
- If the local clone doesn't exist, the fix command fails with a clear error.
- Budget is $3.00/fix (8x investigation), timeout 600s (2x investigation) — the agent reads more code and writes changes, but the worktree creation itself is near-instant.
- The agent cannot run tests that require external services (DB, Redis, APIs) not available locally. It tries to discover the test runner (package.json, Makefile, etc.) and proceeds without tests if it can't run them. CI on the PR is the real validation.
