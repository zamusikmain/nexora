import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Sequence,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def uid() -> str:
    return str(uuid.uuid4())


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Department(Timestamped, Base):
    __tablename__ = "departments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name_ru: Mapped[str] = mapped_column(String(100))
    name_en: Mapped[str] = mapped_column(String(100))


class User(Timestamped, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('USER','REVIEWER','APPROVER','LEGAL','MANAGER','ADMIN')", name="user_role"),
        CheckConstraint("status IN ('ACTIVE','BLOCKED','DISABLED')", name="user_status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="USER")
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    department_id: Mapped[str | None] = mapped_column(ForeignKey("departments.id"), index=True)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (UniqueConstraint("public_id", name="uq_auth_session_public_id"),)
    public_id: Mapped[str] = mapped_column(String(36), default=uid)
    user_agent: Mapped[str] = mapped_column(String(200), default="", server_default="")
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LoginThrottle(Base):
    __tablename__ = "login_throttles"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DocumentType(Timestamped, Base):
    __tablename__ = "document_types"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name_ru: Mapped[str] = mapped_column(String(100))
    name_en: Mapped[str] = mapped_column(String(100))
    metadata_schema: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


number_sequence = Sequence("document_number_seq", metadata=Base.metadata)


class Document(Timestamped, Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','SUBMITTED','IN_REVIEW','IN_APPROVAL','REVISION_REQUIRED','APPROVED','REJECTED','CANCELLED','ARCHIVED')",
            name="document_status",
        ),
        ForeignKeyConstraint(
            ["id", "current_version_id"],
            ["document_versions.document_id", "document_versions.id"],
            name="fk_document_current_version",
            use_alter=True,
        ),
        CheckConstraint(
            "confidentiality IN ('PUBLIC','INTERNAL','CONFIDENTIAL','RESTRICTED')",
            name="document_confidentiality",
        ),
        CheckConstraint(
            "effective_date IS NULL OR expiration_date IS NULL OR expiration_date >= effective_date",
            name="document_dates",
        ),
        Index("ix_documents_department_status", "department_id", "status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    number: Mapped[str] = mapped_column(String(40), unique=True)
    title: Mapped[str] = mapped_column(String(240))
    type_id: Mapped[str] = mapped_column(ForeignKey("document_types.id"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    department_id: Mapped[str | None] = mapped_column(ForeignKey("departments.id"))
    status: Mapped[str] = mapped_column(String(30), default="DRAFT")
    business_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    current_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    description: Mapped[str] = mapped_column(String(4000), default="", server_default="")
    category: Mapped[str] = mapped_column(String(100), default="", server_default="")
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    responsible_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    confidentiality: Mapped[str] = mapped_column(String(20), default="INTERNAL", server_default="INTERNAL")
    effective_date: Mapped[date | None] = mapped_column(Date)
    expiration_date: Mapped[date | None] = mapped_column(Date)
    folder_id: Mapped[str | None] = mapped_column(ForeignKey("folders.id"), index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class Folder(Timestamped, Base):
    __tablename__ = "folders"
    __table_args__ = (CheckConstraint("parent_id IS NULL OR parent_id <> id", name="folder_not_self"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(120))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("folders.id"), index=True)


class Favorite(Base):
    __tablename__ = "document_favorites"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_document_version_number"),
        UniqueConstraint("document_id", "id", name="uq_document_version_identity"),
        CheckConstraint("version_number > 0 AND size > 0", name="version_positive"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    original_filename: Mapped[str] = mapped_column(String(200))
    storage_key: Mapped[str] = mapped_column(String(64), unique=True)
    mime_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    change_note: Mapped[str | None] = mapped_column(String(1000))
    metadata_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Comment(Base):
    __tablename__ = "comments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(String(4000))
    version_id: Mapped[str | None] = mapped_column(ForeignKey("document_versions.id"))
    instance_id: Mapped[str | None] = mapped_column(ForeignKey("workflow_instances.id"))
    stage: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(60), index=True)
    target_type: Mapped[str] = mapped_column(String(30))
    target_id: Mapped[str | None] = mapped_column(String(36), index=True)
    safe_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    request_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class WorkflowTemplate(Base):
    __tablename__ = "workflow_templates"
    __table_args__ = (
        UniqueConstraint("code", "version", name="uq_workflow_template_version"),
        CheckConstraint("version > 0", name="workflow_template_positive"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    code: Mapped[str] = mapped_column(String(40), index=True)
    version: Mapped[int] = mapped_column(Integer)
    name_ru: Mapped[str] = mapped_column(String(120))
    name_en: Mapped[str] = mapped_column(String(120))
    definition: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkflowInstance(Base):
    __tablename__ = "workflow_instances"
    __table_args__ = (
        CheckConstraint(
            "status IN ('RUNNING','APPROVED','REJECTED','REVISION_REQUIRED','CANCELLED')",
            name="workflow_status",
        ),
        ForeignKeyConstraint(
            ["document_id", "document_version_id"],
            ["document_versions.document_id", "document_versions.id"],
            name="fk_workflow_document_version",
        ),
        Index(
            "uq_workflow_active_document",
            "document_id",
            unique=True,
            postgresql_where=text("status = 'RUNNING'"),
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    document_version_id: Mapped[str] = mapped_column(String(36))
    template_id: Mapped[str] = mapped_column(ForeignKey("workflow_templates.id"))
    metadata_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    stage: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="RUNNING")
    started_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = (
        UniqueConstraint("instance_id", "stage", "user_id", name="uq_approval_assignee"),
        CheckConstraint(
            "status IN ('WAITING','PENDING','APPROVED','REJECTED','REVISION_REQUIRED','CANCELLED')",
            name="approval_status",
        ),
        Index("ix_approvals_user_status_due", "user_id", "status", "due_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    instance_id: Mapped[str] = mapped_column(ForeignKey("workflow_instances.id"), index=True)
    stage: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(30))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkflowEvent(Base):
    __tablename__ = "workflow_events"
    __table_args__ = (UniqueConstraint("actor_id", "idempotency_key", name="uq_workflow_actor_request"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    instance_id: Mapped[str] = mapped_column(ForeignKey("workflow_instances.id"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(30))
    comment: Mapped[str] = mapped_column(String(2000))
    previous_state: Mapped[str] = mapped_column(String(30))
    new_state: Mapped[str] = mapped_column(String(30))
    idempotency_key: Mapped[str] = mapped_column(String(36))
    request_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FileScan(Base):
    __tablename__ = "file_scans"
    version_id: Mapped[str] = mapped_column(ForeignKey("document_versions.id"), primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64))
    engine: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AclAuthority(Base):
    """Operator-managed business authority. Runtime can SELECT, never assign it."""
    __tablename__ = "acl_authorities"
    __table_args__ = (
        UniqueConstraint("user_id", "department_id", "office", name="uq_acl_authority"),
        CheckConstraint("office IN ('CUSTODIAN','SECURITY')", name="acl_authority_office"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    department_id: Mapped[str] = mapped_column(ForeignKey("departments.id"))
    office: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DepartmentReviewPolicy(Base):
    __tablename__ = "acl_department_policies"
    department_id: Mapped[str] = mapped_column(ForeignKey("departments.id"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AccessGrant(Base):
    __tablename__ = "access_grants"
    __table_args__ = (
        ForeignKeyConstraint(["document_id", "version_id"],
                             ["document_versions.document_id", "document_versions.id"], name="fk_grant_version"),
        CheckConstraint("status IN ('PENDING','ACTIVE','DENIED','REVOKED','EXPIRED')", name="grant_status"),
        CheckConstraint("purpose IN ('personal','review','audit_snapshot','draft','incident')", name="grant_purpose"),
        CheckConstraint("duration_hours > 0 AND duration_hours <= 168", name="grant_duration"),
        Index("ix_grants_recipient_document", "recipient_id", "document_id", "status", "expires_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"))
    version_id: Mapped[str] = mapped_column(String(36))
    recipient_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    recipient_role: Mapped[str] = mapped_column(String(20))
    recipient_department_id: Mapped[str | None] = mapped_column(String(36))
    department_id: Mapped[str | None] = mapped_column(String(36))
    classification: Mapped[str] = mapped_column(String(20))
    purpose: Mapped[str] = mapped_column(String(20))
    instance_id: Mapped[str | None] = mapped_column(ForeignKey("workflow_instances.id"))
    approval_id: Mapped[str | None] = mapped_column(ForeignKey("approvals.id"))
    can_card: Mapped[bool] = mapped_column(Boolean, default=False)
    can_file: Mapped[bool] = mapped_column(Boolean, default=False)
    can_snapshot: Mapped[bool] = mapped_column(Boolean, default=False)
    can_comments: Mapped[bool] = mapped_column(Boolean, default=False)
    can_history: Mapped[bool] = mapped_column(Boolean, default=False)
    can_compare: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str] = mapped_column(String(1000))
    duration_hours: Mapped[int] = mapped_column(Integer)
    scope_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    review_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class GrantEndorsement(Base):
    __tablename__ = "grant_endorsements"
    __table_args__ = (
        UniqueConstraint("grant_id", "office", name="uq_grant_office"),
        UniqueConstraint("grant_id", "actor_id", name="uq_grant_actor"),
        CheckConstraint("office IN ('CUSTODIAN','SECURITY')", name="grant_office"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    grant_id: Mapped[str] = mapped_column(ForeignKey("access_grants.id"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    authority_id: Mapped[str] = mapped_column(ForeignKey("acl_authorities.id"))
    office: Mapped[str] = mapped_column(String(20))
    scope_hash: Mapped[str] = mapped_column(String(64))
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReviewReceipt(Base):
    __tablename__ = "review_receipts"
    __table_args__ = (UniqueConstraint("actor_id", "idempotency_key", name="uq_receipt_request"),)
    approval_id: Mapped[str] = mapped_column(ForeignKey("approvals.id"), primary_key=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    version_id: Mapped[str] = mapped_column(ForeignKey("document_versions.id"))
    outcome: Mapped[str] = mapped_column(String(30))
    process_status: Mapped[str] = mapped_column(String(30))
    idempotency_key: Mapped[str] = mapped_column(String(36))
    acted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class ReceiptRevocation(Base):
    __tablename__ = "receipt_revocations"
    approval_id: Mapped[str] = mapped_column(ForeignKey("approvals.id"), primary_key=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(String(1000))
    hide_receipt: Mapped[bool] = mapped_column(Boolean, default=False)
    revoked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OperationKey(Base):
    __tablename__ = "operation_keys"
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    key: Mapped[str] = mapped_column(String(36), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Signed key expiry; NULL for legacy client UUID keys, which are never purged automatically.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class WorkflowRequirement(Base):
    """Required route per document type; classification '*' applies to any classification."""

    __tablename__ = "workflow_requirements"
    __table_args__ = (
        CheckConstraint(
            "classification IN ('*','PUBLIC','INTERNAL','CONFIDENTIAL','RESTRICTED')",
            name="ck_workflow_requirement_classification",
        ),
    )
    type_id: Mapped[str] = mapped_column(ForeignKey("document_types.id"), primary_key=True)
    classification: Mapped[str] = mapped_column(String(20), primary_key=True, default="*", server_default="*")
    template_id: Mapped[str] = mapped_column(ForeignKey("workflow_templates.id"))
    reviewer_roles: Mapped[list[str]] = mapped_column(JSON)
