"""watched_containers — obserwowane kontenery per user (gwiazdka)

Revision ID: de45fa67bc89
Revises: cd34ef56ab78
Create Date: 2026-09-08 17:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'de45fa67bc89'
down_revision: Union[str, Sequence[str], None] = 'cd34ef56ab78'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'watched_containers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('container_id', sa.Integer(), sa.ForeignKey('containers.id'),
                  nullable=False),
        sa.UniqueConstraint('user_id', 'container_id'),
    )
    op.create_index('ix_watched_containers_user_id', 'watched_containers', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_watched_containers_user_id', table_name='watched_containers')
    op.drop_table('watched_containers')
