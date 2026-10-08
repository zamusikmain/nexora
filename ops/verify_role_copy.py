"""Read working services; restore/test only in a separately labelled Docker cluster."""

import argparse
import json
import os
import re
import subprocess
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(args, **kwargs):
    return subprocess.run(args, check=True, cwd=ROOT, **kwargs)


def inspect(container):
    return json.loads(run(["docker", "inspect", container], capture_output=True, text=True).stdout)[0]


def env_of(container):
    return dict(item.split("=", 1) for item in container["Config"]["Env"])


def source_snapshot(container):
    command = ["docker", "exec", "-i", container, "sh", "-c",
               'psql -X -qAt -U "$POSTGRES_USER" -d "$POSTGRES_DB"']
    tables = run(command, input=b"SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;",
                 capture_output=True).stdout.decode().splitlines()
    if any(not re.fullmatch(r"[a-z_]+", table) for table in tables):
        raise ValueError("Unexpected table identifier")
    statements = ["BEGIN READ ONLY;"]
    for table in tables:
        statements.append(
            f"SELECT '{table}',count(*),md5(coalesce(string_agg(row_to_json(t)::text,'|' "
            f"ORDER BY row_to_json(t)::text),'')) FROM public.{table} t;"
        )
    statements.append("COMMIT;")
    return run(command, input="\n".join(statements).encode(), capture_output=True).stdout.decode().strip()


