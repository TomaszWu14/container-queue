"""wycena v2: dane oferty (armator/ETD/ETA/transit/flagi) + termin odpowiedzi i SCFI

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-07-09 22:10:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f5a6b7c8d9e0'
down_revision: Union[str, Sequence[str], None] = 'e4f5a6b7c8d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- oferta spedytora ---
    op.add_column('quotes', sa.Column('carrier_id', sa.Integer(), nullable=True))
    op.add_column('quotes', sa.Column('etd', sa.Date(), nullable=True))
    op.add_column('quotes', sa.Column('eta', sa.Date(), nullable=True))
    op.add_column('quotes', sa.Column('transit_time_days', sa.Integer(), nullable=True))
    op.add_column('quotes', sa.Column('no_equipment', sa.Boolean(create_constraint=False),
                                      nullable=False, server_default=sa.text('false')))
    op.add_column('quotes', sa.Column('can_roll_booking', sa.Boolean(create_constraint=False),
                                      nullable=False, server_default=sa.text('false')))

    # --- zlecenie transportowe: termin odpowiedzi + indeks SCFI ---
    op.add_column('transport_jobs', sa.Column('response_hours', sa.Integer(),
                                              nullable=False, server_default='24'))
    op.add_column('transport_jobs', sa.Column('response_deadline', sa.DateTime(), nullable=True))
    op.add_column('transport_jobs', sa.Column('scfi_index', sa.String(length=60),
                                              nullable=False, server_default=''))


def downgrade() -> None:
    for column in ('scfi_index', 'response_deadline', 'response_hours'):
        op.drop_column('transport_jobs', column)
    for column in ('can_roll_booking', 'no_equipment', 'transit_time_days', 'eta', 'etd',
                   'carrier_id'):
        op.drop_column('quotes', column)
