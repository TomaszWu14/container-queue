"""DB-007: ograniczenia CHECK (słowniki tekstowe, zakresy) + unikalne klucze biznesowe.

Dane produkcyjne mogą łamać nowe reguły — deploy NIE może przez to paść. Na PostgreSQL:
1. Naprawa bezstratna: wielkość liter / spacje (`' Otwarty'` → `otwarty`) dla słowników.
2. Kolumny opcjonalne (ramp_stage, special_reason, on_carriage) z wartością spoza słownika
   → NULL, stara wartość zapisana w audit_log (field = kolumna, note „migracja chk001”).
3. `ADD CONSTRAINT … NOT VALID` (nowe i zmieniane wiersze już sprawdzane), potem
   `VALIDATE CONSTRAINT` — tylko gdy nic nie łamie reguły. Inaczej ostrzeżenie w logu
   z liczbą i przykładami; ograniczenie zostaje NOT VALID do ręcznej poprawy danych
   i `ALTER TABLE <t> VALIDATE CONSTRAINT <nazwa>` (lista: pg_constraint.convalidated).
4. Unikalny indeks częściowy (CONCURRENTLY) numeru kontenera wśród niezrealizowanych
   w spółce (N-20) — tylko bez duplikatów; przy duplikatach
   ostrzeżenie z listą i pominięcie — indeks do założenia ręcznie po sprzątnięciu
   (SQL w ostrzeżeniu). Duplikat dopisany w trakcie budowy indeksu → to samo.
DDL w autocommit_block z lock_timeout i ponowieniem — ADD CONSTRAINT bierze na chwilę
ACCESS EXCLUSIVE, a VALIDATE już nie blokuje zapisów. SQLite (dev/testy): CHECK-i daje
create_all z modeli (ALTER ADD CONSTRAINT nie istnieje); indeksy — jak na PG.
ETA ≥ ETD świadomie bez CHECK: ETD/ETA przychodzą z trackingu i Excela, a CHECK zamieniłby
błędną daną źródła w nieudany sync — raport: audit/sql/data_06_daty_nierealne.sql.

Revision ID: chk001
Revises: tidseq001
"""
import datetime
import logging
import time

import sqlalchemy as sa
from alembic import op

revision = "chk001"
down_revision = "tidseq001"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic")

# nazwa: (tabela, kolumna, dozwolone wartości, nullable, normalizacja)
_IN = {
    "ck_containers_consolidation_status": (
        "containers", "consolidation_status", ("otwarty", "wypelniony", "zamkniety"), False, "lower"),
    "ck_containers_ramp_stage": (
        "containers", "ramp_stage", ("PODSTAWIONY", "ROZLADOWANY", "PRZYJETY"), True, "upper"),
    "ck_containers_special_reason": (
        "containers", "special_reason", ("zlecenie_klienta", "pilne", "kontrola_jakosci",
                                         "nowe_produkty", "nowy_producent"), True, "lower"),
    "ck_containers_on_carriage": (
        "containers", "on_carriage", ("drogowo", "intermodal"), True, "lower"),
    "ck_suppliers_sap_status": (
        "suppliers", "sap_status", ("active", "blocked", "inactive_in_sap"), False, "lower"),
    "ck_purchase_orders_cart_status": (
        "purchase_orders", "cart_status", ("w_koszyku", "zwolnione", "przypisane", "zablokowane"),
        False, "lower"),
    "ck_freight_invoices_status": (
        "freight_invoices", "status", ("NOWA", "DO_AKCEPTACJI", "ZAAKCEPTOWANA", "ODRZUCONA"),
        False, "upper"),
    "ck_sap_orders_sap_status": ("sap_orders", "sap_status", ("aktywny", "brak_w_sap"), False, "lower"),
    "ck_material_units_sap_status": (
        "material_units", "sap_status", ("aktywny", "brak_w_sap"), False, "lower"),
}
_RANGES = {
    "ck_containers_capacity_cbm": ("containers", "capacity_cbm > 0"),
    "ck_containers_pallet_count": ("containers", "pallet_count >= 0"),
    "ck_containers_unload_order": ("containers", "unload_finished_at >= unload_started_at"),
}


def _in_sql(column: str, values, nullable: bool) -> str:
    expr = f"{column} IN ({', '.join(repr(v) for v in values)})"
    return f"{column} IS NULL OR {expr}" if nullable else expr


# nazwa: (tabela, wyrażenie CHECK, normalizacja albo None) — te same co w modelach (test)
CHECKS = {**{n: (t, _in_sql(c, v, nl), fix) for n, (t, c, v, nl, fix) in _IN.items()},
          **{n: (t, sql, None) for n, (t, sql) in _RANGES.items()}}

# nazwa: (tabela, kolumny, warunek indeksu częściowego). Kod SAP dostawcy (suppliers.sap_code)
# świadomie NIE tutaj: kartoteka ma jeszcze kopie z importów per spółka, które scala
# supplier_consolidation — unikalność to osobny krok po scaleniu („kartoteka002”, etap B).
UNIQUES = {
    "ux_containers_active_no": ("containers", ["company_id", "container_no"],
                                "status <> 'ZREALIZOWANY' AND container_no <> ''"),
}

_audit = sa.table("audit_log", sa.column("entity_type", sa.String),
                  sa.column("entity_id", sa.Integer), sa.column("field", sa.String),
                  sa.column("old_value", sa.Text), sa.column("new_value", sa.Text),
                  sa.column("note", sa.Text), sa.column("created_at", sa.DateTime))


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _rows(sql: str, **params):
    return op.get_bind().execute(sa.text(sql), params).all()


