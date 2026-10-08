#!/usr/bin/env sh
# Odtworzenie bazy PostgreSQL z pliku backupu (.sql.gz z backup.sh; .sql.gz.age — zaszyfrowany,
# wymaga BACKUP_AGE_IDENTITY=<plik klucza prywatnego age>, BACKUP-007).
# UWAGA: nadpisuje dane w bazie wskazanej przez DATABASE_URL.
# Użycie:  sh scripts/restore.sh /data/backups/timporye-YYYYMMDD-HHMMSS.sql.gz [--force]
set -eu

: "${DATABASE_URL:?DATABASE_URL nie jest ustawione}"
FILE="${1:-}"
[ -n "$FILE" ] || { echo "Użycie: restore.sh <plik.sql.gz> [--force]"; exit 1; }
[ -f "$FILE" ] || { echo "Nie znaleziono pliku: $FILE"; exit 1; }

PG_URL=$(printf '%s' "$DATABASE_URL" | sed -E 's#^postgresql\+[a-z0-9]+://#postgresql://#')
case "$PG_URL" in
  postgresql://*) : ;;
  *) echo "restore: DATABASE_URL nie jest Postgresem — przerywam"; exit 1 ;;
esac

if [ "${2:-}" != "--force" ]; then
  printf 'To NADPISZE obecne dane w bazie danymi z %s.\nWpisz "tak", aby kontynuować: ' "$FILE"
  read -r ans
  [ "$ans" = "tak" ] || { echo "Przerwano."; exit 1; }
fi

echo "restore: odtwarzam z $FILE …"
# ON_ERROR_STOP: przerwij przy pierwszym błędzie zamiast wgrywać częściowo
case "$FILE" in
  *.age)
    # BACKUP-007: kopia zaszyfrowana age — klucz PRYWATNY (plik) tylko na czas odtwarzania
    [ -n "${BACKUP_AGE_IDENTITY:-}" ] || {
      echo "restore: $FILE jest zaszyfrowany — ustaw BACKUP_AGE_IDENTITY=<plik klucza prywatnego age>"
      exit 1; }
    DEC_FAIL=$(mktemp)
    trap 'rm -f "$DEC_FAIL"' EXIT
    { age -d -i "$BACKUP_AGE_IDENTITY" "$FILE" || echo x > "$DEC_FAIL"; } \
      | gunzip -c | psql "$PG_URL" -v ON_ERROR_STOP=1 --quiet
    if [ -s "$DEC_FAIL" ]; then echo "restore: BŁĄD odszyfrowania (zły klucz?)" >&2; exit 1; fi
    ;;
  *) gunzip -c "$FILE" | psql "$PG_URL" -v ON_ERROR_STOP=1 --quiet ;;
esac
echo "restore: gotowe. Zrestartuj aplikację, aby na pewno pracowała na świeżej bazie."
