"""Profil dokumentów dostawcy (CI+PL), próbki, jednostka uzupełniająca materiału,
format eksportu agencji. Backfill: niepusty Supplier.column_map → profil draft z ci_map.

Revision ID: profil001
Revises: trgm001
"""
import sqlalchemy as sa
from alembic import op

revision = "profil001"
down_revision = "trgm001"
branch_labels = None
depends_on = None

ROLES = {"ref", "desc", "qty", "price", "net", "unit", "lot", "weight_net", "weight_gross", "cartons", "no"}


def ci_map_from_column_map(text: str) -> dict[str, list[str]]:
    """„ref=Item No.; qty=Q'ty" → {"ref": ["Item No."], "qty": ["Q'ty"]} (ta sama składnia co
    extractor.parse_column_map; nieznane role i puste aliasy pomijane)."""
    out: dict[str, list[str]] = {}
    for part in (text or "").split(";"):
        role, _, header = part.partition("=")
        role, header = role.strip().lower(), header.strip()
        if role in ROLES and header:
            out.setdefault(role, []).append(header)
    return out


def upgrade() -> None:
    op.create_table(
        "supplier_doc_profiles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("supplier_id", sa.Integer, sa.ForeignKey("suppliers.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="draft"),
        sa.Column("currency", sa.String(3), nullable=False, server_default=""),
        sa.Column("doc_language", sa.String(10), nullable=False, server_default=""),
        sa.Column("keywords", sa.JSON, nullable=False),
        sa.Column("ci_map", sa.JSON, nullable=False),
        sa.Column("pl_map", sa.JSON, nullable=False),
        sa.Column("ref_kind", sa.String(10), nullable=False, server_default="ours"),
        sa.Column("split_marker", sa.String(60), nullable=False, server_default=""),
        sa.Column("tol_amount_pct", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("tol_qty_pct", sa.Float, nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )
    op.create_table(
        "supplier_doc_samples",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("profile_id", sa.Integer,
                  sa.ForeignKey("supplier_doc_profiles.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("stored_path", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("last_test", sa.JSON, nullable=False),
        sa.Column("last_test_at", sa.DateTime, nullable=True),
    )
    with op.batch_alter_table("materials") as b:
        b.add_column(sa.Column("suppl_unit", sa.String(20), nullable=False, server_default=""))
        b.add_column(sa.Column("suppl_factor", sa.Float, nullable=True))
    with op.batch_alter_table("customs_agencies") as b:
        b.add_column(sa.Column("export_format", sa.String(20), nullable=False, server_default="standard"))
        b.add_column(sa.Column("export_params", sa.JSON, nullable=True))

    conn = op.get_bind()
    backfill(conn)


def backfill(conn) -> None:
    profiles = sa.table("supplier_doc_profiles", sa.column("supplier_id", sa.Integer),
                        sa.column("keywords", sa.JSON), sa.column("ci_map", sa.JSON),
                        sa.column("pl_map", sa.JSON), sa.column("status", sa.String))
    rows = conn.execute(sa.text("SELECT id, column_map FROM suppliers WHERE column_map <> ''")).all()
    batch = [{"supplier_id": sid, "keywords": [], "ci_map": ci_map_from_column_map(cm), "pl_map": {},
              "status": "draft"} for sid, cm in rows if ci_map_from_column_map(cm)]
    if batch:
        op.bulk_insert(profiles, batch)


def downgrade() -> None:
    with op.batch_alter_table("customs_agencies") as b:
        b.drop_column("export_params")
        b.drop_column("export_format")
    with op.batch_alter_table("materials") as b:
        b.drop_column("suppl_factor")
        b.drop_column("suppl_unit")
    op.drop_table("supplier_doc_samples")
    op.drop_table("supplier_doc_profiles")
