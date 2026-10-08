"""DB-011: licznik numeracji transport_id w bazie (tabela transport_id_counters).

Numer nadawany był jako max+1 liczony w Pythonie — dwie równoległe transakcje (sync
SharePoint + ręczne dodanie, import) dostawały ten sam numer, a druga padała na unikalnym
ix_containers_transport_id (500 / przerwany import). Teraz upsert licznika per prefiks
(„AT-2026-”) z blokadą wiersza — routers/containers_common.reserve_transport_seqs.

Kroki (bezpieczne dla danych prod — sprawdzenie, raport w logu i w audit_log):
1. Tabela liczników.
2. Kontrola duplikatów transport_id. Przy unikalnym indeksie (stan po migracjach) nie ma
   ich prawa być; gdyby baza go nie miała (dryf), duplikat NIE wywraca deployu: kontener
   o najniższym id zachowuje numer, pozostałe dostają kolejne wolne numery prefiksu,
   każda zmiana → ostrzeżenie w logu i wpis audit_log (field=transport_id).
3. Unikalny ix_containers_transport_id — założony, jeśli go brak.
4. Liczniki zasiane maksimum numerycznym istniejących numerów każdego prefiksu.
Downgrade usuwa tylko tabelę liczników (numery kontenerów zostają).

Revision ID: tidseq001
Revises: loginlim001
"""
import datetime
import logging
import re

import sqlalchemy as sa
from alembic import op

revision = "tidseq001"
down_revision = "loginlim001"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic")
_TID = re.compile(r"^(?P<prefix>.+-)(?P<seq>\d+)$")   # „AT-2026-0042” → „AT-2026-”, 42

_containers = sa.table("containers", sa.column("id", sa.Integer),
                       sa.column("transport_id", sa.String))
_counters = sa.table("transport_id_counters", sa.column("prefix", sa.String),
                     sa.column("last_seq", sa.Integer))
_audit = sa.table("audit_log", sa.column("entity_type", sa.String),
                  sa.column("entity_id", sa.Integer), sa.column("field", sa.String),
                  sa.column("old_value", sa.Text), sa.column("new_value", sa.Text),
                  sa.column("note", sa.Text), sa.column("created_at", sa.DateTime))


def _max_per_prefix(rows) -> dict[str, int]:
    out: dict[str, int] = {}
    for _id, tid in rows:
        m = _TID.match(tid or "")
        if m:
            out[m["prefix"]] = max(out.get(m["prefix"], 0), int(m["seq"]))
    return out


def _repair_duplicates(bind, rows, maxes: dict[str, int]) -> None:
    seen: set[str] = set()
    for cid, tid in sorted(rows):   # po id: najstarszy kontener zachowuje numer
        if tid is None:
            continue
        if tid not in seen:
            seen.add(tid)
            continue
        m = _TID.match(tid)
        prefix = m["prefix"] if m else f"{tid}-"
        maxes[prefix] = maxes.get(prefix, 0) + 1
        new = f"{prefix}{maxes[prefix]:04d}"
        log.warning("DB-011: duplikat transport_id %s — kontener id=%s dostaje %s", tid, cid, new)
        bind.execute(_containers.update().where(_containers.c.id == cid)
                     .values(transport_id=new))
        bind.execute(_audit.insert().values(
            entity_type="containers", entity_id=cid, field="transport_id", old_value=tid,
            new_value=new, note="migracja tidseq001 (DB-011): duplikat numeru transportu",
            created_at=datetime.datetime.now(datetime.UTC).replace(tzinfo=None)))


def _has_unique_index(bind) -> bool:
    return any(ix["name"] == "ix_containers_transport_id" and ix["unique"]
               for ix in sa.inspect(bind).get_indexes("containers"))


def upgrade() -> None:
    op.create_table(
        "transport_id_counters",
        sa.Column("prefix", sa.String(20), primary_key=True),
        sa.Column("last_seq", sa.Integer(), nullable=False),
        if_not_exists=True,   # dev/SQLite: bootstrap create_all mógł ją już założyć
    )
    bind = op.get_bind()
    rows = bind.execute(sa.select(_containers.c.id, _containers.c.transport_id)
                        .where(_containers.c.transport_id.is_not(None))).all()
    maxes = _max_per_prefix(rows)
    dups = len(rows) - len({tid for _id, tid in rows})
    log.info("DB-011: %d numerów transport_id, duplikatów: %d", len(rows), dups)
    if dups:
        _repair_duplicates(bind, rows, maxes)
    if not _has_unique_index(bind):
        log.warning("DB-011: brak unikalnego ix_containers_transport_id — zakładam")
        op.execute("DROP INDEX IF EXISTS ix_containers_transport_id")
        op.create_index("ix_containers_transport_id", "containers", ["transport_id"],
                        unique=True)
    existing = set(bind.execute(sa.select(_counters.c.prefix)).scalars())
    seed = [{"prefix": p, "last_seq": n} for p, n in sorted(maxes.items())
            if p not in existing and len(p) <= 20]
    if seed:
        bind.execute(_counters.insert(), seed)
    log.info("DB-011: zasiano %d liczników prefiksów", len(seed))


def downgrade() -> None:
    op.drop_table("transport_id_counters", if_exists=True)
