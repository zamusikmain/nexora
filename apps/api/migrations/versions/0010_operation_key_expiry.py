"""Expiring operation keys (B2): purge only rows whose signed key expired over a day ago.

Rows stay immutable. DELETE is permitted by the trigger only for keys with a stored expiry
older than one day (clock skew and in-flight transactions); legacy rows (NULL expiry) and
anything newer are refused for every role. The runtime role still has no DELETE grant.
"""

import sqlalchemy as sa
from alembic import op

revision = "0010_operation_key_expiry"
down_revision = "0009_route_classification"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("operation_keys", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_operation_keys_expires_at", "operation_keys", ["expires_at"])
    op.execute("""CREATE FUNCTION nexora_operation_key_purge_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
        IF OLD.expires_at IS NULL OR OLD.expires_at >= now() - interval '1 day' THEN
            RAISE EXCEPTION 'operation key is not expired';
        END IF;
        RETURN OLD;
        END $$""")
    op.execute("DROP TRIGGER operation_keys_immutable ON operation_keys")
    op.execute(
        "CREATE TRIGGER operation_keys_immutable BEFORE UPDATE ON operation_keys "
        "FOR EACH ROW EXECUTE FUNCTION nexora_immutable_row()"
    )
    op.execute(
        "CREATE TRIGGER operation_keys_purge_guard BEFORE DELETE ON operation_keys "
        "FOR EACH ROW EXECUTE FUNCTION nexora_operation_key_purge_guard()"
    )


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM operation_keys WHERE expires_at IS NOT NULL")):
        raise RuntimeError("Key expiry rollback blocked: signed operation keys exist")
    op.execute("DROP TRIGGER operation_keys_purge_guard ON operation_keys")
    op.execute("DROP TRIGGER operation_keys_immutable ON operation_keys")
    op.execute(
        "CREATE TRIGGER operation_keys_immutable BEFORE UPDATE OR DELETE ON operation_keys "
        "FOR EACH ROW EXECUTE FUNCTION nexora_immutable_row()"
    )
    op.execute("DROP FUNCTION nexora_operation_key_purge_guard()")
    op.drop_index("ix_operation_keys_expires_at", "operation_keys")
    op.drop_column("operation_keys", "expires_at")
