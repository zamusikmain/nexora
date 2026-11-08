"""Electronic signatures (ЭЦП, NCALayer) over immutable document versions."""

import sqlalchemy as sa
from alembic import op

revision = "0012_signatures"
down_revision = "0011_notifications"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "document_signatures",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("version_id", sa.String(36), nullable=False),
        sa.Column("signer_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("cms", sa.String(400_000), nullable=False),
        sa.Column("cms_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("verifier", sa.String(20), nullable=False),
        sa.Column("subject_name", sa.String(300), nullable=True),
        sa.Column("subject_iin", sa.String(12), nullable=True),
        sa.Column("subject_bin", sa.String(12), nullable=True),
        sa.Column("certificate_serial", sa.String(80), nullable=True),
        sa.Column("certificate_not_before", sa.DateTime(timezone=True), nullable=True),
        sa.Column("certificate_not_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("version_id", "signer_id", name="uq_signature_version_signer"),
        sa.ForeignKeyConstraint(["document_id", "version_id"],
                                ["document_versions.document_id", "document_versions.id"],
                                name="fk_signature_version"),
        sa.CheckConstraint("status IN ('VALID','UNVERIFIED')", name="signature_status"),
    )
    op.create_index("ix_signatures_document", "document_signatures", ["document_id", "created_at"])
    # Signatures are evidence: no role may change or delete them.
    op.execute(
        "CREATE TRIGGER document_signatures_immutable BEFORE UPDATE OR DELETE ON document_signatures "
        "FOR EACH ROW EXECUTE FUNCTION nexora_immutable_row()"
    )


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM document_signatures")):
        raise RuntimeError("Signature rollback blocked: signed evidence exists")
    op.drop_table("document_signatures")
