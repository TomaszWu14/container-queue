"""Dział zakupów: rola `purchasing` + kolumna containers.purchasing_status

Dodaje wartość 'purchasing' do enuma `role` oraz nowy typ `purchasingstatus`
i kolumnę `containers.purchasing_status` (domyślnie BRAK, jak customs_status —
istniejące rekordy nie zyskują fałszywego stanu obiegu zakupowego).

Revision ID: f2a3b4c5d6e7
Revises: d1e2f3a4b5c6
Create Date: 2026-07-21
"""
import sqlalchemy as sa
from alembic import op

revision = 'f2a3b4c5d6e7'
down_revision = 'd1e2f3a4b5c6'
branch_labels = None
depends_on = None

_PS_VALUES = ('BRAK', 'DO_ZAMOWIENIA', 'ZAMOWIONE', 'POTWIERDZONE',
              'ZREALIZOWANE', 'WSTRZYMANE')


def upgrade() -> None:
    bind = op.get_bind()
    # 1) nowa wartość roli — idempotentnie; nie jest używana w tej samej transakcji,
    #    więc jest bezpieczna na PostgreSQL 12+ (prod: PG16).
    if bind.dialect.name == 'postgresql':
        op.execute("ALTER TYPE role ADD VALUE IF NOT EXISTS 'purchasing'")

    # 2) nowy typ enum + kolumna statusu zakupów (BRAK dla istniejących wierszy)
    purchasingstatus = sa.Enum(*_PS_VALUES, name='purchasingstatus')
    purchasingstatus.create(bind, checkfirst=True)
    op.add_column('containers', sa.Column(
        'purchasing_status', purchasingstatus,
        server_default='BRAK', nullable=False))


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_column('containers', 'purchasing_status')
    sa.Enum(name='purchasingstatus').drop(bind, checkfirst=True)
    # Uwaga: PostgreSQL nie wspiera DROP VALUE dla enuma — wartość 'purchasing'
    # w typie `role` pozostaje (usunięcie wymagałoby rekreacji typu). Nieszkodliwe.
