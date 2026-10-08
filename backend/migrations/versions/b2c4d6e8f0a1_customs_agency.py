"""Agencja celna: tabela customs_agencies + users.customs_agency_id + pola odprawy na kontenerze

Revision ID: b2c4d6e8f0a1
Revises: 7a3f9c1e0b52
Create Date: 2026-07-17
"""
import sqlalchemy as sa
from alembic import op

revision = 'b2c4d6e8f0a1'
down_revision = '7a3f9c1e0b52'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'customs_agencies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=160), nullable=False),
        sa.Column('email', sa.String(length=200), server_default='', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.add_column('users', sa.Column('customs_agency_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_users_customs_agency', 'users',
                          'customs_agencies', ['customs_agency_id'], ['id'])

    op.add_column('containers', sa.Column('customs_agency_id', sa.Integer(), nullable=True))
    op.add_column('containers', sa.Column(
        'customs_agent_name', sa.String(length=160), server_default='', nullable=False))
    op.add_column('containers', sa.Column(
        'customs_agent_phone', sa.String(length=40), server_default='', nullable=False))
    op.add_column('containers', sa.Column(
        'customs_agent_email', sa.String(length=160), server_default='', nullable=False))
    op.add_column('containers', sa.Column('customs_assigned_at', sa.DateTime(), nullable=True))
    op.create_index('ix_containers_customs_agency_id', 'containers', ['customs_agency_id'])
    op.create_foreign_key('fk_containers_customs_agency', 'containers',
                          'customs_agencies', ['customs_agency_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint('fk_containers_customs_agency', 'containers', type_='foreignkey')
    op.drop_index('ix_containers_customs_agency_id', table_name='containers')
    op.drop_column('containers', 'customs_assigned_at')
    op.drop_column('containers', 'customs_agent_email')
    op.drop_column('containers', 'customs_agent_phone')
    op.drop_column('containers', 'customs_agent_name')
    op.drop_column('containers', 'customs_agency_id')

    op.drop_constraint('fk_users_customs_agency', 'users', type_='foreignkey')
    op.drop_column('users', 'customs_agency_id')
    op.drop_table('customs_agencies')
