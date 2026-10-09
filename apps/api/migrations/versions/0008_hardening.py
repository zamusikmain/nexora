"""Add explicit workflow requirements and durable operation keys; preserve old rows."""

import sqlalchemy as sa
from alembic import op

revision = "0008_hardening"
down_revision = "0007_acl"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "operation_keys",
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("key", sa.String(36), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "workflow_requirements",
        sa.Column("type_id", sa.String(36), sa.ForeignKey("document_types.id"), primary_key=True),
        sa.Column("template_id", sa.String(36), sa.ForeignKey("workflow_templates.id"), nullable=False),
        sa.Column("reviewer_roles", sa.JSON(), nullable=False),
    )
    op.execute(
        "CREATE TRIGGER operation_keys_immutable BEFORE UPDATE OR DELETE ON operation_keys "
        "FOR EACH ROW EXECUTE FUNCTION nexora_immutable_row()"
    )


def downgrade():
    for table in ("operation_keys", "workflow_requirements"):
        if op.get_bind().scalar(sa.text(f"SELECT count(*) FROM {table}")):
            raise RuntimeError("Hardening rollback blocked: preserve operation keys and route requirements")
    op.drop_table("workflow_requirements")
    op.drop_table("operation_keys")
