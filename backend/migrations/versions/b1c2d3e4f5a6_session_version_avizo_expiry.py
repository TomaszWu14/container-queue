"""wersja sesji (unieważnianie tokenów) + wygasanie linku awizacji

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f6
Create Date: 2026-07-08 15:45:00.000000

Migracja wstecznie kompatybilna: tylko dodanie kolumn (najpierw dodaj).
users.session_version — podbicie unieważnia wydane access tokeny (wylogowanie).
avizo_requests.expires_at — publiczny formularz awizacji przestaje działać po tym czasie.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('session_version', sa.Integer(), nullable=False,
                                     server_default='0'))
    op.add_column('avizo_requests', sa.Column('expires_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('avizo_requests', 'expires_at')
    op.drop_column('users', 'session_version')
