# Bezpieczeństwo aplikacji

Dokument opisuje mechanizmy bezpieczeństwa aplikacji (kolejka kontenerów). **Nie zawiera haseł,
tokenów ani kluczy** — sekrety żyją wyłącznie w zmiennych środowiskowych (katalog nazw:
`docs/ZMIENNE-SRODOWISKOWE.md`).

## 1. Architektura

- Backend FastAPI (Python 3.12) + PostgreSQL 16; frontend React serwowany przez ten sam origin
  (brak CORS między domenami). Obraz: `Dockerfile.coolify`, stack: `docker-compose.coolify.yml`
  (Docker + Coolify, on-prem lub VPS).
- Produkcja wymaga HTTPS: `SECURE_COOKIES=true` włącza flagę `Secure` ciasteczek i nagłówek HSTS
  (`main.py`). Wyjątek dla instancji bez certyfikatu tylko jawnym `ALLOW_INSECURE_HTTP=true` (§2).

## 2. Zabezpieczenia aplikacji (zweryfikowane w kodzie)

| Obszar | Kontrola |
|---|---|
| Uwierzytelnianie | JWT w cookies `HttpOnly` + `SameSite=Lax` (+ `Secure` przy `SECURE_COOKIES=true`); refresh tokeny jednorazowe (rotacja), unieważnianie wszystkich sesji (`session_version`) przy wylogowaniu/resecie hasła; 2FA (TOTP + kody zapasowe) dla każdej roli, obowiązkowe dla administratorów po włączeniu `REQUIRE_2FA_ADMIN=true` (domyślnie wyłączone): admin bez 2FA widzi po zalogowaniu ekran włączania i do tego czasu ma tylko odczyt (`backend/app/twofa_policy.py`, SEC-006); zgubiony telefon — 2FA wyłącza inny administrator (z audytem) |
| CSRF | Zapis na `/api` (POST/PUT/PATCH/DELETE) z ciasteczkiem sesji wymaga nagłówka `X-Requested-With` (front dokłada go do każdego żądania, `frontend/src/csrf.ts`) albo `Origin`/`Referer` = adres panelu (`PUBLIC_BASE_URL` lub `Host`, z portem) — inaczej 403 (`backend/app/csrf.py`, SEC-004). Chroni przed innymi usługami pod tym samym IP (ten sam „site” dla `SameSite=Lax`). Nie chroni przed treścią z tego samego originu (np. `/n8n/` za tą samą bramą) — docelowo osobna nazwa hosta i ciasteczka `__Host-` (wymaga HTTPS) |
| Brute force | Rate-limit logowania per para IP+login (`LOGIN_MAX_ATTEMPTS`), sumarycznie per IP (`LOGIN_MAX_ATTEMPTS_PER_IP`, wyżej — wielu użytkowników za NAT) i per konto ze wszystkich IP z progresywną przerwą (`LOGIN_ACCOUNT_LOCK_AFTER`, `LOGIN_ACCOUNT_LOCK_SECONDS`) + alert do adminów; stan w bazie (`login_failures`), więc restart i kilka workerów go nie zerują; globalny limit API per IP; stały czas odpowiedzi przy nieistniejącym loginie |
| Reset hasła | Jednorazowe tokeny z TTL, odpowiedź zawsze 202 (bez zdradzania istnienia konta), rate-limit, unieważnienie sesji po resecie; konto z hasłem tymczasowym (zaproszenie, reset przez admina — `must_change_password`) do ustawienia własnego hasła dostaje 403 na całe API poza `GET /api/auth/me`, `GET /api/auth/me/prefs`, `POST /api/auth/change-password` i wylogowaniem (`security.py`, SEC-007) |
| Autoryzacja | RBAC — **7 ról** (`Role` w `backend/app/models/enums.py`: admin, logistics, warehouse, forwarder, customs, purchasing, sales) + izolacja per-zasób scentralizowana w `deps.py` (`scope_containers`/`scope_transport_orders`); spedytor/magazyn/agencja widzą wyłącznie swoje zasoby; macierz uprawnień pilnowana testem `tests/test_permissions_matrix.py` |
| Audyt | Rejestr zmian (kto/co/kiedy, także nieudane logowania z IP) w tabeli audytu |
| Automatyzacje (n8n) | Token serwisowy `X-Automation-Token` porównywany w stałym czasie, mapowany na konto użytkownika → te same role i izolacja; wyłączenie konta = natychmiastowe 403; zdarzenia wychodzące podpisane HMAC-SHA256 (`docs/N8N.md`) |
| Nagłówki HTTP | CSP (`default-src 'self'`, `frame-ancestors 'none'`; jedyny inline skrypt = przycisk „Drukuj” dopuszczony hashem, `app/print_button.py`), `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy: camera=(self), microphone=(), geolocation=()`, `Cross-Origin-Opener-Policy: same-origin`; HSTS tylko za HTTPS (`SECURE_COOKIES=true`); panel z docker-compose (nginx) ma te same nagłówki |
| Konfiguracja | Fail-fast przy `ENVIRONMENT=production`: start blokowany przy domyślnych sekretach, `SECRET_KEY` < 32 znaki, `SECURE_COOKIES=false`, braku `PUBLIC_BASE_URL`; `/docs` wyłączone. **Uwaga:** instancja po HTTP ustawia `ENVIRONMENT=production` + `ALLOW_INSECURE_HTTP=true` — zwalnia to tylko wymóg `SECURE_COOKIES` (ciasteczka bez `Secure`, bez HSTS), reszta fail-fast i ukryte `/docs` działają (`docker-compose.coolify.yml`, SEC-003). |
| RODO / telemetria | Sentry ze scrubbingiem PII (gdy `SENTRY_DSN` ustawiony): bez zmiennych lokalnych ramek i parametrów logów, maskowanie e-maili/telefonów w tekście — imion i nazwisk w wolnym tekście regex nie wyłapie, więc nie wstawiamy ich do komunikatów błędów; czyszczenie danych kierowców po `DRIVER_DATA_RETENTION_DAYS` |
| Sekrety | Wyłącznie w zmiennych środowiskowych Coolify; brak sekretów w repozytorium; na każdym PR gitleaks + Bandit (`security.yml`, blokuje merge), CodeQL nie jest skonfigurowany (`SECURITY.md`) |

## 3. Kopie zapasowe

- **baza** — `pg_dump` cyklicznie (zadanie w Coolify), retencja `BACKUP_KEEP`;
- **załączniki** — archiwum, retencja `BACKUP_KEEP_UPLOADS`;
- kopie szyfrowane (`age`), weryfikacja odtworzenia `verify_backup.py`; kopia poza serwer zalecana.

Skrypty i odtworzenie: `docs/BACKUPY.md`, `backend/scripts/backup.sh`, `restore.sh`, `verify_backup.py`.

## 4. Zgłaszanie podatności

Patrz `SECURITY.md`. Po incydencie: rotacja sekretów, przegląd audytu logowań, kopia bazy
przed zmianami.
