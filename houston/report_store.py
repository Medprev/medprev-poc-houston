"""reports/ as an injected collaborator, not a module-level global.

Before this module, `REPORTS_DIR` was defined in `dedup.py` and imported by
copy into `frontmatter.py` and `metrics.py`; `QUARANTINE_DIR` was derived
from it once, at import time, in `frontmatter.py`. Isolating a test meant
monkeypatching four separate names, and `frontmatter.py` importing from
`dedup.py` while `dedup.needs_investigation` needed a function-local import
of `frontmatter.read_report` to avoid a real import cycle (ADR-0029,
ADR-0030).

`ReportStore` is the intended single place a report *body* reaches
`reports/` -- write() and write_quarantined() below are the only writers
this module owns. One exception, out of this module's scope and left
unchanged by it: `houston/cli.py`'s `update_front_matter` still writes
`fix_pr`/`fix_state` directly, bypassing both this store and the PII gate,
because those values are code-owned (a URL `gh` printed, a state the CLI
chose) rather than model text -- see ADR-0030's "Bad" section. `quarantine`
is a property, computed on every access from `self.root`, which is what
makes the import-time-snapshot problem disappear by construction rather
than by test discipline."""
from collections.abc import Iterator
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


class ReportStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    @property
    def quarantine(self) -> Path:
        return self.root / ".quarantine"

    @staticmethod
    def _filename(fingerprint: str) -> str:
        # Every fingerprint format (et-{issue_id}, mon-{monitor_id}[-{group}],
        # k8s-{cluster}-{reason}-{namespace}) is meant to be one path
        # segment. A "/" would silently turn into a directory separator
        # instead -- a nested, uncreated parent that fails after an
        # already-paid investigation, invisible to iter_paths' non-recursive
        # glob on every future run.
        if "/" in fingerprint or "\\" in fingerprint or fingerprint in ("", ".", ".."):
            raise ValueError(f"unsafe fingerprint for a report filename: {fingerprint!r}")
        return f"{fingerprint}.md"

    def path(self, fingerprint: str) -> Path:
        return self.root / self._filename(fingerprint)

    def exists(self, fingerprint: str) -> bool:
        return self.path(fingerprint).exists()

    def write(self, fingerprint: str, markdown: str) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.path(fingerprint)
        path.write_text(markdown)
        return path

    def write_quarantined(self, fingerprint: str, markdown: str) -> Path:
        self.quarantine.mkdir(parents=True, exist_ok=True)
        path = self.quarantine / self._filename(fingerprint)
        path.write_text(markdown)
        return path

    def iter_paths(self) -> Iterator[Path]:
        """*.md directly under root, ordered -- never descends into
        `.quarantine/`, since `root.glob("*.md")` is non-recursive."""
        if not self.root.exists():
            return iter(())
        return iter(sorted(self.root.glob("*.md")))


DEFAULT_STORE = ReportStore(_ROOT / "reports")
