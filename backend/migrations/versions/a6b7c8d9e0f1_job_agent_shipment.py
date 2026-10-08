"""wiersz 16-18: numer przesyłki + dane agenta na zleceniu transportowym

Revision ID: a6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-07-10 08:10:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a6b7c8d9e0f1'
down_revision: Union[str, Sequence[str], None] = 'f5a6b7c8d9e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('transport_jobs', sa.Column('shipment_number', sa.String(length=80),
                                              nullable=False, server_default=''))
    op.add_column('transport_jobs', sa.Column('agent_name', sa.String(length=160),
                                              nullable=False, server_default=''))
    op.add_column('transport_jobs', sa.Column('agent_phone', sa.String(length=60),
                                              nullable=False, server_default=''))
    op.add_column('transport_jobs', sa.Column('agent_company', sa.String(length=160),
                                              nullable=False, server_default=''))
    op.add_column('transport_jobs', sa.Column('agent_submitted_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    for column in ('agent_submitted_at', 'agent_company', 'agent_phone', 'agent_name',
                   'shipment_number'):
        op.drop_column('transport_jobs', column)
