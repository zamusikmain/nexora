"""Executable POLICY PROPOSAL only. Never imported by the application.

Inputs describe trusted server facts, not fields accepted from the browser.
No grants/schema/runtime ACL changes are implemented by this reference model.
"""

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from json import dumps


@dataclass(frozen=True)
class Context:
    active: bool = True
    owner: bool = False
    role: str = "LEGAL"
    same_department: bool = False
    classification: str = "INTERNAL"
    document_status: str = "IN_APPROVAL"
    trash: bool = False
    current_version: str = "v2"
    requested_version: str = "v2"
    process_status: str = "RUNNING"
    assignment_status: str = "PENDING"
    assigned: bool = True
    assignment_stage: int = 0
    active_stage: int = 0
    workflow_version: str = "v2"
    department_review_enabled: bool = False
    draft_shared_version: str | None = None
    draft_share_valid: bool = False
    # Explicit grant must already be validated for actor, document, action,
    # expiry, revocation, authority, and restricted two-person authorization.
    validated_grant_version: str | None = None
    validated_grant_resources: frozenset[str] = frozenset({"card", "file", "versions"})


def content_read(c: Context, resource: str = "file") -> bool:
    """Owner full history; others version-specific, no implicit admin override."""
    if not c.active or c.classification not in {"PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"}:
        return False
    if c.owner:
        return resource in {"card", "file", "versions", "comments", "history", "workflow"}
    if c.trash:
        return False
    if resource not in {"card", "file", "versions", "comments", "history", "workflow"}:
        return False
    # This minimal draft models content grants only. Comment/history/workflow
    # scopes need their own grants and are deliberately denied here.
    if c.validated_grant_version == c.requested_version and resource in c.validated_grant_resources:
        return resource in {"card", "file", "versions"}
    if (
        c.role == "MANAGER"
        and c.same_department
        and c.classification in {"PUBLIC", "INTERNAL"}
        and c.document_status == "APPROVED"
        and c.requested_version == c.current_version
    ):
        return resource in {"card", "file", "versions"}
    if (
        c.role == "MANAGER"
        and c.same_department
        and c.department_review_enabled
        and c.draft_share_valid
        and c.draft_shared_version == c.requested_version == c.current_version
        and c.document_status in {"DRAFT", "REVISION_REQUIRED"}
        and c.classification in {"PUBLIC", "INTERNAL"}
    ):
        return resource in {"card", "file", "versions"}
    participant = (
        c.assigned
        and c.assignment_status == "PENDING"
        and c.assignment_stage == c.active_stage
        and c.process_status == "RUNNING"
        and c.document_status == "IN_APPROVAL"
        and c.requested_version == c.workflow_version
        # Restricted assignments additionally require a vetted grant.
        and c.classification != "RESTRICTED"
    )
    # "card" means frozen workflow snapshot, "versions" a singleton.
    # Global legacy comments/history/full workflow responses are never allowed.
    return participant and resource in {"card", "file", "versions"}


