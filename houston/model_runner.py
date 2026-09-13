"""The `claude -p` subprocess call behind a port (ADR-0031, Move B).

`houston/agent.py` and `houston/fix_agent.py` each invoke `claude -p` with
a different shape: `agent.py` passes the finding as JSON on stdin, no
`cwd`, and a read-only `--disallowedTools`; `fix_agent.py` passes the
prompt as the last argv element, `cwd` set to a git worktree, and no
`--disallowedTools`. One port covers both -- decoding the JSON envelope on
stdout (including on a non-zero exit, ADR-0013) is already identical
between them, which is why `fix_agent.py` imports `agent.py`'s private
`_payload_or_none`/`_input_tokens`/`_error_text`.

`SubprocessRunner` is the only place `subprocess.run` is called to invoke
`claude` in the package. The five `git` calls in `fix_agent.py` are
plumbing, not the model runner, and stay direct `subprocess.run` calls --
out of scope for this port (see the tracking issue, #29)."""
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ModelRun:
    argv: list[str]
    stdin: str | None = None
    cwd: Path | None = None
    env: Mapping[str, str] | None = None
    timeout_s: int = 300


@dataclass(frozen=True)
class ModelOutcome:
    # None only when timed_out is True -- the process never produced an
    # exit code the CLI could observe.
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool = False


class ModelRunner(Protocol):
    def run(self, request: ModelRun) -> ModelOutcome: ...


class SubprocessRunner:
    """The real `claude -p` subprocess call."""

    def run(self, request: ModelRun) -> ModelOutcome:
        try:
            proc = subprocess.run(
                request.argv,
                input=request.stdin,
                capture_output=True,
                text=True,
                env=dict(request.env) if request.env is not None else None,
                timeout=request.timeout_s,
                cwd=str(request.cwd) if request.cwd is not None else None,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            # The CLI prints its JSON envelope on stdout even on a timeout
            # kill (ADR-0013) -- exc.stdout carries whatever was captured
            # before the process was killed, str or bytes depending on the
            # `text=True` flag having been in effect when the timeout hit.
            stdout = exc.stdout
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            return ModelOutcome(
                returncode=None, stdout=stdout or "", stderr="", timed_out=True,
            )
        return ModelOutcome(returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


DEFAULT_RUNNER = SubprocessRunner()
