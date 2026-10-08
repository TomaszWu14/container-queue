"""Moduły magazynu W10: propozycje zmian awizacji, pomiar czasu rozładunku,
zdjęcia z rozładunku.

Revision ID: b9c0d1e2f3a4
Revises: d7e8f9a0b1c3
Create Date: 2026-09-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b9c0d1e2f3a4'
down_revision: Union[str, Sequence[str], None] = 'd7e8f9a0b1c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'avizo_change_proposals',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('request_id', sa.Integer(), sa.ForeignKey('avizo_requests.id'),
                  nullable=False, index=True),
        sa.Column('container_id', sa.Integer(), sa.ForeignKey('containers.id'),
                  nullable=False, index=True),
        sa.Column('proposed_date', sa.Date(), nullable=False),
        sa.Column('proposed_time', sa.String(length=5), nullable=False, server_default=''),
        sa.Column('note', sa.Text(), nullable=False, server_default=''),
        sa.Column('status', sa.Enum('pending', 'accepted', 'rejected',
                                    name='avizoproposalstatus'),
                  nullable=False, server_default='pending', index=True),
        sa.Column('reject_reason', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.Column('decided_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
    )
    op.create_table(
        'unload_photos',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('container_id', sa.Integer(), sa.ForeignKey('containers.id'),
                  nullable=False, index=True),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('stored_name', sa.String(length=255), nullable=False, unique=True),
        sa.Column('content_type', sa.String(length=120), nullable=False, server_default=''),
        sa.Column('size', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('caption', sa.String(length=300), nullable=False, server_default=''),
        sa.Column('uploaded_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.add_column('containers', sa.Column('unload_started_at', sa.DateTime(), nullable=True))
    op.add_column('containers', sa.Column('unload_finished_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('containers', 'unload_finished_at')
    op.drop_column('containers', 'unload_started_at')
    op.drop_table('unload_photos')
    op.drop_table('avizo_change_proposals')