@dataclass(frozen=True)
class RestrictedRequest:
    request_id: str
    requester: str
    recipient: str
    document: str
    version: str
    actions: frozenset[str]
    purpose: str
    reason: str
    requested_at: datetime
    review_deadline: datetime
    duration: timedelta
    revoked: bool = False

    def fingerprint(self) -> str:
        return sha256(dumps({
            "id": self.request_id, "requester": self.requester, "recipient": self.recipient,
            "document": self.document, "version": self.version, "actions": sorted(self.actions),
            "purpose": self.purpose, "reason": self.reason,
            "requested_at": self.requested_at.isoformat(), "deadline": self.review_deadline.isoformat(),
            "duration": self.duration.total_seconds(),
        }, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class Endorsement:
    actor: str
    office: str  # data_custodian or security; trusted server authority, NOT ADMIN
    scope: str
    approved_at: datetime


def restricted_valid(
    request: RestrictedRequest, approvals: tuple[Endorsement, ...], *, now: datetime,
    actor: str, document: str, version: str, action: str,
    active: bool = True, trash: bool = False, authorities_valid: bool = True,
    need_valid: bool = True, purpose: str = "review", denied: bool = False,
) -> bool:
    """Test-only gate; caller supplies CURRENT authority/need facts from server.

No storage, identity provider, approval API, concurrency protection or audit
implementation is claimed. Those are deployment prerequisites in the proposal.
"""
    times = (now, request.requested_at, request.review_deadline, *(a.approved_at for a in approvals))
    if any(t.tzinfo is None or t.utcoffset() != timedelta(0) for t in times):
        return False
    if not active or trash or not authorities_valid or not need_valid or denied or request.revoked:
        return False
    if (
        actor != request.recipient or document != request.document or version != request.version
        or action not in request.actions or purpose != request.purpose
        or not request.reason.strip() or len(request.reason) > 1000
        or request.purpose not in {"review", "audit_snapshot", "incident"}
        or not request.actions or not request.actions <= {"card", "file", "snapshot"}
        or not timedelta(0) < request.duration <= timedelta(hours=8)
        or not request.requested_at < request.review_deadline <= request.requested_at + timedelta(hours=24)
        or len(approvals) != 2
    ):
        return False
    if len({a.actor for a in approvals}) != 2:
        return False
    if {a.office for a in approvals} != {"data_custodian", "security"}:
        return False
    if any(
        a.actor in {request.requester, request.recipient}
        or a.scope != request.fingerprint()
        or not request.requested_at <= a.approved_at < request.review_deadline
        or a.approved_at > now
        for a in approvals
    ):
        return False
    activated_at = max(a.approved_at for a in approvals)
    return activated_at <= now < activated_at + request.duration


@dataclass(frozen=True)
class OwnReview:
    actor: str = "legal"
    assignment_id: str = "assignment-1"
    version: str = "v2"
    outcome: str = "APPROVED"
    acted_at: datetime = datetime(2026, 10, 8, tzinfo=UTC)
    frozen_title: str = "Reviewed title v2"
    own_comment: str = "My review"


def own_review_view(
    c: Context, review: OwnReview, *, actor: str, now: datetime,
    restricted_snapshot_valid: bool = False, receipt_revoked: bool = False,
    snapshot_revoked: bool = False, snapshot_need_valid: bool = True,
) -> dict | None:
    """Receipt survives closure; content-bearing snapshot requires live need.

No full file or live card is ever returned. RESTRICTED uses a separate valid
snapshot grant. Its validity must have been checked by restricted_valid.
"""
    if (
        not c.active or actor != review.actor or receipt_revoked
        or review.outcome not in {"APPROVED", "REJECTED", "REVISION_REQUIRED"}
        or now.tzinfo is None or review.acted_at.tzinfo is None or now < review.acted_at
    ):
        return None
    result: dict = {
        "kind": "receipt", "assignment_id": review.assignment_id,
        "version_id": review.version, "outcome": review.outcome,
        "acted_at": review.acted_at.isoformat(), "can_download": False,
        "href": "/approvals/" + review.assignment_id + "/receipt",
    }
    snapshot = (
        not c.trash and not snapshot_revoked and snapshot_need_valid
        and c.classification in {"PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"}
        and review.version == c.workflow_version
        and (
            restricted_snapshot_valid if c.classification == "RESTRICTED" else
            c.process_status == "RUNNING" and c.document_status == "IN_APPROVAL"
            and now < review.acted_at + timedelta(days=7)
        )
    )
    if snapshot:
        result["snapshot"] = {"version_id": review.version, "title": review.frozen_title,
                              "own_comment": review.own_comment}
    return result


def task_view(c: Context, *, assignment_id: str, title: str, due_at: str | None) -> dict | None:
    """Draft DTO for current tasks. Restricted missing grant retains a safe row."""
    if (
        not c.active or c.trash or not c.assigned or c.assignment_status != "PENDING"
        or c.assignment_stage != c.active_stage or c.process_status != "RUNNING"
        or c.document_status != "IN_APPROVAL"
    ):
        return None
    available = content_read(replace(c, requested_version=c.workflow_version), "card")
    return {
        "kind": "active_task" if available else "access_required",
        "id": assignment_id, "label": title if available else "Restricted task",
        "due_at": due_at, "can_decide": available,
        "href": "/approvals/" + assignment_id + ("/review" if available else "/access"),
    }


def notification_view(c: Context, *, assignment_id: str, title: str) -> dict | None:
    """FUTURE notifications only: generic signal; content rechecked on opening."""
    task = task_view(c, assignment_id=assignment_id, title=title, due_at=None)
    if task is None:
        return None
    return {"label": "Task available", "href": task["href"]}
