"""Inspect private backups without modifying them; restore ONLY in a labelled isolated cluster."""

import argparse
import hashlib
import json
import re
import subprocess
import tarfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, **kwargs)


def inspect_archive(path):
    files = {}
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:
            if (not member.isfile() or not re.fullmatch(r"[a-f0-9]{32}", member.name)
                    or member.size > 100 * 1024 * 1024 or member.name in files):
                raise ValueError("Unsafe, oversized or duplicate archive member")
            with archive.extractfile(member) as stream:
                files[member.name] = (member.size, hashlib.file_digest(stream, "sha256").hexdigest())
    return files


def restored_state(container, database):
    command = ["docker", "exec", "-i", container, "psql", "-X", "-qAt", "-U", "postgres", "-d", database]
    tables = run(command, input=b"SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;").stdout.decode().splitlines()
    if any(not re.fullmatch(r"[a-z_]+", table) for table in tables):
        raise ValueError("Unexpected table identifier")
    statements = ["BEGIN READ ONLY;"]
    for table in tables:
        statements.append(
            f"SELECT '{table}',count(*),md5(coalesce(string_agg(row_to_json(t)::text,'|' "
            f"ORDER BY row_to_json(t)::text),'')) FROM public.{table} t;"
        )
    statements.append("COMMIT;")
    return run(command, input="\n".join(statements).encode()).stdout.decode().strip()


def audit(directory, container, expected_state=None):
    result = {"name": directory.name, "archive_files": 0, "referenced_versions": None,
              "verified_files": 0, "reliable": False, "reason": ""}
    try:
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        expected_names = {"database.dump", "storage.tar.gz", "compose.yaml", ".env.example"}
        if manifest.get("format") != 1 or set(manifest["files"]) != expected_names:
            raise ValueError("Invalid manifest")
        files = inspect_archive(directory / "storage.tar.gz")
        result["archive_files"] = len(files)
        for name, expected in manifest["files"].items():
            with (directory / name).open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                    raise ValueError("Manifest checksum mismatch")
        database = "nexora_restore_test_audit_" + uuid.uuid4().hex[:12]
        run(["docker", "exec", container, "createdb", "-U", "postgres", database])
        with (directory / "database.dump").open("rb") as dump:
            run(["docker", "exec", "-i", container, "pg_restore", "-U", "postgres", "-d", database,
                 "--no-owner", "--no-acl", "--exit-on-error"], stdin=dump)
        if expected_state is not None and restored_state(container, database) != expected_state:
            raise ValueError("Restored table fingerprints differ from captured database state")
        output = run(["docker", "exec", container, "psql", "-X", "-U", "postgres", "-d", database,
                      "-At", "-F", "|", "-c", "SELECT storage_key,size,sha256 FROM document_versions ORDER BY id"],
                     text=True).stdout
        refs = [line.split("|") for line in output.splitlines()]
        result["referenced_versions"] = len(refs)
        for key, size, digest in refs:
            if files.get(key) != (int(size), digest):
                raise ValueError("Missing or mismatched document file")
            result["verified_files"] += 1
        result["reliable"] = True
        result["reason"] = "Restored DB and all referenced file sizes/SHA-256 match"
    except (ValueError, OSError, KeyError, tarfile.TarError, subprocess.CalledProcessError) as exc:
        # Never include database contents or command/environment secrets in a publishable report.
        result["reason"] = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("isolated_database_container")
    parser.add_argument("--directory", type=Path, help="Check one specific private backup")
    parser.add_argument("--compare-state", type=Path, help="Require restored rows to match a captured state")
    args = parser.parse_args()
    target = args.isolated_database_container
    if not re.fullmatch(r"nexora-roles-db-[a-f0-9]{12}", target):
        raise ValueError("Only an isolated role-test PostgreSQL instance is accepted")
    info = json.loads(run(["docker", "inspect", target], text=True).stdout)[0]
    if info["Config"]["Labels"].get("nexora.role-test") != "true":
        raise ValueError("Missing isolated role-test label")
    networks = list(info["NetworkSettings"]["Networks"])
    if len(networks) != 1 or not networks[0].startswith("nexora-roles-"):
        raise ValueError("Separate test network required")
    if args.compare_state and not args.directory:
        raise ValueError("State comparison requires one explicitly selected backup")
    expected_state = None
    if args.compare_state:
        state_path = args.compare_state.resolve()
        if not state_path.is_relative_to(ROOT / "backups"):
            raise ValueError("Only private ignored state files are allowed")
        expected_state = state_path.read_text(encoding="utf-8")
    directories = [args.directory.resolve()] if args.directory else sorted((ROOT / "backups").iterdir())
    failed = False
    for directory in directories:
        if not directory.resolve().is_relative_to(ROOT / "backups"):
            raise ValueError("Only private ignored backups are allowed")
        if directory.is_dir() and not directory.is_symlink():
            result = audit(directory, target, expected_state)
            print(json.dumps(result, ensure_ascii=False), flush=True)
            failed |= not result["reliable"]
        else:
            raise ValueError("Backup directory is missing or a symlink")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
