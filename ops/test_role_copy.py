"""Verify an existing-data COPY; operator runner is allowed only in the isolated cluster."""

import json
import os

import psycopg
from alembic import command
from alembic.config import Config
from database_roles import provision
from fastapi.testclient import TestClient
from psycopg import sql


def snapshot(conn):
    result = {}
    for (table,) in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"):
        result[table] = conn.execute(sql.SQL(
            "SELECT count(*),md5(coalesce(string_agg(row_to_json(t)::text,'|' ORDER BY row_to_json(t)::text),'')) "
            "FROM public.{} t"
        ).format(sql.Identifier(table))).fetchone()
    return result


def run():
    if os.environ.get("NEXORA_ISOLATED_ROLE_TEST") != "isolated-docker-cluster":
        raise RuntimeError("Isolated cluster confirmation required")
    with psycopg.connect(os.environ["NEXORA_ROLE_ADMIN_URL"]) as conn:
        if conn.info.dbname != "nexora_restore_test_existing_roles":
            raise RuntimeError("Only the designated COPY is allowed")
        before = snapshot(conn)
        provision(conn, [os.environ[k] for k in (
            "DB_RUNTIME_PASSWORD", "DB_MIGRATIONS_PASSWORD", "DB_BACKUP_PASSWORD")])
    from app.config import settings

    cfg = settings()
    cfg.database_url = os.environ["NEXORA_TEST_MIGRATIONS_URL"]
    command.upgrade(Config("alembic.ini"), "head")
    cfg.database_url = os.environ["DATABASE_URL"]
    with psycopg.connect(os.environ["NEXORA_ROLE_ADMIN_URL"]) as conn:
        assert before == snapshot(conn), "Provisioning/migrations changed existing records"
    print("COPY_RECORDS_UNCHANGED", json.dumps(before), flush=True)
    with psycopg.connect(cfg.database_url.replace("postgresql+psycopg://", "postgresql://")) as conn:
        assert conn.execute("SELECT current_user").fetchone()[0] == "nexora_runtime"
        email = conn.execute("SELECT email FROM users WHERE role='ADMIN' AND status='ACTIVE' LIMIT 1").fetchone()[0]
    from app.main import app

    client = TestClient(app)
    client.headers["origin"] = cfg.web_origin
    login = client.post("/api/v1/auth/login", json={"email": email, "password": os.environ["COPY_DEMO_PASSWORD"]})
    assert login.status_code == 200, login.text
    client.headers["x-csrf-token"] = login.json()["csrf_token"]
    docs = client.get("/api/v1/documents").json()
    assert docs["total"] == before["documents"][0]
    checked = 0
    for doc in docs["items"]:
        base = "/api/v1/documents/" + doc["id"]
        assert client.get(base).status_code == 200
        assert client.get(base + "/workflows").status_code == 200
        for version in client.get(base + "/versions").json():
            response = client.get(base + "/versions/" + version["id"] + "/download")
            assert response.status_code == 200, response.text
            import hashlib

            assert len(response.content) == version["size"]
            assert hashlib.sha256(response.content).hexdigest() == version["sha256"]
            checked += 1
    assert checked == before["document_versions"][0]
    assert client.post("/api/v1/auth/logout").status_code == 204
    print("COPY_RUNTIME_LOGIN_LIST_WORKFLOWS_DOWNLOAD_LOGOUT_PASSED", checked, flush=True)


if __name__ == "__main__":
    run()
