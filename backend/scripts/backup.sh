#!/usr/bin/env sh
# Kopia zapasowa bazy PostgreSQL do lokalnego pliku .sql.gz, z retencją.
# Uruchamiany ręcznie lub z harmonogramu (Coolify Scheduled Task / cron), np. co noc.
# Pliki lądują w BACKUP_DIR (domyślnie /data/backups — trwały wolumen).
set -eu

BACKUP_DIR="${BACKUP_DIR:-/data/backups}"
KEEP="${BACKUP_KEEP:-14}"          # ile najnowszych kopii zostawić
KEEP_WEEKLY="${BACKUP_KEEP_WEEKLY:-8}"     # + najnowsza kopia z każdego z ostatnich N tygodni
KEEP_MONTHLY="${BACKUP_KEEP_MONTHLY:-12}"  # + najnowsza kopia z każdego z ostatnich N miesięcy
KEEP_UPLOADS="${BACKUP_KEEP_UPLOADS:-7}"   # archiwa załączników są duże — osobna retencja
UPLOADS_DIR="${UPLOADS_DIR:-/data/uploads}"
# BACKUP-007: klucz PUBLICZNY age (age1…) → kopie tylko zaszyfrowane (*.age); prywatny przechowuj offline, poza serwerem
# IT/u właściciela, NIE na serwerze. Puste = jak dotąd, jawne .sql.gz / .tar.gz.
AGE_RECIPIENT="${BACKUP_AGE_RECIPIENT:-}"
EXT=""
if [ -n "$AGE_RECIPIENT" ]; then EXT=".age"; fi
mkdir -p "$BACKUP_DIR"

# strumień → (opcjonalnie) age; przy kluczu nigdy nie zapisujemy wersji jawnej
szyfruj() {
  if [ -n "$AGE_RECIPIENT" ]; then age -r "$AGE_RECIPIENT"; else cat; fi
}

# retencja GFS (BACKUP-008): usuwa kopie spoza KEEP najnowszych, tygodniowych i miesięcznych.
# Data z nazwy timporye-YYYYMMDD-HHMMSS.sql.gz (bez `date -d`); tydzień = pon–niedz.
retencja() {
  ls -1 "$BACKUP_DIR" | grep -E '^timporye-[0-9]{8}-[0-9]{6}\.sql\.gz(\.age)?$' | sort -r \
    | awk -v k="$KEEP" -v kw="$KEEP_WEEKLY" -v km="$KEEP_MONTHLY" '{
        y = substr($0, 10, 4) + 0; m = substr($0, 14, 2) + 0; d = substr($0, 16, 2) + 0
        mon = y * 100 + m
        if (m <= 2) { y--; m += 12 }
        days = 365 * y + int(y / 4) - int(y / 100) + int(y / 400) + int((153 * (m - 3) + 2) / 5) + d
        wk = int((days + 1) / 7)               # dzień z days%7==6 to poniedziałek
        keep = (NR <= k)
        if (!(wk in W) && nw < kw) { W[wk] = 1; nw++; keep = 1 }
        if (!(mon in M) && nm < km) { M[mon] = 1; nm++; keep = 1 }
        if (!keep) print
      }' \
    | while read -r f; do
        echo "backup: usuwam stary $BACKUP_DIR/$f"
        rm -f "$BACKUP_DIR/$f"
      done
}
if [ "${1:-}" = "--retencja" ]; then retencja; exit 0; fi   # sama retencja (testy, ręczne sprzątanie)

: "${DATABASE_URL:?DATABASE_URL nie jest ustawione}"

# pg_dump rozumie URI libpq — usuwamy sufiks sterownika SQLAlchemy (postgresql+psycopg2://)
PG_URL=$(printf '%s' "$DATABASE_URL" | sed -E 's#^postgresql\+[a-z0-9]+://#postgresql://#')
case "$PG_URL" in
  postgresql://*) : ;;
  *) echo "backup: pomijam — DATABASE_URL nie jest Postgresem (dev/SQLite)"; exit 0 ;;
