import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.auth import digest, password_hasher
from app.config import settings
from app.db import get_db
from app.main import app
from app.models import AuditEvent, AuthSession, Department, DocumentType, User

TEST_PASSWORD = "Test-only-password-2026"


@pytest.fixture(scope="module")
def database(tmp_path_factory):
    url = os.getenv("NEXORA_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set NEXORA_TEST_DATABASE_URL to a disposable PostgreSQL database named nexora_test")
    engine = create_engine(url)
    if engine.url.database != "nexora_test":
        pytest.fail("Integration tests only accept database named nexora_test")
    admin_url = os.getenv("NEXORA_TEST_ADMIN_URL", url)
    migration_url = os.getenv("NEXORA_TEST_MIGRATIONS_URL", url)
    admin_engine = create_engine(admin_url)
    migration_engine = create_engine(migration_url)
    if any(e.url.database != "nexora_test" for e in (admin_engine, migration_engine)):
        pytest.fail("All integration test connections must target nexora_test")
    previous = settings().database_url
    settings().database_url = migration_url
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    settings().database_url = url
    # Fixture setup and deliberate direct-DB tampering are operator actions, not API privileges.
    factory = sessionmaker(admin_engine, expire_on_commit=False)
    runtime_factory = sessionmaker(engine, expire_on_commit=False)
    with factory.begin() as db:
        db.execute(
            text(
                "TRUNCATE audit_events, comments, documents, document_versions, auth_sessions, login_throttles, users, document_types, departments CASCADE"
            )
        )
        it = Department(id="it", code="IT", name_ru="ИТ", name_en="IT")
        legal = Department(id="legal", code="LEGAL", name_ru="Юристы", name_en="Legal")
        db.add_all([it, legal, DocumentType(id="type", code="MEMO", name_ru="Записка", name_en="Memo")])
        db.flush()
        for name, role, department in [
            ("owner", "USER", "it"),
            ("stranger", "USER", "legal"),
            ("manager", "MANAGER", "it"),
            ("legal", "LEGAL", "legal"),
            ("admin", "ADMIN", "it"),
        ]:
            db.add(
                User(
                    id=name,
                    email=name + "@test.local",
                    display_name=name,
                    role=role,
                    status="ACTIVE",
                    department_id=department,
                    password_hash=password_hasher.hash(TEST_PASSWORD),
                )
            )
    settings().storage_root = tmp_path_factory.mktemp("uploads")

    def override():
        with runtime_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override
    yield factory
    app.dependency_overrides.clear()
    settings().database_url = previous
    engine.dispose()
    admin_engine.dispose()
    migration_engine.dispose()


def client(name="owner"):
    c = TestClient(app)
    c.headers["origin"] = settings().web_origin
    response = c.post("/api/v1/auth/login", json={"email": name + "@test.local", "password": TEST_PASSWORD})
    assert response.status_code == 200, response.text
    c.headers["x-csrf-token"] = response.json()["csrf_token"]
    from uuid import uuid4
    original_post, original_patch = c.post, c.patch

    def keyed_post(url, **kwargs):
        kwargs["headers"] = {"Idempotency-Key": str(uuid4()), **kwargs.get("headers", {})}
        return original_post(url, **kwargs)

    def revision_patch(url, **kwargs):
        if str(url).startswith("/api/v1/documents/") and "json" in kwargs:
            payload = dict(kwargs["json"])
            if "expected_revision" not in payload:
                payload["expected_revision"] = c.get(url).json().get("revision", 1)
            kwargs["json"] = payload
        elif "json" in kwargs:
            collection, ident = str(url).rsplit("/", 1)
            if collection in {"/api/v1/users", "/api/v1/document-types", "/api/v1/folders"}:
                rows = c.get(collection + '/' + ident + '/breadcrumbs' if collection == '/api/v1/folders' else collection).json()
                row = next((r for r in rows if r["id"] == ident), {}) if isinstance(rows, list) else {}
                kwargs["json"] = {"expected_updated_at": row.get("updated_at", "2000-01-01T00:00:00Z"), **kwargs["json"]}
        return original_patch(url, **kwargs)

    c.post, c.patch = keyed_post, revision_patch
    return c


