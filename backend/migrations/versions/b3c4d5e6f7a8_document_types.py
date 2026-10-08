"""Słownik typów dokumentów (checklista kompletności) + attachments.document_type_id

Nowa tabela document_types (name/sort_order/is_active/is_required) i nullable FK
na załączniku — istniejące pliki zostają bez typu.

Revision ID: b3c4d5e6f7a8
Revises: a7c8d9e0f1a2
Create Date: 2026-09-01
"""
import sqlalchemy as sa
from alembic import op

revision = 'b3c4d5e6f7a8'
down_revision = 'a7c8d9e0f1a2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'document_types',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(160), nullable=False, unique=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('is_required', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column('attachments', sa.Column(
        'document_type_id', sa.Integer(),
        sa.ForeignKey('document_types.id'), nullable=True))
    op.create_index('ix_attachments_document_type_id', 'attachments', ['document_type_id'])


def downgrade() -> None:
    op.drop_index('ix_attachments_document_type_id', table_name='attachments')
    op.drop_column('attachments', 'document_type_id')
    op.drop_table('document_types')
