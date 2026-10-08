"""sap_orders — nagłówki zamówień zakupu z eksportu SAP (EKKO)

Revision ID: d5a2b8e31c47
Revises: a1c7d4e90b26
Create Date: 2026-09-17

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd5a2b8e31c47'
down_revision: Union[str, Sequence[str], None] = 'a1c7d4e90b26'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sap_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("order_number", sa.String(60), nullable=False),
        sa.Column("container_id", sa.Integer(), sa.ForeignKey("containers.id"), nullable=True),
        sa.Column("doc_kind", sa.String(10), nullable=False, server_default=""),
        sa.Column("supplier_sap", sa.String(20), nullable=False, server_default=""),
        sa.Column("buyer", sa.String(40), nullable=False, server_default=""),
        sa.Column("buyer_group", sa.String(10), nullable=False, server_default=""),
        sa.Column("payment_terms", sa.String(20), nullable=False, server_default=""),
        sa.Column("payment_days", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default=""),
        sa.Column("fx_rate", sa.Numeric(12, 5), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("incoterms", sa.String(10), nullable=False, server_default=""),
        sa.Column("incoterms_place", sa.String(60), nullable=False, server_default=""),
        sa.Column("doc_date", sa.Date(), nullable=True),
        sa.Column("delivery_date", sa.Date(), nullable=True),
        sa.Column("required_ship_date", sa.Date(), nullable=True),
        sa.Column("planned_ship_date", sa.Date(), nullable=True),
        sa.Column("supplier_order_no", sa.String(60), nullable=False, server_default=""),
        sa.Column("is_asap", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("supplier_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("artwork_approved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("imported_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("company_id", "order_number", name="uq_sap_orders_company_order"),
    )
    op.create_index("ix_sap_orders_company_id", "sap_orders", ["company_id"])
    op.create_index("ix_sap_orders_order_number", "sap_orders", ["order_number"])
    op.create_index("ix_sap_orders_container_id", "sap_orders", ["container_id"])
    op.create_index("ix_sap_orders_supplier_sap", "sap_orders", ["supplier_sap"])


def downgrade() -> None:
    op.drop_table("sap_orders")
