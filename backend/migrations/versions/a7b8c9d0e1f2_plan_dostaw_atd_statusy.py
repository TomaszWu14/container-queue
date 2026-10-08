"""Plan dostaw (§10): containers.atd, containers.document_status, rozszerzenie customsstatus

Etap 7, część niezablokowana pytaniami biznesowymi:
- `atd` — rzeczywista data dostawy (ETA zostaje jako plan),
- `document_status` — obieg dokumentów (BRAK/ZALACZONE/WYSLANE), docelowo zastępuje
  luźne `documents_ok` + tekstowy `document_flow` (te zostają dla zgodności z importem),
- `customsstatus` += DRAFT_WYSLANY, DRAFT_POTWIERDZONY (etap zgłoszenia celnego,
  wstawiane między ZLECONA a ODPRAWIONY).

Revision ID: a7b8c9d0e1f2
Revises: f2a3b4c5d6e7
Create Date: 2026-07-22
"""
import sqlalchemy as sa
from alembic import op

revision = 'a7b8c9d0e1f2'
down_revision = 'f2a3b4c5d6e7'
branch_labels = None
depends_on = None

_DS_VALUES = ('BRAK', 'ZALACZONE', 'WYSLANE')


def upgrade() -> None:
    bind = op.get_bind()
    # 1) nowe wartości statusu odprawy — idempotentnie, w tej samej transakcji nieużywane
    #    (bezpieczne na PostgreSQL 12+; prod: PG16). AFTER ustawia kolejność w typie.
    if bind.dialect.name == 'postgresql':
        op.execute("ALTER TYPE customsstatus ADD VALUE IF NOT EXISTS "
                   "'DRAFT_WYSLANY' AFTER 'ZLECONA'")
        op.execute("ALTER TYPE customsstatus ADD VALUE IF NOT EXISTS "
                   "'DRAFT_POTWIERDZONY' AFTER 'DRAFT_WYSLANY'")

    # 2) status dokumentów — BRAK dla istniejących wierszy (bez fałszywego stanu obiegu)
    documentstatus = sa.Enum(*_DS_VALUES, name='documentstatus')
    documentstatus.create(bind, checkfirst=True)
    op.add_column('containers', sa.Column(
        'document_status', documentstatus, server_default='BRAK', nullable=False))

    # 3) ATD — pusty do czasu potwierdzenia dostawy
    op.add_column('containers', sa.Column('atd', sa.Date(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_column('containers', 'atd')
    op.drop_column('containers', 'document_status')
    sa.Enum(name='documentstatus').drop(bind, checkfirst=True)
    # Uwaga: PostgreSQL nie wspiera DROP VALUE dla enuma — DRAFT_* zostają w typie
    # `customsstatus` (usunięcie wymagałoby rekreacji typu). Nieszkodliwe.
