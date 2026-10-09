"""PostgreSQL + real HTTP tests of the implemented Revision 2 policy."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.exc import DBAPIError
from test_acl_contracts import setup_flow, uploaded
from test_api import TEST_PASSWORD, client
from test_api import database as database  # noqa: F401

from app.auth import password_hasher
from app.models import (
    AccessGrant,
    AclAuthority,
    Document,
    DocumentVersion,
    GrantEndorsement,
    ReviewReceipt,
    User,
)


@pytest.mark.parametrize("hours,expected", [(0, 422), (1, 201), (8, 201), (9, 422), (168, 422)])
def test_restricted_duration_boundaries(database, actors, hours, expected):
    owner, base, version = document(actors, "RESTRICTED")
    result = owner.post(base + "/access-requests", json={"recipient_id": "stranger", "version_id": version,
        "hours": hours, "reason": "Synthetic duration boundary"})
    assert result.status_code == expected, result.text


def test_first_endorsement_must_still_be_valid_at_activation(database, actors):
    owner, base, version = document(actors, "RESTRICTED")
    grant = request_grant(owner, base, version, classification="RESTRICTED")
    assert endorse(actors["custodian"], grant, "CUSTODIAN").status_code == 200
    with database.begin() as db:
        db.get(User, "custodian").status = "BLOCKED"
    try:
        assert endorse(actors["security"], grant, "SECURITY").status_code == 409
        assert client("stranger").get(base).status_code == 404
    finally:
        with database.begin() as db:
            db.get(User, "custodian").status = "ACTIVE"
    assert endorse(actors["security"], grant, "SECURITY").status_code == 200


def test_search_uses_granted_frozen_title_not_current_metadata(database, actors):
    owner, base, version = document(actors)
    frozen = owner.get(base).json()["title"]
    request_grant(owner, base, version)
    changed = "New private title " + uuid4().hex
    with database.begin() as db:
        db.get(Document, base.rsplit("/", 1)[1]).title = changed
    reader = client("stranger")
    assert reader.get(base).json()["title"] == frozen
    assert reader.get("/api/v1/documents", params={"q": changed}).json()["total"] == 0
    assert reader.get("/api/v1/documents", params={"q": frozen}).json()["total"] == 1


def test_parallel_independent_votes_activate_exactly_once(database, actors):
    owner, base, version = document(actors, "RESTRICTED")
    grant = request_grant(owner, base, version, classification="RESTRICTED")
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(endorse, actors[name], grant, office)
                   for name, office in (("custodian", "CUSTODIAN"), ("security", "SECURITY"))]
        assert [f.result().status_code for f in futures] == [200, 200]
    with database() as db:
        assert db.get(AccessGrant, grant["id"]).status == "ACTIVE"
        assert len(list(db.query(GrantEndorsement).filter_by(grant_id=grant["id"]))) == 2
    assert client("stranger").get(base).status_code == 200


def test_parallel_same_decision_key_returns_one_own_receipt(database, actors):
    _, _, _, _, decisions = setup_flow()
    clients = [client("legal"), client("legal")]
    body = {"action": "approve", "comment": "Parallel own finding", "idempotency_key": str(uuid4())}
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(c.post, decisions, json=body) for c in clients]
        responses = [f.result() for f in futures]
        assert [r.status_code for r in responses] == [200, 200]
        assert responses[0].json()["receipt"]["id"] == responses[1].json()["receipt"]["id"]
    with database() as db:
        assert db.query(ReviewReceipt).filter_by(idempotency_key=body["idempotency_key"]).count() == 1


def test_restored_version_has_its_own_snapshot_without_inheriting_access(database, actors):
    owner, base, first = document(actors)
    second = uploaded(owner, base, "Second version.txt")
    request_grant(owner, base, second)
    response = owner.post(base + "/versions/" + first + "/restore",
                          json={"expected_revision": owner.get(base).json()["revision"]})
    assert response.status_code == 201, response.text
    restored = response.json()["id"]
    reader = client("stranger")
    assert reader.get(base).status_code == 404
    assert reader.get(base + "/versions/" + restored + "/download").status_code == 404
    with database() as db:
        version = db.get(DocumentVersion, restored)
        assert version.metadata_snapshot["current_version_id"] == restored
        assert version.metadata_snapshot["revision"] == owner.get(base).json()["revision"]
    request_grant(owner, base, restored)
    assert reader.get(base).status_code == 200
    assert reader.get(base + "/versions/" + restored + "/download").status_code == 200


def test_owner_replies_are_visible_only_to_their_current_review_stage(database, actors):
    owner, base, _, _, decisions = setup_flow()
    legal, future = client("legal"), client("stranger")
    reply = owner.post(base + "/comments", json={"body": "Owner reply to legal stage"})
    assert reply.status_code == 201
    assert reply.json()["id"] in {c["id"] for c in legal.get(base + "/comments").json()}
    assert future.get(base + "/comments").status_code == 404
    assert legal.post(decisions, json={"action": "approve", "comment": "Own decision",
                                      "idempotency_key": str(uuid4())}).status_code == 200
    next_reply = owner.post(base + "/comments", json={"body": "Owner reply to next stage"})
    assert next_reply.status_code == 201
    current = future.get(base + "/comments")
    assert current.status_code == 200
    assert {c["id"] for c in current.json()} == {next_reply.json()["id"]}
    assert legal.get(base + "/comments").status_code == 404

ROLES = ["USER", "REVIEWER", "APPROVER", "LEGAL", "MANAGER", "ADMIN"]
CLASSES = ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"]
STATES = ["DRAFT", "SUBMITTED", "IN_REVIEW", "IN_APPROVAL", "REVISION_REQUIRED", "APPROVED", "REJECTED", "CANCELLED", "ARCHIVED"]


@pytest.fixture(scope="module")
def actors(database):
    with database.begin() as db:
        for role in ROLES:
            db.add(User(id="matrix-" + role, email=("matrix-" + role).lower() + "@test.local", display_name=role,
                        role=role, department_id="it", status="ACTIVE", password_hash=password_hasher.hash(TEST_PASSWORD)))
        for name in ("custodian", "security"):
            db.add(User(id=name, email=name + "@test.local", display_name=name, role="USER", department_id="it",
                        status="ACTIVE", password_hash=password_hasher.hash(TEST_PASSWORD)))
        db.flush()
        for name, office in (("custodian", "CUSTODIAN"), ("security", "SECURITY"), ("custodian", "SECURITY")):
            db.add(AclAuthority(user_id=name, department_id="it", office=office, active=True,
                                expires_at=datetime.now(UTC) + timedelta(days=1)))
    return {**{role: client("matrix-" + role) for role in ROLES},
            "owner": client(), "custodian": client("custodian"), "security": client("security")}


def document(actors, classification="INTERNAL"):
    owner = actors["owner"]
    r = owner.post("/api/v1/documents", json={"title": "ACL " + uuid4().hex, "type_id": "type",
                                              "confidentiality": classification})
    assert r.status_code == 201, r.text
    base = "/api/v1/documents/" + r.json()["id"]
    version = uploaded(owner, base)
    return owner, base, version


@pytest.mark.parametrize("classification", CLASSES)
@pytest.mark.parametrize("state", STATES)
@pytest.mark.parametrize("role", ROLES)
def test_actual_role_classification_state_matrix(database, actors, role, state, classification):
    owner, base, version = document(actors, classification)
    with database.begin() as db:
        db.get(Document, base.rsplit("/", 1)[1]).status = state
    expected = 200 if role == "MANAGER" and state == "APPROVED" and classification in {"PUBLIC", "INTERNAL"} else 404
    reader = actors[role]
    assert reader.get(base).status_code == expected
    assert reader.get(base + "/versions/" + version + "/download").status_code == expected
    assert owner.get(base).status_code == 200
    assert reader.get(base + "/activity").status_code == 404
    assert reader.get(base + "/comments").status_code == 404


def request_grant(owner, base, version, recipient="stranger", classification="INTERNAL", **changes):
    body = {"recipient_id": recipient, "version_id": version, "actions": ["card", "file"],
            "hours": 4, "reason": "Synthetic necessary access", **changes}
    r = owner.post(base + "/access-requests", json=body)
    assert r.status_code == 201, r.text
    assert r.json()["status"] == ("PENDING" if classification == "RESTRICTED" else "ACTIVE")
    return r.json()


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("classification", CLASSES)
def test_each_role_can_review_only_its_current_pinned_version_and_own_receipt(database, actors, role, classification):
    owner, base, old = document(actors, classification)
    pinned = uploaded(owner, base, "Pinned review.txt")
    template = client("admin").post("/api/v1/workflow-templates", json={
        "code": "ALLROLES_" + uuid4().hex[:10].upper(), "name_ru": "Матрица этапа", "name_en": "Stage matrix",
        "stages": [{"name_ru": "Текущий", "name_en": "Current", "selector": "user", "targets": ["matrix-" + role]},
                   {"name_ru": "Будущий", "name_en": "Future", "selector": "user", "targets": ["stranger"]}]})
    assert template.status_code == 201, template.text
    response = owner.post(base + "/workflows", json={"template_id": template.json()["id"],
        "expected_revision": owner.get(base).json()["revision"], "idempotency_key": str(uuid4())})
    assert response.status_code == 201, response.text
    instance = response.json()
    approval = next(a for a in instance["approvals"] if a["user_id"] == "matrix-" + role)
    reader = actors[role]
    review_url = "/api/v1/approvals/" + approval["id"] + "/review"
    if classification == "RESTRICTED":
        assert reader.get(review_url).json()["kind"] == "access_required"
        assert reader.get(base).status_code == 404
        grant = reader.post("/api/v1/approvals/" + approval["id"] + "/access-requests",
                            json={"reason": "Synthetic role review"})
        assert grant.status_code == 201, grant.text
        assert endorse(actors["custodian"], grant.json(), "CUSTODIAN").status_code == 200
        assert endorse(actors["security"], grant.json(), "SECURITY").status_code == 200
    assert reader.get(review_url).json()["version"]["id"] == pinned
    assert reader.get(base + "/versions/" + old + "/download").status_code == 404
    assert reader.get(base + "/versions/" + pinned + "/download").status_code == 200
    assert reader.get(base + "/workflows").status_code == 404
    assert reader.get(base + "/activity").status_code == 404
    assert client("stranger").get(base).status_code == 404
    result = reader.post("/api/v1/workflows/" + instance["id"] + "/decisions", json={
        "action": "approve", "comment": "Own role finding", "idempotency_key": str(uuid4())})
    assert result.status_code == 200 and result.json()["kind"] == "receipt", result.text
    assert result.json()["receipt"]["snapshot"]["own_comment"] == "Own role finding"
    assert "approvals" not in result.json()
    assert reader.get(base).status_code == 404
    assert reader.get(base + "/versions/" + pinned + "/download").status_code == 404
    assert reader.get(base + "/comments").status_code == 404


def endorse(actor, grant, office):
    return actor.post("/api/v1/access/grants/" + grant["id"] + "/endorse",
                      json={"office": office, "scope_hash": grant["scope_hash"]})


@pytest.mark.parametrize("classification", CLASSES)
def test_personal_grant_revoke_and_no_new_version(database, actors, classification):
    owner, base, version = document(actors, classification)
    reader = client("stranger")
    grant = request_grant(owner, base, version, classification=classification)
    if classification == "RESTRICTED":
        assert reader.get(base).status_code == 404
        assert endorse(actors["custodian"], grant, "CUSTODIAN").json()["status"] == "PENDING"
        assert reader.get(base).status_code == 404
        assert endorse(actors["security"], grant, "SECURITY").json()["status"] == "ACTIVE"
    assert reader.get(base).status_code == 200
    assert reader.get(base + "/versions/" + version + "/download").status_code == 200
    assert reader.get(base + "/comments").status_code == 404
    assert reader.get(base + "/activity").status_code == 404
    new_version = uploaded(owner, base, "new-version.txt")
    assert reader.get(base).status_code == 404
    assert reader.get(base + "/versions/" + new_version + "/download").status_code == 404
    assert reader.get(base + "/versions/" + version + "/download").status_code == 200
    r = reader.post("/api/v1/access/grants/" + grant["id"] + "/revoke", json={"reason": "No longer needed"})
    assert r.status_code == 200 and r.json()["status"] == "REVOKED"
    assert reader.get(base + "/versions/" + version + "/download").status_code == 404


def test_restricted_no_self_approval_duplicate_vote_or_scope_mutation(database, actors):
    owner, base, version = document(actors, "RESTRICTED")
    grant = request_grant(owner, base, version, recipient="custodian", classification="RESTRICTED")
    assert endorse(actors["custodian"], grant, "CUSTODIAN").status_code == 403
    assert endorse(client("admin"), grant, "SECURITY").status_code == 404
    assert endorse(actors["security"], {**grant, "scope_hash": "0" * 64}, "SECURITY").status_code == 409
    grant = request_grant(owner, base, version, classification="RESTRICTED")
    assert endorse(actors["custodian"], grant, "CUSTODIAN").status_code == 200
    assert endorse(actors["custodian"], grant, "SECURITY").status_code == 409
    with pytest.raises(DBAPIError), database.begin() as db:
        db.get(AccessGrant, grant["id"]).version_id = str(uuid4())
    assert endorse(actors["security"], grant, "SECURITY").status_code == 200
    with database.begin() as db:
        db.get(User, "security").status = "BLOCKED"
    try:
        assert client("stranger").get(base + "/versions/" + version + "/download").status_code == 404
    finally:
        with database.begin() as db:
            db.get(User, "security").status = "ACTIVE"


def test_expired_grant_and_authority_are_denied_on_every_request(database, actors):
    owner, base, version = document(actors, "CONFIDENTIAL")
    grant = request_grant(owner, base, version)
    owner.post("/api/v1/access/grants/" + grant["id"] + "/revoke", json={"reason": "Replace with expired fixture"})
    with database.begin() as db:
        original = db.get(AccessGrant, grant["id"])
        data = {c.name: getattr(original, c.name) for c in AccessGrant.__table__.columns if c.name != "id"}
        data.update(status="ACTIVE", revoked_at=None, activated_at=datetime.now(UTC) - timedelta(hours=4),
                    expires_at=datetime.now(UTC) - timedelta(microseconds=1))
        db.add(AccessGrant(**data))
    reader = client("stranger")
    assert reader.get(base).status_code == 404
    assert reader.get(base + "/versions/" + version + "/download").status_code == 404
    assert base.rsplit("/", 1)[1] not in {d["id"] for d in reader.get("/api/v1/documents").json()["items"]}


def test_manager_draft_handoff_captures_people_and_revokes_with_new_version(database, actors):
    owner, base, version = document(actors)
    assert actors["MANAGER"].get(base).status_code == 404
    assert client("admin").put("/api/v1/departments/it/review-policy", json={"enabled": True}).status_code == 404
    assert actors["custodian"].put("/api/v1/departments/it/review-policy", json={"enabled": True}).status_code == 200
    r = owner.post(base + "/department-review", json={"version_id": version, "hours": 4, "reason": "Draft check"})
    assert r.status_code == 201, r.text
    assert actors["MANAGER"].get(base).status_code == 200
    with database.begin() as db:
        db.get(User, "matrix-USER").role = "MANAGER"
    try:
        assert actors["USER"].get(base).status_code == 404
    finally:
        with database.begin() as db:
            db.get(User, "matrix-USER").role = "USER"
    uploaded(owner, base, "v3.txt")
    assert actors["MANAGER"].get(base).status_code == 404
    for classification in ("CONFIDENTIAL", "RESTRICTED"):
        _, other, other_version = document(actors, classification)
        assert owner.post(other + "/department-review", json={"version_id": other_version, "reason": "Forbidden share"}).status_code == 422


def test_restricted_review_task_receipt_snapshot_and_close(database, actors):
    owner, base, version = document(actors, "RESTRICTED")
    admin = client("admin")
    r = admin.post("/api/v1/workflow-templates", json={"code": "RESTRICTED_" + uuid4().hex[:10].upper(),
        "name_ru": "Маршрут", "name_en": "Route", "stages": [
            {"name_ru": "Юристы", "name_en": "Legal", "selector": "user", "targets": ["legal"]},
            {"name_ru": "Другой", "name_en": "Next", "selector": "user", "targets": ["stranger"]}]})
    assert r.status_code == 201
    r = owner.post(base + "/workflows", json={"template_id": r.json()["id"],
        "expected_revision": owner.get(base).json()["revision"], "idempotency_key": str(uuid4())})
    assert r.status_code == 201
    instance = r.json()
    approval = next(a for a in instance["approvals"] if a["user_id"] == "legal")
    future = next(a for a in instance["approvals"] if a["user_id"] == "stranger")
    reader = client("legal")
    task = reader.get("/api/v1/approvals/" + approval["id"] + "/review").json()
    assert task["kind"] == "access_required" and "document" not in task and "title" not in task
    assert client("stranger").get("/api/v1/approvals/" + future["id"] + "/review").status_code == 404
    r = reader.post("/api/v1/approvals/" + approval["id"] + "/access-requests", json={"reason": "Current review"})
    assert r.status_code == 201, r.text
    grant = r.json()
    assert endorse(actors["custodian"], grant, "CUSTODIAN").status_code == 200
    assert endorse(actors["security"], grant, "SECURITY").status_code == 200
    assert reader.get("/api/v1/approvals/" + approval["id"] + "/review").json()["version"]["id"] == version
    key = str(uuid4())
    payload = {"action": "approve", "comment": "Own restricted finding", "idempotency_key": key}
    decisions = "/api/v1/workflows/" + instance["id"] + "/decisions"
    r = reader.post(decisions, json=payload)
    assert r.status_code == 200 and r.json()["kind"] == "receipt", r.text
    assert r.json()["receipt"]["snapshot"]["own_comment"] == "Own restricted finding"
    assert reader.get(base + "/versions/" + version + "/download").status_code == 404
    repeated = reader.post(decisions, json=payload)
    assert repeated.status_code == 200 and repeated.json()["receipt"]["assignment_id"] == approval["id"]
    receipt_url = "/api/v1/approvals/" + approval["id"] + "/receipt"
    assert client("stranger").get(receipt_url).status_code == 404
    assert owner.post(decisions, json={"action": "cancel", "comment": "Closed", "idempotency_key": str(uuid4())}).status_code == 200
    assert "snapshot" not in reader.get(receipt_url).json()
    assert reader.post(decisions, json=payload).status_code == 200
    assert client("stranger").get("/api/v1/approvals/" + future["id"] + "/receipt").json()["kind"] == "cancelled"
    r = reader.post("/api/v1/approvals/" + approval["id"] + "/access-requests", json={
        "purpose": "audit_snapshot", "actions": ["snapshot"], "reason": "Closed process own audit"})
    assert r.status_code == 201, r.text
    audit_grant = r.json()
    assert endorse(actors["custodian"], audit_grant, "CUSTODIAN").status_code == 200
    assert "snapshot" not in reader.get(receipt_url).json()
    assert endorse(actors["security"], audit_grant, "SECURITY").status_code == 200
    assert reader.get(receipt_url).json()["snapshot"]["own_comment"] == "Own restricted finding"
    assert reader.get(base).status_code == 404
    assert reader.get(base + "/versions/" + version + "/download").status_code == 404
    assert actors["custodian"].post("/api/v1/approvals/" + approval["id"] + "/receipt/revoke",
                                  json={"reason": "Hide own synthetic receipt", "hide_receipt": True}).status_code == 200
    assert reader.get(receipt_url).status_code == 404
    completed = reader.get("/api/v1/approvals", params={"view": "completed"})
    assert completed.status_code == 200
    assert approval["id"] not in {a["id"] for a in completed.json()["items"]}


def test_own_snapshot_no_other_stages_and_seven_day_expiry(database, actors, monkeypatch):
    owner, base, _, _, decisions = setup_flow()
    reader = client("legal")
    reader.post(base + "/comments", json={"body": "Current stage comment"})
    assert client("stranger").get(base + "/comments").status_code == 404
    r = reader.post(decisions, json={"action": "approve", "comment": "Own comment", "idempotency_key": str(uuid4())})
    assert r.status_code == 200, r.text
    receipt = r.json()["receipt"]
    url = "/api/v1/approvals/" + receipt["id"] + "/receipt"
    assert reader.get(url).json()["snapshot"]["own_comment"] == "Own comment"
    assert reader.get(base).status_code == 404
    assert reader.get(base + "/comments").status_code == 404
    import app.access as access_module

    future = datetime.now(UTC) + timedelta(days=7)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return future

    monkeypatch.setattr(access_module, "datetime", Clock)
    assert "snapshot" not in reader.get(url).json()
    assert owner.get(base + "/workflows").status_code == 200
