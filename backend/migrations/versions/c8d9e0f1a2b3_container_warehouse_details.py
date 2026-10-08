"""faza 3 (DLT): szczegóły kontenera dla magazynu — lista materiałów, paletyzacja, ilość palet

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-07-10 11:40:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c8d9e0f1a2b3'
down_revision: Union[str, Sequence[str], None] = 'b7c8d9e0f1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('containers', sa.Column('materials_list', sa.Text(),
                                          nullable=False, server_default=''))
    op.add_column('containers', sa.Column('palletization_note', sa.Text(),
                                          nullable=False, server_default=''))
    op.add_column('containers', sa.Column('pallet_count', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('containers', 'pallet_count')
    op.drop_column('containers', 'palletization_note')
    op.drop_column('containers', 'materials_list')