def _ddl(sql: str, attempts: int = 6) -> None:
    """ALTER z lock_timeout: nie ustawiamy się bez końca w kolejce za długą transakcją
    (blokując wszystkich za sobą) — ponawiamy co 5 s, po 6 próbach błąd."""
    for attempt in range(1, attempts + 1):
        try:
            op.execute(sql)
            return
        except sa.exc.OperationalError as exc:
            if "lock timeout" not in str(exc).lower() or attempt == attempts:
                raise
            log.warning("DB-007: tabela zajęta (lock_timeout), próba %d/%d: %s",
                        attempt, attempts, sql[:80])
            time.sleep(5)


def _repair(name: str) -> None:
    table, column, values, nullable, fix = _IN[name]
    listed = ", ".join(repr(v) for v in values)
    norm = f"{fix}(btrim({column}))"
    n = op.get_bind().execute(sa.text(
        f"UPDATE {table} SET {column} = {norm} WHERE {column} IS NOT NULL "
        f"AND {column} NOT IN ({listed}) AND {norm} IN ({listed})")).rowcount
    if n:
        log.warning("DB-007: %s.%s — ujednolicono zapis %d wartości (wielkość liter/spacje)",
                    table, column, n)
    if not nullable:
        return
    bad = _rows(f"SELECT id, {column} FROM {table} WHERE {column} NOT IN ({listed})")
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    for row_id, value in bad:
        op.get_bind().execute(_audit.insert().values(
            entity_type=table, entity_id=row_id, field=column, old_value=value, new_value=None,
            note="migracja chk001 (DB-007): wartość spoza słownika → pusto", created_at=now))
    if bad:
        op.execute(f"UPDATE {table} SET {column} = NULL WHERE {column} NOT IN ({listed})")
        log.warning("DB-007: %s.%s — %d wartości spoza słownika wyczyszczono (stare w audit_log)",
                    table, column, len(bad))


def _add_check(name: str, table: str, sql: str) -> None:
    exists = _rows("SELECT convalidated FROM pg_constraint WHERE conname = :n", n=name)
    if not exists:
        _ddl(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({sql}) NOT VALID")
    elif exists[0][0]:
        return
    bad = _rows(f"SELECT count(*) FROM {table} WHERE NOT ({sql})")[0][0]
    if bad:
        sample = _rows(f"SELECT id FROM {table} WHERE NOT ({sql}) ORDER BY id LIMIT 10")
        log.warning("DB-007: %s — %d wierszy %s łamie regułę (np. id %s); ograniczenie zostaje "
                    "NOT VALID (nowe/zmieniane wiersze już sprawdzane). Po poprawie danych: "
                    "ALTER TABLE %s VALIDATE CONSTRAINT %s", name, bad, table,
                    [r[0] for r in sample], table, name)
        return
    _ddl(f"ALTER TABLE {table} VALIDATE CONSTRAINT {name}")


def _duplicates(table: str, cols: list[str], where: str) -> list:
    keys = ", ".join(cols)
    return _rows(f"SELECT {keys}, count(*) FROM {table} WHERE {where} "
                 f"GROUP BY {keys} HAVING count(*) > 1 ORDER BY {keys} LIMIT 20")


def _add_unique(name: str, pg: bool) -> None:
    table, cols, where = UNIQUES[name]
    create = (f"CREATE UNIQUE INDEX {'CONCURRENTLY ' if pg else ''}IF NOT EXISTS {name} "
              f"ON {table} ({', '.join(cols)}) WHERE {where}")
    dups = _duplicates(table, cols, where)
    if dups:
        log.warning("DB-007: %s pominięty — duplikaty %s: %s. Po sprzątnięciu (zakończ "
                    "albo scal zdublowane kontenery) uruchom ręcznie: %s",
                    name, cols, [tuple(r) for r in dups], create)
        return
    if pg:
        invalid = _rows("SELECT 1 FROM pg_class c JOIN pg_index i ON i.indexrelid = c.oid "
                        "WHERE c.relname = :n AND NOT i.indisvalid", n=name)
        if invalid:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
    try:
        op.execute(create)
    except sa.exc.IntegrityError:   # duplikat dopisany w trakcie budowy indeksu
        if pg:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
        log.warning("DB-007: %s pominięty — duplikat powstał w trakcie migracji; uruchom "
                    "ręcznie: %s", name, create)


def upgrade() -> None:
    if not _is_postgres():
        log.info("DB-007: SQLite — CHECK-i z modeli (create_all), tu tylko indeksy unikalne")
        for name in UNIQUES:
            _add_unique(name, pg=False)
        return
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")
        for name, (table, sql, fix) in CHECKS.items():
            if fix:
                _repair(name)
            _add_check(name, table, sql)
        # CONCURRENTLY czeka na starsze transakcje (bez blokowania zapisów) — bez lock_timeout,
        # inaczej długi przebieg joba w tle wywróciłby migrację
        op.execute("RESET lock_timeout")
        for name in UNIQUES:
            _add_unique(name, pg=True)


def downgrade() -> None:
    pg = _is_postgres()
    if not pg:
        for name, (table, _cols, _where) in UNIQUES.items():
            op.drop_index(name, table_name=table, if_exists=True)
        return
    with op.get_context().autocommit_block():
        for name in UNIQUES:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
        for name, (table, _sql, _fix) in CHECKS.items():
            op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
