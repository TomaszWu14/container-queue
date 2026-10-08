"""Nazwa dostawcy z pliku kolejki (containers.supplier_raw) + aliasy nazw → dostawca
(supplier_aliases). Import kolejki przestaje tworzyć dostawców. Backfill: supplier_raw =
nazwa przypiętego dostawcy, żeby istniejące kontenery nie straciły nazwy.

Revision ID: dostalias001
Revises: profil001
"""
import sqlalchemy as sa
from alembic import op

revision = "dostalias001"
down_revision = "profil001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("containers") as batch:
        batch.add_column(sa.Column("supplier_raw", sa.String(160), nullable=False,
                                   server_default=sa.text("''")))
    op.execute("UPDATE containers SET supplier_raw = (SELECT name FROM suppliers "
               "WHERE suppliers.id = containers.supplier_id) WHERE supplier_id IS NOT NULL")
    op.create_table(
        "supplier_aliases",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("alias_norm", sa.String(160), nullable=False),
        sa.Column("alias", sa.String(160), nullable=False),
        sa.Column("supplier_id", sa.Integer,
                  sa.ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("company_id", "alias_norm"),
    )
    op.create_index("ix_supplier_aliases_company_id", "supplier_aliases", ["company_id"])
    op.create_index("ix_supplier_aliases_supplier_id", "supplier_aliases", ["supplier_id"])


def downgrade() -> None:
    op.drop_table("supplier_aliases")
    with op.batch_alter_table("containers") as batch:
        batch.drop_column("supplier_raw")
