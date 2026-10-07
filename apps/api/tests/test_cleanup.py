import os
import time

import pytest

from app.cleanup import candidates, sweep
from app.storage import LocalStorage


def test_cleanup_candidate_age_reference_and_name_safety(tmp_path):
    old = time.time() - 72 * 3600
    referenced = "a" * 32
    orphan = "b" * 32
    recent = "c" * 32
    quarantine = ".quarantine-" + "d" * 32
    for name in [referenced, orphan, recent, quarantine, "outside.txt"]:
        (tmp_path / name).write_bytes(b"synthetic")
        if name != recent:
            os.utime(tmp_path / name, (old, old))
    selected = candidates(LocalStorage(tmp_path), {referenced}, time.time() - 48 * 3600)
    assert {p.name for p in selected} == {orphan, quarantine}
    assert (tmp_path / referenced).exists()


def test_database_failure_prevents_any_storage_access(monkeypatch):
    import app.cleanup as cleanup

    class BrokenDB:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def scalars(self, *args):
            raise RuntimeError("Database unavailable")

    monkeypatch.setattr(cleanup, "SessionLocal", lambda: BrokenDB())
    monkeypatch.setattr(
        cleanup, "storage", lambda: pytest.fail("Filesystem must not be accessed after DB failure")
    )
    with pytest.raises(RuntimeError):
        sweep(apply=True)
