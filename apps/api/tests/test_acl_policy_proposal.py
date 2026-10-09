"""Draft-policy matrix. Passing this suite does NOT mean production ACL is fixed."""

from dataclasses import replace

import pytest
from acl_candidate import Context, content_read


@pytest.mark.parametrize("role", ["USER", "REVIEWER", "APPROVER", "LEGAL", "MANAGER", "ADMIN"])
@pytest.mark.parametrize("classification", ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"])
def test_role_alone_never_grants_content(role, classification):
    assert not content_read(Context(role=role, classification=classification, assigned=False))


@pytest.mark.parametrize("resource", ["card", "file", "versions", "comments", "history", "workflow"])
def test_owner_retains_independent_right_after_workflow_closes(resource):
    assert content_read(Context(owner=True, process_status="CANCELLED", trash=True), resource)
    assert not content_read(Context(owner=True, active=False), resource)


@pytest.mark.parametrize(
    "change",
    [
        {"assignment_status": "WAITING"},
        {"assignment_status": "APPROVED"},
        {"assignment_status": "REJECTED"},
        {"assignment_status": "CANCELLED"},
        {"assignment_status": "REVISION_REQUIRED"},
        {"assignment_stage": 1},
        {"process_status": "APPROVED"},
        {"process_status": "REJECTED"},
        {"process_status": "REVISION_REQUIRED"},
        {"process_status": "CANCELLED"},
        {"document_status": "DRAFT"},
        {"trash": True},
        {"active": False},
        {"requested_version": "v1"},
        {"requested_version": "v3"},
        {"classification": "RESTRICTED"},
        {"classification": "UNKNOWN"},
    ],
)
def test_workflow_access_is_revoked_or_scoped(change):
    assert content_read(Context())
    assert not content_read(replace(Context(), **change))


@pytest.mark.parametrize("resource", ["comments", "history", "workflow", "unknown"])
def test_participant_cannot_read_unscoped_streams(resource):
    assert not content_read(Context(), resource)


@pytest.mark.parametrize("classification", ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"])
@pytest.mark.parametrize("status", ["DRAFT", "SUBMITTED", "IN_APPROVAL", "APPROVED", "ARCHIVED"])
def test_manager_department_matrix(classification, status):
    c = Context(role="MANAGER", same_department=True, assigned=False,
                classification=classification, document_status=status)
    assert content_read(c) == (classification in {"PUBLIC", "INTERNAL"} and status == "APPROVED")
    assert not content_read(replace(c, requested_version="v1"))
    assert not content_read(replace(c, same_department=False))


def test_validated_explicit_grant_is_version_scoped_and_never_bypasses_active_or_trash():
    c = Context(role="ADMIN", classification="RESTRICTED", assigned=False,
                validated_grant_version="v2")
    assert content_read(c)
    assert not content_read(replace(c, requested_version="v3"))
    assert not content_read(replace(c, active=False))
    assert not content_read(replace(c, trash=True))
    assert not content_read(c, "history")
