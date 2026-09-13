"""Shared fixtures for the refactor safety net (ADR-0029, ADR-0030).

`store` isolates the reports directory by mutating `DEFAULT_STORE.root` in
place, rather than rebinding a module-level name. `ReportStore` is a single
shared object -- `dedup.py`, `frontmatter.py`, `metrics.py`, and every
function's `store: ReportStore = DEFAULT_STORE` default all reference the
*same* instance, so patching one attribute on it reaches every consumer
without needing a separate monkeypatch per module. `quarantine` is a
property derived from `self.root`, so it re-derives automatically -- no
second name to patch the way `QUARANTINE_DIR` used to need.
"""
from pathlib import Path

import pytest

from houston.report_store import DEFAULT_STORE


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Points every collaborator that defaults to DEFAULT_STORE at an
    isolated tmp_path. Returns the directory itself (a Path, not a
    ReportStore -- passing this fixture where a `store: ReportStore`
    parameter is expected raises TypeError at the Path.exists()/write_text()
    call inside, not here), since most existing tests only need to inspect
    files on disk, not call the store's methods directly.

    Deliberately opt-in, not autouse: `tests/test_report_corpus.py` asserts
    invariants over the real, committed `reports/` corpus on purpose, and
    an autouse guard would have to special-case that file. A test that
    calls write_report()/filter_new()/load_all_reports() without requesting
    this fixture touches the real reports/ directory -- see ADR-0030's
    'Bad' section."""
    monkeypatch.setattr(DEFAULT_STORE, "root", tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def no_real_datadog_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Belt-and-suspenders: the suite's own promise (.mise/tasks/test's
    description) is "no network". Findings that build a real Config would
    otherwise silently pick up whatever's in a developer's .env."""
    monkeypatch.delenv("DD_API_KEY", raising=False)
    monkeypatch.delenv("DD_APP_KEY", raising=False)
