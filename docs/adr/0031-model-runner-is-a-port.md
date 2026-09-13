# ADR-0031: The model runner is a port; investigations replay without spending quota

**Status:** Accepted
**Date:** 2026-09-13
**Deciders:** Carla Cury (Move B of the dependency-inversion refactor tracked in #29; designed
and verified in `refactor/model-runner-port`, against the test net from ADR-0029 and the
`ReportStore` collaborator shape from ADR-0030)
**Decision style:** Design fix — inverts a dependency direction; no behavior change verified by
the unedited E2E test bodies and assertions from ADR-0029 (only the `monkeypatch` target string
needed updating, see below).
**Related:** [[0029-refactor-net-anchored-at-boundaries-that-do-not-move]],
[[0030-reports-dir-becomes-an-injected-report-store]],
[[0006-no-max-turns-flag-use-budget-and-timeout]],
[[0013-cost-includes-cache-tokens-and-failed-runs]], [[0023-agent-model-and-effort-are-pinned]]

## Context

`houston/agent.py`'s `investigate()` and `houston/fix_agent.py`'s `fix()` each called
`subprocess.run(["claude", "-p", ...])` directly. Two consequences:

1. **No way to inject a fake or a recorded response** without patching `subprocess.run` by name
   inside each module — the pattern the 19 tests in `test_agent.py` and 12 in `test_fix_agent.py`
   used, via `@patch("houston.agent.subprocess.run")` / `@patch("houston.fix_agent.subprocess.run")`.
   That coupling is exactly what breaks the moment the call site moves.
2. **A duplicated decode path.** The JSON envelope decoding (`_payload_or_none`, `_input_tokens`,
   `_error_text`) already lived once, in `agent.py`, and `fix_agent.py` imported those three
   private names across a module boundary (`fix_agent.py:19`) because the shape of "what `claude
   -p` printed" is identical for both callers even though the two invocations differ in every
   other respect: `investigate()` passes the finding as JSON on stdin, no `cwd`, and a read-only
   `--disallowedTools Bash,Write,Edit`; `fix()` passes the prompt as the last argv element, `cwd`
   set to a git worktree, and no `--disallowedTools`.

## Decision

`houston/model_runner.py` introduces one port for both callers, since the difference between them
is data, not decoding logic:

```python
@dataclass(frozen=True)
class ModelRun:
    argv: list[str]
    stdin: str | None = None
    cwd: Path | None = None
    env: Mapping[str, str] | None = None
    timeout_s: int = 300

@dataclass(frozen=True)
class ModelOutcome:
    returncode: int | None  # None only when timed_out is True
    stdout: str
    stderr: str
    timed_out: bool = False

class ModelRunner(Protocol):
    def run(self, request: ModelRun) -> ModelOutcome: ...

class SubprocessRunner:  # the real subprocess.run call, the only one for `claude`
    ...

DEFAULT_RUNNER = SubprocessRunner()
```

`SubprocessRunner.run()` catches `subprocess.TimeoutExpired` internally and returns
`ModelOutcome(timed_out=True, returncode=None, stdout=<whatever was captured>)` instead of letting
it propagate — this is what lets both `agent.investigate()` and `fix_agent.fix()` decide `state`
from data returned by the port, the same way they already decided it from `payload`/`returncode`,
rather than from a `try/except subprocess.TimeoutExpired` at the call site. `agent.py` no longer
imports `subprocess` at all. `fix_agent.py` keeps its `import subprocess` for the five `git` calls
(`_count_existing_attempts`, `_prepare_worktree`, `_cleanup_worktree`) — plumbing, not the model
runner, explicitly out of scope for this port.

`agent.investigate(..., runner: ModelRunner = DEFAULT_RUNNER)` and
`fix_agent.fix(..., runner: ModelRunner = DEFAULT_RUNNER)` take the port as a keyword-defaulted
parameter, the same shape Move A (ADR-0030) used for `store: ReportStore = DEFAULT_STORE`. A
module-level singleton, not `SubprocessRunner()` called inline in the default — `ruff`'s B008 rule
caught the inline-call version immediately (mutable-default-style bug class: a function call in an
argument default evaluates once, at def time, not per call, so it should be a named singleton the
reader can see is shared on purpose).

## Consequences

### Good

- `test_model_runner.py` (new, 14 tests, 100% line+branch coverage of `model_runner.py`) directly
  proves `SubprocessRunner` builds the real `subprocess.run()` call the same way the two agents
  used to — this is the merge rule this PR was held to: it must not reduce the number of assertions
  made against a real argv/env/cwd/stdin/timeout/check shape. Confirmed: every assertion that
  existed in `test_agent.py`/`test_fix_agent.py` before this PR still exists after, just addressed
  through `FakeRunner.calls[0].argv` instead of `mock_run.call_args.args[0]`.
- `fix_agent.py:19`'s cross-module import of `agent.py`'s private `_error_text`/`_input_tokens`/
  `_payload_or_none` is now legitimate rather than a boundary violation waiting to be noticed: both
  callers share one decode path because they share one port.
- Opens the door (not built here, tracked as follow-up in #29) to a `RecordedRunner` that replays a
  saved envelope — an investigation could be re-run against a changed prompt with zero Claude Code
  quota spent, which ADR-0023 and ADR-0024 both paid real money to learn the hard way.
- 208 pre-existing tests → 222 total: 24 in `test_agent.py` (rewritten, same assertions, `FakeRunner`
  instead of `@patch`), 22 in `test_fix_agent.py` (same), 14 new in `test_model_runner.py`. Zero
  tests deleted. `mise run lint` clean, `model_runner.py` at 100% line+branch coverage.

### Bad

- The E2E tests from ADR-0029 (`tests/test_e2e_pipeline.py`) needed one edit: the `monkeypatch`
  target string moved from `"houston.agent.subprocess.run"` to
  `"houston.model_runner.subprocess.run"`, because `unittest.mock`/`monkeypatch.setattr` target
  names resolve in the *calling* module's namespace, not the object's origin, and the call site
  moved. No assertion in any of those tests changed — only the string naming where to intercept.
  Worth stating plainly rather than claiming (as an earlier draft of this ADR's own test-net
  predecessor did) that the file was untouched by every move: it wasn't, and the honest, narrower
  claim ("no assertion changed") is the one that's actually true.
- `DEFAULT_RUNNER` is a second module-level singleton after `DEFAULT_STORE` (ADR-0030) — same
  trade-off accepted there: real dependency injection would have every `cmd_*` in `cli.py`
  construct and thread its own runner, deferred to the use-case extraction (Move C, tracked in
  #29) where those functions are being rewritten anyway.

### Follow-up

- Move C (use-cases out of `cli.py`), tracked in #29, builds on this PR's `runner` parameter shape
  the same way it builds on Move A's `store` parameter shape.
- A `RecordedRunner` for replaying saved envelopes is a natural next use of this port, not built in
  this PR.
