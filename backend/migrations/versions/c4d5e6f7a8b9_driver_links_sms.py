"""Łącznik kierowcy: driver_links + sms_messages + dane magazynu dla kierowcy

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-09-01
"""
import sqlalchemy as sa
from alembic import op

revision = 'c4d5e6f7a8b9'
down_revision = 'b3c4d5e6f7a8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'driver_links',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('token', sa.String(64), nullable=False, unique=True, index=True),
        sa.Column('container_id', sa.Integer(),
                  sa.ForeignKey('containers.id'), nullable=False, index=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('deactivated_at', sa.DateTime(), nullable=True),
    )
    op.create_table(
        'sms_messages',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('container_id', sa.Integer(),
                  sa.ForeignKey('containers.id'), nullable=False, index=True),
        sa.Column('phone', sa.String(40), nullable=False),
        sa.Column('body', sa.Text(), nullable=False, server_default=''),
        sa.Column('status', sa.String(20), nullable=False, server_default='sent'),
        sa.Column('error', sa.String(300), nullable=False, server_default=''),
        sa.Column('delivery_date', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.add_column('warehouses', sa.Column('address', sa.String(300),
                                          nullable=False, server_default=''))
    op.add_column('warehouses', sa.Column('contact_phone', sa.String(40),
                                          nullable=False, server_default=''))
    op.add_column('warehouses', sa.Column('entry_instructions', sa.Text(),
                                          nullable=False, server_default=''))


def downgrade() -> None:
    op.drop_column('warehouses', 'entry_instructions')
    op.drop_column('warehouses', 'contact_phone')
    op.drop_column('warehouses', 'address')
    op.drop_table('sms_messages')
    op.drop_table('driver_links')
