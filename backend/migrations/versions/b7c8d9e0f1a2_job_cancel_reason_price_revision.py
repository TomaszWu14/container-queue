"""wiersz 20-21: powód anulowania zlecenia + pilna zmiana ceny na ofercie

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
Create Date: 2026-07-10 11:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, Sequence[str], None] = 'a6b7c8d9e0f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # wiersz 20: anulowanie z podaniem powodu
    op.add_column('transport_jobs', sa.Column('cancel_reason', sa.Text(),
                                              nullable=False, server_default=''))
    op.add_column('transport_jobs', sa.Column('cancelled_at', sa.DateTime(), nullable=True))
    # wiersz 21: pilna zmiana ceny zgłoszona przez zwycięską spedycję
    op.add_column('quotes', sa.Column('revised_amount', sa.Numeric(12, 2), nullable=True))
    op.add_column('quotes', sa.Column('revised_note', sa.Text(),
                                      nullable=False, server_default=''))
    op.add_column('quotes', sa.Column('revised_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('quotes', 'revised_at')
    op.drop_column('quotes', 'revised_note')
    op.drop_column('quotes', 'revised_amount')
    op.drop_column('transport_jobs', 'cancelled_at')
    op.drop_column('transport_jobs', 'cancel_reason')