def create(c):
    r = c.post(
        "/api/v1/documents",
        json={"title": "Test document", "type_id": "type", "business_metadata": {"amount": 100}},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_auth_csrf_block_expiry_logout(database):
    anonymous = TestClient(app)
    assert anonymous.get("/api/v1/documents").status_code == 401
    assert (
        anonymous.post(
            "/api/v1/auth/login", json={"email": "owner@test.local", "password": TEST_PASSWORD}
        ).status_code
        == 403
    )
    c = client()
    assert "HttpOnly" in c.cookies.jar._cookies["testserver.local"]["/"]["nexora_session"]._rest
    assert c.get("/api/v1/auth/me").json()["user"]["role"] == "USER"
    assert (
        c.post(
            "/api/v1/documents", headers={"x-csrf-token": "bad"}, json={"title": "x", "type_id": "type"}
        ).status_code
        == 403
    )
    with database.begin() as db:
        u = db.get(User, "owner")
        u.status = "BLOCKED"
    assert c.get("/api/v1/auth/me").status_code == 401
    assert (
        c.post(
            "/api/v1/auth/login", json={"email": "owner@test.local", "password": TEST_PASSWORD}
        ).status_code
        == 401
    )
    with database.begin() as db:
        db.get(User, "owner").status = "ACTIVE"
    c = client()
    with database.begin() as db:
        s = db.get(AuthSession, digest(c.cookies.get("nexora_session")))
        s.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert c.get("/api/v1/auth/me").status_code == 401
    c = client()
    assert c.post("/api/v1/auth/logout").status_code == 204
    assert c.get("/api/v1/auth/me").status_code == 401


def test_document_versions_lifecycle_audit_bola(database):
    owner, stranger, manager, admin = client(), client("stranger"), client("manager"), client("admin")
    doc = create(owner)
    base = "/api/v1/documents/" + doc["id"]
    assert doc["number"].startswith("DOC-")
    assert stranger.get(base).status_code == 404
    assert stranger.get(base + "/versions").status_code == 404
    assert stranger.get(base + "/comments").status_code == 404
    assert stranger.get(base + "/activity").status_code == 404
    assert doc["id"] not in [d["id"] for d in stranger.get("/api/v1/documents").json()["items"]]
    assert manager.get(base).status_code == 404
    assert manager.patch(base, json={"title": "forged", "business_metadata": {}}).status_code == 404
    assert owner.patch(base, json={"title": "forged", "status": "APPROVED"}).status_code == 422
    assert owner.post(base + "/transitions", json={"action": "submit"}).status_code == 409
    v1 = owner.post(base + "/versions", files={"file": ("one.txt", b"first", "text/plain")}).json()
    assert v1["version_number"] == 1
    v2 = owner.post(base + "/versions", files={"file": ("two.txt", b"second", "text/plain")}).json()
    assert v2["version_number"] == 2
    assert owner.get(base).json()["current_version_id"] == v2["id"]
    assert len(owner.get(base + "/versions").json()) == 2
    download = base + "/versions/" + v1["id"] + "/download"
    assert owner.get(download).content == b"first"
    assert stranger.get(download).status_code == 404
    other = create(owner)
    assert (
        owner.get("/api/v1/documents/" + other["id"] + "/versions/" + v1["id"] + "/download").status_code
        == 404
    )
    assert owner.post(base + "/comments", json={"body": "hello"}).status_code == 201
    assert owner.post(base + "/transitions", json={"action": "submit"}).json()["status"] == "SUBMITTED"
    assert owner.post(base + "/transitions", json={"action": "archive"}).status_code == 409
    assert (
        owner.post(base + "/versions", files={"file": ("three.txt", b"no", "text/plain")}).status_code == 409
    )
    assert owner.post(base + "/transitions", json={"action": "cancel"}).json()["status"] == "CANCELLED"
    assert owner.post(base + "/transitions", json={"action": "archive"}).json()["status"] == "ARCHIVED"
    assert owner.post(base + "/comments", json={"body": "no"}).status_code == 409
    actions = {a["action"] for a in owner.get(base + "/activity").json()}
    assert {
        "DOCUMENT_CREATED",
        "VERSION_CREATED",
        "FILE_DOWNLOADED",
        "COMMENT_ADDED",
        "DOCUMENT_SUBMITTED",
        "DOCUMENT_ARCHIVED",
    } <= actions
    assert owner.get("/api/v1/audit").status_code == 403
    assert admin.get("/api/v1/audit").status_code == 200
    assert owner.get("/api/v1/users").status_code == 403
    assert "password_hash" not in admin.get("/api/v1/users").text
    assert (
        owner.get(
            "/api/v1/documents",
            params={"q": doc["number"], "status": "ARCHIVED", "type_id": "type", "department_id": "it"},
        ).json()["total"]
        == 1
    )
    assert stranger.get("/api/v1/dashboard").json()["by_status"] == {}
    with database() as db:
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == "USER_LOGIN_FAILED"))


