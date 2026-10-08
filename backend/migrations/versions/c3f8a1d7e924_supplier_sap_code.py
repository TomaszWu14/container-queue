"""dostawcy: kod SAP (LIFNR) i kraj — pod import słownika LFA1

Revision ID: c3f8a1d7e924
Revises: b7e1a9c3d5f2
Create Date: 2026-09-17

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3f8a1d7e924'
down_revision: Union[str, Sequence[str], None] = 'b7e1a9c3d5f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('suppliers', sa.Column('sap_code', sa.String(20),
                                         nullable=False, server_default=''))
    op.add_column('suppliers', sa.Column('country', sa.String(2),
                                         nullable=False, server_default=''))
    op.create_index('ix_suppliers_sap_code', 'suppliers', ['sap_code'])


def downgrade() -> None:
    op.drop_index('ix_suppliers_sap_code', table_name='suppliers')
    op.drop_column('suppliers', 'country')
    op.drop_column('suppliers', 'sap_code')
