"""Front-half: pola CRD/koszyk na zamowieniu + stan konsolidacji na kontenerze.

Revision ID: frontmodel001
Revises: care001
Create Date: 2026-09-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'frontmodel001'
down_revision: Union[str, Sequence[str], None] = 'care001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('purchase_orders', sa.Column('crd', sa.Date(), nullable=True))
    op.add_column('purchase_orders', sa.Column('crd_target', sa.Date(), nullable=True))
    op.add_column('purchase_orders', sa.Column(
        'cart_status', sa.String(length=20), nullable=False, server_default='w_koszyku'))
    op.add_column('containers', sa.Column(
        'consolidation_status', sa.String(length=20), nullable=False, server_default='otwarty'))
    op.add_column('containers', sa.Column(
        'capacity_cbm', sa.Numeric(10, 3), nullable=False, server_default='70'))


def downgrade() -> None:
    op.drop_column('containers', 'capacity_cbm')
    op.drop_column('containers', 'consolidation_status')
    op.drop_column('purchase_orders', 'cart_status')
    op.drop_column('purchase_orders', 'crd_target')
    op.drop_column('purchase_orders', 'crd')
