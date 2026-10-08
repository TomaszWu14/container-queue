"""DATA-006: usuń martwe liczniki supplier_doc_variants.docs_count/ok_count.

Nikt ich nie zapisywał ani nie czytał (zawsze 0); model ORM już ich nie ma.

Revision ID: dropcnt001
Revises: trgm002
"""
import sqlalchemy as sa
from alembic import op

revision = "dropcnt001"
down_revision = "trgm002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("supplier_doc_variants") as batch:
        batch.drop_column("docs_count")
        batch.drop_column("ok_count")


def downgrade() -> None:
    with op.batch_alter_table("supplier_doc_variants") as batch:
        batch.add_column(sa.Column("docs_count", sa.Integer, nullable=False, server_default="0"))
        batch.add_column(sa.Column("ok_count", sa.Integer, nullable=False, server_default="0"))
