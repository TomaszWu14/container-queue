"""pola kolejki Acme: ID transportu, SENT, przepływ dokumentów, notatki

Revision ID: c3d4e5f6a7b8
Revises: a1f2e3d4c5b6
Create Date: 2026-07-08 08:20:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'a1f2e3d4c5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('containers', sa.Column('transport_id', sa.String(length=20), nullable=True))
    op.add_column('containers', sa.Column('order_numbers', sa.Text(), nullable=False,
                                          server_default=''))
    op.add_column('containers', sa.Column('delivery_note', sa.Text(), nullable=False,
                                          server_default=''))
    op.add_column('containers', sa.Column('purchase_note', sa.Text(), nullable=False,
                                          server_default=''))
    op.add_column('containers', sa.Column('document_flow', sa.Text(), nullable=False,
                                          server_default=''))
    op.add_column('containers', sa.Column('sent_required', sa.Boolean(), nullable=True))
    op.add_column('containers', sa.Column('sent_number', sa.Text(), nullable=False,
                                          server_default=''))
    op.add_column('containers', sa.Column('sent_status', sa.String(length=120),
                                          nullable=False, server_default=''))
    op.create_index(op.f('ix_containers_transport_id'), 'containers',
                    ['transport_id'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_containers_transport_id'), table_name='containers')
    for column in ('sent_status', 'sent_number', 'sent_required', 'document_flow',
                   'purchase_note', 'delivery_note', 'order_numbers', 'transport_id'):
        op.drop_column('containers', column)
