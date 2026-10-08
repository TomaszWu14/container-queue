"""container_share_links

Revision ID: 0c10984de306
Revises: b4d2e5f6a7c8
Create Date: 2026-09-15 08:32:56.189718

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0c10984de306'
down_revision: Union[str, Sequence[str], None] = 'b4d2e5f6a7c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "container_share_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("container_id", sa.Integer(),
                  sa.ForeignKey("containers.id"), nullable=False),
        sa.Column("created_by_id", sa.Integer(),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_container_share_links_token",
                    "container_share_links", ["token"], unique=True)
    op.create_index("ix_container_share_links_container_id",
                    "container_share_links", ["container_id"], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("container_share_links")
