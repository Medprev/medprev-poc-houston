"""E9 — one `claude -p` subprocess per promoted finding, with code tools.
Reads the investigation report, navigates the source repo (via local
worktree), writes a fix, and opens a PR linked to the tracking issue.

The investigation agent (agent.py) is read-only. This one is write-enabled
on the target repo: Bash, Read, Write, Edit, Glob, Grep. It has no
Datadog tools — the report already contains the evidence.

Bounded by --max-budget-usd and a wall-clock timeout, same as agent.py.
"""
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml

from houston.agent import _error_text, _input_tokens, _payload_or_none

ROOT = Path(__file__).resolve().parent.parent
SERVICE_REPOS_PATH = ROOT / "houston" / "service_repos.yaml"

DEFAULT_MAX_BUDGET_USD = "3.00"
DEFAULT_TIMEOUT_S = 600

ALLOWED_TOOLS = "Bash,Read,Write,Edit,Glob,Grep"

FIX_PROMPT = """\
Você é um agente de correção de bugs. Recebeu um relatório de investigação \
de observabilidade e precisa corrigir o código no repositório clonado.

Instruções:
1. Leia o relatório inteiro para entender a causa raiz e ação recomendada.
2. Navegue o repositório para encontrar os arquivos mencionados (ou busque \
por nome de componente/função se o relatório não menciona arquivos exatos).
3. Faça a correção mínima que resolve o problema descrito.
4. Tente descobrir como rodar os testes (package.json, Makefile, mise tasks, \
CLAUDE.md do repo). Se conseguir rodar, rode. Se falharem por dependência \
externa, registre no commit/PR e siga. Se não encontrar test runner, diga.
5. Crie um commit descritivo referenciando a issue: \
"fix: <descrição curta> (#{issue_number})"
6. Faça push da branch e crie o PR com `gh pr create` linkando a issue.

Restrições:
- NUNCA faça push para main/master. Trabalhe APENAS na branch {branch_name}.
- NUNCA force-push.
- O PR é o gate humano. Não tente fazer merge.
- Se não conseguir encontrar o código ou não tiver certeza da correção, \
diga claramente em vez de chutar.

Branch: {branch_name}
Issue: {issue_url}
Repo: {repo_name}
Fingerprint: {fingerprint}

--- RELATÓRIO DE INVESTIGAÇÃO ---
{report_markdown}
"""


@dataclass
class FixResult:
    pr_url: str | None
    body: str | None
    input_tokens: int
    output_tokens: int
    duration_s: float
    usd: float
    state: str  # "pr_open" | "incomplete"
    error: str | None = None
    branch: str | None = None
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


def load_service_repos() -> dict:
    return yaml.safe_load(SERVICE_REPOS_PATH.read_text()) or {}


def resolve_repo(service: str | None, report_body: str = "") -> dict | None:
    """Two-phase resolution: front-matter service first, then body scan."""
    mapping = load_service_repos()
    if service and service in mapping and mapping[service] is not None:
        return mapping[service]
    for name, entry in mapping.items():
        if entry is not None and re.search(rf'\b{re.escape(name)}\b', report_body):
            return entry
    return None


def _extract_pr_url(text: str) -> str | None:
    match = re.search(r'https://github\.com/[^\s)]+/pull/\d+', text or "")
    return match.group(0) if match else None


def _branch_name(fingerprint: str, attempt: int) -> str:
    suffix = f"-v{attempt}" if attempt > 1 else ""
    return f"houston/fix/{fingerprint}{suffix}"


def _count_existing_attempts(repo_path: Path, fingerprint: str) -> int:
    result = subprocess.run(
        ["git", "branch", "-r", "--list", f"origin/houston/fix/{fingerprint}*"],
        capture_output=True, text=True, cwd=repo_path, check=False,
    )
    return len([l for l in result.stdout.splitlines() if l.strip()])


