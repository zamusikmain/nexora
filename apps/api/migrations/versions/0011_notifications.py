"""In-app notifications with an email outbox, and one-time escalation of overdue approvals."""

import sqlalchemy as sa
from alembic import op

revision = "0011_notifications"
down_revision = "0010_operation_key_expiry"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("approvals", sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("recipient_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("instance_id", sa.String(36), sa.ForeignKey("workflow_instances.id"), nullable=True),
        sa.Column("approval_id", sa.String(36), sa.ForeignKey("approvals.id"), nullable=True),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("dedupe_key", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_status", sa.String(10), server_default="NONE", nullable=False),
        sa.Column("email_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("recipient_id", "dedupe_key", name="uq_notification_dedupe"),
        sa.CheckConstraint(
            "kind IN ('TASK_ASSIGNED','TASK_CANCELLED','TASK_OVERDUE','TASK_ESCALATED',"
            "'WORKFLOW_APPROVED','WORKFLOW_REJECTED','WORKFLOW_RETURNED','WORKFLOW_OVERDUE')",
            name="notification_kind",
        ),
        sa.CheckConstraint(
            "email_status IN ('NONE','PENDING','SENT','FAILED','SKIPPED')", name="notification_email_status"
        ),
    )
    op.create_index("ix_notifications_recipient_created", "notifications", ["recipient_id", "created_at"])
    op.create_index(
        "ix_notifications_unread", "notifications", ["recipient_id"], postgresql_where=sa.text("read_at IS NULL")
    )
    op.create_index(
        "ix_notifications_email_pending", "notifications", ["created_at"],
        postgresql_where=sa.text("email_status = 'PENDING'"),
    )


def downgrade():
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT count(*) FROM approvals WHERE escalated_at IS NOT NULL")) or bind.scalar(
        sa.text("SELECT count(*) FROM notifications")
    ):
        raise RuntimeError("Notification rollback blocked: notifications or escalation history exist")
    op.drop_table("notifications")
    op.drop_column("approvals", "escalated_at")
