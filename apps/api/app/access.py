"""Version-bound grants. Technical administrators cannot assign business authority."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from pydantic import Field
from sqlalchemy import func, or_, select

from app.audit import audit
from app.auth import Actor, Db
from app.idempotency import begin, finish
from app.models import (
    AccessGrant,
    AclAuthority,
    Approval,
    DepartmentReviewPolicy,
    Document,
    DocumentVersion,
    GrantEndorsement,
    ReceiptRevocation,
    ReviewReceipt,
    User,
    WorkflowInstance,
)
from app.policy import authority, grant_conditions
from app.schemas import Input

router = APIRouter(tags=["access"])
ACTION = Literal["card", "file", "snapshot", "comments", "history", "compare"]


def read_actions() -> list[ACTION]:
    return ["card", "file"]


def review_actions() -> list[ACTION]:
    return ["card", "file", "snapshot"]


class GrantInput(Input):
    recipient_id: str = Field(min_length=1, max_length=36)
    version_id: str = Field(min_length=1, max_length=36)
    actions: list[ACTION] = Field(default_factory=read_actions, min_length=1, max_length=6)
    purpose: Literal["personal", "review", "audit_snapshot", "incident"] = "personal"
    approval_id: str | None = Field(default=None, max_length=36)
    reason: str = Field(min_length=3, max_length=1000)
    hours: int = Field(default=4, ge=1, le=168)


class OwnAccessInput(Input):
    purpose: Literal["review", "audit_snapshot"] = "review"
    actions: list[ACTION] = Field(default_factory=review_actions, min_length=1, max_length=3)
    reason: str = Field(min_length=3, max_length=1000)
    hours: int = Field(default=4, ge=1, le=8)


class EndorseInput(Input):
    office: Literal["CUSTODIAN", "SECURITY"]
    scope_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class RevokeInput(Input):
    reason: str = Field(min_length=3, max_length=1000)
    hide_receipt: bool = False


class ReviewPolicyInput(Input):
    enabled: bool


class DraftShareInput(Input):
    version_id: str = Field(min_length=1, max_length=36)
    hours: int = Field(default=168, ge=1, le=168)
    reason: str = Field(min_length=3, max_length=1000)


def scope_hash(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, allow_nan=False).encode()).hexdigest()


def grant_data(g: AccessGrant) -> dict:
    now = datetime.now(UTC)
    status = g.status
    if (status == "PENDING" and now >= g.review_deadline) or (
        status == "ACTIVE" and g.expires_at and now >= g.expires_at
    ):
        status = "EXPIRED"
    return {"id": g.id, "document_id": g.document_id, "version_id": g.version_id,
            "department_id": g.department_id,
            "recipient_id": g.recipient_id, "requested_by": g.requested_by,
            "classification": g.classification, "purpose": g.purpose, "approval_id": g.approval_id,
            "actions": [a for a in ("card", "file", "snapshot", "comments", "history", "compare")
                        if getattr(g, "can_" + a)],
            "reason": g.reason, "hours": g.duration_hours, "scope_hash": g.scope_hash,
            "status": status, "expires_at": g.expires_at, "review_deadline": g.review_deadline}


def locked_doc(db: Db, doc_id: str) -> Document:
    doc = db.scalar(select(Document).where(Document.id == doc_id).with_for_update().execution_options(populate_existing=True))
    if doc is None:
        raise HTTPException(404, "not_found")
    return doc


def may_manage(db: Db, user: Actor, doc: Document) -> bool:
    return doc.owner_id == user.id or authority(db, user, doc.department_id, "CUSTODIAN") is not None


def prepare_grant(db: Db, user: Actor, doc: Document, body: GrantInput, purpose: str | None = None) -> AccessGrant:
    from app.documents import document_data

    if doc.deleted_at:
        raise HTTPException(409, "document_in_trash")
    recipient = db.get(User, body.recipient_id)
    version = db.scalar(select(DocumentVersion).where(
        DocumentVersion.id == body.version_id, DocumentVersion.document_id == doc.id,
    ))
    if recipient is None or recipient.status != "ACTIVE" or version is None:
        raise HTTPException(422, "invalid_grant_target")
    restricted = doc.confidentiality == "RESTRICTED"
    if restricted and body.hours > 8:
        raise HTTPException(422, "invalid_grant_duration")
    if len(body.actions) != len(set(body.actions)):
        raise HTTPException(422, "invalid_grant_actions")
    actual_purpose = purpose or body.purpose
    approval, instance = None, None
    if actual_purpose in {"review", "audit_snapshot"}:
        approval = db.get(Approval, body.approval_id, populate_existing=True) if body.approval_id else None
        instance = db.get(WorkflowInstance, approval.instance_id, populate_existing=True) if approval else None
        if not approval or not instance or approval.user_id != recipient.id or instance.document_id != doc.id \
                or instance.document_version_id != version.id:
            raise HTTPException(422, "invalid_grant_target")
        if actual_purpose == "review" and (
            instance.status != "RUNNING" or approval.status != "PENDING" or approval.stage != instance.stage
        ):
            raise HTTPException(409, "approval_not_active")
        if actual_purpose == "audit_snapshot" and (
            approval.acted_at is None or set(body.actions) != {"snapshot"}
        ):
            raise HTTPException(422, "invalid_grant_actions")
        if actual_purpose == "audit_snapshot":
            saved = db.get(ReviewReceipt, approval.id)
            if saved is None or saved.snapshot is None:
                raise HTTPException(409, "snapshot_unavailable")
    elif body.approval_id:
        raise HTTPException(422, "invalid_grant_target")
    if actual_purpose == "personal" and doc.status == "IN_APPROVAL":
        raise HTTPException(422, "review_grant_required")
    if actual_purpose == "draft" and (
        doc.confidentiality not in {"PUBLIC", "INTERNAL"} or doc.status not in {"DRAFT", "REVISION_REQUIRED"}
        or recipient.role != "MANAGER" or recipient.department_id != doc.department_id
        or version.id != doc.current_version_id
    ):
        raise HTTPException(422, "invalid_grant_target")
    card = jsonable_encoder(document_data(doc)) if version.id == doc.current_version_id else version.metadata_snapshot
    if actual_purpose == "review" and instance:
        card = instance.metadata_snapshot.get("card")
    if "card" in body.actions and card is None:
        raise HTTPException(409, "snapshot_unavailable")
    now = datetime.now(UTC)
    data = {"doc": doc.id, "version": version.id, "recipient": recipient.id,
            "requester": user.id, "actions": sorted(body.actions), "purpose": actual_purpose,
            "approval": body.approval_id, "hours": body.hours, "reason": body.reason,
            "classification": doc.confidentiality, "department": doc.department_id,
            "requested_at": now.isoformat()}
    grant = AccessGrant(
        document_id=doc.id, version_id=version.id, recipient_id=recipient.id, requested_by=user.id,
        recipient_role=recipient.role, recipient_department_id=recipient.department_id,
        department_id=doc.department_id, classification=doc.confidentiality, purpose=actual_purpose,
        instance_id=instance.id if instance else None, approval_id=body.approval_id,
        **{"can_" + action: action in body.actions for action in ("card", "file", "snapshot", "comments", "history", "compare")},
        reason=body.reason, duration_hours=body.hours, scope_hash=scope_hash(data),
        requested_at=now, review_deadline=now + timedelta(hours=24), snapshot=card,
        status="ACTIVE" if not restricted and doc.owner_id == user.id else "PENDING",
        activated_at=now if not restricted and doc.owner_id == user.id else None,
        expires_at=now + timedelta(hours=body.hours) if not restricted and doc.owner_id == user.id else None,
    )
    db.add(grant)
    db.flush()
    return grant


@router.post("/documents/{doc_id}/access-requests", status_code=201)
def create_grant(doc_id: str, body: GrantInput, request: Request, db: Db, user: Actor) -> dict:
    replay = begin(db, user, request, body.model_dump(mode="json"))
    doc = locked_doc(db, doc_id)
    if not may_manage(db, user, doc):
        raise HTTPException(404, "not_found")
    if replay is not None:
        return replay
    grant = prepare_grant(db, user, doc, body)
    audit(db, request, user.id, "ACCESS_REQUESTED", "access_grant", grant.id)
    if grant.status == "ACTIVE":
        audit(db, request, user.id, "ACCESS_ACTIVATED", "access_grant", grant.id)
    return finish(db, grant_data(grant))


@router.post("/approvals/{approval_id}/access-requests", status_code=201)
def request_own_access(approval_id: str, body: OwnAccessInput, request: Request, db: Db, user: Actor) -> dict:
    replay = begin(db, user, request, body.model_dump(mode="json"))
    approval = db.get(Approval, approval_id)
    if approval is None or approval.user_id != user.id:
        raise HTTPException(404, "not_found")
    instance = db.get(WorkflowInstance, approval.instance_id)
    assert instance is not None
    doc = locked_doc(db, instance.document_id)
    if doc.confidentiality != "RESTRICTED" or not set(body.actions) <= {"card", "file", "snapshot"}:
        raise HTTPException(422, "invalid_grant_actions")
    if replay is not None:
        return replay
    grant = prepare_grant(db, user, doc, GrantInput(
        recipient_id=user.id, version_id=instance.document_version_id, approval_id=approval.id,
        purpose=body.purpose, actions=body.actions, reason=body.reason, hours=body.hours,
    ))
    audit(db, request, user.id, "ACCESS_REQUESTED", "access_grant", grant.id)
    return finish(db, grant_data(grant))


def visible_grant(db: Db, user: Actor, grant: AccessGrant, doc: Document) -> bool:
    return user.id in {grant.requested_by, grant.recipient_id, doc.owner_id} or any(
        authority(db, user, doc.department_id, office) is not None for office in ("CUSTODIAN", "SECURITY")
    )


@router.get("/access/grants")
def grants(request: Request, db: Db, user: Actor, page: int = Query(1, ge=1)) -> dict:
    offices = select(AclAuthority.department_id).where(
        AclAuthority.user_id == user.id, AclAuthority.active.is_(True), AclAuthority.expires_at > func.now(),
    )
    query = select(AccessGrant).join(Document, Document.id == AccessGrant.document_id).where(or_(
        AccessGrant.recipient_id == user.id, AccessGrant.requested_by == user.id,
        Document.owner_id == user.id, Document.department_id.in_(offices),
    ))
    now = datetime.now(UTC)
    expired = query.where(or_(
        (AccessGrant.status == "ACTIVE") & (AccessGrant.expires_at <= now),
        (AccessGrant.status == "PENDING") & (AccessGrant.review_deadline <= now),
    )).with_for_update(of=AccessGrant).limit(100)
    for grant in db.scalars(expired):
        grant.status = "EXPIRED"
        audit(db, request, user.id, "ACCESS_EXPIRED", "access_grant", grant.id)
    db.commit()
    return {"total": db.scalar(select(func.count()).select_from(query.subquery())),
            "items": [{**grant_data(g), "endorsed_offices": list(db.scalars(
                select(GrantEndorsement.office).where(GrantEndorsement.grant_id == g.id)
            )), "can_endorse": user.id not in {g.requested_by, g.recipient_id}} for g in db.scalars(
                query.order_by(AccessGrant.requested_at.desc(), AccessGrant.id).offset((page - 1) * 25).limit(25))]}


@router.post("/access/grants/{grant_id}/endorse")
def endorse(grant_id: str, body: EndorseInput, request: Request, db: Db, user: Actor) -> dict:
    replay = begin(db, user, request, body.model_dump(mode="json"))
    initial = db.get(AccessGrant, grant_id)
    if initial is None:
        raise HTTPException(404, "not_found")
    doc = locked_doc(db, initial.document_id)
    grant = db.scalar(select(AccessGrant).where(AccessGrant.id == grant_id).with_for_update().execution_options(populate_existing=True))
    assert grant is not None
    office = authority(db, user, doc.department_id, body.office)
    if office is None:
        raise HTTPException(404, "not_found")
    if user.id in {grant.requested_by, grant.recipient_id}:
        raise HTTPException(403, "self_approval_forbidden")
    if replay is not None:
        return replay
    if body.scope_hash != grant.scope_hash:
        raise HTTPException(409, "grant_scope_changed")
    now = datetime.now(UTC)
    if grant.status != "PENDING" or now >= grant.review_deadline:
        raise HTTPException(409, "grant_not_pending")
    if grant.classification != doc.confidentiality or grant.department_id != doc.department_id or doc.deleted_at:
        raise HTTPException(409, "grant_scope_changed")
    recipient = db.get(User, grant.recipient_id)
    requester = db.get(User, grant.requested_by)
    if not recipient or not requester or recipient.status != "ACTIVE" or requester.status != "ACTIVE" \
            or recipient.role != grant.recipient_role or recipient.department_id != grant.recipient_department_id:
        raise HTTPException(409, "grant_scope_changed")
    votes = list(db.scalars(select(GrantEndorsement).where(GrantEndorsement.grant_id == grant.id)))
    if any(v.office == body.office or v.actor_id == user.id for v in votes):
        raise HTTPException(409, "duplicate_endorsement")
    if grant.classification != "RESTRICTED" and body.office != "CUSTODIAN":
        raise HTTPException(403, "forbidden")
    if grant.purpose == "review":
        instance = db.get(WorkflowInstance, grant.instance_id)
        approval = db.get(Approval, grant.approval_id)
        if not instance or not approval or instance.status != "RUNNING" or approval.status != "PENDING" \
                or approval.stage != instance.stage:
            raise HTTPException(409, "approval_not_active")
    db.add(GrantEndorsement(grant_id=grant.id, actor_id=user.id, authority_id=office.id,
                            office=body.office, scope_hash=grant.scope_hash, approved_at=now))
    audit(db, request, user.id, "ACCESS_ENDORSED", "access_grant", grant.id)
    if grant.classification != "RESTRICTED" or len(votes) == 1:
        for vote in votes:
            voter = db.get(User, vote.actor_id)
            existing_office = authority(db, voter, doc.department_id, vote.office) if voter else None
            if existing_office is None or existing_office.id != vote.authority_id:
                raise HTTPException(409, "grant_scope_changed")
        grant.status, grant.activated_at = "ACTIVE", now
        grant.expires_at = now + timedelta(hours=grant.duration_hours)
        audit(db, request, user.id, "ACCESS_ACTIVATED", "access_grant", grant.id)
    return finish(db, grant_data(grant))


@router.post("/access/grants/{grant_id}/revoke")
def revoke(grant_id: str, body: RevokeInput, request: Request, db: Db, user: Actor) -> dict:
    initial = db.get(AccessGrant, grant_id)
    if initial is None:
        raise HTTPException(404, "not_found")
    doc = locked_doc(db, initial.document_id)
    grant = db.scalar(select(AccessGrant).where(AccessGrant.id == grant_id).with_for_update().execution_options(populate_existing=True))
    assert grant is not None
    if not visible_grant(db, user, grant, doc):
        raise HTTPException(404, "not_found")
    if grant.status not in {"REVOKED", "DENIED", "EXPIRED"}:
        grant.status = "DENIED" if grant.status == "PENDING" else "REVOKED"
        grant.revoked_at = datetime.now(UTC)
        audit(db, request, user.id, "ACCESS_REVOKED", "access_grant", grant.id, {"reason": body.reason})
        db.commit()
    return grant_data(grant)


@router.put("/departments/{department_id}/review-policy")
def review_policy(department_id: str, body: ReviewPolicyInput, request: Request, db: Db, user: Actor) -> dict:
    if not authority(db, user, department_id, "CUSTODIAN"):
        raise HTTPException(404, "not_found")
    row = db.get(DepartmentReviewPolicy, department_id)
    if row is None:
        row = DepartmentReviewPolicy(department_id=department_id)
        db.add(row)
    row.enabled, row.updated_by, row.updated_at = body.enabled, user.id, datetime.now(UTC)
    audit(db, request, user.id, "DEPARTMENT_REVIEW_UPDATED", "department", department_id)
    db.commit()
    return {"enabled": row.enabled}


@router.post("/documents/{doc_id}/department-review", status_code=201)
def share_draft(doc_id: str, body: DraftShareInput, request: Request, db: Db, user: Actor) -> dict:
    replay = begin(db, user, request, body.model_dump(mode="json"))
    doc = locked_doc(db, doc_id)
    policy = db.get(DepartmentReviewPolicy, doc.department_id) if doc.department_id else None
    if doc.owner_id != user.id:
        raise HTTPException(404, "not_found")
    if replay is not None:
        return replay
    if not policy or not policy.enabled:
        raise HTTPException(409, "department_review_disabled")
    if doc.confidentiality not in {"PUBLIC", "INTERNAL"} or doc.status not in {"DRAFT", "REVISION_REQUIRED"} \
            or body.version_id != doc.current_version_id:
        raise HTTPException(422, "invalid_grant_target")
    audience = list(db.scalars(select(User).where(User.role == "MANAGER", User.status == "ACTIVE",
                                                User.department_id == doc.department_id, User.id != user.id)))
    created = []
    for recipient in audience:
        grant = prepare_grant(db, user, doc, GrantInput(
            recipient_id=recipient.id, version_id=body.version_id, hours=body.hours,
            actions=["card", "file"], reason=body.reason,
        ), purpose="draft")
        created.append(grant_data(grant))
        audit(db, request, user.id, "ACCESS_ACTIVATED", "access_grant", grant.id)
    return finish(db, {"items": created})


@router.post("/approvals/{approval_id}/receipt/revoke")
def revoke_receipt(approval_id: str, body: RevokeInput, request: Request, db: Db, user: Actor) -> dict:
    approval = db.get(Approval, approval_id)
    instance = db.get(WorkflowInstance, approval.instance_id) if approval else None
    if not approval or not instance:
        raise HTTPException(404, "not_found")
    doc = locked_doc(db, instance.document_id)
    if not any(authority(db, user, doc.department_id, office) for office in ("CUSTODIAN", "SECURITY")):
        raise HTTPException(404, "not_found")
    if db.get(ReceiptRevocation, approval_id):
        raise HTTPException(409, "receipt_already_revoked")
    db.add(ReceiptRevocation(approval_id=approval_id, actor_id=user.id, reason=body.reason,
                            hide_receipt=body.hide_receipt, revoked_at=datetime.now(UTC)))
    audit(db, request, user.id, "RECEIPT_REVOKED", "approval", approval_id)
    db.commit()
    return {"status": "REVOKED"}


def receipt_data(db: Db, user: Actor, approval: Approval, instance: WorkflowInstance, doc: Document) -> dict:
    if approval.user_id != user.id:
        raise HTTPException(404, "not_found")
    revocation = db.get(ReceiptRevocation, approval.id)
    if revocation and revocation.hide_receipt:
        raise HTTPException(404, "not_found")
    if not approval.acted_at or approval.status == "CANCELLED":
        if approval.status != "CANCELLED":
            raise HTTPException(404, "not_found")
        return {"kind": "cancelled", "id": approval.id, "status": "CANCELLED", "can_download": False}
    receipt = db.get(ReviewReceipt, approval.id)
    acted_at = receipt.acted_at if receipt else approval.acted_at
    assert acted_at is not None
    result = {"kind": "receipt", "id": approval.id, "assignment_id": approval.id,
              "document_id": doc.id,  # opaque compatibility identity, never a content link
              "version_id": instance.document_version_id, "outcome": receipt.outcome if receipt else approval.status,
              "status": receipt.outcome if receipt else approval.status, "acted_at": acted_at,
              "can_download": False, "href": f"/approvals/{approval.id}/receipt"}
    ordinary_snapshot = (
        doc.confidentiality != "RESTRICTED" and instance.status == "RUNNING" and doc.status == "IN_APPROVAL"
        and datetime.now(UTC) < acted_at + timedelta(days=7)
    )
    explicit_snapshot = db.scalar(select(Document.id).where(
        Document.id == doc.id, select(AccessGrant.id).where(
            grant_conditions(user, instance.document_version_id, "snapshot"),
            AccessGrant.approval_id == approval.id,
        ).correlate(Document).exists(),
    ))
    if receipt and receipt.snapshot and not doc.deleted_at and not revocation and (ordinary_snapshot or explicit_snapshot):
        result["snapshot"] = receipt.snapshot
    result["snapshot_available"] = "snapshot" in result
    result["can_request_snapshot"] = bool(doc.confidentiality == "RESTRICTED" and receipt and receipt.snapshot
                                           and not doc.deleted_at and not revocation)
    return result


@router.get("/approvals/{approval_id}/receipt")
def receipt(approval_id: str, db: Db, user: Actor) -> dict:
    approval = db.get(Approval, approval_id)
    if not approval or approval.user_id != user.id:
        raise HTTPException(404, "not_found")
    instance = db.get(WorkflowInstance, approval.instance_id)
    assert instance is not None
    doc = db.get(Document, instance.document_id)
    assert doc is not None
    return receipt_data(db, user, approval, instance, doc)


@router.get("/access/people")
def people(db: Db, user: Actor) -> list[dict]:
    # Authenticated organization directory, no document associations/passwords.
    return [{"id": u.id, "display_name": u.display_name, "department_id": u.department_id}
            for u in db.scalars(select(User).where(User.status == "ACTIVE").order_by(User.display_name).limit(500))]


@router.get("/access/authority")
def own_authority(db: Db, user: Actor) -> list[dict]:
    return [{"department_id": a.department_id, "office": a.office}
            for a in db.scalars(select(AclAuthority).where(
                AclAuthority.user_id == user.id, AclAuthority.active.is_(True),
                AclAuthority.expires_at > datetime.now(UTC),
            ))]
