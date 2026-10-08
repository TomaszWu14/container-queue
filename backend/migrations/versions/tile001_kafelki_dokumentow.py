"""Kafelki dokumentów dostawy: document_types.tile_code + typy BL / SAD-PZ / SAD-PW
(spec 2026-10-01-kafelki-dokumentow). Istniejący „Draft SAD” dostaje kod SAD_DRAFT.

Revision ID: tile001
Revises: zwol001
"""
import sqlalchemy as sa
from alembic import op

revision = "tile001"
down_revision = "zwol001"
branch_labels = None
depends_on = None

# kod → nazwa tworzonego typu (gdy żaden typ nie ma jeszcze tego kodu)
_SEED = (("BL", "Konosament (B/L)"), ("SAD_PZ", "SAD — po odprawie (PZ)"),
         ("SAD_PW", "SAD — zwolnienie (PW)"), ("SAD_DRAFT", "Draft SAD"))


def upgrade() -> None:
    with op.batch_alter_table("document_types") as batch:
        batch.add_column(sa.Column("tile_code", sa.String(12), nullable=True))
        batch.create_unique_constraint("uq_document_types_tile_code", ["tile_code"])
    bind = op.get_bind()
    for code, name in _SEED:
        if bind.execute(sa.text("SELECT 1 FROM document_types WHERE tile_code = :c"), {"c": code}).first():
            continue
        found = bind.execute(sa.text("SELECT id FROM document_types WHERE name = :n"), {"n": name}).first()
        if found:
            bind.execute(sa.text("UPDATE document_types SET tile_code = :c WHERE id = :i"),
                         {"c": code, "i": found[0]})
        else:
            bind.execute(sa.text("INSERT INTO document_types (name, sort_order, is_active, is_required, "
                                 "tile_code) VALUES (:n, 100, :t, :f, :c)"),
                         {"n": name, "t": True, "f": False, "c": code})


def downgrade() -> None:
    with op.batch_alter_table("document_types") as batch:
        batch.drop_constraint("uq_document_types_tile_code", type_="unique")
        batch.drop_column("tile_code")
