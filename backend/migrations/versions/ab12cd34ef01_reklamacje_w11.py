"""reklamacje W11: adresat/terminy, koszty, auto-szkic, checklista przyjęcia

Revision ID: ab12cd34ef01
Revises: b9c0d1e2f3a4
Create Date: 2026-09-18

Nowe kolumny `complaints`, wartość SZKIC w enumie statusu (Postgres)
i tabele checklisty kontroli przyjęcia.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'ab12cd34ef01'
down_revision: Union[str, Sequence[str], None] = 'b9c0d1e2f3a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name == 'postgresql':
        # SQLite trzyma enum jako VARCHAR — nowej wartości nie trzeba dodawać
        op.execute("ALTER TYPE complaintstatus ADD VALUE IF NOT EXISTS 'SZKIC'")
    op.add_column('complaints', sa.Column(
        'recipient_type', sa.String(length=20), nullable=False, server_default=''))
    op.add_column('complaints', sa.Column(
        'auto_draft', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index(op.f('ix_complaints_auto_draft'), 'complaints', ['auto_draft'])
    op.add_column('complaints', sa.Column(
        'claim_amount', sa.Numeric(14, 2), nullable=True))
    op.add_column('complaints', sa.Column(
        'recovered_amount', sa.Numeric(14, 2), nullable=True))
    op.add_column('complaints', sa.Column(
        'claim_currency', sa.String(length=3), nullable=False, server_default='PLN'))

    op.create_table(
        'checklist_points',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=160), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_table(
        'checklist_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('container_id', sa.Integer(), nullable=False),
        sa.Column('point_id', sa.Integer(), nullable=False),
        sa.Column('result', sa.String(length=10), nullable=False),
        sa.Column('note', sa.Text(), nullable=False),
        sa.Column('checked_by_id', sa.Integer(), nullable=True),
        sa.Column('checked_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['container_id'], ['containers.id']),
        sa.ForeignKeyConstraint(['point_id'], ['checklist_points.id']),
        sa.ForeignKeyConstraint(['checked_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('container_id', 'point_id'),
    )
    op.create_index(op.f('ix_checklist_results_container_id'),
                    'checklist_results', ['container_id'])


def downgrade() -> None:
    op.drop_table('checklist_results')
    op.drop_table('checklist_points')
    op.drop_column('complaints', 'claim_currency')
    op.drop_column('complaints', 'recovered_amount')
    op.drop_column('complaints', 'claim_amount')
    op.drop_index(op.f('ix_complaints_auto_draft'), table_name='complaints')
    op.drop_column('complaints', 'auto_draft')
    op.drop_column('complaints', 'recipient_type')
    # wartości enuma (SZKIC) w Postgresie nie da się usunąć bez przebudowy typu — zostaje
