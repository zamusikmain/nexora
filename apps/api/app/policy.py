"""One resource policy shared by SQL collections and individual requests."""

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import and_, case, false, func, literal, or_, select
from sqlalchemy.orm import Session, aliased
from sqlalchemy.sql.elements import ColumnElement

from app.models import (
    AccessGrant,
    AclAuthority,
    Approval,
    DepartmentReviewPolicy,
    Document,
    DocumentVersion,
    GrantEndorsement,
    User,
    WorkflowInstance,
)

PERMISSIONS = {
    role: {"create", "comment"} for role in ("USER", "REVIEWER", "APPROVER", "LEGAL", "MANAGER", "ADMIN")
}
PERMISSIONS["ADMIN"] |= {"admin", "audit"}


def require(user: User, permission: str) -> None:
    if user.status != "ACTIVE" or permission not in PERMISSIONS.get(user.role, set()):
        raise HTTPException(403, "forbidden")


def authority(db: Session, user: User, department_id: str | None, office: str) -> AclAuthority | None:
    if user.status != "ACTIVE" or not department_id:
        return None
    return db.scalar(select(AclAuthority).where(
        AclAuthority.user_id == user.id, AclAuthority.department_id == department_id,
        AclAuthority.office == office, AclAuthority.active.is_(True),
        AclAuthority.expires_at > datetime.now(UTC),
    ))


def endorsement_valid(office: str) -> ColumnElement[bool]:
    issuer = aliased(User)
    return select(GrantEndorsement.id).join(AclAuthority, AclAuthority.id == GrantEndorsement.authority_id).join(
        issuer, issuer.id == GrantEndorsement.actor_id,
    ).where(
        GrantEndorsement.grant_id == AccessGrant.id, GrantEndorsement.office == office,
        GrantEndorsement.scope_hash == AccessGrant.scope_hash,
        GrantEndorsement.actor_id != AccessGrant.requested_by,
        GrantEndorsement.actor_id != AccessGrant.recipient_id,
        GrantEndorsement.approved_at >= AccessGrant.requested_at,
        GrantEndorsement.approved_at < AccessGrant.review_deadline,
        GrantEndorsement.approved_at <= func.now(),
        AclAuthority.user_id == GrantEndorsement.actor_id, AclAuthority.office == office,
        AclAuthority.department_id == Document.department_id,
        AclAuthority.active.is_(True), AclAuthority.expires_at > func.now(), issuer.status == "ACTIVE",
    ).correlate(AccessGrant, Document).exists()


def grant_conditions(user: User, version, action: str) -> ColumnElement[bool]:
    allowed = getattr(AccessGrant, "can_" + action)
    requester = aliased(User)
    issuer_active = select(requester.id).where(
        requester.id == AccessGrant.requested_by, requester.status == "ACTIVE",
    ).correlate(AccessGrant).exists()
    review_need = select(Approval.id).join(WorkflowInstance, WorkflowInstance.id == Approval.instance_id).where(
        Approval.id == AccessGrant.approval_id, Approval.user_id == user.id, Approval.status == "PENDING",
        Approval.stage == WorkflowInstance.stage, WorkflowInstance.id == AccessGrant.instance_id,
        WorkflowInstance.document_id == Document.id, WorkflowInstance.document_version_id == AccessGrant.version_id,
        WorkflowInstance.status == "RUNNING", Document.status == "IN_APPROVAL",
    ).correlate(AccessGrant, Document).exists()
    if action == "snapshot":
        review_need = select(Approval.id).join(WorkflowInstance, WorkflowInstance.id == Approval.instance_id).where(
            Approval.id == AccessGrant.approval_id, Approval.user_id == user.id,
            Approval.status.in_(["PENDING", "APPROVED"]),
            WorkflowInstance.id == AccessGrant.instance_id, WorkflowInstance.status == "RUNNING",
            WorkflowInstance.document_id == Document.id,
            WorkflowInstance.document_version_id == AccessGrant.version_id,
        ).correlate(AccessGrant, Document).exists()
    draft_need = and_(
        literal(user.role == "MANAGER"), Document.department_id == user.department_id,
        Document.confidentiality.in_(["PUBLIC", "INTERNAL"]),
        Document.status.in_(["DRAFT", "REVISION_REQUIRED"]), AccessGrant.version_id == Document.current_version_id,
        select(DepartmentReviewPolicy.department_id).where(
            DepartmentReviewPolicy.department_id == Document.department_id, DepartmentReviewPolicy.enabled.is_(True),
        ).correlate(Document).exists(),
    )
    return and_(
        AccessGrant.document_id == Document.id, AccessGrant.version_id == version,
        AccessGrant.recipient_id == user.id, AccessGrant.recipient_role == user.role,
        AccessGrant.recipient_department_id.is_not_distinct_from(user.department_id),
        AccessGrant.department_id.is_not_distinct_from(Document.department_id),
        AccessGrant.classification == Document.confidentiality,
        AccessGrant.status == "ACTIVE", AccessGrant.activated_at <= func.now(), AccessGrant.expires_at > func.now(),
        AccessGrant.revoked_at.is_(None), allowed.is_(True), Document.deleted_at.is_(None), issuer_active,
        or_(
            and_(AccessGrant.classification == "RESTRICTED", AccessGrant.duration_hours <= 8,
                 endorsement_valid("CUSTODIAN"), endorsement_valid("SECURITY")),
            and_(AccessGrant.classification != "RESTRICTED", or_(
                AccessGrant.requested_by == Document.owner_id, endorsement_valid("CUSTODIAN"),
            )),
        ),
        or_(
            and_(AccessGrant.purpose == "review", review_need),
            and_(AccessGrant.purpose == "draft", draft_need),
            AccessGrant.purpose.in_(["personal", "incident", "audit_snapshot"]),
        ),
    )