def test_concurrent_numbering_and_versions(database):
    c = client()
    token = c.cookies.get("nexora_session")
    csrf = c.headers["x-csrf-token"]

    def concurrent_client():
        new = TestClient(app)
        new.cookies.set("nexora_session", token)
        import uuid
        new.headers.update({"origin": settings().web_origin, "x-csrf-token": csrf,
                            "Idempotency-Key": str(uuid.uuid4())})
        return new

    with ThreadPoolExecutor(max_workers=4) as pool:
        docs = list(pool.map(lambda _: create(concurrent_client()), range(8)))
    assert len({d["number"] for d in docs}) == 8
    base = "/api/v1/documents/" + docs[0]["id"]

    def upload(_):
        r = concurrent_client().post(base + "/versions", files={"file": ("v.txt", b"content", "text/plain")})
        assert r.status_code == 201, r.text
        return r.json()["version_number"]

    with ThreadPoolExecutor(max_workers=4) as pool:
        numbers = list(pool.map(upload, range(4)))
    assert sorted(numbers) == [1, 2, 3, 4]


def test_admin_status_and_role_enforcement(database):
    admin = client("admin")
    other = client("stranger")
    assert other.patch("/api/v1/users/owner", json={"role": "ADMIN", "status": "ACTIVE"}).status_code == 403
    assert admin.patch("/api/v1/users/admin", json={"role": "USER", "status": "BLOCKED"}).status_code == 409
    assert (
        admin.patch(
            "/api/v1/users/stranger", json={"role": "USER", "status": "DISABLED", "department_id": "legal"}
        ).status_code
        == 200
    )
    assert other.get("/api/v1/auth/me").status_code == 401
    assert (
        admin.patch(
            "/api/v1/users/stranger", json={"role": "USER", "status": "ACTIVE", "department_id": "legal"}
        ).status_code
        == 200
    )


def test_database_immutability_and_current_version_integrity(database):
    from sqlalchemy.exc import DBAPIError

    c = client()
    doc = create(c)
    base = "/api/v1/documents/" + doc["id"]
    version = c.post(base + "/versions", files={"file": ("immutable.txt", b"safe", "text/plain")}).json()
    for statement in [
        "UPDATE document_versions SET original_filename='changed' WHERE id=:id",
        "DELETE FROM document_versions WHERE id=:id",
    ]:
        with pytest.raises(DBAPIError), database.begin() as db:
            db.execute(text(statement), {"id": version["id"]})
    with pytest.raises(DBAPIError), database.begin() as db:
        db.execute(text("UPDATE audit_events SET action='changed' WHERE target_id=:id"), {"id": doc["id"]})
    other = create(c)
    with pytest.raises(DBAPIError), database.begin() as db:
        db.execute(
            text("UPDATE documents SET current_version_id=:version WHERE id=:id"),
            {"version": version["id"], "id": other["id"]},
        )


def test_rate_limit_and_request_body_cap(database, monkeypatch):
    with database.begin() as db:
        db.execute(text("TRUNCATE login_throttles"))
    c = TestClient(app)
    c.headers["origin"] = settings().web_origin
    for _ in range(20):
        assert (
            c.post(
                "/api/v1/auth/login", json={"email": "missing@test.local", "password": "wrong"}
            ).status_code
            == 401
        )
    assert (
        c.post("/api/v1/auth/login", json={"email": "missing@test.local", "password": "wrong"}).status_code
        == 429
    )
    with database.begin() as db:
        db.execute(text("TRUNCATE login_throttles"))
    monkeypatch.setattr(settings(), "max_upload_bytes", 8)
    response = c.post(
        "/api/v1/auth/login", content=b"x" * (1024 * 1024 + 9), headers={"content-type": "application/json"}
    )
    assert response.status_code == 413


