"""Wymagane dokumenty per dostawca (spec 2026-10-06 decyzja 16): supplier_doc_profiles.required_docs.

Revision ID: reqdoc001
Revises: link001
"""
import sqlalchemy as sa
from alembic import op

revision = "reqdoc001"
down_revision = "link001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("supplier_doc_profiles") as batch:
        batch.add_column(sa.Column("required_docs", sa.JSON, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("supplier_doc_profiles") as batch:
        batch.drop_column("required_docs")
