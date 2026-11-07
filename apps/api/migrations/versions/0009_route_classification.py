"""Key required workflow routes by document type AND classification.

Existing requirements become wildcard ('*') rows, so their behaviour is unchanged. An exact
(type, classification) row takes precedence over the type's wildcard row at workflow start.
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_route_classification"
down_revision = "0008_hardening"
branch_labels = None
depends_on = None

CLASSIFICATIONS = "'*','PUBLIC','INTERNAL','CONFIDENTIAL','RESTRICTED'"


def upgrade():
    op.add_column(
        "workflow_requirements",
        sa.Column("classification", sa.String(20), nullable=False, server_default="*"),
    )
    op.create_check_constraint(
        "ck_workflow_requirement_classification",
        "workflow_requirements",
        f"classification IN ({CLASSIFICATIONS})",
    )
    op.drop_constraint("workflow_requirements_pkey", "workflow_requirements", type_="primary")
    op.create_primary_key("workflow_requirements_pkey", "workflow_requirements", ["type_id", "classification"])


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM workflow_requirements WHERE classification <> '*'")):
        raise RuntimeError("Route rollback blocked: classification-specific requirements exist")
    op.drop_constraint("workflow_requirements_pkey", "workflow_requirements", type_="primary")
    op.create_primary_key("workflow_requirements_pkey", "workflow_requirements", ["type_id"])
    op.drop_constraint("ck_workflow_requirement_classification", "workflow_requirements", type_="check")
    op.drop_column("workflow_requirements", "classification")