def test_dms_folders_trash_favorites_revision_restore_diff(database):
    c, stranger = client(), client("stranger")
    root = c.post("/api/v1/folders", json={"name": "Root"}).json()
    child = c.post("/api/v1/folders", json={"name": "Child", "parent_id": root["id"]}).json()
    assert (
        c.patch("/api/v1/folders/" + root["id"], json={"name": "Root", "parent_id": child["id"]}).status_code
        == 409
    )
    assert stranger.get("/api/v1/folders/" + root["id"] + "/breadcrumbs").status_code == 404
    assert len(c.get("/api/v1/folders/" + child["id"] + "/breadcrumbs").json()) == 2
    d = create(c)
    base = "/api/v1/documents/" + d["id"]
    moved = c.post(base + "/move", json={"folder_id": child["id"], "expected_revision": d["revision"]})
    assert moved.status_code == 200, moved.text
    d = moved.json()
    assert c.patch(base, json={"title": "stale", "expected_revision": 1}).status_code == 409
    assert c.put(base + "/favorite").status_code == 204
    assert c.put(base + "/favorite").status_code == 204
    assert d["id"] in [x["id"] for x in c.get("/api/v1/documents?view=favorites").json()["items"]]
    assert stranger.put(base + "/favorite").status_code == 404
    v1 = c.post(base + "/versions", files={"file": ("a.txt", b"first\n", "text/plain")}).json()
    v2 = c.post(base + "/versions", files={"file": ("b.txt", b"second\n", "text/plain")}).json()
    assert "-first" in c.get(base + "/versions/" + v1["id"] + "/diff/" + v2["id"]).json()["diff"]
    assert stranger.get(base + "/versions/" + v1["id"] + "/diff/" + v2["id"]).status_code == 404
    d = c.get(base).json()
    result = c.post(base + "/versions/" + v1["id"] + "/restore", json={"expected_revision": d["revision"]})
    assert result.status_code == 201, result.text
    v3 = result.json()
    assert v3["version_number"] == 3 and v3["sha256"] == v1["sha256"]
    assert c.get(base + "/versions/" + v2["id"] + "/download").content == b"second\n"
    assert c.get(base + "/versions/" + v3["id"] + "/download").content == b"first\n"
    d = c.get(base).json()
    deleted = c.post(base + "/trash", json={"expected_revision": d["revision"]}).json()
    assert deleted["deleted_at"]
    assert d["id"] not in [x["id"] for x in c.get("/api/v1/documents").json()["items"]]
    assert d["id"] in [x["id"] for x in c.get("/api/v1/documents?view=trash").json()["items"]]
    assert c.patch(base, json={"title": "no"}).status_code == 409
    assert c.post(base + "/comments", json={"body": "no"}).status_code == 409
    assert c.post(base + "/transitions", json={"action": "submit"}).status_code == 409
    assert (
        stranger.post(base + "/restore", json={"expected_revision": deleted["revision"]}).status_code == 404
    )
    restored = c.post(base + "/restore", json={"expected_revision": deleted["revision"]})
    assert restored.status_code == 200 and restored.json()["deleted_at"] is None
    assert {"DOCUMENT_TRASHED", "DOCUMENT_RESTORED", "VERSION_RESTORED", "DOCUMENT_MOVED"} <= {
        x["action"] for x in c.get(base + "/activity").json()
    }


def test_concurrent_folder_moves_cannot_create_cycle(database):
    c = client()
    roots = [c.post("/api/v1/folders", json={"name": name}).json() for name in ("A", "B")]
    token, csrf = c.cookies.get("nexora_session"), c.headers["x-csrf-token"]

    def move(i):
        new = TestClient(app)
        new.cookies.set("nexora_session", token)
        new.headers.update({"origin": settings().web_origin, "x-csrf-token": csrf})
        return new.patch(
            "/api/v1/folders/" + roots[i]["id"],
            json={"name": roots[i]["name"], "parent_id": roots[1 - i]["id"],
                  "expected_updated_at": roots[i]["updated_at"]},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(move, range(2)))
    assert sorted(results) == [200, 409]


