# Wdrożenie z Coolify (on-prem lub VPS)

Repozytorium zawiera gotową konfigurację: `docker-compose.coolify.yml`
(PostgreSQL + jeden kontener aplikacji serwujący API i panel) oraz
`Dockerfile.coolify`. Domenę i certyfikat HTTPS zapewnia Coolify. Merge do `main` **niczego
nie wdraża** — wdrożenie to ręczny Redeploy w Coolify (sekcja 4).

## 1. Utwórz zasób w Coolify

1. **+ New Resource → Public Repository** (lub **Private Repository (GitHub App)**,
   jeśli repo jest prywatne — zainstaluj GitHub App wg kreatora Coolify).
2. Adres repozytorium: `https://github.com/TomaszWu14/container-queue`, gałąź: `main`.
3. **Build Pack: Docker Compose**.
4. **Docker Compose Location:** `/docker-compose.coolify.yml`.

## 2. Ustaw zmienne środowiskowe

W zakładce **Environment Variables** dodaj (Coolify sam wykryje `${...}` z compose).

**Wymagane (produkcja nie wystartuje bez nich):**

| Zmienna | Wartość |
|---|---|
| `SECRET_KEY` | **min. 32 znaki** — wygeneruj: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `POSTGRES_PASSWORD` | silne hasło do bazy |
| `ADMIN_PASSWORD` | hasło pierwszego admina — silne, zgodne z polityką haseł (`PASSWORD_MIN_LENGTH`, domyślnie 12 znaków); **nie** `admin123` |
| `PUBLIC_BASE_URL` | pełny adres panelu, np. `https://kolejka.twojafirma.pl` — bez tego linki e-mail (reset hasła) budują się z nagłówka `Host` (podatność) |

**Zalecane / opcjonalne:**

| Zmienna | Domyślnie | Znaczenie |
|---|---|---|
| `ALLOWED_HOSTS` | *(puste)* | dozwolone domeny panelu (CSV) — ochrona przed host-header injection |
| `TRUSTED_PROXY_COUNT` | `1` | liczba proxy przed aplikacją (Coolify/Traefik = 1) — poprawne IP klienta do limitów |
| `TRUSTED_PROXY_CIDRS` | `172.16.0.0/12,127.0.0.1/32` | sieci proxy (CSV CIDR), od których aplikacja i uvicorn honorują `X-Forwarded-For`; podsieć Traefika: `docker network inspect coolify --format '{{range .IPAM.Config}}{{.Subnet}}{{end}}'`. Nie wpisuj `10.0.0.0/8` — to sieć firmowa (podrabianie IP) |
| `API_RATE_LIMIT_PER_MINUTE` | `300` | globalny limit żądań API na IP (`0` = wyłączony) |
| `BACKUP_KEEP` | `14` | ile kopii bazy zostawić (patrz sekcja 6) |
| `BACKUP_KEEP_WEEKLY` / `BACKUP_KEEP_MONTHLY` | `8` / `12` | dodatkowo kopie tygodniowe/miesięczne (retencja GFS, `docs/BACKUPY.md`) |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_FROM` | *(puste)* | powiadomienia i wyceny e-mail — **bez tego maile nie wychodzą** |
| `SENTRY_DSN` | *(puste)* | monitoring błędów (sentry.io) |
| `LOG_FILE` | *(puste)* | trwałe logi: `/data/logs/app.log` (wolumen `logs`, rotacja 10×10 MB) — przeżywają Redeploy |
| `TEAMS_WEBHOOK_URL` | *(puste)* | powiadomienia na Teams/Slack |
| `AUTOMATION_API_TOKEN` / `AUTOMATION_WEBHOOK_URL` | *(puste)* | automatyzacje n8n — patrz **[docs/N8N.md](N8N.md)** |

`UPLOADS_DIR`, `BACKUP_DIR` są ustawione w compose — nie ruszaj. `SECURE_COOKIES` ma w compose
domyślnie `true` (serwer za HTTPS).

Uwaga: `ENVIRONMENT=production` wymusza bezpieczne sekrety i HTTPS — aplikacja
**nie wystartuje** z domyślnym/słabym `SECRET_KEY`, domyślnym hasłem admina,
bez `SECURE_COOKIES` ani bez `PUBLIC_BASE_URL`. To zabezpieczenie, nie błąd.
Serwer bez certyfikatu (tylko HTTP, np. w sieci wewnętrznej): zostaw `ENVIRONMENT=production`
i ustaw `SECURE_COOKIES=false` + `ALLOW_INSECURE_HTTP=true` — to zwalnia wyłącznie wymóg
`SECURE_COOKIES` (reszta kontroli działa), a sesje idą bez flagi `Secure` (SEC-003).

## 3. Podepnij domenę

W ustawieniach usługi **app** wpisz domenę, np. `https://timporye.twojafirma.pl`
(port kontenera: **8000**). Coolify wystawi certyfikat Let's Encrypt automatycznie.
W DNS domeny dodaj rekord **A** wskazujący na IP serwera.

