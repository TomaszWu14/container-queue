"""Kontener: dowóz po odprawie (on_carriage: drogowo / intermodal).

Revision ID: dowoz001
Revises: morlot001
"""
import sqlalchemy as sa
from alembic import op

revision = "dowoz001"
down_revision = "morlot001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # VARCHAR, nie natywny enum — model: Enum(OnCarriage, native_enum=False)
    op.add_column("containers", sa.Column("on_carriage", sa.String(length=10), nullable=True))


def downgrade() -> None:
    op.drop_column("containers", "on_carriage")
