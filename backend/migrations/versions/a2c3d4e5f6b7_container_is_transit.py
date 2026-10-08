"""kontenery tranzytowe: flaga is_transit

Revision ID: a2c3d4e5f6b7
Revises: d6e7f8a9b0c1
Create Date: 2026-09-02 11:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a2c3d4e5f6b7'
down_revision: Union[str, Sequence[str], None] = 'd6e7f8a9b0c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('containers', sa.Column('is_transit', sa.Boolean(),
                                          nullable=False, server_default=sa.false()))
    op.create_index('ix_containers_is_transit', 'containers', ['is_transit'])


def downgrade() -> None:
    op.drop_index('ix_containers_is_transit', table_name='containers')
    op.drop_column('containers', 'is_transit')
