"""portal klienta: klienci, linki klienckie, flaga dokumentu

Revision ID: d7e8f9a0b1c3
Revises: e6f1a2b3c4d5
Create Date: 2026-09-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd7e8f9a0b1c3'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(),
                  sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("contact", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_customers_company_id", "customers", ["company_id"])
    op.create_table(
        "customer_share_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("customer_id", sa.Integer(),
                  sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("created_by_id", sa.Integer(),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_customer_share_links_token",
                    "customer_share_links", ["token"], unique=True)
    op.create_index("ix_customer_share_links_customer_id",
                    "customer_share_links", ["customer_id"])
    op.add_column("containers", sa.Column(
        "customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True))
    op.create_index("ix_containers_customer_id", "containers", ["customer_id"])
    op.add_column("attachments", sa.Column(
        "client_visible", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("attachments", "client_visible")
    op.drop_index("ix_containers_customer_id", table_name="containers")
    op.drop_column("containers", "customer_id")
    op.drop_table("customer_share_links")
    op.drop_table("customers")
