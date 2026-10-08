"""Kartoteka dostawców (PR1, spec 2026-09-25-kartoteka-dostawcy): suppliers globalne —
company_id → client_company_id (ustawione tylko dla nadawców spółek-klientów), pola SAP/mapy,
kontakty z rolą, supplier_materials (kopia supplier_material_maps jako unconfirmed), warianty
układu dokumentów, rozbudowa próbek, dziennik importów SAP.

Scalanie dubli NIE tutaj: podgląd + wykonanie w app/supplier_consolidation.py (ekran „Do
rozstrzygnięcia", scripts/consolidate_suppliers.py). Unikalności — kartoteka002 (etap B).

Revision ID: kartoteka001
Revises: dowoz001
"""
import datetime

import sqlalchemy as sa
from alembic import op

revision = "kartoteka001"
down_revision = "dowoz001"
branch_labels = None
depends_on = None

# spółki pracujące na materiałach Acme w chwili migracji (w aplikacji: settings.supplier_company_codes)
MATERIAL_CODES = ("ACME", "PT")


def upgrade() -> None:
    with op.batch_alter_table("suppliers") as b:
        b.add_column(sa.Column("client_company_id", sa.Integer, nullable=True))
        b.add_column(sa.Column("street", sa.String(160), nullable=False, server_default=""))
        b.add_column(sa.Column("city", sa.String(80), nullable=False, server_default=""))
        b.add_column(sa.Column("zip", sa.String(20), nullable=False, server_default=""))
        b.add_column(sa.Column("vat", sa.String(30), nullable=False, server_default=""))
        b.add_column(sa.Column("sap_status", sa.String(20), nullable=False, server_default="active"))
        b.add_column(sa.Column("lat", sa.Float, nullable=True))
        b.add_column(sa.Column("lng", sa.Float, nullable=True))
        b.add_column(sa.Column("geo_source", sa.String(10), nullable=False, server_default="none"))
        b.add_column(sa.Column("shipping_port_id", sa.Integer, nullable=True))
    # nadawcy spółek-klientów (Borealis, Cobalt…) zostają przy swojej spółce; reszta = kartoteka
    op.execute(sa.text(
        "UPDATE suppliers SET client_company_id = company_id WHERE company_id IN "
        "(SELECT id FROM companies WHERE code NOT IN :codes)"
    ).bindparams(sa.bindparam("codes", MATERIAL_CODES, expanding=True)))
    with op.batch_alter_table("suppliers") as b:
        # PG: DROP COLUMN zdejmuje też FK i unique(company_id, name); SQLite: batch przebudowuje
        # tabelę bez ograniczeń na usuniętej kolumnie. ix_suppliers_sap_code (c3f8a1d7e924) zostaje.
        b.drop_column("company_id")
        b.create_foreign_key("fk_suppliers_client_company_id", "companies",
                             ["client_company_id"], ["id"])
        b.create_foreign_key("fk_suppliers_shipping_port_id", "ports", ["shipping_port_id"], ["id"])
        b.create_index("ix_suppliers_client_company_id", ["client_company_id"])

    with op.batch_alter_table("supplier_contacts") as b:
        b.add_column(sa.Column("role", sa.String(20), nullable=False, server_default="other"))
        b.add_column(sa.Column("messenger", sa.String(120), nullable=False, server_default=""))
        b.add_column(sa.Column("is_primary", sa.Boolean, nullable=False, server_default=sa.false()))

    op.create_table(
        "supplier_materials",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("supplier_id", sa.Integer, sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("material_id", sa.Integer, sa.ForeignKey("materials.id"), nullable=False),
        sa.Column("supplier_code", sa.String(120), nullable=False, server_default=""),
        sa.Column("sap_status", sa.String(20), nullable=False, server_default=""),
        sa.Column("origin_country", sa.String(2), nullable=False, server_default=""),
        sa.Column("tariff_cn", sa.String(30), nullable=False, server_default=""),
        sa.Column("lead_days", sa.Integer, nullable=True),
        sa.Column("unconfirmed", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("supplier_id", "material_id",
                            name="uq_supplier_materials_supplier_material"),
    )
    op.create_index("ix_supplier_materials_supplier_code", "supplier_materials",
                    ["supplier_id", "supplier_code"])
    op.create_index("ix_supplier_materials_material_id", "supplier_materials", ["material_id"])
    copy_material_maps(op.get_bind())

    op.create_table(
        "supplier_doc_variants",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("profile_id", sa.Integer,
                  sa.ForeignKey("supplier_doc_profiles.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("doc_type", sa.String(4), nullable=False),
        sa.Column("fingerprint", sa.JSON, nullable=False),
        sa.Column("column_map", sa.JSON, nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="proposed"),
        sa.Column("docs_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("ok_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("ref_hit_pct", sa.Float, nullable=True),
        sa.Column("approved_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
    )
    with op.batch_alter_table("supplier_doc_samples") as b:
        b.add_column(sa.Column("sha256", sa.String(64), nullable=True))
        b.add_column(sa.Column("doc_type", sa.String(4), nullable=False, server_default=""))
        b.add_column(sa.Column("variant_id", sa.Integer, nullable=True))
        b.add_column(sa.Column("pages", sa.JSON, nullable=True))
        b.add_column(sa.Column("result", sa.JSON, nullable=True))
        b.add_column(sa.Column("status", sa.String(12), nullable=False, server_default="ok"))
        b.add_column(sa.Column("reason", sa.String(300), nullable=False, server_default=""))
    with op.batch_alter_table("supplier_doc_samples") as b:
        b.create_foreign_key("fk_supplier_doc_samples_variant_id", "supplier_doc_variants",
                             ["variant_id"], ["id"], ondelete="SET NULL")
        b.create_unique_constraint("uq_supplier_doc_samples_profile_sha", ["profile_id", "sha256"])

    op.create_table(
        "sap_imports",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False, server_default=""),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("counts", sa.JSON, nullable=False),
        sa.Column("errors", sa.JSON, nullable=False),
    )


def copy_material_maps(conn) -> int:
    """supplier_material_maps (per spółka, ref_code tekstem) → supplier_materials (per dostawca,
    material_id) ze znacznikiem unconfirmed. Idempotentne (PR2 ponawia przed przełączeniem
    dopasowania faktur); mapy bez materiału w master data zostają tylko w starej tabeli.
    Kolizja (dostawca, materiał) z kilku spółek/kodów → najmniejszy kod dostawcy."""
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    return conn.execute(sa.text(
        "INSERT INTO supplier_materials (supplier_id, material_id, supplier_code, sap_status, "
        "origin_country, tariff_cn, unconfirmed, created_at, updated_at) "
        "SELECT m.supplier_id, mat.id, MIN(m.supplier_code), '', '', '', :yes, :now, :now "
        "FROM supplier_material_maps m JOIN materials mat ON mat.ref_code = m.ref_code "
        "WHERE NOT EXISTS (SELECT 1 FROM supplier_materials sm "
        "WHERE sm.supplier_id = m.supplier_id AND sm.material_id = mat.id) "
        "GROUP BY m.supplier_id, mat.id"
    ).bindparams(yes=True, now=now)).rowcount


def downgrade() -> None:
    """Stratne: scalonych dostawców nie da się rozdzielić z powrotem na spółki — kartoteka
    wraca do spółki ACME, nadawcy klientów do swojej spółki (bez unique(company_id, name))."""
    op.drop_table("sap_imports")
    with op.batch_alter_table("supplier_doc_samples") as b:
        b.drop_constraint("uq_supplier_doc_samples_profile_sha", type_="unique")
        b.drop_constraint("fk_supplier_doc_samples_variant_id", type_="foreignkey")
        for col in ("reason", "status", "result", "pages", "variant_id", "doc_type", "sha256"):
            b.drop_column(col)
    op.drop_table("supplier_doc_variants")
    op.drop_table("supplier_materials")
    with op.batch_alter_table("supplier_contacts") as b:
        for col in ("is_primary", "messenger", "role"):
            b.drop_column(col)
    with op.batch_alter_table("suppliers") as b:
        b.add_column(sa.Column("company_id", sa.Integer, nullable=True))
    op.execute("UPDATE suppliers SET company_id = COALESCE(client_company_id, "
               "(SELECT id FROM companies WHERE code = 'ACME'))")
    with op.batch_alter_table("suppliers") as b:
        b.drop_index("ix_suppliers_client_company_id")
        b.drop_constraint("fk_suppliers_shipping_port_id", type_="foreignkey")
        b.drop_constraint("fk_suppliers_client_company_id", type_="foreignkey")
        for col in ("shipping_port_id", "geo_source", "lng", "lat", "sap_status", "vat", "zip",
                    "city", "street", "client_company_id"):
            b.drop_column(col)
        b.create_foreign_key("fk_suppliers_company_id", "companies", ["company_id"], ["id"])
