"""Real API regressions for the approved ACL restrictions.

All fixtures use the disposable nexora_test DB; never a working database.
All previous 23 expected failures are ordinary regression tests now.
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_api import client, create
from test_api import database as database  # noqa: F401 -- pytest fixture, guarded test DB

from app.main import app
from app.models import User


def uploaded(owner, base, name="file.txt"):
    response = owner.post(base + "/versions", files={"file": (name, b"Private test content", "text/plain")})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def setup_flow(parallel=False):
    owner, admin = client(), client("admin")
    doc = create(owner)
    base = "/api/v1/documents/" + doc["id"]
    old = uploaded(owner, base, "old.txt")
    current = uploaded(owner, base, "current.txt")
    response = admin.post("/api/v1/workflow-templates", json={
        "code": "ACL_" + uuid4().hex[:12].upper(), "name_ru": "ACL", "name_en": "ACL",
        "stages": [
            {"name_ru": "Юристы", "name_en": "Legal", "selector": "user",
             "targets": ["legal", "manager"] if parallel else ["legal"]},
            {"name_ru": "Следующий", "name_en": "Next", "selector": "user", "targets": ["stranger"]},
        ],
    })
    assert response.status_code == 201, response.text
    response = owner.post(base + "/workflows", json={
        "template_id": response.json()["id"], "expected_revision": owner.get(base).json()["revision"],
        "idempotency_key": str(uuid4()),
    })
    assert response.status_code == 201, response.text
    return owner, base, old, current, "/api/v1/workflows/" + response.json()["id"] + "/decisions"


@pytest.mark.parametrize("suffix", ["", "/versions", "/comments", "/activity", "/workflows"])
def test_unassigned_foreign_reader_is_denied(database, suffix):
    owner = client()
    base = "/api/v1/documents/" + create(owner)["id"]
    assert client("legal").get(base + suffix).status_code == 404
    assert TestClient(app).get(base + suffix).status_code == 401


def test_foreign_download_diff_and_version_binding_denied(database):
    owner = client()
    base = "/api/v1/documents/" + create(owner)["id"]
    v1, v2 = uploaded(owner, base), uploaded(owner, base)
    download = base + "/versions/" + v1 + "/download"
    assert client("legal").get(download).status_code == 404
    assert TestClient(app).get(download).status_code == 401
    assert client("legal").get(base + "/versions/" + v1 + "/diff/" + v2).status_code == 404
    other = "/api/v1/documents/" + create(owner)["id"]
    assert owner.get(other + "/versions/" + v1 + "/download").status_code == 404
    assert owner.get(other + "/versions/" + v1 + "/diff/" + v2).status_code == 404


def test_unreadable_document_is_absent_from_search_and_dashboard(database):
    owner, reader = client(), client("legal")
    title = "ACL search " + uuid4().hex
    response = owner.post("/api/v1/documents", json={"title": title, "type_id": "type"})
    assert response.status_code == 201, response.text
    doc_id = response.json()["id"]
    listing = reader.get("/api/v1/documents", params={"q": title})
    assert listing.status_code == 200
    assert listing.json()["total"] == 0 and listing.json()["items"] == []
    assert doc_id not in {d["id"] for d in reader.get("/api/v1/dashboard").json()["recent"]}


def test_blocking_active_participant_revokes_file_access(database):
    _, base, _, current, _ = setup_flow()
    reader = client("legal")
    url = base + "/versions/" + current + "/download"
    assert reader.get(url).status_code == 200
    try:
        with database.begin() as db:
            db.get(User, "legal").status = "BLOCKED"
        assert reader.get(url).status_code == 401
        assert reader.get(base).status_code == 401
    finally:
        with database.begin() as db:
            db.get(User, "legal").status = "ACTIVE"


@pytest.mark.parametrize("resource", ["card", "file", "versions", "comments", "activity", "workflows", "list"])
def test_future_stage_cannot_read(database, resource):
    _, base, _, current, _ = setup_flow()
    reader = client("stranger")
    if resource == "list":
        assert base.rsplit("/", 1)[1] not in {
            d["id"] for d in reader.get("/api/v1/documents").json()["items"]
        }
    else:
        suffix = {"card": "", "file": "/versions/" + current + "/download"}.get(resource, "/" + resource)
        assert reader.get(base + suffix).status_code == 404


def test_active_participant_cannot_download_previous_version(database):
    _, base, old, _, _ = setup_flow()
    assert client("legal").get(base + "/versions/" + old + "/download").status_code == 404


def test_active_participant_version_listing_is_scoped(database):
    _, base, _, current, _ = setup_flow()
    assert [v["id"] for v in client("legal").get(base + "/versions").json()] == [current]


def test_completed_receipt_does_not_disclose_document_metadata(database):
    _, base, _, _, decisions = setup_flow()
    reader = client("legal")
    response = reader.post(decisions, json={"action": "approve", "idempotency_key": str(uuid4())})
    assert response.status_code == 200, response.text
    items = reader.get("/api/v1/approvals", params={"view": "completed"}).json()["items"]
    item = next(i for i in items if i["document_id"] == base.rsplit("/", 1)[1])
    assert "title" not in item and "number" not in item


def test_manager_cannot_read_unassigned_department_draft(database):
    base = "/api/v1/documents/" + create(client())["id"]
    assert client("manager").get(base).status_code == 404


@pytest.mark.parametrize("action", ["approve", "reject", "revision", "cancel", "complete"])
def test_finished_assignment_cannot_download(database, action):
    owner, base, _, current, decisions = setup_flow()
    actor = owner if action == "cancel" else client("legal")
    response = actor.post(decisions, json={
        "action": "approve" if action == "complete" else action,
        "comment": "Synthetic decision", "idempotency_key": str(uuid4()),
    })
    assert response.status_code == 200, response.text
    if action == "complete":
        response = client("stranger").post(decisions, json={"action": "approve", "idempotency_key": str(uuid4())})
        assert response.status_code == 200 and response.json()["status"] == "APPROVED"
    assert client("legal").get(base + "/versions/" + current + "/download").status_code == 404


def test_parallel_participant_access_ends_after_own_decision(database):
    owner, base, _, current, decisions = setup_flow(parallel=True)
    reader = client("legal")
    response = reader.post(decisions, json={"action": "approve", "idempotency_key": str(uuid4())})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "RUNNING" and response.json()["stage"] == 0
    assert any(a["user_id"] == "manager" and a["status"] == "PENDING" for a in owner.get(base + "/workflows").json()[0]["approvals"])
    assert reader.get(base + "/versions/" + current + "/download").status_code == 404


def test_trashed_document_cannot_be_downloaded_by_former_participant(database):
    owner, base, _, current, decisions = setup_flow()
    response = owner.post(decisions, json={
        "action": "cancel", "comment": "Cancelled", "idempotency_key": str(uuid4()),
    })
    assert response.status_code == 200, response.text
    response = owner.post(base + "/trash", json={"expected_revision": owner.get(base).json()["revision"]})
    assert response.status_code == 200, response.text
    assert client("legal").get(base + "/versions/" + current + "/download").status_code == 404


def test_revision_participant_cannot_download_new_version(database):
    owner, base, _, _, decisions = setup_flow()
    response = client("legal").post(decisions, json={
        "action": "revision", "comment": "Revise", "idempotency_key": str(uuid4()),
    })
    assert response.status_code == 200, response.text
    new_version = uploaded(owner, base, "revised.txt")
    assert client("legal").get(base + "/versions/" + new_version + "/download").status_code == 404


@pytest.mark.parametrize("role", ["manager", "admin"])
@pytest.mark.parametrize("classification", ["CONFIDENTIAL", "RESTRICTED"])
def test_confidential_content_requires_specific_authority(database, role, classification):
    owner = client()
    response = owner.post("/api/v1/documents", json={
        "title": "Confidential synthetic document", "type_id": "type", "confidentiality": classification,
    })
    assert response.status_code == 201, response.text
    base = "/api/v1/documents/" + response.json()["id"]
    version = uploaded(owner, base)
    assert client(role).get(base + "/versions/" + version + "/download").status_code == 404


def test_list_prefilter_admits_exactly_the_full_policy(database):
    """The indexed candidate pre-filter must never hide or reveal a document versus the policy."""
    from sqlalchemy import select

    from app.models import Document
    from app.policy import visibility

    owner, _, _, _, decisions = setup_flow(parallel=True)
    assert client("legal").post(decisions, json={"action": "approve", "idempotency_key": str(uuid4())}).status_code == 200
    with database() as db:
        users = list(db.scalars(select(User)))
        assert len(users) >= 5
        for user in users:
            fast = set(db.scalars(select(Document.id).where(visibility(user))))
            full = set(db.scalars(select(Document.id).where(visibility(user, prefilter=False))))
            assert fast == full, user.id