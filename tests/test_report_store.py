"""Direct proof of ReportStore's contract (ADR-0030): the intended single
writer of a report body under reports/ (write/write_quarantined -- see
ADR-0030's "Bad" section for the one deliberate exception,
pipeline.py's update_front_matter), and the single mutable object every
collaborator's `store: ReportStore = DEFAULT_STORE` default references --
which is what lets tests isolate everything by mutating one attribute on
one object instead of patching a name per module."""
import pytest

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


@pytest.mark.parametrize("fingerprint", ["a/b", "a\\b", "", ".", ".."])
def test_path_rejects_a_fingerprint_that_is_not_one_path_segment(tmp_path, fingerprint):
    """A '/' in a fingerprint would silently become a directory separator
    instead of a literal character -- a nested, uncreated parent that fails
    only after an already-paid investigation."""
    store = ReportStore(tmp_path)
    with pytest.raises(ValueError):
        store.path(fingerprint)


def test_write_quarantined_rejects_the_same_unsafe_fingerprints_as_write(tmp_path):
    store = ReportStore(tmp_path)
    with pytest.raises(ValueError):
        store.write_quarantined("a/b", "x")


def test_iter_paths_excludes_the_quarantine_subdirectory(tmp_path):
    store = ReportStore(tmp_path)
    store.write("et-a", "a")
    store.write("et-b", "b")
    store.write_quarantined("et-c", "c")

    names = [p.name for p in store.iter_paths()]
    assert names == ["et-a.md", "et-b.md"]
