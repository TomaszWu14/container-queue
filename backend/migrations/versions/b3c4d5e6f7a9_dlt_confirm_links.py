"""Potwierdzenia DLT: tabela pallet_call_links + statusy przygotowane/wyslane_z_dlt.

Revision ID: b3c4d5e6f7a9
Revises: ab12cd34ef01
Create Date: 2026-09-18
"""
import sqlalchemy as sa
from alembic import op

revision = 'b3c4d5e6f7a9'
down_revision = 'ab12cd34ef01'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'pallet_call_links',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('token', sa.String(length=64), nullable=False),
        sa.Column('pallet_call_id', sa.Integer(),
                  sa.ForeignKey('pallet_calls.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('deactivated_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_pallet_call_links_token', 'pallet_call_links', ['token'],
                    unique=True)
    op.create_index('ix_pallet_call_links_pallet_call_id', 'pallet_call_links',
                    ['pallet_call_id'])
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        # ADD VALUE nie może działać w bloku transakcji; commit bieżącej transakcji
        op.execute('COMMIT')
        op.execute("ALTER TYPE palletcallstatus ADD VALUE IF NOT EXISTS 'przygotowane'")
        op.execute("ALTER TYPE palletcallstatus ADD VALUE IF NOT EXISTS 'wyslane_z_dlt'")
    # sqlite/inne: enum trzymany jako VARCHAR — brak zmiany schematu


def downgrade() -> None:
    op.drop_table('pallet_call_links')
    # PostgreSQL nie wspiera usuwania wartości z enum — no-op (bez utraty danych)
