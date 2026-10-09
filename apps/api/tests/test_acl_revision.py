"""Revision 2: test-only access, approval lifecycle and UI projection contracts."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from acl_candidate import (
    Context,
    Endorsement,
    OwnReview,
    RestrictedRequest,
    content_read,
    notification_view,
    own_review_view,
    restricted_valid,
    task_view,
)

NOW = datetime(2026, 10, 8, 12, tzinfo=UTC)


def request_and_approvals():
    request = RestrictedRequest(
        "request-1", "owner", "legal", "doc-1", "v2", frozenset({"card", "file", "snapshot"}),
        "review", "Required review of contract v2", NOW - timedelta(minutes=5),
        NOW + timedelta(hours=24) - timedelta(minutes=5), timedelta(hours=4),
    )
    approvals = (
        Endorsement("custodian", "data_custodian", request.fingerprint(), NOW - timedelta(minutes=2)),
        Endorsement("security-officer", "security", request.fingerprint(), NOW),
    )
    return request, approvals


def allowed(request, approvals, **changes):
    args = dict(now=NOW, actor="legal", document="doc-1", version="v2", action="file")
    args.update(changes)
    return restricted_valid(request, approvals, **args)


@pytest.mark.parametrize("classification", ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"])
@pytest.mark.parametrize("status", ["DRAFT", "REVISION_REQUIRED", "SUBMITTED", "IN_APPROVAL", "APPROVED"])
def test_manager_explicit_draft_handoff_matrix(classification, status):
    c = Context(role="MANAGER", same_department=True, assigned=False, classification=classification,
                document_status=status, department_review_enabled=True,
                draft_share_valid=True, draft_shared_version="v2")
    assert content_read(c) == (classification in {"PUBLIC", "INTERNAL"}
                              and status in {"DRAFT", "REVISION_REQUIRED", "APPROVED"})
    assert not content_read(replace(c, requested_version="v3"))
    assert not content_read(replace(c, role="ADMIN"))
    assert not content_read(replace(c, same_department=False))
    assert not content_read(replace(c, trash=True))
    assert not content_read(c, "history")


@pytest.mark.parametrize("changes", [
    {"department_review_enabled": False}, {"draft_share_valid": False},
    {"draft_shared_version": "v1"}, {"current_version": "v3"}, {"active": False},
])
def test_draft_handoff_is_opt_in_revocable_and_never_follows_version(changes):
    c = Context(role="MANAGER", same_department=True, assigned=False, document_status="DRAFT",
                department_review_enabled=True, draft_share_valid=True, draft_shared_version="v2")
    assert content_read(c)
    assert not content_read(replace(c, **changes))


def test_restricted_activation_requires_both_offices_and_no_self_approval():
    request, approvals = request_and_approvals()
    assert allowed(request, approvals)
    assert not allowed(request, ())
    assert not allowed(request, approvals[:1])
    for actor in ("owner", "legal", approvals[0].actor):
        assert not allowed(request, (approvals[0], replace(approvals[1], actor=actor)))
    for office in ("ADMIN", "MANAGER", "data_custodian"):
        assert not allowed(request, (approvals[0], replace(approvals[1], office=office)))


@pytest.mark.parametrize("changes", [
    {"actor": "stranger"}, {"document": "doc-2"}, {"version": "v3"}, {"action": "history"},
    {"active": False}, {"trash": True}, {"authorities_valid": False}, {"need_valid": False},
    {"denied": True}, {"purpose": "incident"},
])
def test_restricted_scope_and_current_revocation_facts(changes):
    request, approvals = request_and_approvals()
    assert allowed(request, approvals)
    assert not allowed(request, approvals, **changes)


@pytest.mark.parametrize("changes", [
    {"recipient": "stranger"}, {"version": "v3"}, {"actions": frozenset({"history"})},
    {"duration": timedelta(hours=9)}, {"duration": timedelta(0)},
    {"reason": ""}, {"purpose": "all_access"}, {"document": "doc-2"}, {"revoked": True},
])
def test_request_modification_cannot_reuse_endorsements(changes):
    request, approvals = request_and_approvals()
    assert not allowed(replace(request, **changes), approvals)


def test_expiry_boundaries_renewal_and_invalid_timestamps():
    request, approvals = request_and_approvals()
    assert allowed(request, approvals, now=NOW + timedelta(hours=4) - timedelta(microseconds=1))
    assert not allowed(request, approvals, now=NOW + timedelta(hours=4))
    assert not allowed(request, approvals, now=NOW - timedelta(seconds=1))
    renewed = replace(request, request_id="request-2", requested_at=NOW,
                      review_deadline=NOW + timedelta(hours=24))
    assert not allowed(renewed, approvals)
    assert not allowed(request, (approvals[0], replace(approvals[1], approved_at=request.review_deadline)))
    assert not allowed(request, approvals, now=NOW.replace(tzinfo=None))


@pytest.mark.parametrize("status", ["RUNNING", "APPROVED", "REJECTED", "REVISION_REQUIRED", "CANCELLED"])
def test_receipt_is_own_and_does_not_reveal_live_document(status):
    c = Context(process_status=status, requested_version="v3")
    review = OwnReview(acted_at=NOW)
    result = own_review_view(c, review, actor="legal", now=NOW)
    assert result is not None and result["version_id"] == "v2"
    assert result["can_download"] is False and result["href"].endswith("/receipt")
    assert "title" not in result and "number" not in result and "document_id" not in result
    assert ("snapshot" in result) == (status == "RUNNING")
    assert not content_read(replace(c, assignment_status="APPROVED"))
    assert own_review_view(c, review, actor="stranger", now=NOW) is None
    assert own_review_view(replace(c, active=False), review, actor="legal", now=NOW) is None


def test_snapshot_is_frozen_expires_and_has_no_file_or_other_comments():
    c = Context(assignment_status="APPROVED")
    review = OwnReview(acted_at=NOW, frozen_title="Old title v2")
    view = own_review_view(c, review, actor="legal", now=NOW + timedelta(days=6))
    assert view["snapshot"] == {"version_id": "v2", "title": "Old title v2", "own_comment": "My review"}
    assert "snapshot" not in own_review_view(c, review, actor="legal", now=NOW + timedelta(days=7))
    assert "snapshot" not in own_review_view(replace(c, trash=True), review, actor="legal", now=NOW)
    assert "snapshot" not in own_review_view(replace(c, workflow_version="v3"), review, actor="legal", now=NOW)
    assert own_review_view(c, review, actor="legal", now=NOW, receipt_revoked=True) is None
    revoked = own_review_view(c, review, actor="legal", now=NOW, snapshot_revoked=True)
    assert revoked["kind"] == "receipt" and "snapshot" not in revoked
    no_need = own_review_view(c, review, actor="legal", now=NOW, snapshot_need_valid=False)
    assert no_need["kind"] == "receipt" and "snapshot" not in no_need


def test_restricted_snapshot_needs_separate_current_grant_even_after_own_decision():
    c = Context(classification="RESTRICTED", assignment_status="APPROVED", process_status="APPROVED")
    review = OwnReview(acted_at=NOW)
    request, approvals = request_and_approvals()
    assert "snapshot" not in own_review_view(c, review, actor="legal", now=NOW)
    # Closed workflow grant has no current business need. A NEW audit_snapshot
    # request with two new approvals is the only way to read retained content.
    assert not allowed(request, approvals, action="snapshot", need_valid=False)
    request = replace(request, purpose="audit_snapshot", request_id="audit-1")
    approvals = tuple(replace(a, scope=request.fingerprint()) for a in approvals)
    valid = allowed(request, approvals, action="snapshot", purpose="audit_snapshot")
    assert valid
    assert "snapshot" in own_review_view(c, review, actor="legal", now=NOW, restricted_snapshot_valid=valid)
    expired = allowed(request, approvals, action="snapshot", purpose="audit_snapshot", now=NOW + timedelta(hours=4))
    assert not expired
    assert "snapshot" not in own_review_view(c, review, actor="legal", now=NOW, restricted_snapshot_valid=expired)


@pytest.mark.parametrize("changes", [
    {"assignment_status": "WAITING"}, {"assignment_stage": 1}, {"process_status": "CANCELLED"},
    {"process_status": "APPROVED"}, {"trash": True}, {"active": False},
])
def test_future_closed_and_revoked_tasks_do_not_leak_notifications(changes):
    c = replace(Context(), **changes)
    assert task_view(c, assignment_id="a1", title="Secret title", due_at=None) is None
    assert notification_view(c, assignment_id="a1", title="Secret title") is None


def test_restricted_pending_task_survives_missing_grant_without_leaking_title():
    c = Context(classification="RESTRICTED")
    task = task_view(c, assignment_id="a1", title="Secret title", due_at="2026-10-09")
    assert task["kind"] == "access_required" and task["can_decide"] is False
    assert task["label"] != "Secret title" and task["href"].endswith("/access")
    c = replace(c, validated_grant_version="v2")
    assert task_view(c, assignment_id="a1", title="Secret title", due_at=None)["kind"] == "active_task"
    notice = notification_view(c, assignment_id="a1", title="Secret title")
    assert notice == {"label": "Task available", "href": "/approvals/a1/review"}


def test_snapshot_only_grant_never_enables_files_or_task_for_another_version():
    c = Context(classification="RESTRICTED", validated_grant_version="v2",
                validated_grant_resources=frozenset({"snapshot"}))
    assert not content_read(c, "file") and not content_read(c, "card")
    assert task_view(c, assignment_id="a1", title="Secret", due_at=None)["kind"] == "access_required"
    c = Context(classification="RESTRICTED", requested_version="v3", validated_grant_version="v3")
    assert task_view(c, assignment_id="a1", title="Secret", due_at=None)["kind"] == "access_required"
