"""moduł reklamacyjny: problemy, reklamacje, zdjęcia, ustawienia

Revision ID: a1b2c3d4e5f6
Revises: f9a0b1c2d3e4
Create Date: 2026-07-08 12:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f9a0b1c2d3e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

KIND = sa.Enum('PROBLEM', 'REKLAMACJA', name='complaintkind')
STATUS = sa.Enum('NOWA', 'ZGLOSZONA', 'WYSLANA', 'ODPOWIEDZ', 'ZAMKNIETA',
                 name='complaintstatus')


def upgrade() -> None:
    op.create_table(
        'app_settings',
        sa.Column('key', sa.String(length=60), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('key'),
    )
    op.create_table(
        'problem_types',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=160), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_table(
        'complaints',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('number', sa.String(length=40), nullable=False),
        sa.Column('kind', KIND, nullable=False),
        sa.Column('status', STATUS, nullable=False),
        sa.Column('container_id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('driver_note', sa.Text(), nullable=False),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('reported_at', sa.DateTime(), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('sent_target', sa.String(length=200), nullable=False),
        sa.Column('response_at', sa.DateTime(), nullable=True),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        sa.Column('reminders_sent', sa.String(length=120), nullable=False),
        sa.ForeignKeyConstraint(['container_id'], ['containers.id']),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_complaints_number'), 'complaints', ['number'], unique=True)
    op.create_index(op.f('ix_complaints_container_id'), 'complaints', ['container_id'])
    op.create_index(op.f('ix_complaints_company_id'), 'complaints', ['company_id'])
    op.create_index(op.f('ix_complaints_status'), 'complaints', ['status'])
    op.create_index(op.f('ix_complaints_created_at'), 'complaints', ['created_at'])
    op.create_table(
        'complaint_problems',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('complaint_id', sa.Integer(), nullable=False),
        sa.Column('problem_type_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['complaint_id'], ['complaints.id']),
        sa.ForeignKeyConstraint(['problem_type_id'], ['problem_types.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_complaint_problems_complaint_id'), 'complaint_problems',
                    ['complaint_id'])
    op.create_table(
        'complaint_photos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('complaint_id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('stored_name', sa.String(length=255), nullable=False),
        sa.Column('content_type', sa.String(length=120), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('caption', sa.String(length=300), nullable=False),
        sa.Column('uploaded_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['complaint_id'], ['complaints.id']),
        sa.ForeignKeyConstraint(['uploaded_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stored_name'),
    )
    op.create_index(op.f('ix_complaint_photos_complaint_id'), 'complaint_photos',
                    ['complaint_id'])


def downgrade() -> None:
    op.drop_table('complaint_photos')
    op.drop_table('complaint_problems')
    op.drop_table('complaints')
    op.drop_table('problem_types')
    op.drop_table('app_settings')
    STATUS.drop(op.get_bind(), checkfirst=True)
    KIND.drop(op.get_bind(), checkfirst=True)