def _prepare_worktree(
    repo_path: Path, fingerprint: str, attempt: int,
) -> tuple[Path, str]:
    branch = _branch_name(fingerprint, attempt)
    worktree_dir = repo_path / ".houston-fix" / fingerprint
    if attempt > 1:
        worktree_dir = repo_path / ".houston-fix" / f"{fingerprint}-v{attempt}"

    subprocess.run(
        ["git", "fetch", "origin"],
        cwd=repo_path, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "worktree", "add", str(worktree_dir), "origin/main"],
        cwd=repo_path, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "-b", branch],
        cwd=worktree_dir, check=True, capture_output=True,
    )
    return worktree_dir, branch


def _cleanup_worktree(repo_path: Path, worktree_dir: Path) -> None:
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(worktree_dir)],
        cwd=repo_path, check=False, capture_output=True,
    )


def _result(
    payload: dict | None,
    state: str,
    pr_url: str | None = None,
    branch: str | None = None,
    error: str | None = None,
    fallback_duration_s: float = 0.0,
) -> FixResult:
    usage = (payload or {}).get("usage") or {}
    total_input, cache_read, cache_creation = _input_tokens(usage)
    duration_ms = (payload or {}).get("duration_ms")
    return FixResult(
        pr_url=pr_url,
        body=(payload or {}).get("result"),
        input_tokens=total_input,
        output_tokens=int(usage.get("output_tokens") or 0),
        duration_s=(duration_ms / 1000) if duration_ms else fallback_duration_s,
        usd=float((payload or {}).get("total_cost_usd") or 0.0),
        state=state,
        error=error,
        branch=branch,
        cache_read_input_tokens=cache_read,
        cache_creation_input_tokens=cache_creation,
    )


def fix(
    fingerprint: str,
    report_markdown: str,
    issue_url: str,
    repo_info: dict,
    max_budget_usd: str = DEFAULT_MAX_BUDGET_USD,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> FixResult:
    repo_path = Path(repo_info["path"]).expanduser()
    repo_name = repo_info["repo"]

    attempt = _count_existing_attempts(repo_path, fingerprint) + 1
    worktree_dir, branch = _prepare_worktree(repo_path, fingerprint, attempt)

    issue_match = re.search(r'#?(\d+)$', issue_url)
    issue_number = issue_match.group(1) if issue_match else "???"

    prompt = FIX_PROMPT.format(
        branch_name=branch,
        issue_url=issue_url,
        issue_number=issue_number,
        repo_name=repo_name,
        fingerprint=fingerprint,
        report_markdown=report_markdown,
    )

    env = {**os.environ}
    env.pop("CLAUDECODE", None)

    cmd = [
        "claude", "-p",
        "--output-format", "json",
        "--allowedTools", ALLOWED_TOOLS,
        "--max-budget-usd", max_budget_usd,
        prompt,
    ]

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            env=env, timeout=timeout_s, cwd=str(worktree_dir), check=False,
        )
    except subprocess.TimeoutExpired as exc:
        partial = _payload_or_none(exc.stdout)
        return _result(
            partial, "incomplete", branch=branch,
            error=_error_text(partial, "", prefix=f"timed out after {timeout_s}s"),
            fallback_duration_s=float(timeout_s),
        )
    finally:
        _cleanup_worktree(repo_path, worktree_dir)

    payload = _payload_or_none(proc.stdout)

    if proc.returncode != 0:
        return _result(
            payload, "incomplete", branch=branch,
            error=_error_text(payload, proc.stderr),
        )

    if payload is None:
        return _result(
            None, "incomplete", branch=branch,
            error=f"non-JSON stdout: {proc.stdout[:500]}",
        )

    result_text = payload.get("result", "")
    pr_url = _extract_pr_url(result_text)

    if payload.get("is_error") or not result_text:
        return _result(
            payload, "incomplete", branch=branch,
            error=_error_text(payload, proc.stderr),
        )

    state = "pr_open" if pr_url else "incomplete"
    return _result(payload, state, pr_url=pr_url, branch=branch)
