#!/usr/bin/env bash
# Jednorazowe przygotowanie serwera pod n8n obok panelu (jedna domena, kilka aplikacji).
# Uruchom NA SERWERZE — w Coolify: zasób panelu → Terminal, albo przez SSH.
#
#   ./deploy/setup-n8n.sh kolejka.twojafirma.pl     # domena (HTTPS przez Traefik Coolify)
#   ./deploy/setup-n8n.sh 192.0.2.10:81          # bez domeny: IP[:port] w sieci wewnętrznej
#
# Skrypt NIE dotyka Coolify ani aplikacji: tworzy sieć współdzieloną (jedyny krok,
# którego nie da się zrobić z interfejsu) i generuje sekrety, które wklejasz w
# Environment Variables. Bezpiecznie uruchomić ponownie — sieć nie jest tworzona
# dwa razy, ale sekrety za każdym razem są NOWE (nie nadpisuj nimi działających).
#
# Pełny opis architektury i kroków: docs/N8N.md
set -euo pipefail

NETWORK="${NETWORK:-timporye-apps}"
DOMAIN="${1:-}"

if [ -z "$DOMAIN" ]; then
    echo "Użycie: $0 <domena-lub-IP[:port]>   np. $0 kolejka.twojafirma.pl  albo  $0 192.0.2.10:81" >&2
    exit 2
fi
case "$DOMAIN" in
    http*|*/*) echo "Podaj samą domenę (albo IP:port), bez http:// i bez ścieżki." >&2; exit 2 ;;
esac

# Sam adres IP = serwer bez domeny: brak certyfikatu, więc HTTP, a brama jest wystawiona
# portem prosto na hosta (bez Traefika) — przed aplikacją stoi jedno proxy, nie dwa.
if [[ "${DOMAIN%:*}" =~ ^[0-9]+(\.[0-9]+){3}$ ]]; then
    SCHEME=http; HOPS=1
else
    SCHEME=https; HOPS=2
fi
command -v docker >/dev/null || { echo "Brak polecenia docker — uruchom to na serwerze." >&2; exit 1; }

# losowy sekret: podshell bez pipefail, bo `head` zamyka potok i zabija `tr` (SIGPIPE)
rand() (
    set +o pipefail
    LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c "${1:-40}"
)

echo "== 1/3 sieć współdzielona =="
if docker network inspect "$NETWORK" >/dev/null 2>&1; then
    echo "  sieć '$NETWORK' już istnieje — zostawiam"
else
    docker network create "$NETWORK" >/dev/null
    echo "  utworzona: $NETWORK"
fi

echo
echo "== 2/3 zmienne dla zasobu n8n (docker-compose.n8n.yml) =="
echo "N8N_DB_PASSWORD=$(rand 40)"
echo "N8N_ENCRYPTION_KEY=$(rand 48)"
echo "N8N_PUBLIC_BASE_URL=$SCHEME://$DOMAIN/"
[ "$HOPS" = 1 ] && echo "N8N_PROXY_HOPS=1"
echo
echo "  MIGRUJESZ istniejącego n8n? Zamiast wygenerowanego klucza wpisz STARY"
echo "  (w starym kontenerze: cat /home/node/.n8n/config → pole encryptionKey),"
echo "  inaczej stracisz dostęp do zapisanych credentiali w workflow."

echo
echo "== 3/3 zmienne dla zasobu panelu (docker-compose.coolify.yml) =="
echo "COMPOSE_PROFILES=gateway"
echo "TRUSTED_PROXY_COUNT=$HOPS"
echo "AUTOMATION_API_TOKEN=$(rand 43)"
echo "AUTOMATION_ACTOR_LOGIN=n8n"
echo "AUTOMATION_WEBHOOK_SECRET=$(rand 40)"
echo
echo "  AUTOMATION_WEBHOOK_URL dopisz dopiero, gdy będzie workflow z triggerem Webhook:"
echo "  http://gateway/n8n/webhook/<id-webhooka>"
echo "  Masz ustawione ALLOWED_HOSTS? Dopisz tam: gateway"
if [ "$SCHEME" = http ]; then
    echo "  Bez domeny (HTTP): SECURE_COOKIES=false, PUBLIC_BASE_URL=http://$DOMAIN"
fi

echo
echo "== co dalej (interfejs Coolify) =="
cat <<TXT
  1. + New Resource → Docker Compose, to samo repo, plik docker-compose.n8n.yml,
     BEZ domeny → wklej zmienne z sekcji 2 → Deploy
  2. zasób panelu → wklej zmienne z sekcji 3 → przenieś domenę z serwisu 'app'
     na 'gateway' (port 80) → Deploy
     (bez domeny: mapowanie portu hosta przenieś z 'app' na 'gateway', np. 81:80 —
      adres panelu się nie zmienia; szczegóły: docs/N8N.md, sekcja 1f)
  3. sprawdź:
       curl -s $SCHEME://$DOMAIN/gateway-health      # ok
       curl -s $SCHEME://$DOMAIN/api/health          # {"status":"ok"...}
       curl -so /dev/null -w '%{http_code}\n' $SCHEME://$DOMAIN/n8n/webhook/test   # 404 od n8n
  4. edytor n8n (z własnego laptopa, nie z serwera):
       ssh -L 5678:127.0.0.1:5678 <user>@<serwer>   →   http://localhost:5678
TXT
