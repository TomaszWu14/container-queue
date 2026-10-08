"""anty-replay TOTP: users.totp_last_step (ostatni zaakceptowany krok czasowy)

Revision ID: totpstep001
Revises: avz2stg001
Create Date: 2026-09-23
"""
import sqlalchemy as sa
from alembic import op

revision = "totpstep001"
down_revision = "avz2stg001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("totp_last_step", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "totp_last_step")