def grant_read(user: User, version, action: str) -> ColumnElement[bool]:
    return select(AccessGrant.id).where(grant_conditions(user, version, action)).correlate(Document, WorkflowInstance, DocumentVersion).exists()


def active_assignment(user: User, version=None) -> ColumnElement[bool]:
    conditions = [
        Approval.user_id == user.id, Approval.status == "PENDING", Approval.stage == WorkflowInstance.stage,
        WorkflowInstance.document_id == Document.id, WorkflowInstance.status == "RUNNING",
        Document.status == "IN_APPROVAL", Document.deleted_at.is_(None),
        or_(Document.confidentiality != "RESTRICTED", grant_read(user, WorkflowInstance.document_version_id, "card")),
    ]
    if version is not None:
        conditions.append(WorkflowInstance.document_version_id == version)
    return select(Approval.id).join(WorkflowInstance, Approval.instance_id == WorkflowInstance.id).where(
        *conditions,
    ).correlate(Document, DocumentVersion).exists()


def manager_read(user: User, version) -> ColumnElement[bool]:
    return and_(literal(user.role == "MANAGER" and user.department_id is not None),
                Document.department_id == user.department_id, Document.status == "APPROVED",
                Document.confidentiality.in_(["PUBLIC", "INTERNAL"]),
                Document.deleted_at.is_(None), Document.current_version_id == version)


def resource_visibility(user: User, action: str = "card", version=None) -> ColumnElement[bool]:
    if user.status != "ACTIVE":
        return false()
    version = Document.current_version_id if version is None else version
    owner = Document.owner_id == user.id
    if action in {"card", "file"}:
        assigned = active_assignment(user, version)
        if action == "file":
            assigned = and_(assigned, or_(Document.confidentiality != "RESTRICTED", grant_read(user, version, "file")))
        return or_(owner, manager_read(user, version), assigned, grant_read(user, version, action))
    return or_(owner, grant_read(user, version, action))


def visibility(user: User) -> ColumnElement[bool]:
    return resource_visibility(user)


def visible_field(user: User, field: str):
    """Search/count the same frozen data returned to the reader, never live fields."""
    live = or_(Document.owner_id == user.id, manager_read(user, Document.current_version_id))
    review = select(
        WorkflowInstance.metadata_snapshot["title"].as_string() if field == "title" else literal("IN_APPROVAL")
    ).select_from(WorkflowInstance).join(Approval, Approval.instance_id == WorkflowInstance.id).where(
        WorkflowInstance.document_id == Document.id, WorkflowInstance.status == "RUNNING",
        Approval.user_id == user.id, Approval.status == "PENDING", Approval.stage == WorkflowInstance.stage,
    ).correlate(Document).limit(1).scalar_subquery()
    grant = select(AccessGrant.snapshot[field].as_string()).where(
        grant_conditions(user, Document.current_version_id, "card"),
    ).correlate(Document).order_by(AccessGrant.requested_at.desc(), AccessGrant.id).limit(1).scalar_subquery()
    return case((live, getattr(Document, field)), else_=func.coalesce(review, grant))


def can_read(db: Session, user: User, doc: Document, action: str = "card", version=None) -> bool:
    return bool(db.scalar(select(Document.id).where(
        Document.id == doc.id, resource_visibility(user, action, version),
    )))


def read_actions(db: Session, user: User, doc: Document, actions: tuple[str, ...]) -> dict[str, bool]:
    """can_read for several actions in one statement; owners skip the query (policy grants them)."""
    if user.status == "ACTIVE" and doc.owner_id == user.id and not {"card", "file"} & set(actions):
        return dict.fromkeys(actions, True)
    row = db.execute(select(*(
        case((resource_visibility(user, action), True), else_=False).label(action) for action in actions
    )).where(Document.id == doc.id)).one_or_none()
    return {action: bool(row and row._mapping[action]) for action in actions}


def assert_read(db: Session, user: User, doc: Document, action: str = "card", version=None) -> None:
    if not can_read(db, user, doc, action, version):
        raise HTTPException(404, "not_found")


def require_write(user: User, doc: Document) -> None:
    if doc.owner_id != user.id:
        raise HTTPException(403, "forbidden")
    if doc.deleted_at is not None:
        raise HTTPException(409, "document_in_trash")
    if doc.status not in {"DRAFT", "REVISION_REQUIRED"}:
        raise HTTPException(409, "document_not_editable")