def test_admin_document_types_and_server_custom_field_validation(database):
    admin, c = client("admin"), client()
    payload = {
        "code": "CUSTOM_CONTRACT",
        "name_ru": "Договор",
        "name_en": "Contract",
        "fields": [
            {
                "key": "amount",
                "name_ru": "Сумма",
                "name_en": "Amount",
                "kind": "number",
                "required": True,
                "minimum": 0,
            },
            {
                "key": "currency",
                "name_ru": "Валюта",
                "name_en": "Currency",
                "kind": "select",
                "options": ["KZT", "USD"],
                "default": "KZT",
            },
            {"key": "date", "name_ru": "Дата", "name_en": "Date", "kind": "date"},
            {"key": "url", "name_ru": "Ссылка", "name_en": "Link", "kind": "URL"},
            {"key": "person", "name_ru": "Ответственный", "name_en": "Responsible", "kind": "user"},
        ],
    }
    assert c.post("/api/v1/document-types", json=payload).status_code == 403
    response = admin.post("/api/v1/document-types", json=payload)
    assert response.status_code == 201, response.text
    type_id = response.json()["id"]
    assert admin.post("/api/v1/document-types", json=payload).status_code == 409

    def create_custom(values):
        return c.post(
            "/api/v1/documents", json={"title": "Contract", "type_id": type_id, "business_metadata": values}
        )

    for values in (
        {},
        {"amount": -1},
        {"amount": True},
        {"amount": 1, "currency": "EUR"},
        {"amount": 1, "date": "bad"},
        {"amount": 1, "url": "javascript:alert(1)"},
        {"amount": 1, "person": "missing"},
        {"amount": 1, "unknown": 2},
    ):
        assert create_custom(values).status_code == 422, values
    result = create_custom({"amount": 150, "date": "2026-10-07", "person": "owner"})
    assert result.status_code == 201 and result.json()["business_metadata"]["currency"] == "KZT"
    base = "/api/v1/documents/" + result.json()["id"]
    preserved = c.patch(base, json={"title": "Contract", "business_metadata": {}})
    assert preserved.status_code == 200 and preserved.json()["business_metadata"]["amount"] == 150
    assert c.patch(base, json={"business_metadata": {"amount": None}}).status_code == 422
    assert c.patch("/api/v1/document-types/" + type_id, json=payload).status_code == 403
    payload["fields"][0]["enabled"] = False
    assert admin.patch("/api/v1/document-types/" + type_id, json=payload).status_code == 200
    assert create_custom({}).status_code == 201
    payload["fields"].append(payload["fields"][0])
    assert admin.post("/api/v1/document-types", json=payload).status_code == 422


def test_structured_metadata_dates_and_references(database):
    c = client()
    response = c.post(
        "/api/v1/documents",
        json={
            "title": "Metadata",
            "type_id": "type",
            "description": "Description",
            "category": "Policy",
            "tags": ["finance", "2026"],
            "responsible_id": "owner",
            "confidentiality": "CONFIDENTIAL",
            "effective_date": "2026-10-01",
            "expiration_date": "2026-12-01",
        },
    )
    assert response.status_code == 201, response.text
    doc = response.json()
    assert doc["tags"] == ["finance", "2026"] and doc["confidentiality"] == "CONFIDENTIAL"
    base = "/api/v1/documents/" + doc["id"]
    assert c.patch(base, json={"title": "Metadata", "expiration_date": "2026-01-01"}).status_code == 422
    assert c.patch(base, json={"title": "Metadata", "responsible_id": "missing"}).status_code == 422
    assert c.patch(base, json={"title": "Metadata", "tags": ["a", "a"]}).status_code == 422
    response = c.patch(base, json={"title": "Metadata renamed", "expected_revision": doc["revision"]})
    assert response.status_code == 200 and response.json()["description"] == "Description"


