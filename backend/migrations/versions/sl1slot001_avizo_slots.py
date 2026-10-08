"""avizo slots — okna rozładunku magazynu + zarezerwowany slot kontenera (#13)

Revision ID: sl1slot001
Revises: fi1appr001
Create Date: 2026-09-23
"""
import sqlalchemy as sa
from alembic import op

revision = "sl1slot001"
down_revision = "fi1appr001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("warehouses",
                  sa.Column("slot_windows", sa.String(200), nullable=False, server_default=""))
    op.add_column("warehouses",
                  sa.Column("slot_capacity", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("containers",
                  sa.Column("slot_time", sa.String(5), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("containers", "slot_time")
    op.drop_column("warehouses", "slot_capacity")
    op.drop_column("warehouses", "slot_windows")
