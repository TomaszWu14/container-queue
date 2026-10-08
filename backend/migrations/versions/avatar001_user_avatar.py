"""Awatar użytkownika (users.avatar — nazwa pliku w uploads/avatars/).

Revision ID: avatar001
Revises: watch001
"""
import sqlalchemy as sa
from alembic import op

revision = "avatar001"
down_revision = "watch001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("avatar", sa.String(255), nullable=False,
                                   server_default=sa.text("''")))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("avatar")