def workflow_template(admin, code="QA_FLOW", parallel=False, conditions=None):
    stages = [
        {
            "name_ru": "Проверка",
            "name_en": "Review",
            "selector": "user",
            "targets": ["manager", "legal"] if parallel else ["manager"],
            "require_comment": True,
            "due_hours": 24,
        }
    ]
    if conditions is not None:
        stages[0]["conditions"] = conditions
    stages.append(
        {"name_ru": "Согласование", "name_en": "Approval", "selector": "user", "targets": ["admin"]}
    )
    response = admin.post(
        "/api/v1/workflow-templates",
        json={"code": code, "name_ru": "Маршрут", "name_en": "Route", "stages": stages},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_workflow_parallel_snapshots_bola_and_idempotency(database):
    import uuid

    from sqlalchemy.exc import DBAPIError

    from app.models import WorkflowInstance

    owner, admin, manager, legal, stranger = (
        client(),
        client("admin"),
        client("manager"),
        client("legal"),
        client("stranger"),
    )
    template = workflow_template(admin, parallel=True)
    doc = create(owner)
    base = "/api/v1/documents/" + doc["id"]
    version = owner.post(
        base + "/versions", files={"file": ("wf.txt", b"Approval version", "text/plain")}
    ).json()
    doc = owner.get(base).json()
    key = str(uuid.uuid4())
    payload = {"template_id": template["id"], "expected_revision": doc["revision"], "idempotency_key": key}
    assert stranger.post(base + "/workflows", json=payload).status_code == 404
    response = owner.post(base + "/workflows", json=payload)
    assert response.status_code == 201, response.text
    instance = response.json()
    wf = "/api/v1/workflows/" + instance["id"] + "/decisions"
    assert owner.post(base + "/workflows", json=payload).json()["id"] == instance["id"]
    assert legal.get(base).status_code == 200
    assert legal.get(base + "/versions/" + version["id"] + "/download").content == b"Approval version"
    assert stranger.get(base).status_code == 404
    assert stranger.get(base + "/workflows").status_code == 404
    assert (
        stranger.post(wf, json={"action": "approve", "idempotency_key": str(uuid.uuid4())}).status_code == 404
    )
    assert owner.post(wf, json={"action": "approve", "idempotency_key": str(uuid.uuid4())}).status_code == 403
    assert admin.post(wf, json={"action": "approve", "idempotency_key": str(uuid.uuid4())}).status_code == 404
    assert (
        manager.post(wf, json={"action": "approve", "idempotency_key": str(uuid.uuid4())}).status_code == 422
    )
    # Creating a new template version does not alter the bound instance.
    changed = workflow_template(admin, parallel=False)
    assert changed["version"] == 2
    loaded = owner.get(base + "/workflows").json()[0]
    assert loaded["template"]["version"] == 1 and len(loaded["approvals"]) == 3
    assert owner.patch(base, json={"title": "no"}).status_code == 409
    decision = {"action": "approve", "comment": "Reviewed", "idempotency_key": str(uuid.uuid4())}
    response = manager.post(wf, json=decision)
    assert response.status_code == 200 and response.json()["stage"] == 0
    assert manager.post(wf, json=decision).status_code == 200
    assert manager.post(wf, json={**decision, "comment": "Different"}).status_code == 409
    assert manager.post(wf, json={**decision, "idempotency_key": str(uuid.uuid4())}).status_code == 404
    assert legal.post(wf, json={**decision, "idempotency_key": str(uuid.uuid4())}).json()["kind"] == "receipt"
    assert owner.get(base + "/workflows").json()[0]["stage"] == 1
    assert admin.get("/api/v1/approvals").json()["total"] >= 1
    final = admin.post(wf, json={"action": "approve", "idempotency_key": str(uuid.uuid4())})
    assert final.status_code == 200 and final.json()["status"] == "APPROVED"
    assert owner.get(base).json()["status"] == "APPROVED"
    assert len(owner.get(base + "/workflows").json()[0]["events"]) == 4
    with database() as db:
        saved = db.get(WorkflowInstance, instance["id"])
        assert saved.metadata_snapshot["metadata"]["amount"] == 100
    for sql in [
        "UPDATE workflow_templates SET name_en='forged' WHERE id=:id",
        "DELETE FROM workflow_templates WHERE id=:id",
    ]:
        with pytest.raises(DBAPIError), database.begin() as db:
            db.execute(text(sql), {"id": template["id"]})
    with pytest.raises(DBAPIError), database.begin() as db:
        db.execute(
            text("UPDATE workflow_instances SET metadata_snapshot='{}' WHERE id=:id"), {"id": instance["id"]}
        )
    with pytest.raises(DBAPIError), database.begin() as db:
        db.execute(
            text("UPDATE workflow_events SET comment='forged' WHERE instance_id=:id"), {"id": instance["id"]}
        )


def test_workflow_revision_rejection_cancel_conditions_and_concurrency(database):
    import uuid

    owner, admin, manager = client(), client("admin"), client("manager")
    template = workflow_template(
        admin, code="CONDITIONAL", conditions=[{"field": "metadata.amount", "op": "gte", "value": 1000}]
    )
    doc = create(owner)
    base = "/api/v1/documents/" + doc["id"]
    owner.post(base + "/versions", files={"file": ("flow.txt", b"v1", "text/plain")})

    def start(template_id):
        current = owner.get(base).json()
        r = owner.post(
            base + "/workflows",
            json={
                "template_id": template_id,
                "expected_revision": current["revision"],
                "idempotency_key": str(uuid.uuid4()),
            },
        )
        assert r.status_code == 201, r.text
        return r.json()

    instance = start(template["id"])
    assert instance["stage"] == 1 and len(instance["approvals"]) == 1
    wf = "/api/v1/workflows/" + instance["id"] + "/decisions"
    assert owner.post(wf, json={"action": "cancel", "idempotency_key": str(uuid.uuid4())}).status_code == 422
    assert (
        owner.post(
            wf, json={"action": "cancel", "comment": "Cancelled", "idempotency_key": str(uuid.uuid4())}
        ).json()["status"]
        == "CANCELLED"
    )
    # New document: return to revision, resubmit, then race two decisions.
    doc = create(owner)
    base = "/api/v1/documents/" + doc["id"]
    owner.post(base + "/versions", files={"file": ("flow.txt", b"v1", "text/plain")})
    regular = workflow_template(admin, code="REVISION_FLOW")
    instance = start(regular["id"])
    wf = "/api/v1/workflows/" + instance["id"] + "/decisions"
    assert (
        manager.post(
            wf, json={"action": "revision", "comment": "Correct amount", "idempotency_key": str(uuid.uuid4())}
        ).json()["status"]
        == "REVISION_REQUIRED"
    )
    assert (
        owner.patch(base, json={"title": "Corrected", "business_metadata": {"amount": 200}}).status_code
        == 200
    )
    instance = start(regular["id"])
    wf = "/api/v1/workflows/" + instance["id"] + "/decisions"
    token, csrf = manager.cookies.get("nexora_session"), manager.headers["x-csrf-token"]
    key = str(uuid.uuid4())

    def approve(_):
        c = TestClient(app)
        c.cookies.set("nexora_session", token)
        c.headers.update({"origin": settings().web_origin, "x-csrf-token": csrf})
        return c.post(wf, json={"action": "approve", "comment": "Checked", "idempotency_key": key})

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(approve, range(2)))
    assert [r.status_code for r in results] == [200, 200]
    assert len(owner.get(base + "/workflows").json()[0]["events"]) == 2
    assert (
        admin.post(
            wf, json={"action": "reject", "comment": "Rejected", "idempotency_key": str(uuid.uuid4())}
        ).json()["status"]
        == "REJECTED"
    )
    assert owner.get(base).json()["status"] == "REJECTED"


