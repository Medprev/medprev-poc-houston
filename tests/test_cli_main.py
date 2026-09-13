"""Characterizes `main(argv)`'s argparse surface (ADR-0029) -- the boundary
`houston/usecases.py`-style refactors (Move C in the tracking plan) rewire
without changing. No test calls `main()` before this file; every existing
cmd_* test builds an `argparse.Namespace` by hand and so cannot catch a
subcommand wired to the wrong function or a changed default.
"""
import pytest

from houston.cli import main


def test_missing_subcommand_exits_nonzero(capsys):
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code != 0


def test_unknown_subcommand_exits_nonzero(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["not-a-real-command"])
    assert exc.value.code != 0


@pytest.mark.parametrize(
    "argv,expected",
    [
        (["seed"], {"window_hours": 96}),
        (["run"], {"window_hours": 96, "max_findings": 15}),
        (["investigate"], {
            "window_hours": 96, "max_findings": 5,
            "max_budget_usd": "0.75", "timeout_s": 300,
            "model": "sonnet", "effort": "medium",
        }),
        (["metrics"], {}),
        (["promote", "et-fp"], {"fingerprint": "et-fp"}),
        (["fix", "et-fp"], {
            "fingerprint": "et-fp", "max_budget_usd": "3.00", "timeout_s": 600,
        }),
    ],
)
def test_subcommand_parses_with_its_documented_defaults(argv, expected):
    """Doesn't invoke main() -- just proves argparse still hands each
    cmd_* the exact default values ADR-0023/ADR-0024 sized (e.g.
    investigate's deliberately small --max-findings 5, its own
    --max-budget-usd distinct from fix's larger one)."""
    import houston.cli as cli_mod

    ns = None

    def _capture(args):
        nonlocal ns
        ns = args
        return 0

    # Monkeypatch every cmd_* to a capture instead of running it for real,
    # then let main() build its parser and dispatch exactly as it would in
    # production -- this is what proves set_defaults(func=cmd_*) still
    # routes to the right handler after a rewire.
    names = ["cmd_seed", "cmd_run", "cmd_investigate", "cmd_metrics", "cmd_promote", "cmd_fix"]
    originals = {name: getattr(cli_mod, name) for name in names}
    for name in names:
        setattr(cli_mod, name, _capture)
    try:
        exit_code = main(argv)
    finally:
        for name, original in originals.items():
            setattr(cli_mod, name, original)

    assert exit_code == 0
    for key, value in expected.items():
        assert getattr(ns, key) == value, key
