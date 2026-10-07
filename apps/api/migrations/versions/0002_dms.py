"""Private folders, favorites, trash and optimistic revisions."""

import sqlalchemy as sa
from alembic import op

revision = "0002_dms"
down_revision = "0001_core"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "folders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("parent_id", sa.String(36), sa.ForeignKey("folders.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("parent_id IS NULL OR parent_id <> id", name="folder_not_self"),
    )
    op.create_index("ix_folders_owner_id", "folders", ["owner_id"])
    op.create_index("ix_folders_parent_id", "folders", ["parent_id"])
    op.add_column("documents", sa.Column("folder_id", sa.String(36), sa.ForeignKey("folders.id")))
    op.add_column("documents", sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.add_column("documents", sa.Column("revision", sa.Integer(), server_default="1", nullable=False))
    op.create_index("ix_documents_folder_id", "documents", ["folder_id"])
    op.create_index("ix_documents_deleted_at", "documents", ["deleted_at"])
    op.create_table(
        "document_favorites",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    op.drop_table("document_favorites")
    op.drop_index("ix_documents_deleted_at", "documents")
    op.drop_index("ix_documents_folder_id", "documents")
    op.drop_column("documents", "revision")
    op.drop_column("documents", "deleted_at")
    op.drop_column("documents", "folder_id")
    op.drop_table("folders")