def test_scan_quarantine_fail_closed_attestation_and_legacy_download(database, monkeypatch):
    from fastapi import HTTPException
    from sqlalchemy.exc import DBAPIError

    from app import storage as store_module
    from app.models import FileScan

    c = client()
    doc = create(c)
    base = "/api/v1/documents/" + doc["id"]

    class BrokenScanner:
        def scan(self, path):
            raise HTTPException(503, "scanner_unavailable")

    monkeypatch.setattr(store_module, "scanner", lambda: BrokenScanner())
    result = c.post(base + "/versions", files={"file": ("blocked.txt", b"safe", "text/plain")})
    assert result.status_code == 503
    assert c.get(base + "/versions").json() == []
    assert not list(settings().storage_root.glob(".quarantine-*"))
    assert "FILE_UPLOAD_BLOCKED" in {a["action"] for a in c.get(base + "/activity").json()}

    # A successful scanner result is recorded separately from immutable version content.
    class CleanScanner:
        def scan(self, path):
            pass

    monkeypatch.setattr(store_module, "scanner", lambda: CleanScanner())
    monkeypatch.setattr(settings(), "malware_scanner", "clamav")
    version = c.post(base + "/versions", files={"file": ("scanned.txt", b"verified", "text/plain")}).json()
    with database() as db:
        record = db.get(FileScan, version["id"])
        assert record and record.sha256 == version["sha256"]
        for statement in [
            "UPDATE file_scans SET engine='changed' WHERE version_id=:id",
            "DELETE FROM file_scans WHERE version_id=:id",
        ]:
            with pytest.raises(DBAPIError):
                db.execute(text(statement), {"id": version["id"]})
                db.commit()
            db.rollback()

    monkeypatch.setattr(settings(), "app_env", "production")
    assert c.get(base + "/versions/" + version["id"] + "/download").content == b"verified"
    from app.models import DocumentVersion

    with database() as db:
        row = db.get(DocumentVersion, version["id"])
        assert row
        path = store_module.storage().path(row.storage_key)
    path.write_bytes(b"corrupted")
    assert c.get(base + "/versions/" + version["id"] + "/download").status_code == 503
    path.write_bytes(b"verified")

    monkeypatch.setattr(settings(), "app_env", "development")
    monkeypatch.setattr(settings(), "malware_scanner", "disabled-development")
    version = c.post(base + "/versions", files={"file": ("legacy.txt", b"legacy", "text/plain")}).json()
    monkeypatch.setattr(settings(), "app_env", "production")
    assert c.get(base + "/versions/" + version["id"] + "/download").status_code == 503
    assert c.post(base + "/transitions", json={"action": "submit"}).status_code == 503


