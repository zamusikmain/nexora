"""Structured metadata; preserves existing freeform metadata."""

import sqlalchemy as sa
from alembic import op

revision = "0003_metadata"
down_revision = "0002_dms"
branch_labels = None
depends_on = None


def upgrade():
    for column in [
        sa.Column("description", sa.String(4000), server_default="", nullable=False),
        sa.Column("category", sa.String(100), server_default="", nullable=False),
        sa.Column("tags", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("responsible_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("confidentiality", sa.String(20), server_default="INTERNAL", nullable=False),
        sa.Column("effective_date", sa.Date()),
        sa.Column("expiration_date", sa.Date()),
    ]:
        op.add_column("documents", column)
    op.create_index("ix_documents_responsible_id", "documents", ["responsible_id"])
    op.create_check_constraint(
        "document_confidentiality",
        "documents",
        "confidentiality IN ('PUBLIC','INTERNAL','CONFIDENTIAL','RESTRICTED')",
    )
    op.create_check_constraint(
        "document_dates",
        "documents",
        "effective_date IS NULL OR expiration_date IS NULL OR expiration_date >= effective_date",
    )


def downgrade():
    op.drop_constraint("document_dates", "documents", type_="check")
    op.drop_constraint("document_confidentiality", "documents", type_="check")
    op.drop_index("ix_documents_responsible_id", "documents")
    for name in [
        "expiration_date",
        "effective_date",
        "confidentiality",
        "responsible_id",
        "tags",
        "category",
        "description",
    ]:
        op.drop_column("documents", name)
