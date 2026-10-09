"""Run inside an isolated API test container, never against the working cluster."""

import os
import subprocess

import psycopg
from alembic import command
from alembic.config import Config
from database_roles import provision

PASSWORDS = [os.environ[key] for key in (
    "DB_RUNTIME_PASSWORD", "DB_MIGRATIONS_PASSWORD", "DB_BACKUP_PASSWORD")]
ADMIN_URL = os.environ["NEXORA_ROLE_ADMIN_URL"]


def run():
    if os.environ.get("NEXORA_ISOLATED_ROLE_TEST") != "isolated-docker-cluster":
        raise RuntimeError("Only run in the separate disposable role-test cluster")
    with psycopg.connect(ADMIN_URL) as conn:
        if conn.info.dbname != "nexora_test":
            raise RuntimeError("Only nexora_test is allowed")
        provision(conn, PASSWORDS)
    from app.config import settings

    settings().database_url = os.environ["NEXORA_TEST_MIGRATIONS_URL"]
    config = Config("alembic.ini")
    from verify_acl_compatibility import verify

    verify(config, settings())
    # Prove complete fresh migrations AND full downgrade/reupgrade without SUPERUSER.
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    with psycopg.connect(ADMIN_URL) as conn:
        provision(conn, PASSWORDS)
    settings().database_url = os.environ["NEXORA_TEST_DATABASE_URL"]
    subprocess.run(["python", "-m", "ruff", "check", "app", "tests"], check=True)
    subprocess.run(["python", "-m", "ruff", "check", "--no-cache", "/ops"], check=True)
    subprocess.run(["python", "-m", "mypy", "app"], check=True)
    subprocess.run(["python", "-m", "pytest", "-q", "--maxfail=1", "tests", "/ops/tests", "-o",
                    "cache_dir=/tmp/roles-pytest"], check=True)
    print("ISOLATED_ROLE_SUITE_PASSED", flush=True)


if __name__ == "__main__":
    run()