def test_session_inventory_scoping_revocation_and_admin(database):
    a, b, stranger, admin = client(), client(), client("stranger"), client("admin")
    rows = a.get("/api/v1/auth/sessions").json()
    assert rows and all("csrf_token" not in s and len(s["id"]) == 36 for s in rows)
    assert sum(s["current"] for s in rows) == 1
    foreign = stranger.get("/api/v1/auth/sessions").json()[0]["id"]
    assert a.delete("/api/v1/auth/sessions/" + foreign).status_code == 404
    assert a.post("/api/v1/auth/sessions/revoke-others").status_code == 204
    assert b.get("/api/v1/auth/me").status_code == 401
    assert a.get("/api/v1/auth/me").status_code == 200
    assert stranger.post("/api/v1/auth/users/owner/sessions/revoke").status_code == 403
    assert admin.post("/api/v1/auth/users/owner/sessions/revoke").status_code == 204
    assert a.get("/api/v1/auth/me").status_code == 401
    a = client()
    current = next(x for x in a.get("/api/v1/auth/sessions").json() if x["current"])
    assert a.delete("/api/v1/auth/sessions/" + current["id"]).status_code == 204
    assert a.get("/api/v1/auth/me").status_code == 401


def test_document_list_query_count_does_not_grow_with_owned_rows(database):
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    c = client()
    statements: list[str] = []

    def count(conn, cursor, statement, *args):
        statements.append(statement)

    def queries_for_my_list() -> tuple[int, list[dict]]:
        statements.clear()
        event.listen(Engine, "before_cursor_execute", count)
        try:
            response = c.get("/api/v1/documents", params={"view": "my", "page_size": 100})
        finally:
            event.remove(Engine, "before_cursor_execute", count)
        assert response.status_code == 200
        return len(statements), response.json()["items"]

    for _ in range(2):
        create(c)
    small, _ = queries_for_my_list()
    for _ in range(6):
        create(c)
    large, items = queries_for_my_list()
    assert len(items) >= 8
    # Owner capability checks are answered by policy without per-row queries.
    assert large == small, (small, large)
    assert all(
        {k: i["capabilities"][k] for k in ("activity", "compare", "comments", "workflow")}
        == dict.fromkeys(("activity", "compare", "comments", "workflow"), True)
        for i in items
    )
