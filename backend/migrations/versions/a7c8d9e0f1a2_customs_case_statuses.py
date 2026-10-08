"""Słownik statusów sprawy celnej (panel admina) + containers.customs_case_status_id

Nowa tabela customs_case_statuses (name/sort_order/is_active, wzór ProblemType)
i nullable FK na kontenerze — istniejące rekordy zostają bez statusu sprawy.

Revision ID: a7c8d9e0f1a2
Revises: f7a8b9c0d1e2
Create Date: 2026-09-01
"""
import sqlalchemy as sa
from alembic import op

revision = 'a7c8d9e0f1a2'
down_revision = 'f7a8b9c0d1e2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'customs_case_statuses',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(160), nullable=False, unique=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column('containers', sa.Column(
        'customs_case_status_id', sa.Integer(),
        sa.ForeignKey('customs_case_statuses.id'), nullable=True))
    op.create_index('ix_containers_customs_case_status_id', 'containers',
                    ['customs_case_status_id'])


def downgrade() -> None:
    op.drop_index('ix_containers_customs_case_status_id', table_name='containers')
    op.drop_column('containers', 'customs_case_status_id')
    op.drop_table('customs_case_statuses')
