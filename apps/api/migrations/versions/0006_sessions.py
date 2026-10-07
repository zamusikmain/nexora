"""Public session identities and sanitized user-agent metadata."""

import sqlalchemy as sa
from alembic import op

revision = "0006_sessions"
down_revision = "0005_scans"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "auth_sessions",
        sa.Column(
            "public_id", sa.String(36), server_default=sa.text("gen_random_uuid()::text"), nullable=False
        ),
    )
    op.alter_column("auth_sessions", "public_id", server_default=None)
    op.add_column("auth_sessions", sa.Column("user_agent", sa.String(200), server_default="", nullable=False))
    op.create_unique_constraint("uq_auth_session_public_id", "auth_sessions", ["public_id"])


def downgrade():
    op.drop_constraint("uq_auth_session_public_id", "auth_sessions", type_="unique")
    op.drop_column("auth_sessions", "user_agent")
    op.drop_column("auth_sessions", "public_id")
