"""Direct proof of ReportStore's contract (ADR-0030): the sole place a
report path under reports/ gets written, and the single mutable object
every collaborator's `store: ReportStore = DEFAULT_STORE` default
references -- which is what lets tests isolate everything by mutating one
attribute on one object instead of patching a name per module."""
from houston.report_store import ReportStore


def test_exists_reflects_the_written_file(tmp_path):
    store = ReportStore(tmp_path)
    assert not store.exists("et-fp")
    store.write("et-fp", "x")
    assert store.exists("et-fp")


def test_quarantine_is_derived_from_root_not_snapshotted(tmp_path):
    store = ReportStore(tmp_path)
    assert store.quarantine == tmp_path / ".quarantine"

    store.root = tmp_path / "moved"
    assert store.quarantine == tmp_path / "moved" / ".quarantine"


def test_write_creates_the_root_directory_on_demand(tmp_path):
    store = ReportStore(tmp_path / "does-not-exist-yet")
    path = store.write("et-fp", "---\nstate: new\n---\n")

    assert path == store.path("et-fp")
    assert path.read_text() == "---\nstate: new\n---\n"


def test_write_quarantined_creates_the_quarantine_directory_on_demand(tmp_path):
    store = ReportStore(tmp_path)
    path = store.write_quarantined("et-fp", "full text with pii")

    assert path == tmp_path / ".quarantine" / "et-fp.md"
    assert path.read_text() == "full text with pii"


def test_iter_paths_on_a_missing_root_returns_nothing(tmp_path):
    store = ReportStore(tmp_path / "never-created")
    assert list(store.iter_paths()) == []


def test_iter_paths_excludes_the_quarantine_subdirectory(tmp_path):
    store = ReportStore(tmp_path)
    store.write("et-a", "a")
    store.write("et-b", "b")
    store.write_quarantined("et-c", "c")

    names = [p.name for p in store.iter_paths()]
    assert names == ["et-a.md", "et-b.md"]
