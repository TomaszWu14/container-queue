"""W14 bezpieczeństwo: 2FA TOTP, uprawnienia per magazyn, błędy klienta, BlockedIP.

Revision ID: w14sec2fa001
Revises: a9b8c7d6e5f4
Create Date: 2026-09-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'w14sec2fa001'
down_revision: Union[str, Sequence[str], None] = 'b1a2c3d4e5a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('totp_secret', sa.String(length=64), nullable=True))
    op.add_column('users', sa.Column('totp_backup_codes', sa.Text(),
                                     nullable=False, server_default=''))
    op.add_column('users', sa.Column('allowed_warehouse_ids', sa.JSON(), nullable=True))
    op.create_table(
        'client_errors',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('stack', sa.Text(), nullable=False),
        sa.Column('url', sa.String(length=500), nullable=False),
        sa.Column('user_agent', sa.String(length=300), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_client_errors_created_at', 'client_errors', ['created_at'])
    op.create_table(
        'blocked_ips',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('ip', sa.String(length=64), nullable=False),
        sa.Column('note', sa.String(length=300), nullable=False),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_blocked_ips_ip', 'blocked_ips', ['ip'], unique=True)


def downgrade() -> None:
    op.drop_table('blocked_ips')
    op.drop_table('client_errors')
    op.drop_column('users', 'allowed_warehouse_ids')
    op.drop_column('users', 'totp_backup_codes')
    op.drop_column('users', 'totp_secret')