Aplikacja wysyła cookies z flagą `Secure` i nagłówek HSTS (`SECURE_COOKIES=true`
w compose), więc działa wyłącznie po HTTPS — dokładnie tak, jak ma być.

## 4. Deploy

Kliknij **Deploy**. Przy starcie kontener sam wykonuje migracje bazy
(`alembic upgrade head`) i tworzy konto `admin` z hasłem z `ADMIN_PASSWORD`.

Kolejne wdrożenia: Coolify → **Redeploy** (albo auto-deploy z webhooka GitHub App, jeśli go
włączysz); po wdrożeniu `scripts/smoke.sh` sprawdza `/health`.

## 5. Dane startowe

Jednorazowy import z Excela (`scripts/import_excel.py` + `seed_data.json`) usunięty 2026-09-28 —
plik zawierał prawdziwe dane firmy. Dane wprowadza się importami w panelu (Master data → Importy).
Instancja pokazowa (portfolio): `scripts/seed_demo.py` (zmyślone dane, patrz opis w pliku).

## 6. Backup bazy

Aplikacja ma gotowe skrypty: `backend/scripts/backup.sh` (pg_dump → `.sql.gz`
z retencją) i `restore.sh`. `pg_dump`/`psql` są w obrazie.

W Coolify: zasób aplikacji → **Scheduled Tasks → Add** — harmonogram i polecenie dokładnie wg
[BACKUPY.md](BACKUPY.md) (decyzja 2026-09-28: raz w tygodniu, sobota 22:00, baza + załączniki;
cotygodniowa weryfikacja akceptuje kopię do `BACKUP_MAX_AGE_HOURS` = 194 h).

Kopie lądują w `/data/backups` (trwały wolumen, jak uploady) — konfiguracja
`BACKUP_DIR` / `BACKUP_KEEP`. Pełny opis, restore i dobre praktyki: **[docs/BACKUPY.md](BACKUPY.md)**.

Wolumeny `pgdata`, `uploads` i `backups` są trwałe — przeżywają redeploy.

## 7. (Opcjonalnie) kilka aplikacji na jednej domenie

`docker-compose.coolify.yml` zawiera serwis `gateway` (nginx) — bramę, która na jednym
hoście rozdziela ruch po ścieżce: `/` do panelu, `/n8n/...` do niezależnego stacku n8n
(`docker-compose.n8n.yml`). Brama jest w profilu compose `gateway`, więc startuje dopiero
po ustawieniu `COMPOSE_PROFILES=gateway` — bez tego wdrożenie zachowuje się jak dotąd
(domena zostaje na serwisie `app`).

Pełna instrukcja (sieć współdzielona, przeniesienie domeny, `TRUSTED_PROXY_COUNT=2`,
edytor n8n przez tunel SSH, token serwisowy i webhooki): **[docs/N8N.md](N8N.md)**.

## Diagnostyka

- **Health check:** `https://twoja-domena/api/health` → `{"status":"ok","database":"ok"}`
- **Logi:** zakładka Logs usługi `app`; zdarzenia logowań są też w audycie aplikacji
- **Swagger `/docs`:** dostępny tylko poza produkcją (w produkcji celowo wyłączony —
  nie publikujemy powierzchni API). Do podglądu API uruchom lokalnie z `ENVIRONMENT=dev`.
