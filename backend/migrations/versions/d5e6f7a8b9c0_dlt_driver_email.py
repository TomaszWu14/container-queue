"""panel DLT, dane kierowców, e-mail spedytora

Revision ID: d5e6f7a8b9c0
Revises: c3d4e5f6a7b8
Create Date: 2026-07-08 09:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('warehouse_id', sa.Integer(),
                                     sa.ForeignKey('warehouses.id'), nullable=True))
    op.add_column('forwarders', sa.Column('email', sa.String(length=200),
                                          nullable=False, server_default=''))
    for name, length in (('driver_name', 160), ('driver_id_no', 60),
                         ('truck_no', 40), ('trailer_no', 40), ('driver_phone', 40)):
        op.add_column('containers', sa.Column(name, sa.String(length=length),
                                              nullable=False, server_default=''))


def downgrade() -> None:
    for name in ('driver_phone', 'trailer_no', 'truck_no', 'driver_id_no', 'driver_name'):
        op.drop_column('containers', name)
    op.drop_column('forwarders', 'email')
    op.drop_column('users', 'warehouse_id')
