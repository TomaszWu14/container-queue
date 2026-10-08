"""Dane kontroli dokumentu faktury (etap 3 profilu dostawcy): suma z faktury i ilości z PL.

Revision ID: kontrole001
Revises: log001
"""
import sqlalchemy as sa
from alembic import op

revision = "kontrole001"
down_revision = "log001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("invoice_jobs") as b:
        b.add_column(sa.Column("check_data", sa.JSON, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("invoice_jobs") as b:
        b.drop_column("check_data")
