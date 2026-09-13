"""Shared fixtures for the refactor safety net (ADR-0029).

`store` isolates the reports directory the way every future ReportStore
consumer will: by rebinding the module globals that own it today
(`dedup.REPORTS_DIR`, `frontmatter.REPORTS_DIR`, `frontmatter.QUARANTINE_DIR`,
`metrics.REPORTS_DIR`) to a `tmp_path`. Four names, not three -- metrics.py
imports its own copy and no existing test isolates it, which is why
`houston metrics` today silently reads the real reports/ directory unless a
test happens to monkeypatch all four.
"""
from pathlib import Path

import pytest

import houston.dedup as dedup_mod
import houston.frontmatter as fm
import houston.metrics as metrics_mod


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Points every module that reads/writes reports/ at an isolated tmp_path.
    Returns the directory itself -- today's global-based collaborators don't
    need an object, only a path. After ReportStore lands (Move A) this
    fixture's body changes to `ReportStore(tmp_path)`; no test that uses it
    should need to change."""
    monkeypatch.setattr(dedup_mod, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(fm, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(fm, "QUARANTINE_DIR", tmp_path / ".quarantine")
    monkeypatch.setattr(metrics_mod, "REPORTS_DIR", tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def no_real_datadog_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Belt-and-suspenders: the suite's own promise (.mise/tasks/test's
    description) is "no network". Findings that build a real Config would
    otherwise silently pick up whatever's in a developer's .env."""
    monkeypatch.delenv("DD_API_KEY", raising=False)
    monkeypatch.delenv("DD_APP_KEY", raising=False)
