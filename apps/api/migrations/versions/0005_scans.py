"""Immutable clean scan attestations; legacy versions stay unscanned."""

import sqlalchemy as sa
from alembic import op

revision = "0005_scans"
down_revision = "0004_workflows"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "file_scans",
        sa.Column("version_id", sa.String(36), sa.ForeignKey("document_versions.id"), primary_key=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("engine", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.execute(
        "CREATE TRIGGER file_scans_immutable BEFORE UPDATE OR DELETE ON file_scans FOR EACH ROW EXECUTE FUNCTION nexora_immutable_row()"
    )


def downgrade():
    op.drop_table("file_scans")
