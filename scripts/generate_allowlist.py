"""Generate the E4 read-only tool allowlist from a snapshot of the Datadog MCP
tool inventory.

The snapshot (houston/mcp_tool_inventory_snapshot.txt) is a one-name-per-line
capture of every tool the `claude.ai Datadog` MCP server exposed on the date
recorded below. There is no scriptable "list tools" introspection surface on
`claude mcp` today, so the snapshot has to be refreshed by hand (via
ToolSearch inside a Claude Code session) whenever the server's tool set
changes — this script only does the filtering, not the discovery.

The filter fails CLOSED: a tool has to *declare* itself read-only by leading
with a read verb, and must also carry no write verb. Blacklisting write
verbs alone shipped `clean-up-flag`, `clone_datadog_form`,
`clone_llmobs_dataset`, `ddsql_run_query`, `run_synthetics_tests` and
`verify-onboarding-flag` into the committed allowlist — none of them match a
write verb, all of them mutate or spend (ADR-0016).

Usage: python scripts/generate_allowlist.py
Writes houston/allowedtools.txt (one tool name per line).
"""
import re
from pathlib import Path

# A tool qualifies only if one of its name tokens is one of these. Tokens,
# not prefixes, because read-only tools like `monitor_groups_search` and
# `ddsql_schema_search_tables` put the verb in the middle. `load` is here
# for `load_datadog_skill` — the only `load` tool in the snapshot, and the
# MCP server's own instructions ask for it before its data tools.
READ_VERBS = frozenset({
    "get", "list", "search", "read", "describe", "analyze", "aggregate",
    "find", "explore", "inspect", "summarize", "diff", "expand", "rank",
    "schema", "count", "coverage", "status", "history", "details", "load",
})

# Second gate, also token-exact. Substring matching was the original bug in
# both directions: it let `clean-up-flag` through (no write verb in it) and
# it denied read-only tools whose names merely contain a verb — "set" inside
# `dataset`, "run" inside `runtime`.
WRITE_VERBS = frozenset({
    "create", "delete", "update", "upsert", "mute", "unmute", "assign",
    "unassign", "archive", "publish", "execute", "exec", "edit", "add",
    "append", "submit", "cancel", "retry", "sync", "reorder", "restore",
    "detach", "unblock", "run", "clone", "clean", "copy", "move", "set",
    "apply", "trigger", "verify", "onboarding", "onboard", "install",
    "activate", "enable", "disable", "remap", "write", "import", "export",
    "refresh", "generate", "annotate", "resolve", "close", "open", "start",
    "stop", "bulk", "manage", "optimize", "recommend", "suggest", "wizard",
    "uploads", "up",
})

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "houston" / "mcp_tool_inventory_snapshot.txt"
OUTPUT = ROOT / "houston" / "allowedtools.txt"


def tool_name(full_name: str) -> str:
    """`mcp__claude_ai_Datadog__get_datadog_metric` -> `get_datadog_metric`."""
    return full_name.rsplit("__", 1)[-1]


def tokens(name: str) -> list[str]:
    return [t for t in re.split(r"[_\-]+", name.lower()) if t]


def is_read_only(full_name: str) -> bool:
    name_tokens = set(tokens(tool_name(full_name)))
    if name_tokens & WRITE_VERBS:
        return False
    return bool(name_tokens & READ_VERBS)


def generate() -> list[str]:
    names = [
        line.strip()
        for line in SNAPSHOT.read_text().splitlines()
        if line.strip()
    ]
    return sorted(name for name in names if is_read_only(name))


def main() -> None:
    allowed = generate()
    OUTPUT.write_text("\n".join(allowed) + "\n")
    print(f"{len(allowed)} read-only tools written to {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
