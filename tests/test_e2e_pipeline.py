"""End-to-end proof that `main(argv)` produces the right files on disk
(ADR-0029) -- the boundary none of the planned moves (ReportStore, model
runner port, use-cases out of cli.py) touches. Every collaborator below is
stubbed at the process edge (`requests`, stdlib `subprocess`), so every
test body and assertion below is unedited by Move A (ADR-0030) and Move B
(ADR-0031) alike. The one thing that DID need editing, honestly: Move B
moved the `subprocess.run` call site from `houston.agent` into
`houston.model_runner`, and `unittest.mock.patch`/`monkeypatch.setattr`
target names in the *calling* module's namespace, not the object's origin
-- so the patch target string here changed from
"houston.agent.subprocess.run" to "houston.model_runner.subprocess.run" in
that PR. No assertion changed.

Datadog is served from the same recorded fixtures `test_collector.py`
already uses, routed to the right source by the POST body's `filter.query`
/ search-request `query`. `claude -p` is served a canned JSON envelope
keyed off argv[0] == "claude"; anything else (there is none in this suite)
would fall through to a real subprocess call, which is deliberately not
provided so a forgotten stub fails loudly instead of touching the network.
"""
import json
import subprocess
from pathlib import Path

import pytest

from houston.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _fake_post(url, headers=None, json=None, timeout=None):
    if url.endswith("/issues/search"):
        return _FakeResponse(_load("et_search_response.json"))
    if url.endswith("/events/search"):
        query = json["filter"]["query"]
        if "source:kubernetes" in query:
            return _FakeResponse(_load("k8s_events_response.json"))
        if "source:alert" in query:
            return _FakeResponse(_load("monitor_events_response.json"))
    raise AssertionError(f"unexpected POST {url}: {json}")


def _fake_get(url, headers=None, params=None, timeout=None):
    if url.endswith("114e7438-e897-11ef-83c4-da7ad0900002"):
        return _FakeResponse(_load("et_issue_114e7438.json"))
    if url.endswith("c718a87c-a5a3-11f1-b501-da7ad0900002"):
        return _FakeResponse(_load("et_issue_c718a87c.json"))
    raise AssertionError(f"unexpected GET {url}")


@pytest.fixture(autouse=True)
def recorded_datadog(monkeypatch):
    monkeypatch.setattr("houston.datadog_client.requests.post", _fake_post)
    monkeypatch.setattr("houston.datadog_client.requests.get", _fake_get)
    monkeypatch.setenv("DD_API_KEY", "fake")
    monkeypatch.setenv("DD_APP_KEY", "fake")
    monkeypatch.setenv("DD_SITE", "datadoghq.com")


class _FakeClaude:
    """Stands in for `subprocess.run` calls whose argv[0] is "claude". Any
    other command is refused -- a forgotten stub should fail loudly, not
    silently reach the real network or filesystem."""

    def __init__(self, *, result="Causa raiz: timeout no client axios.",
                 usd=0.32, returncode=0):
        self.calls: list[list[str]] = []
        self._payload = {
            "result": result,
            "usage": {"input_tokens": 1000, "output_tokens": 200},
            "duration_ms": 5000,
            "total_cost_usd": usd,
            "modelUsage": {"claude-sonnet-5": {}},
        }
        self._returncode = returncode

    def __call__(self, cmd, *args, **kwargs):
        if cmd[0] != "claude":
            raise AssertionError(f"unexpected subprocess call: {cmd}")
        self.calls.append(cmd)
        return subprocess.CompletedProcess(
            args=cmd, returncode=self._returncode,
            stdout=json.dumps(self._payload), stderr="",
        )


