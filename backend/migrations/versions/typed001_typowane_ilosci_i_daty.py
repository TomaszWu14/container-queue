"""DB-008: typowane kopie liczb i dat zapisanych jako tekst.

Nowe kolumny (tekstowe zostają jako „surowe” — nic nie jest kasowane ani nadpisywane):
- order_items.quantity_num, goods_receipt_lines.qty_received_num — Numeric(14, 3),
- purchase_orders.ready_on, purchase_orders.oem_sample_on — Date.
Wypełnienie istniejących wierszy: PostgreSQL najpierw jednym UPDATE dla tekstu, który już jest
zwykłą liczbą (po normalizacji importu REF — większość), resztę parserem aplikacji
(app.models.typed_text — ta sama semantyka co nasłuch ORM przy nowych zapisach: „1.234,000”,
„1 200,5”, pojedynczy przecinek = dziesiętny). Import parsera tylko, gdy są wiersze do
przeliczenia (świeża baza w CI go nie potrzebuje). Tekst nieparsowalny → NULL (odczyty mają
wtedy fallback na tekst); liczba takich wierszy trafia do logu.

Revision ID: typed001
Revises: chk001
"""
import logging

import sqlalchemy as sa
from alembic import op

revision = "typed001"
down_revision = "chk001"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic")
_BATCH = 1000

# (tabela, kolumna tekstowa, kolumna typowana, typ, parser z app.models.typed_text)
_COLUMNS = [
    ("order_items", "quantity", "quantity_num", sa.Numeric(14, 3), "parse_quantity"),
    ("goods_receipt_lines", "qty_received", "qty_received_num", sa.Numeric(14, 3),
     "parse_quantity"),
    ("purchase_orders", "ready_date", "ready_on", sa.Date(), "parse_text_date"),
    ("purchase_orders", "oem_sample_date", "oem_sample_on", sa.Date(), "parse_text_date"),
]
# Szybkie ścieżki SQL (PG) tylko dla zapisów jednoznacznych — wynik identyczny z parserem,
# bez zaokrąglania (≤ 3 miejsca), mieszczący się w Numeric(14, 3). Reszta (np. „1.234” —
# dwuznaczne, parser bierze kropkę jako dziesiętną) idzie parserem aplikacji.
_FAST_PATHS = {
    "zwykła liczba": (r"^-?[0-9]{1,11}(\.[0-9]{1,3})?$", "btrim({src})"),
    # PL: przecinek dziesiętny, opcjonalnie kropki tysięcy („742,000”, „1.234,000”)
    "zapis PL": (r"^-?([0-9]{1,11}|[0-9]{1,3}(\.[0-9]{3}){1,2}),[0-9]{1,3}$",
                 "replace(replace(btrim({src}), '.', ''), ',', '.')"),
}


def _backfill(table: str, src: str, dst: str, type_, parser_name: str, pg: bool) -> None:
    bind = op.get_bind()
    if pg and parser_name == "parse_quantity":
        for label, (regex, expr) in _FAST_PATHS.items():
            fast = bind.execute(sa.text(
                f"UPDATE {table} SET {dst} = CAST({expr.format(src=src)} AS NUMERIC(14, 3)) "
                f"WHERE {dst} IS NULL AND btrim({src}) ~ :re"), {"re": regex}).rowcount
            log.info("DB-008: %s.%s — %d wierszy (%s) przepisanych w SQL", table, dst, fast,
                     label)
    rows = bind.execute(sa.text(
        f"SELECT id, {src} FROM {table} WHERE {dst} IS NULL AND {src} IS NOT NULL "
        f"AND {src} <> ''")).all()
    if not rows:
        return
    from app.models import typed_text   # ta sama semantyka co zapisy ORM (patrz docstring)
    parse = getattr(typed_text, parser_name)
    values = [{"i": row_id, "v": parse(raw)} for row_id, raw in rows]
    ok = [v for v in values if v["v"] is not None]
    stmt = sa.text(f"UPDATE {table} SET {dst} = :v WHERE id = :i").bindparams(
        sa.bindparam("v", type_=type_))   # Decimal/Date przez typ kolumny (SQLite)
    for start in range(0, len(ok), _BATCH):
        bind.execute(stmt, ok[start:start + _BATCH])
    if len(ok) < len(values):
        log.warning("DB-008: %s.%s — %d wierszy z tekstem nie do odczytania jako %s (zostaje "
                    "NULL, tekst bez zmian; lista: SELECT id, %s FROM %s WHERE %s IS NULL "
                    "AND %s <> '')", table, src, len(values) - len(ok),
                    "liczba" if parser_name == "parse_quantity" else "data",
                    src, table, dst, src)
    log.info("DB-008: %s.%s — wypełniono %d wierszy parserem", table, dst, len(ok))


def upgrade() -> None:
    bind = op.get_bind()
    pg = bind.dialect.name == "postgresql"
    for table, src, dst, type_, parser_name in _COLUMNS:
        existing = {c["name"] for c in sa.inspect(bind).get_columns(table)}
        if dst not in existing:   # dev/SQLite: create_all mógł już dodać kolumnę
            op.add_column(table, sa.Column(dst, type_, nullable=True))
        _backfill(table, src, dst, type_, parser_name, pg)


def downgrade() -> None:
    for table in dict.fromkeys(t for t, *_ in _COLUMNS):
        cols = [dst for t, _src, dst, _type, _p in _COLUMNS if t == table]
        with op.batch_alter_table(table) as batch:   # SQLite: przebudowa tabeli
            for col in cols:
                batch.drop_column(col)
