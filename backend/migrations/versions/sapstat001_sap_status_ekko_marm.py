"""DATA-003 (wariant a): status SAP dla zamówień EKKO i jednostek MARM.

Rekord nieobecny w PEŁNYM eksporcie SAP → `sap_status = 'brak_w_sap'` (bez kasowania);
ponownie obecny → 'aktywny'.

Revision ID: sapstat001
Revises: dropcnt001
"""
import sqlalchemy as sa
from alembic import op

revision = "sapstat001"
down_revision = "dropcnt001"
branch_labels = None
depends_on = None

_TABLES = ("sap_orders", "material_units")


def upgrade() -> None:
    for table in _TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("sap_status", sa.String(20), nullable=False,
                                       server_default=sa.text("'aktywny'")))


def downgrade() -> None:
    for table in _TABLES:
        with op.batch_alter_table(table) as batch:
            batch.drop_column("sap_status")
