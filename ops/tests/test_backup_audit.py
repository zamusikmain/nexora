import io
import tarfile

import audit_backups
import pytest


def make_archive(path, names):
    with tarfile.open(path, "w:gz") as archive:
        for name in names:
            entry = tarfile.TarInfo(name)
            entry.size = 3
            archive.addfile(entry, io.BytesIO(b"abc"))


def test_empty_archive_is_identified(tmp_path):
    path = tmp_path / "archive.tar.gz"
    make_archive(path, [])
    assert audit_backups.inspect_archive(path) == {}


def test_private_archive_file_integrity(tmp_path):
    path = tmp_path / "archive.tar.gz"
    make_archive(path, ["a" * 32])
    assert audit_backups.inspect_archive(path)["a" * 32] == (
        3, "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")


@pytest.mark.parametrize("names", [["../escape"], ["a" * 32, "a" * 32]])
def test_unsafe_or_duplicate_archive_is_rejected(tmp_path, names):
    path = tmp_path / "archive.tar.gz"
    make_archive(path, names)
    with pytest.raises(ValueError):
        audit_backups.inspect_archive(path)
