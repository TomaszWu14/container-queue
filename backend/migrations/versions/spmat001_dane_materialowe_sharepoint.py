"""Dane materiałowe z SharePoint: arkusze pliku SAP_Dane_materiałowe.xlsm jako surowe tabele.

Revision ID: spmat001
Revises: marmean001
"""
import sqlalchemy as sa
from alembic import op

revision = "spmat001"
down_revision = "marmean001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sp_material_sheets",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(80), nullable=False, unique=True),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("headers", sa.JSON, nullable=False),
        sa.Column("row_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("filename", sa.String(255), nullable=False, server_default=""),
        sa.Column("imported_at", sa.DateTime, nullable=False),
        sa.Column("imported_by_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_table(
        "sp_material_rows",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("sheet_id", sa.Integer,
                  sa.ForeignKey("sp_material_sheets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("row_no", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cells", sa.JSON, nullable=False),
        sa.Column("search", sa.String(2000), nullable=False, server_default=""),
    )
    op.create_index("ix_sp_material_rows_sheet_id", "sp_material_rows", ["sheet_id"])


def downgrade() -> None:
    op.drop_index("ix_sp_material_rows_sheet_id", table_name="sp_material_rows")
    op.drop_table("sp_material_rows")
    op.drop_table("sp_material_sheets")
