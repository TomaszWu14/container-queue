"""zlecenia transportowe (paczki) i wyceny spedycji (RFQ)

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-07-09 15:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd3e4f5a6b7c8'
down_revision: Union[str, Sequence[str], None] = 'c2d3e4f5a6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JOB_STATUS = sa.Enum('SZKIC', 'WYSLANE', 'ZLECONE', 'ANULOWANE', name='transportjobstatus')
QUOTE_STATUS = sa.Enum('ZAPYTANIE', 'WYCENIONA', 'WYBRANA', 'ODRZUCONA', name='quotestatus')


def upgrade() -> None:
    op.create_table(
        'transport_jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('number', sa.String(length=40), nullable=False),
        sa.Column('status', JOB_STATUS, nullable=False),
        sa.Column('pickup_location', sa.String(length=200), nullable=False),
        sa.Column('delivery_location', sa.String(length=200), nullable=False),
        sa.Column('note', sa.Text(), nullable=False),
        sa.Column('chosen_quote_id', sa.Integer(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_transport_jobs_number'), 'transport_jobs', ['number'], unique=True)
    op.create_index(op.f('ix_transport_jobs_status'), 'transport_jobs', ['status'])

    op.create_table(
        'quotes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False),
        sa.Column('forwarder_id', sa.Integer(), nullable=False),
        sa.Column('status', QUOTE_STATUS, nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('valid_until', sa.Date(), nullable=True),
        sa.Column('note', sa.Text(), nullable=False),
        sa.Column('submitted_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['transport_jobs.id']),
        sa.ForeignKeyConstraint(['forwarder_id'], ['forwarders.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id', 'forwarder_id'),
    )
    op.create_index(op.f('ix_quotes_job_id'), 'quotes', ['job_id'])
    op.create_index(op.f('ix_quotes_forwarder_id'), 'quotes', ['forwarder_id'])
    op.create_index(op.f('ix_quotes_status'), 'quotes', ['status'])
    op.create_foreign_key('fk_job_chosen_quote', 'transport_jobs', 'quotes',
                          ['chosen_quote_id'], ['id'])

    op.create_table(
        'transport_job_containers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.Integer(), nullable=False),
        sa.Column('container_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['transport_jobs.id']),
        sa.ForeignKeyConstraint(['container_id'], ['containers.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id', 'container_id'),
    )
    op.create_index(op.f('ix_transport_job_containers_job_id'),
                    'transport_job_containers', ['job_id'])
    op.create_index(op.f('ix_transport_job_containers_container_id'),
                    'transport_job_containers', ['container_id'])


def downgrade() -> None:
    op.drop_table('transport_job_containers')
    op.drop_constraint('fk_job_chosen_quote', 'transport_jobs', type_='foreignkey')
    op.drop_table('quotes')
    op.drop_table('transport_jobs')
    QUOTE_STATUS.drop(op.get_bind(), checkfirst=True)
    JOB_STATUS.drop(op.get_bind(), checkfirst=True)
