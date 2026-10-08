"""zlecenia (Borealis/Cobalt): master data portów, typy kontenerów, kontakty dostawcy

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-07-09 19:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e4f5a6b7c8d9'
down_revision: Union[str, Sequence[str], None] = 'd3e4f5a6b7c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- master data portów ---
    op.add_column('ports', sa.Column('country', sa.String(length=2),
                                     nullable=False, server_default='CN'))
    op.add_column('ports', sa.Column('category', sa.String(length=9),
                                     nullable=False, server_default='OUT'))
    op.add_column('ports', sa.Column('transit_time_days', sa.Integer(), nullable=True))
    op.add_column('ports', sa.Column('transit_time_long_days', sa.Integer(), nullable=True))
    op.add_column('ports', sa.Column('is_active', sa.Boolean(create_constraint=False),
                                     nullable=False, server_default=sa.text('true')))

    # --- słownik typów kontenerów (z kubaturą) ---
    op.create_table(
        'container_types',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=40), nullable=False),
        sa.Column('inner_length_m', sa.Numeric(5, 2), nullable=True),
        sa.Column('inner_width_m', sa.Numeric(5, 2), nullable=True),
        sa.Column('inner_height_m', sa.Numeric(5, 2), nullable=True),
        sa.Column('max_payload_kg', sa.Integer(), nullable=True),
        sa.Column('teu', sa.Numeric(3, 1), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.UniqueConstraint('name'),
    )

    # --- słownik kontaktów u dostawcy ---
    op.create_table(
        'supplier_contacts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('supplier_id', sa.Integer(), sa.ForeignKey('suppliers.id'), nullable=False),
        sa.Column('full_name', sa.String(length=160), nullable=False),
        sa.Column('email', sa.String(length=200), nullable=False, server_default=''),
        sa.Column('phone', sa.String(length=60), nullable=False, server_default=''),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
    )
    op.create_index('ix_supplier_contacts_supplier_id', 'supplier_contacts', ['supplier_id'])

    # --- pola zlecenia na zamówieniu ---
    # kolumny FK dodajemy bez inline-constraintu — SQLite nie wspiera ALTER ADD CONSTRAINT,
    # a relacje ORM działają po stronie modelu (spójne z ensure_new_columns w devie)
    op.add_column('orders', sa.Column('supplier_contact_id', sa.Integer(), nullable=True))
    op.add_column('orders', sa.Column('departure_port_id', sa.Integer(), nullable=True))
    op.add_column('orders', sa.Column('container_type_id', sa.Integer(), nullable=True))
    op.add_column('orders', sa.Column('main_mode', sa.String(length=9), nullable=True))
    op.add_column('orders', sa.Column('sea_service', sa.String(length=9), nullable=True))
    op.add_column('orders', sa.Column('container_count', sa.Integer(),
                                      nullable=False, server_default='1'))
    op.add_column('orders', sa.Column('goods_type', sa.String(length=200),
                                      nullable=False, server_default=''))
    op.add_column('orders', sa.Column('is_adr', sa.Boolean(create_constraint=False),
                                      nullable=False, server_default=sa.text('false')))
    op.add_column('orders', sa.Column('goods_classification', sa.String(length=200),
                                      nullable=False, server_default=''))
    op.add_column('orders', sa.Column('goods_value', sa.Numeric(14, 2), nullable=True))
    op.add_column('orders', sa.Column('goods_currency', sa.String(length=3),
                                      nullable=False, server_default='USD'))
    op.add_column('orders', sa.Column('goods_weight', sa.String(length=60),
                                      nullable=False, server_default=''))
    op.add_column('orders', sa.Column('readiness_date', sa.Date(), nullable=True))
    op.add_column('orders', sa.Column('created_by_id', sa.Integer(), nullable=True))
    op.add_column('orders', sa.Column('created_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    for column in ('created_at', 'created_by_id', 'readiness_date', 'goods_weight',
                   'goods_currency', 'goods_value', 'goods_classification', 'is_adr',
                   'goods_type', 'container_count', 'sea_service', 'main_mode',
                   'container_type_id', 'departure_port_id', 'supplier_contact_id'):
        op.drop_column('orders', column)
    op.drop_index('ix_supplier_contacts_supplier_id', table_name='supplier_contacts')
    op.drop_table('supplier_contacts')
    op.drop_table('container_types')
    for column in ('is_active', 'transit_time_long_days', 'transit_time_days',
                   'category', 'country'):
        op.drop_column('ports', column)
