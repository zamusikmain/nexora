import subprocess
import sys
import tarfile

import backup
import pytest


def test_backup_script_archives_real_private_keys(tmp_path):
    root = tmp_path / "uploads"
    root.mkdir()
    key = "a" * 32
    (root / key).write_bytes(b"private version")
    (root / "a32").write_bytes(b"wrong key")
    (root / "secret.env").write_text("must not be archived")
    destination = tmp_path / "storage.tar.gz"
    script = backup.storage_archive_script(str(destination)).replace("/data/uploads", str(root))
    subprocess.run([sys.executable, "-c", script], check=True)
    with tarfile.open(destination, "r:gz") as archive:
        assert archive.getnames() == [key]
        assert archive.extractfile(key).read() == b"private version"


def test_dump_never_silently_uses_admin():
    script = backup.dump_command()
    assert "POSTGRES_USER" not in script
    assert "nexora_backup" in script and "127.0.0.1" in script
    assert "DB_BACKUP_PASSWORD:?" in script


def test_missing_backup_credential_fails_closed():
    result = subprocess.run(["sh", "-c", backup.dump_command()], env={}, capture_output=True)
    assert result.returncode != 0


@pytest.mark.parametrize("flag", [False, True])
def test_legacy_dump_requires_explicit_flag(flag):
    assert ("POSTGRES_USER" in backup.dump_command(legacy_admin=flag)) == flag


def test_operator_secret_never_appears_in_docker_arguments(monkeypatch):
    secret = "synthetic-backup-test-credential"
    monkeypatch.setenv("DB_BACKUP_PASSWORD", secret)
    args = backup.dump_environment_args()
    assert "DB_BACKUP_PASSWORD" in args
    assert all(secret not in value for value in args)
    assert backup.dump_environment_args(legacy_admin=True) == []


def test_no_operator_secret_does_not_inject_empty_password(monkeypatch):
    monkeypatch.delenv("DB_BACKUP_PASSWORD", raising=False)
    assert backup.dump_environment_args() == []
