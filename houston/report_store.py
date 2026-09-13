"""reports/ as an injected collaborator, not a module-level global.

Before this module, `REPORTS_DIR` was defined in `dedup.py` and imported by
copy into `frontmatter.py` and `metrics.py`; `QUARANTINE_DIR` was derived
from it once, at import time, in `frontmatter.py`. Isolating a test meant
monkeypatching four separate names, and `frontmatter.py` importing from
`dedup.py` while `dedup.needs_investigation` needed a function-local import
of `frontmatter.read_report` to avoid a real import cycle (ADR-0029,
ADR-0030).

`ReportStore` is the only place a report path under `reports/` gets
written -- `grep -rn "write_text" houston/` should return only the two
lines below. `quarantine` is a property, computed on every access from
`self.root`, which is what makes the import-time-snapshot problem
disappear by construction rather than by test discipline."""
from collections.abc import Iterator
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


class ReportStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    @property
    def quarantine(self) -> Path:
        return self.root / ".quarantine"

    def path(self, fingerprint: str) -> Path:
        return self.root / f"{fingerprint}.md"

    def exists(self, fingerprint: str) -> bool:
        return self.path(fingerprint).exists()

    def write(self, fingerprint: str, markdown: str) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.path(fingerprint)
        path.write_text(markdown)
        return path

    def write_quarantined(self, fingerprint: str, markdown: str) -> Path:
        self.quarantine.mkdir(parents=True, exist_ok=True)
        path = self.quarantine / f"{fingerprint}.md"
        path.write_text(markdown)
        return path

    def iter_paths(self) -> Iterator[Path]:
        """*.md directly under root, ordered -- never descends into
        `.quarantine/`, since `root.glob("*.md")` is non-recursive."""
        if not self.root.exists():
            return iter(())
        return iter(sorted(self.root.glob("*.md")))


DEFAULT_STORE = ReportStore(_ROOT / "reports")
