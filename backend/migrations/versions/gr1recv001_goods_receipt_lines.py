"""goods_receipt_lines — przyjęcie zakupowe per pozycja zamówienia (zamówiono→przyjęto)

Revision ID: gr1recv001
Revises: sm1map001
Create Date: 2026-09-22
"""
import sqlalchemy as sa
from alembic import op

revision = "gr1recv001"
down_revision = "sm1map001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "goods_receipt_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("container_id", sa.Integer(), sa.ForeignKey("containers.id"), nullable=False),
        sa.Column("order_number", sa.String(60), nullable=False),
        sa.Column("position", sa.String(20), nullable=False, server_default=""),
        sa.Column("material", sa.String(120), nullable=False, server_default=""),
        sa.Column("qty_received", sa.String(40), nullable=False, server_default=""),
        sa.Column("received_at", sa.Date(), nullable=True),
        sa.Column("note", sa.String(300), nullable=False, server_default=""),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("company_id", "container_id", "order_number", "position"),
    )
    op.create_index("ix_goods_receipt_lines_company_id", "goods_receipt_lines", ["company_id"])
    op.create_index("ix_goods_receipt_lines_container_id", "goods_receipt_lines", ["container_id"])
    op.create_index("ix_goods_receipt_lines_order_number", "goods_receipt_lines", ["order_number"])


def downgrade() -> None:
    op.drop_table("goods_receipt_lines")
