"""matryca reguł powiadomień (kind × rola × kanał)

Revision ID: b1a2c3d4e5a1
Revises: e8f9a0b1c2d4
Create Date: 2026-09-19 09:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b1a2c3d4e5a1'
down_revision: Union[str, Sequence[str], None] = 'b5d6e7f8a9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'notification_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=40), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('channel', sa.String(length=10), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('kind', 'role', 'channel'),
    )


def downgrade() -> None:
    op.drop_table('notification_rules')
