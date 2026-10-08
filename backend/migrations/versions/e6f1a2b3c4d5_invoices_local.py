"""Faktury → Excel lokalnie: master data materiałów, paczki/dokumenty/pozycje faktur (+ OCR, ML)

Zastępuje integrację HTTP z Compare (tabela compare_batches). Gotowe Excele ze starych
paczek zostają jako zwykłe załączniki kontenera — same paczki są tylko historią stanu
u operatora Compare i nie są przenoszone.

Revision ID: e6f1a2b3c4d5
Revises: d5a2b8e31c47
Create Date: 2026-09-17

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e6f1a2b3c4d5'
down_revision: Union[str, Sequence[str], None] = 'b7d4f2a91c05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DOC_KIND = sa.Enum('invoice', 'proforma', 'packing_list', 'other', name='invoicedockind')
JOB_STATUS = sa.Enum('uploaded', 'extracted', 'confirmed', 'error', 'packing_list', 'ignored',
                     name='invoicejobstatus')
MATCH_STATUS = sa.Enum('matched', 'ambiguous', 'unmatched', name='invoicematchstatus')


def upgrade() -> None:
    op.add_column('suppliers', sa.Column('column_map', sa.Text(), nullable=False,
                                         server_default=''))

    op.create_table(
        'materials',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('ref_code', sa.String(length=100), nullable=False, unique=True),
        sa.Column('ref_norm', sa.String(length=100), nullable=False, server_default=''),
        sa.Column('name_pl', sa.String(length=500), nullable=False, server_default=''),
        sa.Column('name_en', sa.String(length=500), nullable=False, server_default=''),
        sa.Column('ean', sa.String(length=14), nullable=False, server_default=''),
        sa.Column('family', sa.String(length=160), nullable=False, server_default=''),
        sa.Column('base_uom', sa.String(length=20), nullable=False, server_default=''),
        sa.Column('producer_code', sa.String(length=60), nullable=False, server_default=''),
        sa.Column('tariff_cn', sa.String(length=30), nullable=False, server_default=''),
        sa.Column('customs_code', sa.String(length=30), nullable=False, server_default=''),
        sa.Column('vat_rate', sa.String(length=10), nullable=False, server_default=''),
        sa.Column('sent', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('supplier_codes', sa.String(length=500), nullable=False, server_default=''),
        sa.Column('levels_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_materials_ref_norm', 'materials', ['ref_norm'])

    op.create_table(
        'material_overrides',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('material_id', sa.Integer(), sa.ForeignKey('materials.id'), nullable=False),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('name_pl', sa.String(length=500), nullable=False, server_default=''),
        sa.Column('tariff_cn', sa.String(length=30), nullable=False, server_default=''),
        sa.Column('customs_code', sa.String(length=30), nullable=False, server_default=''),
        sa.Column('base_uom', sa.String(length=20), nullable=False, server_default=''),
        sa.Column('sent', sa.Boolean(), nullable=True),
        sa.UniqueConstraint('material_id', 'company_id'),
    )
    op.create_index('ix_material_overrides_material_id', 'material_overrides', ['material_id'])
    op.create_index('ix_material_overrides_company_id', 'material_overrides', ['company_id'])

    op.create_table(
        'uom_conversions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('ref_norm', sa.String(length=100), nullable=False, server_default='*'),
        sa.Column('unit_from', sa.String(length=20), nullable=False),
        sa.Column('unit_to', sa.String(length=20), nullable=False),
        sa.Column('factor', sa.Numeric(14, 4), nullable=False),
        sa.UniqueConstraint('ref_norm', 'unit_from', 'unit_to'),
    )

    op.create_table(
        'invoice_batches',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('container_id', sa.Integer(), sa.ForeignKey('containers.id'), nullable=False),
        sa.Column('supplier_id', sa.Integer(), sa.ForeignKey('suppliers.id'), nullable=True),
        sa.Column('ready', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('attachment_id', sa.Integer(), sa.ForeignKey('attachments.id'), nullable=True),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_invoice_batches_container_id', 'invoice_batches', ['container_id'])

    op.create_table(
        'invoice_jobs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('batch_id', sa.Integer(), sa.ForeignKey('invoice_batches.id'), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('stored_name', sa.String(length=255), nullable=False),
        sa.Column('source_name', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('page_from', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('page_to', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('doc_kind', DOC_KIND, nullable=False),
        sa.Column('status', JOB_STATUS, nullable=False),
        sa.Column('error', sa.Text(), nullable=False, server_default=''),
        sa.Column('invoice_number', sa.String(length=80), nullable=False, server_default=''),
        sa.Column('container_no', sa.String(length=20), nullable=False, server_default=''),
        sa.Column('delivery_terms', sa.String(length=60), nullable=False, server_default=''),
        sa.Column('text_excerpt', sa.Text(), nullable=False, server_default=''),
        sa.Column('ocr_used', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_invoice_jobs_batch_id', 'invoice_jobs', ['batch_id'])

    op.create_table(
        'invoice_items',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('job_id', sa.Integer(), sa.ForeignKey('invoice_jobs.id'), nullable=False),
        sa.Column('line_no', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('raw_ref', sa.String(length=100), nullable=False, server_default=''),
        sa.Column('descr', sa.String(length=500), nullable=False, server_default=''),
        sa.Column('qty', sa.String(length=40), nullable=False, server_default=''),
        sa.Column('uom_src', sa.String(length=20), nullable=False, server_default=''),
        sa.Column('net_amount', sa.String(length=40), nullable=False, server_default=''),
        sa.Column('amount', sa.String(length=40), nullable=False, server_default=''),
        sa.Column('weight_net', sa.String(length=40), nullable=False, server_default=''),
        sa.Column('weight_gross', sa.String(length=40), nullable=False, server_default=''),
        sa.Column('cartons', sa.String(length=40), nullable=False, server_default=''),
        sa.Column('weight_source', sa.String(length=10), nullable=False, server_default=''),
        sa.Column('master_ref', sa.String(length=100), nullable=False, server_default=''),
        sa.Column('name_pl', sa.String(length=500), nullable=False, server_default=''),
        sa.Column('tariff_cn', sa.String(length=30), nullable=False, server_default=''),
        sa.Column('sent', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('uom_factor', sa.String(length=40), nullable=False, server_default=''),
        sa.Column('match_status', MATCH_STATUS, nullable=False),
        sa.Column('match_source', sa.String(length=10), nullable=False, server_default=''),
        sa.Column('ml_suggestion', sa.String(length=100), nullable=False, server_default=''),
        sa.Column('ml_confidence', sa.Numeric(5, 3), nullable=True),
        sa.Column('skipped', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index('ix_invoice_items_job_id', 'invoice_items', ['job_id'])

    # stara integracja HTTP z Compare — Excele zostały w attachments, sama paczka
    # to tylko stan „u operatora Compare”, który nie ma już źródła
    op.drop_index('ix_compare_batches_container_id', table_name='compare_batches')
    op.drop_table('compare_batches')


def downgrade() -> None:
    op.create_table(
        'compare_batches',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('container_id', sa.Integer(), sa.ForeignKey('containers.id'), nullable=False),
        sa.Column('batch_id', sa.String(length=64), nullable=False, unique=True),
        sa.Column('supplier_code', sa.String(length=40), nullable=False, server_default=''),
        sa.Column('total', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('confirmed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('errors', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('ready', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('jobs_json', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('attachment_id', sa.Integer(), sa.ForeignKey('attachments.id'), nullable=True),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_compare_batches_container_id', 'compare_batches', ['container_id'])

    op.drop_index('ix_invoice_items_job_id', table_name='invoice_items')
    op.drop_table('invoice_items')
    op.drop_index('ix_invoice_jobs_batch_id', table_name='invoice_jobs')
    op.drop_table('invoice_jobs')
    op.drop_index('ix_invoice_batches_container_id', table_name='invoice_batches')
    op.drop_table('invoice_batches')
    op.drop_table('uom_conversions')
    op.drop_index('ix_material_overrides_company_id', table_name='material_overrides')
    op.drop_index('ix_material_overrides_material_id', table_name='material_overrides')
    op.drop_table('material_overrides')
    op.drop_index('ix_materials_ref_norm', table_name='materials')
    op.drop_table('materials')
    bind = op.get_bind()
    for enum in (MATCH_STATUS, JOB_STATUS, DOC_KIND):
        enum.drop(bind, checkfirst=True)
    op.drop_column('suppliers', 'column_map')
