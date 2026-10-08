"""Defer legacy password replacement until mailbox ownership is verified."""

import sqlalchemy as sa
from alembic import op

revision = "0003_legacy_password_recovery"
down_revision = "0002_identity_access"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "email_verifications",
        sa.Column("password_reset_hash", sa.String(length=255), nullable=True),
    )


def downgrade():
    op.drop_column("email_verifications", "password_reset_hash")
