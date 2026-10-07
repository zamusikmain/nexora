"""Iteration 1 core schema; frozen, independent of runtime models."""

import sqlalchemy as sa
from alembic import op

revision = "0001_core"
down_revision = None
branch_labels = None
depends_on = None


def timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def identity():
    return sa.Column("id", sa.String(36), primary_key=True)


def upgrade():
    op.execute(sa.schema.CreateSequence(sa.Sequence("document_number_seq")))
    op.create_table(
        "departments",
        identity(),
        sa.Column("code", sa.String(40), nullable=False, unique=True),
        sa.Column("name_ru", sa.String(100), nullable=False),
        sa.Column("name_en", sa.String(100), nullable=False),
        *timestamps(),
    )
    op.create_table(
        "users",
        identity(),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("department_id", sa.String(36), sa.ForeignKey("departments.id")),
        *timestamps(),
        sa.CheckConstraint(
            "role IN ('USER','REVIEWER','APPROVER','LEGAL','MANAGER','ADMIN')", name="user_role"
        ),
        sa.CheckConstraint("status IN ('ACTIVE','BLOCKED','DISABLED')", name="user_status"),
    )
    op.create_index("ix_users_department_id", "users", ["department_id"])
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    op.create_table(
        "login_throttles",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "document_types",
        identity(),
        sa.Column("code", sa.String(40), nullable=False, unique=True),
        sa.Column("name_ru", sa.String(100), nullable=False),
        sa.Column("name_en", sa.String(100), nullable=False),
        sa.Column("metadata_schema", sa.JSON(), nullable=False),
        *timestamps(),
    )
    op.create_table(
        "documents",
        identity(),
        sa.Column("number", sa.String(40), nullable=False, unique=True),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("type_id", sa.String(36), sa.ForeignKey("document_types.id"), nullable=False),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("department_id", sa.String(36), sa.ForeignKey("departments.id")),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("business_metadata", sa.JSON(), nullable=False),
        sa.Column("current_version_id", sa.String(36)),
        *timestamps(),
        sa.CheckConstraint(
            "status IN ('DRAFT','SUBMITTED','IN_REVIEW','IN_APPROVAL','REVISION_REQUIRED','APPROVED','REJECTED','CANCELLED','ARCHIVED')",
            name="document_status",
        ),
    )
    for col in ["type_id", "owner_id"]:
        op.create_index("ix_documents_" + col, "documents", [col])
    op.create_index("ix_documents_department_status", "documents", ["department_id", "status"])
    op.create_table(
        "document_versions",
        identity(),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(200), nullable=False),
        sa.Column("storage_key", sa.String(64), nullable=False, unique=True),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("change_note", sa.String(1000)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("document_id", "version_number", name="uq_document_version_number"),
        sa.UniqueConstraint("document_id", "id", name="uq_document_version_identity"),
        sa.CheckConstraint("version_number > 0 AND size > 0", name="version_positive"),
    )
    op.create_index("ix_document_versions_document_id", "document_versions", ["document_id"])
    op.create_foreign_key(
        "fk_document_current_version",
        "documents",
        "document_versions",
        ["id", "current_version_id"],
        ["document_id", "id"],
    )
    op.create_table(
        "comments",
        identity(),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("author_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("body", sa.String(4000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_comments_document_id", "comments", ["document_id"])
    op.create_table(
        "audit_events",
        identity(),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("target_type", sa.String(30), nullable=False),
        sa.Column("target_id", sa.String(36)),
        sa.Column("safe_metadata", sa.JSON(), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    for col in ["action", "target_id", "created_at"]:
        op.create_index("ix_audit_events_" + col, "audit_events", [col])
    op.execute("""CREATE FUNCTION nexora_immutable_row() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN RAISE EXCEPTION 'immutable record'; END; $$""")
    for table in ["document_versions", "audit_events"]:
        op.execute(
            f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION nexora_immutable_row()"
        )


def downgrade():
    for table in ["document_versions", "audit_events"]:
        op.execute(f"DROP TRIGGER immutable_{table} ON {table}")
    op.execute("DROP FUNCTION nexora_immutable_row()")
    op.drop_table("audit_events")
    op.drop_table("comments")
    op.drop_constraint("fk_document_current_version", "documents", type_="foreignkey")
    op.drop_table("document_versions")
    op.drop_table("documents")
    op.drop_table("document_types")
    op.drop_table("login_throttles")
    op.drop_table("auth_sessions")
    op.drop_table("users")
    op.drop_table("departments")
    op.execute(sa.schema.DropSequence(sa.Sequence("document_number_seq")))