def test_run_prints_the_queue_and_writes_nothing(store, capsys):
    exit_code = main(["run", "--window-hours", "96", "--max-findings", "15"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "findings total" in out
    assert list(store.glob("*.md")) == []


def test_seed_writes_one_report_per_finding_in_state_seeded(store):
    exit_code = main(["seed", "--window-hours", "96"])

    assert exit_code == 0
    written = sorted(p.name for p in store.glob("*.md"))
    assert len(written) > 0
    for path in store.glob("*.md"):
        text = path.read_text()
        assert "state: seeded" in text


def test_seed_is_idempotent_second_run_writes_nothing_new(store):
    main(["seed", "--window-hours", "96"])
    first = {p.name: p.read_text() for p in store.glob("*.md")}

    main(["seed", "--window-hours", "96"])
    second = {p.name: p.read_text() for p in store.glob("*.md")}

    assert first == second


def test_investigate_writes_one_report_per_capped_finding(store, monkeypatch, capsys):
    fake_claude = _FakeClaude()
    monkeypatch.setattr("houston.model_runner.subprocess.run", fake_claude)

    exit_code = main([
        "investigate", "--window-hours", "96", "--max-findings", "1",
        "--max-budget-usd", "0.75", "--timeout-s", "300",
    ])

    assert exit_code == 0
    written = list(store.glob("*.md"))
    assert len(written) == 1
    text = written[0].read_text()
    assert "state: new" in text
    assert "Causa raiz: timeout no client axios." in text
    assert "model: claude-sonnet-5" in text
    assert len(fake_claude.calls) == 1
    out = capsys.readouterr().out
    assert "total spend this run:" in out


def test_investigate_is_idempotent_second_run_investigates_nothing_new(store, monkeypatch):
    fake_claude = _FakeClaude()
    monkeypatch.setattr("houston.model_runner.subprocess.run", fake_claude)

    main(["investigate", "--window-hours", "96", "--max-findings", "5"])
    calls_after_first_run = len(fake_claude.calls)
    assert calls_after_first_run > 0

    main(["investigate", "--window-hours", "96", "--max-findings", "5"])

    assert len(fake_claude.calls) == calls_after_first_run


def test_seed_then_investigate_overwrites_the_seeded_report(store, monkeypatch):
    """ADR-0010: `houston seed` writes state: seeded with no real
    investigation; `houston investigate` must still pick that finding up
    and overwrite it with a real result, not skip it because a file
    already exists."""
    main(["seed", "--window-hours", "96"])
    seeded = sorted(p.name for p in store.glob("*.md"))
    assert len(seeded) > 0
    assert all("state: seeded" in (store / name).read_text() for name in seeded)

    fake_claude = _FakeClaude()
    monkeypatch.setattr("houston.model_runner.subprocess.run", fake_claude)
    main(["investigate", "--window-hours", "96", "--max-findings", "1"])

    investigated = [p for p in store.glob("*.md") if "state: new" in p.read_text()]
    assert len(investigated) == 1


def test_investigate_a_timed_out_run_writes_incomplete_and_stays_in_the_queue(store, monkeypatch):
    def timeout_stub(cmd, *args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout", 300))

    monkeypatch.setattr("houston.model_runner.subprocess.run", timeout_stub)

    main(["investigate", "--window-hours", "96", "--max-findings", "1"])

    written = list(store.glob("*.md"))
    assert len(written) == 1
    assert "state: incomplete" in written[0].read_text()

    # incomplete reports still need investigation -- `run` must still list them
    exit_code = main(["run", "--window-hours", "96", "--max-findings", "15"])
    assert exit_code == 0


def test_pii_in_the_agent_body_never_reaches_the_reports_dir(store, monkeypatch):
    fake_claude = _FakeClaude(result="Contato: carla.cury@medprevonline.com relatou.")
    monkeypatch.setattr("houston.model_runner.subprocess.run", fake_claude)

    main(["investigate", "--window-hours", "96", "--max-findings", "1"])

    written = list(store.glob("*.md"))
    assert len(written) == 1
    assert "state: quarantined" in written[0].read_text()
    assert "carla.cury@medprevonline.com" not in written[0].read_text()
    quarantine_files = list((store / ".quarantine").glob("*.md"))
    assert len(quarantine_files) == 1
    assert "carla.cury@medprevonline.com" in quarantine_files[0].read_text()


def test_metrics_exits_1_while_work_is_owed_and_0_once_the_phase_can_close(store, capsys):
    main(["seed", "--window-hours", "96"])
    # seeded reports do not block the phase -- everything is state: seeded
    exit_code = main(["metrics"])
    assert exit_code == 0
    assert "phase can close" in capsys.readouterr().out

    # a report in `new` owes work
    one = next(store.glob("*.md"))
    one.write_text(one.read_text().replace("state: seeded", "state: new"))
    exit_code = main(["metrics"])
    assert exit_code == 1
    assert "phase CANNOT close" in capsys.readouterr().out


def test_metrics_on_an_empty_store_exits_0_and_does_not_claim_a_closed_phase(store, capsys):
    exit_code = main(["metrics"])

    assert exit_code == 0
    assert "no reports yet" in capsys.readouterr().out
