"""Noty eskalacyjne per spółka: knowledge_bulletins.company_id (NULL = cała grupa).

Istniejące noty zostają NULL — nikomu nic nie znika.

Revision ID: bull001
Revises: tile001
"""
import sqlalchemy as sa
from alembic import op

revision = "bull001"
down_revision = "tile001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("knowledge_bulletins") as b:
        b.add_column(sa.Column("company_id", sa.Integer, nullable=True))
        b.create_foreign_key("fk_knowledge_bulletins_company_id", "companies", ["company_id"], ["id"])
        b.create_index("ix_knowledge_bulletins_company_id", ["company_id"])


def downgrade() -> None:
    with op.batch_alter_table("knowledge_bulletins") as b:
        b.drop_index("ix_knowledge_bulletins_company_id")
        b.drop_constraint("fk_knowledge_bulletins_company_id", type_="foreignkey")
        b.drop_column("company_id")
