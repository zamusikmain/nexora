"""Real HTTP and PostgreSQL regression tests; disposable nexora_test only."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from test_acl_contracts import setup_flow, uploaded
from test_api import client, create
from test_api import database as database  # noqa: F401

from app.models import AuditEvent, Document, DocumentVersion, OperationKey, User, WorkflowRequirement


def test_scanner_failure_retry_has_one_blocked_audit(database, monkeypatch):
    from fastapi import HTTPException

    from app import storage as storage_module

    c = client()
    doc = create(c)
    base = "/api/v1/documents/" + doc["id"]
    headers = key()
    unavailable = True

    class Scanner:
        def scan(self, path):
            if unavailable:
                raise HTTPException(503, "scanner_unavailable")
            return "synthetic-clean-scanner"

    monkeypatch.setattr(storage_module, "scanner", lambda: Scanner())

    def upload():
        return c.post(
            base + "/versions", files={"file": ("retry.txt", b"Retry bytes", "text/plain")}, headers=headers
        )

    assert upload().status_code == 503
    assert upload().status_code == 503
    unavailable = False
    result = upload()
    assert result.status_code == 201
    assert upload().json()["id"] == result.json()["id"]
    with database() as db:
        assert db.query(AuditEvent).filter_by(target_id=doc["id"], action="FILE_UPLOAD_BLOCKED").count() == 1
        assert db.query(DocumentVersion).filter_by(document_id=doc["id"]).count() == 1


@pytest.mark.parametrize("conditional", [False, True])
def test_required_route_rejects_unauthorized_roles_and_conditional_stages(database, conditional):
    owner, admin = client(), client("admin")
    doc = create(owner)
    base = "/api/v1/documents/" + doc["id"]
    uploaded(owner, base)
    stage = {"name_ru": "Этап", "name_en": "Stage", "selector": "role", "targets": ["LEGAL"]}
    if conditional:
        stage["conditions"] = [{"field": "confidentiality", "op": "eq", "value": "PUBLIC"}]
    response = admin.post(
        "/api/v1/workflow-templates",
        json={
            "code": "H_" + uuid4().hex[:8].upper(),
            "name_ru": "Тест",
            "name_en": "Test",
            "stages": [stage],
        },
    )
    assert response.status_code == 201, response.text
    template_id = response.json()["id"]
    with database.begin() as db:
        db.add(WorkflowRequirement(type_id="type", template_id=template_id, reviewer_roles=["MANAGER"]))
    try:
        result = owner.post(
            base + "/workflows",
            json={
                "template_id": template_id,
                "expected_revision": owner.get(base).json()["revision"],
                "idempotency_key": str(uuid4()),
            },
        )
        assert result.status_code == (409 if conditional else 422), result.text
    finally:
        with database.begin() as db:
            db.query(WorkflowRequirement).filter_by(type_id="type").delete()


def test_classification_can_only_rise_once_a_file_exists(database):
    owner = client()
    base = "/api/v1/documents/" + create(owner)["id"]

    def classify(value):
        return owner.patch(base, json={"confidentiality": value})

    # Without a file the owner may still correct the classification either way.
    assert classify("CONFIDENTIAL").status_code == 200
    assert classify("INTERNAL").status_code == 200
    assert classify("CONFIDENTIAL").status_code == 200
    uploaded(owner, base)
    lowered = classify("INTERNAL")
    assert lowered.status_code == 403 and lowered.json()["error"] == "classification_change_forbidden"
    assert classify("PUBLIC").status_code == 403
    assert owner.get(base).json()["confidentiality"] == "CONFIDENTIAL"
    assert classify("CONFIDENTIAL").status_code == 200  # unchanged value is not a downgrade
    assert owner.patch(base, json={"title": "Other fields stay editable"}).status_code == 200
    assert classify("RESTRICTED").status_code == 200
    assert classify("CONFIDENTIAL").status_code == 403

    # RESTRICTED is never lowered, even before any file.
    empty = "/api/v1/documents/" + create(owner)["id"]
    assert owner.patch(empty, json={"confidentiality": "RESTRICTED"}).status_code == 200
    assert owner.patch(empty, json={"confidentiality": "PUBLIC"}).status_code == 403


def test_required_route_is_selected_by_type_and_classification(database):
    from app.models import WorkflowInstance

    owner, admin = client(), client("admin")

    def template(role):
        response = admin.post(
            "/api/v1/workflow-templates",
            json={"code": "C_" + uuid4().hex[:8].upper(), "name_ru": "Тест", "name_en": "Test",
                  "stages": [{"name_ru": "Этап", "name_en": "Stage", "selector": "role", "targets": [role]}]},
        )
        assert response.status_code == 201, response.text
        return response.json()["id"]

    def document(classification):
        doc = create(owner)
        base = "/api/v1/documents/" + doc["id"]
        assert owner.patch(base, json={"confidentiality": classification}).status_code == 200
        uploaded(owner, base)
        return base

    def start(base, template_id):
        return owner.post(base + "/workflows", json={
            "template_id": template_id, "expected_revision": owner.get(base).json()["revision"],
            "idempotency_key": str(uuid4()),
        })

    general, strict = template("MANAGER"), template("LEGAL")
    with database.begin() as db:
        db.add(WorkflowRequirement(type_id="type", classification="*", template_id=general, reviewer_roles=["MANAGER"]))
        db.add(WorkflowRequirement(type_id="type", classification="CONFIDENTIAL", template_id=strict,
                                   reviewer_roles=["LEGAL"]))
    try:
        confidential, internal, restricted = document("CONFIDENTIAL"), document("INTERNAL"), document("RESTRICTED")
        # The exact classification route cannot be swapped for the type-wide one.
        assert start(confidential, general).json()["error"] == "required_workflow"
        started = start(confidential, strict)
        assert started.status_code == 201, started.text
        # Classifications without their own route fall back to the '*' route.
        assert start(internal, strict).json()["error"] == "required_workflow"
        assert start(internal, general).status_code == 201
        assert start(restricted, strict).json()["error"] == "required_workflow"
        with database() as db:
            snapshot = db.get(WorkflowInstance, started.json()["id"]).metadata_snapshot
            assert snapshot["required_route"] == {"template_id": strict, "classification": "CONFIDENTIAL"}
            assert snapshot["reviewer_roles"] == ["LEGAL"]
    finally:
        with database.begin() as db:
            db.query(WorkflowRequirement).filter_by(type_id="type").delete()


@pytest.mark.parametrize("committed", [False, True])
def test_upload_commit_failure_and_lost_ack_retry(database, monkeypatch, committed):
    from sqlalchemy.orm import Session

    c = client()
    doc = create(c)
    base = "/api/v1/documents/" + doc["id"]
    headers = key()
    original = Session.commit
    armed = True

    def fail_once(db):
        nonlocal armed
        if armed and any(isinstance(row, OperationKey) for row in db.new):
            armed = False
            if committed:
                original(db)
            raise RuntimeError("Synthetic lost database acknowledgement")
        return original(db)

    monkeypatch.setattr(Session, "commit", fail_once)
    assert (
        c.post(
            base + "/versions",
            files={"file": ("fault.txt", b"Retained bytes", "text/plain")},
            headers=headers,
        ).status_code
        == 500
    )
    response = client().post(
        base + "/versions", files={"file": ("fault.txt", b"Retained bytes", "text/plain")}, headers=headers
    )
    assert response.status_code == 201
    assert c.get(base + "/versions/" + response.json()["id"] + "/download").content == b"Retained bytes"
    with database() as db:
        assert db.query(DocumentVersion).filter_by(document_id=doc["id"]).count() == 1
        assert db.query(AuditEvent).filter_by(target_id=doc["id"], action="VERSION_CREATED").count() == 1


def key():
    return {"Idempotency-Key": str(uuid4())}


def test_required_key_and_restore_repeat(database):
    c = client()
    payload = {"title": "Missing key", "type_id": "type"}
    assert c.request("POST", "/api/v1/documents", json=payload).status_code == 422
    assert (
        c.post("/api/v1/documents", json=payload, headers={"Idempotency-Key": "invalid"}).status_code == 422
    )
    doc = create(c)
    base = "/api/v1/documents/" + doc["id"]
    version = uploaded(c, base)
    headers = key()
    body = {"expected_revision": c.get(base).json()["revision"]}
    first = c.post(base + "/versions/" + version + "/restore", json=body, headers=headers)
    second = c.post(base + "/versions/" + version + "/restore", json=body, headers=headers)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert len(c.get(base + "/versions").json()) == 2


def test_partial_patch_preserves_metadata_and_requires_revision(database):
    c = client()
    doc = create(c)
    base = "/api/v1/documents/" + doc["id"]
    r = c.request("PATCH", base, json={"expected_revision": doc["revision"], "description": "Changed"})
    assert r.status_code == 200, r.text
    assert r.json()["business_metadata"] == {"amount": 100} and r.json()["title"] == doc["title"]
    r = c.patch(base, json={"business_metadata": {"new": "retained"}})
    assert r.json()["business_metadata"] == {"amount": 100, "new": "retained"}
    assert c.request("PATCH", base, json={"title": "No revision"}).status_code == 422
    for payload in (
        {"title": None},
        {"title": ""},
        {"business_metadata": None},
        {"description": None},
        {"status": "APPROVED"},
    ):
        assert c.patch(base, json=payload).status_code == 422
    assert c.patch(base, json={"responsible_id": None, "tags": [], "description": ""}).status_code == 200
    assert c.get(base).json()["business_metadata"] == {"amount": 100, "new": "retained"}


def test_concurrent_patch_one_wins(database):
    clients = [client(), client()]
    doc = create(clients[0])
    base = "/api/v1/documents/" + doc["id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda pair: pair[0].patch(
                    base, json={"expected_revision": doc["revision"], "title": pair[1]}
                ),
                zip(clients, ["First", "Second"], strict=True),
            )
        )
    assert sorted(r.status_code for r in results) == [200, 409]
    assert clients[0].get(base).json()["business_metadata"] == {"amount": 100}


def test_create_parallel_repeat_conflict_and_actor_scope(database):
    clients = [client(), client()]
    headers = key()
    payload = {"title": "Durable creation", "type_id": "type"}
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(lambda c: c.post("/api/v1/documents", json=payload, headers=headers), clients)
        )
    assert [r.status_code for r in responses] == [201, 201]
    assert responses[0].json()["id"] == responses[1].json()["id"]
    assert (
        client().post("/api/v1/documents", json=payload, headers=headers).json()["id"]
        == responses[0].json()["id"]
    )
    assert (
        clients[0]
        .post("/api/v1/documents", json={**payload, "title": "Different"}, headers=headers)
        .status_code
        == 409
    )
    other = client("stranger").post("/api/v1/documents", json=payload, headers=headers)
    assert other.status_code == 201 and other.json()["id"] != responses[0].json()["id"]
    with database() as db:
        assert (
            db.query(AuditEvent)
            .filter_by(target_id=responses[0].json()["id"], action="DOCUMENT_CREATED")
            .count()
            == 1
        )
        assert db.query(OperationKey).filter_by(key=headers["Idempotency-Key"]).count() == 2


def test_parallel_upload_has_one_blob_version_and_audit(database):
    clients = [client(), client()]
    doc = create(clients[0])
    base = "/api/v1/documents/" + doc["id"]
    headers = key()

    def upload(c, content=b"One immutable version"):
        return c.post(
            base + "/versions", files={"file": ("file.txt", content, "text/plain")}, headers=headers
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(upload, clients))
    assert [r.status_code for r in responses] == [201, 201]
    assert responses[0].json()["id"] == responses[1].json()["id"]
    assert upload(client()).json()["id"] == responses[0].json()["id"]
    assert upload(clients[0], b"Different").status_code == 409
    with database() as db:
        assert db.query(DocumentVersion).filter_by(document_id=doc["id"]).count() == 1
        assert db.query(AuditEvent).filter_by(target_id=doc["id"], action="VERSION_CREATED").count() == 1
    assert (
        clients[0].get(base + "/versions/" + responses[0].json()["id"] + "/download").content
        == b"One immutable version"
    )


def test_failed_upload_key_can_retry_without_version(database):
    c = client()
    doc = create(c)
    base = "/api/v1/documents/" + doc["id"]
    headers = key()
    assert (
        c.post(
            base + "/versions", files={"file": ("file.txt", b"", "text/plain")}, headers=headers
        ).status_code
        == 422
    )
    assert (
        c.post(
            base + "/versions", files={"file": ("file.txt", b"", "text/plain")}, headers=headers
        ).status_code
        == 422
    )
    with database() as db:
        assert db.query(AuditEvent).filter_by(target_id=doc["id"], action="FILE_UPLOAD_BLOCKED").count() == 1
    assert (
        c.post(
            base + "/versions", files={"file": ("file.txt", b"Fixed", "text/plain")}, headers=headers
        ).status_code
        == 409
    )
    assert (
        c.post(
            base + "/versions", files={"file": ("file.txt", b"Fixed", "text/plain")}, headers=key()
        ).status_code
        == 201
    )
    assert len(c.get(base + "/versions").json()) == 1


def test_required_route_blocks_shortcut_and_rechecks_reviewer(database):
    owner, admin = client(), client("admin")
    doc = create(owner)
    base = "/api/v1/documents/" + doc["id"]
    uploaded(owner, base)

    def template(targets):
        return admin.post(
            "/api/v1/workflow-templates",
            json={
                "code": "H_" + uuid4().hex[:8].upper(),
                "name_ru": "Тест",
                "name_en": "Test",
                "stages": [{"name_ru": "Этап", "name_en": "Stage", "selector": "role", "targets": targets}],
            },
        ).json()["id"]

    required, shortcut = template(["LEGAL"]), template(["MANAGER"])
    with database.begin() as db:
        db.add(WorkflowRequirement(type_id="type", template_id=required, reviewer_roles=["LEGAL"]))
    try:
        revision = owner.get(base).json()["revision"]
        assert (
            owner.post(
                base + "/workflows",
                json={
                    "template_id": shortcut,
                    "expected_revision": revision,
                    "idempotency_key": str(uuid4()),
                },
            ).status_code
            == 409
        )
        assert owner.post(base + "/transitions", json={"action": "approve"}).status_code == 422
        instance = owner.post(
            base + "/workflows",
            json={"template_id": required, "expected_revision": revision, "idempotency_key": str(uuid4())},
        ).json()
        assert "id" in instance, instance
        assert owner.patch(base, json={"title": "During approval"}).status_code == 409
        assert (
            owner.post(base + "/versions", files={"file": ("bad.txt", b"Changed", "text/plain")}).status_code
            == 409
        )
        with database.begin() as db:
            db.get(User, "legal").role = "USER"
        result = client("legal").post(
            "/api/v1/workflows/" + instance["id"] + "/decisions",
            json={"action": "approve", "idempotency_key": str(uuid4())},
        )
        assert result.status_code == 403
        assert owner.get(base).json()["status"] == "IN_APPROVAL"
    finally:
        with database.begin() as db:
            db.get(User, "legal").role = "LEGAL"
            db.query(WorkflowRequirement).filter_by(type_id="type").delete()


def test_version_scope_tampering_cannot_finish(database):
    owner, base, old, _, decisions = setup_flow()
    with database.begin() as db:
        db.get(Document, base.rsplit("/", 1)[1]).current_version_id = old
    assert (
        client("legal")
        .post(decisions, json={"action": "approve", "idempotency_key": str(uuid4())})
        .status_code
        == 409
    )
    assert owner.get(base).json()["status"] == "IN_APPROVAL"


def test_related_patch_preserves_unsupplied_fields_and_rejects_stale(database):
    admin = client("admin")
    before = next(u for u in admin.get("/api/v1/users").json() if u["id"] == "stranger")
    result = admin.patch("/api/v1/users/stranger", json={"status": "BLOCKED"})
    assert result.status_code == 200 and result.json()["department_id"] == before["department_id"]
    assert (
        admin.patch(
            "/api/v1/users/stranger", json={"status": "ACTIVE", "expected_updated_at": before["updated_at"]}
        ).status_code
        == 409
    )
    admin.patch("/api/v1/users/stranger", json={"status": "ACTIVE"})
    owner = client()
    parent = owner.post("/api/v1/folders", json={"name": "Parent"}).json()
    folder = owner.post("/api/v1/folders", json={"name": "Child", "parent_id": parent["id"]}).json()
    result = owner.patch(
        "/api/v1/folders/" + folder["id"],
        json={"name": "Renamed", "expected_updated_at": folder["updated_at"]},
    )
    assert result.status_code == 200 and result.json()["parent_id"] == parent["id"]
