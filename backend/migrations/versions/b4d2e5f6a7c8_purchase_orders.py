"""purchase_orders — zamówienia zakupowe z arkusza ETD (wczesny etap przed kontenerem)

Revision ID: b4d2e5f6a7c8
Revises: a3c1d2e3f4a5
Create Date: 2026-09-11
"""
import sqlalchemy as sa
from alembic import op

revision = "b4d2e5f6a7c8"
down_revision = "a3c1d2e3f4a5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("order_no", sa.String(120), nullable=False),
        sa.Column("container_id", sa.Integer(), sa.ForeignKey("containers.id"), nullable=True),
        sa.Column("etd", sa.Date(), nullable=True),
        sa.Column("supplier", sa.String(160), nullable=False, server_default=""),
        sa.Column("pi_no", sa.String(120), nullable=False, server_default=""),
        sa.Column("products", sa.Text(), nullable=False, server_default=""),
        sa.Column("cbm", sa.Numeric(10, 3), nullable=True),
        sa.Column("tt_type", sa.String(40), nullable=False, server_default=""),
        sa.Column("transport_mode", sa.String(40), nullable=False, server_default=""),
        sa.Column("purchase_decision", sa.String(20), nullable=False, server_default=""),
        sa.Column("port_of_departure", sa.String(120), nullable=False, server_default=""),
        sa.Column("container_type", sa.String(40), nullable=False, server_default=""),
        sa.Column("expected_inland_charge", sa.String(80), nullable=False, server_default=""),
        sa.Column("amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("ready_date", sa.String(60), nullable=False, server_default=""),
        sa.Column("oem_sample_date", sa.String(60), nullable=False, server_default=""),
        sa.Column("shipper_contact", sa.String(200), nullable=False, server_default=""),
        sa.Column("consignee", sa.String(120), nullable=False, server_default=""),
        sa.Column("port_of_discharge", sa.String(120), nullable=False, server_default=""),
        sa.Column("forwarder", sa.String(160), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("company_id", "order_no"),
    )
    op.create_index("ix_purchase_orders_company_id", "purchase_orders", ["company_id"])
    op.create_index("ix_purchase_orders_order_no", "purchase_orders", ["order_no"])
    op.create_index("ix_purchase_orders_container_id", "purchase_orders", ["container_id"])


def downgrade() -> None:
    op.drop_table("purchase_orders")
