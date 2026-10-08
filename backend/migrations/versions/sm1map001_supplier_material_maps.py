"""supplier_material_maps — słownik: kod artykułu dostawcy → nasz ref_code (per spółka+dostawca)

Revision ID: sm1map001
Revises: t1flag001
Create Date: 2026-09-22
"""
import sqlalchemy as sa
from alembic import op

revision = "sm1map001"
down_revision = "t1flag001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "supplier_material_maps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("supplier_code", sa.String(120), nullable=False),
        sa.Column("ref_code", sa.String(120), nullable=False),
        sa.Column("note", sa.String(300), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("company_id", "supplier_id", "supplier_code"),
    )
    op.create_index("ix_supplier_material_maps_company_id", "supplier_material_maps", ["company_id"])
    op.create_index("ix_supplier_material_maps_supplier_id", "supplier_material_maps", ["supplier_id"])


def downgrade() -> None:
    op.drop_table("supplier_material_maps")
