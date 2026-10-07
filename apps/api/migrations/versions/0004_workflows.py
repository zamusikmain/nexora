"""Versioned workflow templates, snapshots, assignments and immutable decisions."""

import sqlalchemy as sa
from alembic import op

revision = "0004_workflows"
down_revision = "0003_metadata"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "workflow_templates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name_ru", sa.String(120), nullable=False),
        sa.Column("name_en", sa.String(120), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("code", "version", name="uq_workflow_template_version"),
        sa.CheckConstraint("version > 0", name="workflow_template_positive"),
    )
    op.create_index("ix_workflow_templates_code", "workflow_templates", ["code"])
    op.create_table(
        "workflow_instances",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("document_version_id", sa.String(36), nullable=False),
        sa.Column("template_id", sa.String(36), sa.ForeignKey("workflow_templates.id"), nullable=False),
        sa.Column("metadata_snapshot", sa.JSON(), nullable=False),
        sa.Column("stage", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("started_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('RUNNING','APPROVED','REJECTED','REVISION_REQUIRED','CANCELLED')",
            name="workflow_status",
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "document_version_id"],
            ["document_versions.document_id", "document_versions.id"],
            name="fk_workflow_document_version",
        ),
    )
    op.create_index("ix_workflow_instances_document_id", "workflow_instances", ["document_id"])
    op.create_index(
        "uq_workflow_active_document",
        "workflow_instances",
        ["document_id"],
        unique=True,
        postgresql_where=sa.text("status = 'RUNNING'"),
    )
    op.create_table(
        "approvals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("instance_id", sa.String(36), sa.ForeignKey("workflow_instances.id"), nullable=False),
        sa.Column("stage", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("acted_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("instance_id", "stage", "user_id", name="uq_approval_assignee"),
        sa.CheckConstraint(
            "status IN ('WAITING','PENDING','APPROVED','REJECTED','REVISION_REQUIRED','CANCELLED')",
            name="approval_status",
        ),
    )
    op.create_index("ix_approvals_instance_id", "approvals", ["instance_id"])
    op.create_index("ix_approvals_user_status_due", "approvals", ["user_id", "status", "due_at"])
    op.create_table(
        "workflow_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("instance_id", sa.String(36), sa.ForeignKey("workflow_instances.id"), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("comment", sa.String(2000), nullable=False),
        sa.Column("previous_state", sa.String(30), nullable=False),
        sa.Column("new_state", sa.String(30), nullable=False),
        sa.Column("idempotency_key", sa.String(36), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("actor_id", "idempotency_key", name="uq_workflow_actor_request"),
    )
    op.create_index("ix_workflow_events_instance_id", "workflow_events", ["instance_id"])
    for table in ["workflow_templates", "workflow_events"]:
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION nexora_immutable_row()"
        )

    op.execute("""CREATE FUNCTION nexora_workflow_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
        IF NEW.document_id IS DISTINCT FROM OLD.document_id OR NEW.document_version_id IS DISTINCT FROM OLD.document_version_id
        OR NEW.template_id IS DISTINCT FROM OLD.template_id OR NEW.metadata_snapshot::jsonb IS DISTINCT FROM OLD.metadata_snapshot::jsonb
        OR NEW.started_by IS DISTINCT FROM OLD.started_by OR NEW.created_at IS DISTINCT FROM OLD.created_at
        THEN RAISE EXCEPTION 'immutable workflow snapshot'; END IF;
        RETURN NEW; END; $$""")
    op.execute(
        "CREATE TRIGGER workflow_snapshot_immutable BEFORE UPDATE ON workflow_instances FOR EACH ROW EXECUTE FUNCTION nexora_workflow_snapshot()"
    )


def downgrade():
    op.execute("DROP TRIGGER workflow_snapshot_immutable ON workflow_instances")
    op.execute("DROP FUNCTION nexora_workflow_snapshot()")

    op.drop_table("workflow_events")
    op.drop_table("approvals")
    op.drop_table("workflow_instances")
    op.drop_table("workflow_templates")
