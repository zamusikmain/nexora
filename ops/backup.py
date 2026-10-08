"""Docker Compose backup and isolated restore verification. Never overwrite a database."""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(args, *, capture=False):
    result = subprocess.run(args, cwd=ROOT, check=True, capture_output=capture, text=capture)
    return result.stdout.strip() if capture else ""


def service_id(service):
    value = run(["docker", "compose", "ps", "-q", service], capture=True)
    if not re.fullmatch(r"[a-f0-9]{12,64}", value):
        raise RuntimeError("Required service is not running")
    return value


def checksum(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def safe_location(path):
    path = path.resolve()
    if not path.is_relative_to(ROOT / "backups"):
        raise ValueError("Use a directory inside this repository's ignored backups folder")
    return path


def dump_command(*, legacy_admin=False):
    if legacy_admin:
        return 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-acl -Fc'
    # TCP prevents local trust authentication from bypassing the backup password.
    return (
        ': "${DB_BACKUP_PASSWORD:?Dedicated backup credential is required}"; '
        '[ "${DB_BACKUP_USER:-}" = nexora_backup ] || exit 1; '
        'PGPASSWORD="$DB_BACKUP_PASSWORD" pg_dump -h 127.0.0.1 --no-password '
        '-U "$DB_BACKUP_USER" -d "$POSTGRES_DB" --no-owner --no-acl -Fc'
    )


def storage_archive_script(path):
    return f"""from pathlib import Path
import re,tarfile
root=Path('/data/uploads')
with tarfile.open({path!r},'w:gz') as archive:
 for path in root.iterdir():
  if re.fullmatch('[a-f0-9]{{32}}',path.name) and path.is_file() and not path.is_symlink():
   archive.add(path,arcname=path.name,recursive=False)
"""


def dump_environment_args(*, legacy_admin=False):
    if not legacy_admin and os.environ.get("DB_BACKUP_PASSWORD"):
        return ["-e", "DB_BACKUP_PASSWORD", "-e", "DB_BACKUP_USER=nexora_backup"]
    return []


def backup(destination, *, legacy_admin=False):
    destination = safe_location(destination)
    destination.mkdir(parents=True, exist_ok=False)
    db, api = service_id("db"), service_id("api")
    suffix = uuid.uuid4().hex
    db_tmp = f"/tmp/nexora-{suffix}.dump"
    storage_tmp = f"/tmp/nexora-{suffix}.tar.gz"
    # Dump first: referenced immutable blobs already exist before version commits.
    # Inject a secret from the operator process without recreating the DB container.
    # Docker reads the value from the environment; no password appears in command arguments.
    backup_env = dump_environment_args(legacy_admin=legacy_admin)
    run(
        [
            "docker",
            "exec",
            *backup_env,
            db,
            "sh",
            "-c",
            dump_command(legacy_admin=legacy_admin) + " -f " + db_tmp,
        ]
    )
    run(["docker", "cp", f"{db}:{db_tmp}", str(destination / "database.dump")])
    # Only validated private key-shaped files; no symlinks, directories or config secrets.
    script = storage_archive_script(storage_tmp)
    run(["docker", "exec", api, "python", "-c", script])
    run(["docker", "cp", f"{api}:{storage_tmp}", str(destination / "storage.tar.gz")])
    for file in ["compose.yaml", ".env.example"]:
        shutil.copy2(ROOT / file, destination / file)
    files = ["database.dump", "storage.tar.gz", "compose.yaml", ".env.example"]
    manifest = {
        "format": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "files": {f: checksum(destination / f) for f in files},
        "secrets": "Runtime secrets must be escrowed separately in an encrypted secret manager. No .env is copied.",
        "verified_restore": False,
    }
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    run(["docker", "exec", db, "rm", "--", db_tmp])
    run(["docker", "exec", api, "rm", "--", storage_tmp])
    print("Backup created; restore verification is still required:", destination)


def verify(destination, database):
    destination = safe_location(destination)
    if not re.fullmatch(r"nexora_restore_test_[a-z0-9_]{1,30}", database):
        raise ValueError("Restore tests only create NEW databases named nexora_restore_test_<suffix>")
    manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != 1 or set(manifest["files"]) != {
        "database.dump",
        "storage.tar.gz",
        "compose.yaml",
        ".env.example",
    }:
        raise ValueError("Invalid backup manifest")
    for file, expected in manifest["files"].items():
        if checksum(destination / file) != expected:
            raise ValueError("Backup checksum mismatch")
    db = service_id("db")
    exists = run(
        [
            "docker",
            "exec",
            db,
            "sh",
            "-c",
            'psql -U "$POSTGRES_USER" -d postgres -At -c "SELECT 1 FROM pg_database WHERE datname=\''
            + database
            + "'\"",
        ],
        capture=True,
    )
    if exists:
        raise ValueError("Restore target already exists; refusing to overwrite it")
    target = destination / ("restore-" + database)
    target.mkdir(exist_ok=False)
    uploads = target / "uploads"
    uploads.mkdir()
    with tarfile.open(destination / "storage.tar.gz", "r:gz") as archive:
        members = archive.getmembers()
        if len(members) > 1000000:
            raise ValueError("Archive exceeds restore profile")
        for member in members:
            if (
                not re.fullmatch(r"[a-f0-9]{32}", member.name)
                or not member.isfile()
                or member.size > 100 * 1024 * 1024
            ):
                raise ValueError("Unsafe storage archive entry")
            source = archive.extractfile(member)
            if source is None:
                raise ValueError("Missing archive entry")
            with source, (uploads / member.name).open("xb") as output:
                shutil.copyfileobj(source, output)
    tmp = f"/tmp/nexora-restore-{uuid.uuid4().hex}.dump"
    run(["docker", "exec", db, "sh", "-c", 'createdb -U "$POSTGRES_USER" ' + database])
    run(["docker", "cp", str(destination / "database.dump"), f"{db}:{tmp}"])
    run(
        [
            "docker",
            "exec",
            db,
            "sh",
            "-c",
            'pg_restore -U "$POSTGRES_USER" -d ' + database + " --no-owner --no-acl --exit-on-error " + tmp,
        ]
    )
    versions = run(
        [
            "docker",
            "exec",
            db,
            "sh",
            "-c",
            'psql -U "$POSTGRES_USER" -d '
            + database
            + ' -At -F "|" -c "SELECT storage_key,size,sha256 FROM document_versions ORDER BY id"',
        ],
        capture=True,
    )
    verified = 0
    for line in versions.splitlines():
        key, size, digest = line.split("|")
        if not re.fullmatch(r"[a-f0-9]{32}", key):
            raise ValueError("Unsafe database storage key")
        file = uploads / key
        if not file.is_file() or file.stat().st_size != int(size) or checksum(file) != digest:
            raise ValueError("Restored document version failed integrity verification")
        verified += 1
    counts = run(
        [
            "docker",
            "exec",
            db,
            "sh",
            "-c",
            'psql -U "$POSTGRES_USER" -d '
            + database
            + ' -At -F "|" -c "SELECT (SELECT count(*) FROM documents),(SELECT count(*) FROM document_versions),(SELECT count(*) FROM audit_events),(SELECT count(*) FROM workflow_instances),(SELECT count(*) FROM workflow_events)"',
        ],
        capture=True,
    )
    run(["docker", "exec", db, "rm", "--", tmp])
    report = {
        "verified_at": datetime.now(UTC).isoformat(),
        "database": database,
        "counts_documents_versions_audit_workflows_events": counts,
        "verified_blobs": verified,
        "storage_root": str(uploads),
        "scope": "PostgreSQL restore and every referenced version size/SHA-256. HTTP application smoke requires separate validation.",
    }
    (target / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    manifest["verified_restore"] = True
    manifest["restore_report"] = report
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Restore verified:", json.dumps(report))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["backup", "verify"])
    parser.add_argument("directory", type=Path)
    parser.add_argument("--database")
    parser.add_argument("--legacy-admin-dump", action="store_true",
                        help="Explicit pre-cutover backup only; uses the old operator account")
    args = parser.parse_args()
    if args.action == "backup":
        backup(args.directory, legacy_admin=args.legacy_admin_dump)
    elif args.database:
        verify(args.directory, args.database)
    else:
        parser.error("verify requires --database")
