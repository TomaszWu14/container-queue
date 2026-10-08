"""dane klienta docelowego kontenera tranzytowego (customer_name/address/contact)

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-09-02 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, Sequence[str], None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('containers', sa.Column('customer_name', sa.String(), nullable=False, server_default=''))
    op.add_column('containers', sa.Column('customer_address', sa.String(), nullable=False, server_default=''))
    op.add_column('containers', sa.Column('customer_contact', sa.String(), nullable=False, server_default=''))


def downgrade() -> None:
    op.drop_column('containers', 'customer_contact')
    op.drop_column('containers', 'customer_address')
    op.drop_column('containers', 'customer_name')
