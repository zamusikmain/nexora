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
    previous = settings().database_url
    settings().database_url = url
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    factory = sessionmaker(engine, expire_on_commit=False)
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
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override
    yield factory
    app.dependency_overrides.clear()
    settings().database_url = previous
    engine.dispose()


def client(name="owner"):
    c = TestClient(app)
    c.headers["origin"] = settings().web_origin
    response = c.post("/api/v1/auth/login", json={"email": name + "@test.local", "password": TEST_PASSWORD})
    assert response.status_code == 200, response.text
    c.headers["x-csrf-token"] = response.json()["csrf_token"]
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
    assert manager.get(base).status_code == 200
    assert manager.patch(base, json={"title": "forged", "business_metadata": {}}).status_code == 403
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
        new.headers.update({"origin": settings().web_origin, "x-csrf-token": csrf})
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
