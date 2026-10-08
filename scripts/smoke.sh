#!/usr/bin/env sh
# Smoke-test po Redeploy (audyt CICD-001): health + strona główna, opcjonalnie logowanie
# kontem tylko do odczytu i lista kolejki. Kod wyjścia ≠ 0 = wdrożenie do sprawdzenia/cofnięcia.
# Użycie:  sh scripts/smoke.sh http://192.0.2.10:81
#          SMOKE_LOGIN=… SMOKE_PASSWORD=… sh scripts/smoke.sh <url>   (hasło tylko w zmiennej, nie w argumencie)
set -eu
BASE="${1:?Użycie: smoke.sh <adres, np. http://192.0.2.10:81>}"
BASE="${BASE%/}"
fail() { echo "SMOKE: BŁĄD — $*" >&2; exit 1; }

health=$(curl -fsS --max-time 15 "$BASE/api/health") || fail "/api/health nie odpowiada 200"
echo "$health" | grep -q '"status": *"ok"' || fail "/api/health: $health"
echo "$health" | grep -q '"database": *"ok"' || fail "baza: $health"
echo "SMOKE: health ok — $(echo "$health" | sed -n 's/.*"version": *"\([^"]*\)".*/wersja \1/p')"

curl -fsS --max-time 15 -o /dev/null "$BASE/" || fail "strona główna (frontend) nie odpowiada 200"
echo "SMOKE: frontend ok"

if [ -n "${SMOKE_LOGIN:-}" ]; then
  token=$(curl -fsS --max-time 15 -d "username=$SMOKE_LOGIN" --data-urlencode "password=${SMOKE_PASSWORD:?ustaw SMOKE_PASSWORD}" \
    "$BASE/api/auth/login" | sed -n 's/.*"access_token": *"\([^"]*\)".*/\1/p') || fail "logowanie nieudane"
  [ -n "$token" ] || fail "logowanie nieudane — złe dane albo 2FA na koncie smoke"
  curl -fsS --max-time 30 -o /dev/null -H "Authorization: Bearer $token" "$BASE/api/containers?limit=1" \
    || fail "lista kolejki nie odpowiada 200"
  echo "SMOKE: logowanie i kolejka ok"
fi
echo "SMOKE: OK"
