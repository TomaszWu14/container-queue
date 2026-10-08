"""DB-003: zmniejszenie dryfu modele ↔ migracje (scripts/db_drift_baseline.txt).

Prod (PostgreSQL) był częściowo budowany przez `create_all` w bootstrapie, więc część
obiektów może już istnieć, a świeże `alembic upgrade head` ich nie ma. Każdy krok jest
idempotentny (sprawdza stan przez inspektor) i bezpieczny dla danych:
  - material_issues + indeksy: tylko gdy brak,
  - FK: najpierw osierocone odwołania → NULL (kolumny są nullable), potem FK, jeśli brak,
  - created_at/updated_at NOT NULL: najpierw NULL → druga data albo now(),
  - unique: constraint `<tab>_<kol>_key` → unikalny indeks `ix_…` (jak w modelu); duplikatów
    nie ma (pilnował ich constraint); gdy nie było żadnej ochrony i są duplikaty — pomijamy.
Na SQLite (dev/testy: create_all) robi tylko tabelę i indeks — reszta to PG.

Revision ID: drift001
Revises: sapstat001
"""
import logging

import sqlalchemy as sa
from alembic import op

revision = "drift001"
down_revision = "sapstat001"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

# (tabela, kolumna, tabela nadrzędna)
_FKS = [
    ("avizo_requests", "approved_by_id", "users"),
    ("orders", "container_type_id", "container_types"),
    ("orders", "created_by_id", "users"),
    ("orders", "departure_port_id", "ports"),
    ("orders", "supplier_contact_id", "supplier_contacts"),
    ("quotes", "carrier_id", "carriers"),
]
# (tabela, kolumna, kolumna zapasowa do uzupełnienia NULL-i)
_NOT_NULL = [
    ("goods_receipt_lines", "created_at", "updated_at"),
    ("goods_receipt_lines", "updated_at", "created_at"),
    ("orders", "created_at", None),
    ("purchase_orders", "created_at", "updated_at"),
    ("purchase_orders", "updated_at", "created_at"),
    ("quote_revisions", "created_at", None),
    ("supplier_doc_profiles", "updated_at", None),
    ("supplier_doc_samples", "created_at", None),
    ("supplier_material_maps", "created_at", "updated_at"),
    ("supplier_material_maps", "updated_at", "created_at"),
]
# (tabela, kolumna, nazwa constraintu z migracji, nazwa indeksu z modelu)
_UNIQUE = [
    ("tracked_vessels", "mmsi", "tracked_vessels_mmsi_key", "ix_tracked_vessels_mmsi"),
    ("material_stock_targets", "material_no", "material_stock_targets_material_no_key",
     "ix_material_stock_targets_material_no"),
]


def _fk_name(table: str, col: str) -> str:
    return f"{table}_{col}_fkey"   # domyślna nazwa PG — taka sama jak z create_all


def _indexes(insp, table: str) -> dict:
    return {ix["name"]: ix for ix in insp.get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1) material_issues (na prod zwykle już jest z create_all)
    if not insp.has_table("material_issues"):
        op.create_table(
            "material_issues",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("produkt", sa.String(60), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("qty", sa.Numeric(14, 3), nullable=False),
            sa.Column("firma", sa.String(60), nullable=False),
            sa.Column("magazyn", sa.String(60), nullable=False),
            sa.Column("kontrahent", sa.String(120), nullable=False),
            sa.Column("source_file", sa.String(200), nullable=False),
            sa.UniqueConstraint("source_file", "produkt", "date", "magazyn",
                                name="uq_material_issue"),
        )
    op.create_index("ix_material_issues_produkt", "material_issues", ["produkt"],
                    if_not_exists=True)
    op.create_index("ix_material_issues_date", "material_issues", ["date"], if_not_exists=True)
    op.create_index("ix_containers_purchasing_status", "containers", ["purchasing_status"],
                    if_not_exists=True)

    if bind.dialect.name != "postgresql":
        return

    # 2) FK — osierocone odwołania zerujemy (kolumny nullable), FK tylko gdy go brak
    for table, col, parent in _FKS:
        if any(fk["constrained_columns"] == [col] for fk in insp.get_foreign_keys(table)):
            continue
        op.execute(sa.text(
            f"UPDATE {table} SET {col} = NULL WHERE {col} IS NOT NULL AND NOT EXISTS "
            f"(SELECT 1 FROM {parent} p WHERE p.id = {table}.{col})"))
        op.create_foreign_key(_fk_name(table, col), table, parent, [col], ["id"])

    # 3) created_at/updated_at → NOT NULL (najpierw uzupełnij NULL-e)
    for table, col, other in _NOT_NULL:
        cols = {c["name"] for c in insp.get_columns(table)}
        fill = f"COALESCE({other}, now())" if other in cols else "now()"
        op.execute(sa.text(f"UPDATE {table} SET {col} = {fill} WHERE {col} IS NULL"))
        op.alter_column(table, col, existing_type=sa.DateTime(), nullable=False)

    # 4) unique constraint → unikalny indeks (jak deklaruje model: unique=True, index=True)
    for table, col, constraint, index in _UNIQUE:
        has_constraint = any(uc["name"] == constraint for uc in insp.get_unique_constraints(table))
        ix = _indexes(insp, table).get(index)
        if ix and ix["unique"]:
            pass
        else:
            dups = bind.execute(sa.text(
                f"SELECT 1 FROM {table} WHERE {col} IS NOT NULL "
                f"GROUP BY {col} HAVING count(*) > 1 LIMIT 1")).first()
            if dups:   # możliwe tylko bez constraintu — nie ruszamy danych
                log.warning("drift001: %s.%s ma duplikaty — pomijam unikalny indeks", table, col)
                continue
            if ix:
                op.drop_index(index, table_name=table)
            op.create_index(index, table, [col], unique=True)
        if has_constraint:
            op.drop_constraint(constraint, table, type_="unique")


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if bind.dialect.name == "postgresql":
        for table, col, constraint, index in reversed(_UNIQUE):
            if not any(uc["name"] == constraint for uc in insp.get_unique_constraints(table)):
                op.create_unique_constraint(constraint, table, [col])
            op.drop_index(index, table_name=table, if_exists=True)
            if table == "tracked_vessels":   # stan z ab12cd34ef56: zwykły indeks + constraint
                op.create_index(index, table, [col])
        for table, col, _other in reversed(_NOT_NULL):
            op.alter_column(table, col, existing_type=sa.DateTime(), nullable=True)
        for table, col, _parent in reversed(_FKS):
            op.drop_constraint(_fk_name(table, col), table, type_="foreignkey", if_exists=True)
    op.drop_index("ix_containers_purchasing_status", table_name="containers", if_exists=True)
    # material_issues zostaje celowo: na prod trzyma dane (create_all i tak by ją odtworzył)