def verify_backup(target, copy_api, database):
    # Service discovery is redirected ONLY in this test harness, never in normal backup usage.
    import backup

    backup.service_id = lambda service: target if service == "db" else copy_api
    original_run = backup.run

    def isolated_run(command, **kwargs):
        if command[:2] == ["docker", "exec"] and target in command:
            index = command.index(target)
            command = command[:index] + ["-e", "POSTGRES_USER=postgres", "-e", "POSTGRES_DB=" + database] + command[index:]
        return original_run(command, **kwargs)

    backup.run = isolated_run
    suffix = uuid.uuid4().hex[:12]
    destination = ROOT / "backups" / ("roles-" + suffix)
    previous_secret = os.environ.get("DB_BACKUP_PASSWORD")
    os.environ["DB_BACKUP_PASSWORD"] = env_of(inspect(target))["DB_BACKUP_PASSWORD"]
    try:
        backup.backup(destination)
        backup.verify(destination, "nexora_restore_test_roles_" + suffix)
    finally:
        if previous_secret is None:
            os.environ.pop("DB_BACKUP_PASSWORD", None)
        else:
            os.environ["DB_BACKUP_PASSWORD"] = previous_secret


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("isolated_database_container")
    parser.add_argument("--backup-only", action="store_true", help="Retest backup of an already verified isolated copy")
    args = parser.parse_args()
    target = args.isolated_database_container
    if not re.fullmatch(r"nexora-roles-db-[a-f0-9]{12}", target):
        raise ValueError("Only a separately created role-test container is allowed")
    target_info = inspect(target)
    if target_info["Config"]["Labels"].get("nexora.role-test") != "true":
        raise ValueError("Missing isolated role-test label")
    networks = list(target_info["NetworkSettings"]["Networks"])
    if len(networks) != 1 or not networks[0].startswith("nexora-roles-"):
        raise ValueError("Test DB must have an isolated network")
    target_env = env_of(target_info)
    source_db = run(["docker", "compose", "ps", "-q", "db"], capture_output=True, text=True).stdout.strip()
    source_api = run(["docker", "compose", "ps", "-q", "api"], capture_output=True, text=True).stdout.strip()
    for value in (source_db, source_api):
        if not re.fullmatch(r"[a-f0-9]{12,64}", value) or value == target_info["Id"]:
            raise ValueError("Invalid source service identity")
    original_snapshot = source_snapshot(source_db)
    database = "nexora_restore_test_existing_roles"
    copy_api = target.replace("-db-", "-copy-")
    if args.backup_only:
        if inspect(copy_api)["Config"]["Labels"].get("nexora.role-test") != "true":
            raise ValueError("Missing isolated copy label")
        verify_backup(target, copy_api, database)
        assert source_snapshot(source_db) == original_snapshot
        print("WORKING_DATABASE_ALL_TABLE_FINGERPRINTS_UNCHANGED", flush=True)
        return
    # This source operation is pg_dump only, no DDL/DML, no files written in source containers.
    dump = run(["docker", "exec", source_db, "sh", "-c",
                'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-acl -Fc'],
               capture_output=True).stdout
    run(["docker", "exec", target, "createdb", "-U", "postgres", database])
    run(["docker", "exec", "-i", target, "pg_restore", "-U", "postgres", "-d", database,
         "--no-owner", "--no-acl", "--exit-on-error"], input=dump)
    runtime_password = env_of(inspect(target.replace("-db-", "-api-")))["DB_RUNTIME_PASSWORD"]
    migration_password = env_of(inspect(target.replace("-db-", "-api-")))["DB_MIGRATIONS_PASSWORD"]
    secrets = os.environ.copy()
    secrets.update({
        "NEXORA_ROLE_ADMIN_URL": f"postgresql://postgres:{target_env['POSTGRES_PASSWORD']}@db:5432/{database}",
        "DATABASE_URL": f"postgresql+psycopg://nexora_runtime:{runtime_password}@db:5432/{database}",
        "NEXORA_TEST_MIGRATIONS_URL": f"postgresql+psycopg://nexora_migrations:{migration_password}@db:5432/{database}",
        "DB_RUNTIME_PASSWORD": runtime_password,
        "DB_MIGRATIONS_PASSWORD": migration_password,
        "DB_BACKUP_PASSWORD": target_env["DB_BACKUP_PASSWORD"],
        "COPY_DEMO_PASSWORD": env_of(inspect(source_api))["DEMO_PASSWORD"],
    })
    command = ["docker", "run", "-d", "--name", copy_api, "--label", "nexora.role-test=true",
               "--network", networks[0], "--tmpfs", "/data/uploads:rw,uid=10001,gid=10001,mode=0700",
               "-v", str(ROOT / "apps/api") + ":/app:ro", "-v", str(ROOT / "ops") + ":/ops:ro"]
    for key in ("NEXORA_ROLE_ADMIN_URL", "DATABASE_URL", "NEXORA_TEST_MIGRATIONS_URL",
                "DB_RUNTIME_PASSWORD", "DB_MIGRATIONS_PASSWORD", "DB_BACKUP_PASSWORD", "COPY_DEMO_PASSWORD"):
        command += ["-e", key]
    command += ["-e", "PYTHONPATH=/ops:/app", "-e", "PYTHONDONTWRITEBYTECODE=1",
                "-e", "NEXORA_ISOLATED_ROLE_TEST=isolated-docker-cluster", "nexora-api",
                "python", "-c", "import time; time.sleep(86400)"]
    run(command, env=secrets)
    tar_script = """import re,sys,tarfile
from pathlib import Path
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as archive:
 for p in Path('/data/uploads').iterdir():
  if re.fullmatch('[a-f0-9]{32}',p.name) and p.is_file() and not p.is_symlink():
   archive.add(p,arcname=p.name,recursive=False)
"""
    archive = run(["docker", "exec", source_api, "python", "-c", tar_script], capture_output=True).stdout
    extract = """import re,sys,tarfile
from pathlib import Path
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|') as archive:
 for m in archive:
  if not re.fullmatch('[a-f0-9]{32}',m.name) or not m.isfile(): raise ValueError('Unsafe archive')
  with archive.extractfile(m) as src, (Path('/data/uploads')/m.name).open('xb') as out: out.write(src.read())
"""
    run(["docker", "exec", "-i", copy_api, "python", "-c", extract], input=archive)
    run(["docker", "exec", copy_api, "python", "/ops/test_role_copy.py"])
    verify_backup(target, copy_api, database)
    if source_snapshot(source_db) != original_snapshot:
        raise RuntimeError("Working records changed during verification; investigate concurrent activity")
    print("WORKING_DATABASE_ALL_TABLE_FINGERPRINTS_UNCHANGED", flush=True)
    print("Existing-data COPY verified; working DB was only read. Isolated copy retained:", copy_api)


if __name__ == "__main__":
    main()
