"""master dict contact fields (forwarders/customs_agencies/suppliers)

Revision ID: c1d2e3f4a5b6
Revises: b4c5d6e7f8a9
Create Date: 2026-09-06 21:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, Sequence[str], None] = 'b4c5d6e7f8a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CONTACT = [
    ('contact_person', sa.String(length=160)),
    ('contact_phone', sa.String(length=60)),
    ('address', sa.String(length=300)),
    ('note', sa.Text()),
]


def upgrade() -> None:
    for table in ('forwarders', 'customs_agencies'):
        for name, coltype in _CONTACT:
            op.add_column(table, sa.Column(name, coltype, nullable=False, server_default=''))
    # dostawcy: tylko dane organizacyjne (kontakty osobowe są w supplier_contacts)
    op.add_column('suppliers', sa.Column('address', sa.String(length=300),
                                         nullable=False, server_default=''))
    op.add_column('suppliers', sa.Column('note', sa.Text(), nullable=False, server_default=''))


def downgrade() -> None:
    op.drop_column('suppliers', 'note')
    op.drop_column('suppliers', 'address')
    for table in ('customs_agencies', 'forwarders'):
        for name, _ in reversed(_CONTACT):
            op.drop_column(table, name)
