"""cykl planowania dostawy: planning_status + pola towarzyszące

Revision ID: b8c9d0e1f2a3
Revises: a2c3d4e5f6b7
Create Date: 2026-09-02 13:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, Sequence[str], None] = 'a2c3d4e5f6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_PS_VALUES = ('PROPOZYCJA', 'WYSLANE', 'POTWIERDZONE')


def upgrade() -> None:
    # Postgres wymaga jawnego utworzenia typu enum przed add_column
    # (wzorzec jak w f2a3b4c5d6e7/a7b8c9d0e1f2; na SQLite checkfirst=no-op)
    planningstatus = sa.Enum(*_PS_VALUES, name='planningstatus')
    planningstatus.create(op.get_bind(), checkfirst=True)
    op.add_column('containers', sa.Column(
        'planning_status', planningstatus,
        nullable=False, server_default='PROPOZYCJA'))
    op.create_index('ix_containers_planning_status', 'containers', ['planning_status'])
    op.add_column('containers', sa.Column('notify_date_manual', sa.Boolean(),
                                          nullable=False, server_default=sa.false()))
    op.add_column('containers', sa.Column('planning_sent_at', sa.DateTime(), nullable=True))
    op.add_column('containers', sa.Column('planning_confirmed_at', sa.DateTime(), nullable=True))
    op.add_column('containers', sa.Column('planning_confirmed_by_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_containers_planning_confirmed_by', 'containers', 'users',
                          ['planning_confirmed_by_id'], ['id'])
    op.add_column('containers', sa.Column('planning_eta_at_send', sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_constraint('fk_containers_planning_confirmed_by', 'containers', type_='foreignkey')
    op.drop_column('containers', 'planning_eta_at_send')
    op.drop_column('containers', 'planning_confirmed_by_id')
    op.drop_column('containers', 'planning_confirmed_at')
    op.drop_column('containers', 'planning_sent_at')
    op.drop_column('containers', 'notify_date_manual')
    op.drop_index('ix_containers_planning_status', table_name='containers')
    op.drop_column('containers', 'planning_status')
    sa.Enum(name='planningstatus').drop(op.get_bind(), checkfirst=True)
