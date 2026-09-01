"""Generate the E4 read-only tool allowlist from a snapshot of the Datadog MCP
tool inventory.

The snapshot (houston/mcp_tool_inventory_snapshot.txt) is a one-name-per-line
capture of every tool the `claude.ai Datadog` MCP server exposed on the date
recorded below. There is no scriptable "list tools" introspection surface on
`claude mcp` today, so the snapshot has to be refreshed by hand (via
ToolSearch inside a Claude Code session) whenever the server's tool set
changes — this script only does the filtering, not the discovery.

Usage: python scripts/generate_allowlist.py
Writes houston/allowedtools.txt (one tool name per line).
"""
import re
from pathlib import Path

WRITE_VERBS = re.compile(
    r"(create|delete|update|upsert|mute|assign|archive|publish|execute|edit"
    r"|add|append|submit|cancel|retry|sync|reorder|restore|detach|unblock)",
    re.IGNORECASE,
)

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "houston" / "mcp_tool_inventory_snapshot.txt"
OUTPUT = ROOT / "houston" / "allowedtools.txt"


def generate() -> list[str]:
    names = [
        line.strip()
        for line in SNAPSHOT.read_text().splitlines()
        if line.strip()
    ]
    return sorted(name for name in names if not WRITE_VERBS.search(name))


def main() -> None:
    allowed = generate()
    OUTPUT.write_text("\n".join(allowed) + "\n")
    print(f"{len(allowed)} read-only tools written to {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
