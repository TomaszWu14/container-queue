"""awizacja do spedycji: prośby z formularzem, e-mail magazynu

Revision ID: f9a0b1c2d3e4
Revises: e7f8a9b0c1d2
Create Date: 2026-07-08 11:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f9a0b1c2d3e4'
down_revision: Union[str, Sequence[str], None] = 'e7f8a9b0c1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('warehouses', sa.Column('email', sa.String(length=200),
                                          nullable=False, server_default=''))
    op.create_table(
        'avizo_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=64), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('forwarder_id', sa.Integer(), nullable=False),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(), nullable=True),
        sa.Column('note', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.ForeignKeyConstraint(['forwarder_id'], ['forwarders.id']),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_avizo_requests_token'), 'avizo_requests', ['token'], unique=True)
    op.create_index(op.f('ix_avizo_requests_forwarder_id'), 'avizo_requests', ['forwarder_id'])
    op.create_table(
        'avizo_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('request_id', sa.Integer(), nullable=False),
        sa.Column('container_id', sa.Integer(), nullable=False),
        sa.Column('confirmed', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['request_id'], ['avizo_requests.id']),
        sa.ForeignKeyConstraint(['container_id'], ['containers.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_avizo_items_request_id'), 'avizo_items', ['request_id'])
    op.create_index(op.f('ix_avizo_items_container_id'), 'avizo_items', ['container_id'])


def downgrade() -> None:
    op.drop_table('avizo_items')
    op.drop_table('avizo_requests')
    op.drop_column('warehouses', 'email')
