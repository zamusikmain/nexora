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
        excluded = ['metadata_snapshot'] if table == 'document_versions' else (
            ['version_id', 'instance_id', 'stage'] if table == 'comments' else [])
        result[table] = conn.execute(sql.SQL(
            "SELECT count(*),md5(coalesce(string_agg((to_jsonb(t)-%s::text[])::text,'|' ORDER BY (to_jsonb(t)-%s::text[])::text),'')) "
            "FROM public.{} t"
        ).format(sql.Identifier(table)), (excluded, excluded)).fetchone()
    return result


def run():
    if os.environ.get("NEXORA_ISOLATED_ROLE_TEST") != "isolated-docker-cluster":
        raise RuntimeError("Isolated cluster confirmation required")
    with psycopg.connect(os.environ["NEXORA_ROLE_ADMIN_URL"]) as conn:
        if conn.info.dbname != "nexora_restore_test_existing_roles":
            raise RuntimeError("Only the designated COPY is allowed")
        before = snapshot(conn)
        original_revision = conn.execute('SELECT version_num FROM alembic_version').fetchone()[0]
        provision(conn, [os.environ[k] for k in (
            "DB_RUNTIME_PASSWORD", "DB_MIGRATIONS_PASSWORD", "DB_BACKUP_PASSWORD")])
    from app.config import settings

    cfg = settings()
    cfg.database_url = os.environ["NEXORA_TEST_MIGRATIONS_URL"]
    migration_config = Config("alembic.ini")
    command.upgrade(migration_config, "head")
    if original_revision == '0006_sessions':
        command.downgrade(migration_config, '0006_sessions')
        command.upgrade(migration_config, 'head')
    cfg.database_url = os.environ["DATABASE_URL"]
    with psycopg.connect(os.environ["NEXORA_ROLE_ADMIN_URL"]) as conn:
        after = snapshot(conn)
        assert all(after[t] == data for t, data in before.items() if t != 'alembic_version'), 'Historical copy records changed'
        assert all(count == 0 for t, (count, _) in after.items() if t not in before), 'New tables must start empty'
        provision(conn, [os.environ[k] for k in (
            "DB_RUNTIME_PASSWORD", "DB_MIGRATIONS_PASSWORD", "DB_BACKUP_PASSWORD")])
    print("COPY_RECORDS_UNCHANGED", json.dumps({t: data[0] for t, data in before.items()}), flush=True)
    with psycopg.connect(cfg.database_url.replace("postgresql+psycopg://", "postgresql://")) as conn:
        assert conn.execute("SELECT current_user").fetchone()[0] == "nexora_runtime"
        documents = conn.execute('SELECT id,owner_id FROM documents ORDER BY id').fetchall()
        owners = dict(conn.execute('SELECT id,email FROM users WHERE id IN (SELECT owner_id FROM documents) AND status=\'ACTIVE\'').fetchall())
    from app.main import app

    def login(email, password):
        client = TestClient(app)
        client.headers['origin'] = cfg.web_origin
        response = client.post('/api/v1/auth/login', json={'email': email, 'password': password})
        assert response.status_code == 200, 'Copy-only login failed'
        client.headers['x-csrf-token'] = response.json()['csrf_token']
        return client

    clients = {owner: login(email, os.environ['COPY_DEMO_PASSWORD']) for owner, email in owners.items()}
    checked = 0
    download_urls = []
    for doc_id, owner_id in documents:
        client = clients[owner_id]
        base = "/api/v1/documents/" + doc_id
        assert client.get(base).status_code == 200
        assert client.get(base + "/workflows").status_code == 200
        for version in client.get(base + "/versions").json():
            download_url = base + "/versions/" + version["id"] + "/download"
            download_urls.append(download_url)
            response = client.get(download_url)
            assert response.status_code == 200, response.text
            import hashlib

            assert len(response.content) == version["size"]
            assert hashlib.sha256(response.content).hexdigest() == version["sha256"]
            checked += 1
    assert checked == before["document_versions"][0]
    for client in clients.values():
        assert client.post("/api/v1/auth/logout").status_code == 204
    from app.auth import password_hasher

    probe_password = 'Test-only-password-2026'
    with psycopg.connect(os.environ['NEXORA_ROLE_ADMIN_URL']) as conn:
        conn.execute("INSERT INTO users(id,email,display_name,password_hash,role,status) VALUES "
                     "('copy-acl-admin','copy-acl-admin@test.local','Copy-only ACL probe',%s,'ADMIN','ACTIVE')",
                     (password_hasher.hash(probe_password),))
    probe = login('copy-acl-admin@test.local', probe_password)
    assert probe.get('/api/v1/documents').json()['total'] == 0
    for doc_id, _ in documents:
        base = '/api/v1/documents/'+doc_id
        for suffix in ('', '/versions', '/comments', '/activity', '/workflows'):
            assert probe.get(base+suffix).status_code == 404
    for download_url in download_urls:
        assert probe.get(download_url).status_code == 404
    assert probe.post('/api/v1/auth/logout').status_code == 204
    print('COPY_ACL_ADMIN_FOREIGN_CONTENT_DENIED', flush=True)
    print("COPY_RUNTIME_LOGIN_LIST_WORKFLOWS_DOWNLOAD_LOGOUT_PASSED", checked, flush=True)


if __name__ == "__main__":
    run()