esac

# klucz ustawiony, a age nie działa (brak programu, zły klucz) → głośny błąd, bez jawnej kopii
if [ -n "$AGE_RECIPIENT" ] && ! printf '' | age -r "$AGE_RECIPIENT" >/dev/null; then
  echo "backup: BŁĄD — BACKUP_AGE_RECIPIENT ustawiony, ale szyfrowanie age nie działa" >&2
  exit 1
fi

# sprzątamy niedokończone kopie z ew. wcześniejszej, przerwanej próby
rm -f "$BACKUP_DIR"/*.part 2>/dev/null || true

STAMP=$(date -u +%Y%m%d-%H%M%S)
OUT="$BACKUP_DIR/timporye-$STAMP.sql.gz$EXT"
TMP="$OUT.part"
FAIL="$TMP.failed"
trap 'rm -f "$TMP" "$FAIL"' EXIT   # przy błędzie nie zostawiamy uszkodzonego pliku

echo "backup: pg_dump → $OUT"
# --clean --if-exists: zrzut da się odtworzyć nawet na istniejącej bazie
# sh nie ma pipefail: błąd pg_dump w potoku dawał ucięty, „udany” plik (audyt BACKUP-005)
{ pg_dump --dbname="$PG_URL" --no-owner --no-privileges --clean --if-exists || : > "$FAIL"; } \
  | gzip -9 | szyfruj > "$TMP"
if [ -e "$FAIL" ]; then
  echo "backup: BŁĄD pg_dump — kopia NIE powstała" >&2
  exit 1
fi
mv "$TMP" "$OUT"                   # atomowo: gotowa kopia pojawia się dopiero po sukcesie
trap - EXIT
echo "backup: gotowe ($(du -h "$OUT" | cut -f1))"
# heartbeat do zewnętrznego monitora (Uptime Kuma „Push”, audyt OBS-001): brak pingu w oknie = alert
if [ -n "${BACKUP_PING_URL:-}" ]; then
  curl -fsS --max-time 10 "$BACKUP_PING_URL" >/dev/null 2>&1 || echo "backup: ping monitora nieudany" >&2
fi

retencja

# załączniki (wolumen uploads) — bez nich odtworzona baza wskazuje na nieistniejące pliki (BACKUP-003)
# BACKUP_SKIP_UPLOADS=1: kopia co 8 h tylko bazy — archiwum załączników robi zadanie nocne
if [ "${BACKUP_SKIP_UPLOADS:-0}" = "1" ]; then
  echo "backup: załączniki pominięte (BACKUP_SKIP_UPLOADS=1)"
elif [ -d "$UPLOADS_DIR" ]; then
  UP="$BACKUP_DIR/uploads-$STAMP.tar.gz$EXT"
  echo "backup: załączniki → $UP"
  if [ -n "$AGE_RECIPIENT" ]; then
    # jak przy pg_dump: bez pipefail błąd tar w potoku zginąłby — znacznik .failed
    { tar -czf - -C "$(dirname "$UPLOADS_DIR")" "$(basename "$UPLOADS_DIR")" || : > "$UP.failed"; } \
      | szyfruj > "$UP.part"
    if [ -e "$UP.failed" ]; then
      rm -f "$UP.part" "$UP.failed"
      echo "backup: BŁĄD archiwum załączników" >&2
      exit 1
    fi
  else
    tar -czf "$UP.part" -C "$(dirname "$UPLOADS_DIR")" "$(basename "$UPLOADS_DIR")"
  fi
  mv "$UP.part" "$UP"
  ls -1t "$BACKUP_DIR"/uploads-*.tar.gz "$BACKUP_DIR"/uploads-*.tar.gz.age 2>/dev/null \
    | tail -n +$((KEEP_UPLOADS + 1)) | while read -r f; do
    echo "backup: usuwam stary $f"
    rm -f "$f"
  done
fi
