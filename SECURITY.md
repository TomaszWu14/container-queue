# Bezpieczeństwo

## Zgłaszanie podatności
Podatności zgłaszaj prywatnie do administratora projektu (nie przez publiczne Issue).
Postaramy się odpowiedzieć w ciągu kilku dni roboczych.

## Automatyczne kontrole (CI)
Stan z `.github/workflows/` (wszystkie te joby chodzą na self-hosted runnerze `[self-hosted, linux]`).
„Blokuje merge” = job jest na liście `REQUIRED` w `automerge.yml`, więc czerwony wynik zatrzymuje
bramkę „CI OK”, bez której auto-merge nie scala PR-a.

| Narzędzie | Co robi | Kiedy | Blokuje merge? |
|---|---|---|---|
| **gitleaks** | sekrety w historii gita | każdy PR (tylko jego commity) + co tydzień i ręcznie cała historia — `security.yml` | **tak** (job „Skany — sekrety i Bandit”) |
| **Bandit** | SAST kodu `backend/app` | jak wyżej — `security.yml` | **tak** (ten sam job) |
| **pip-audit / npm audit** (`--audit-level=high`) | znane podatności zależności | PR ruszający `Dockerfile*`, `docker-compose*.yml`, `backend/requirements*`, `frontend/package*.json` + co tydzień — `ci-infra.yml` | **tak**, dla PR-ów z tymi ścieżkami |
| **Trivy** (`fs`, HIGH/CRITICAL) | podatności, sekrety i błędy konfiguracji w plikach | tylko co tydzień i ręcznie — `security.yml` | nie (raport w logu joba, `--exit-code 0`) |
| **Dependabot** | cotygodniowe PR-y z aktualizacjami: pip, npm, GitHub Actions, obrazy Docker | `.github/dependabot.yml` | — |

Czego **nie ma** (mimo wcześniejszych wpisów w tym pliku): workflow CodeQL i uploadu SARIF, więc
zakładka *Security → Code scanning* nic z CI nie dostaje — wyniki są tylko w logach jobów.
Alerty CVE Dependabota zależą od ustawień repo (*Settings → Code security*), nie od pliku w repo —
TODO(właściciel): potwierdzić, że są włączone.

## Kontrole lokalne (pre-commit)
```bash
pip install pre-commit
pre-commit install
```
Od tej pory przed każdym commitem uruchamiają się (`.pre-commit-config.yaml`): ruff (lint backendu),
bandit (SAST `backend/app`), gitleaks (sekrety) oraz podstawowe kontrole plików (m.in. wykrywanie
kluczy prywatnych i znaczników konfliktu). Ręcznie: `pre-commit run --all-files`.

## Wbudowane zabezpieczenia aplikacji
- **Nagłówki** (`main.py`, `SecurityHeadersMiddleware`): CSP, `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, `Referrer-Policy` — zawsze; **HSTS tylko przy `SECURE_COOKIES=true`**.
- **Ciasteczka sesji**: `HttpOnly` i `SameSite=Lax` zawsze; flaga **`Secure` tylko przy
  `SECURE_COOKIES=true`** (domyślnie `false` w `config.py`, `true` w `docker-compose.coolify.yml`).
  Produkcja po samym HTTP wstaje wyłącznie z jawnym `ALLOW_INSECURE_HTTP=true` — wtedy ciasteczka
  idą bez `Secure` (audyt SEC-003).
- **Start produkcji fail-fast** (`validate_settings`): odmowa startu z domyślnym `SECRET_KEY` /
  `ADMIN_PASSWORD`, z `SECRET_KEY` krótszym niż 32 znaki, bez `PUBLIC_BASE_URL`, bez
  `SECURE_COOKIES` (chyba że `ALLOW_INSECURE_HTTP=true`). Na produkcji `/docs` i `/openapi.json` są wyłączone.
- **CSRF** (`csrf.py`, SEC-004): żądanie zmieniające stan z ciasteczkiem sesji musi mieć nagłówek
  `X-Requested-With` albo `Origin`/`Referer` z adresu aplikacji.
- **Sesje**: refresh token rotowany przy każdym odświeżeniu (krótkie okno łaski na wyścig kart),
  użytkownik i admin mogą odwołać sesje.
- **Limity**: nieudane logowania na parę IP+login i łącznie na IP, globalny limit żądań API na IP,
  lista zablokowanych IP (sprawdzana przy logowaniu). Liczniki są w pamięci procesu — dlatego
  aplikacja odmawia startu przy więcej niż jednym workerze (`docs/JEDNA-INSTANCJA.md`).
- **Uploady**: limit rozmiaru `MAX_UPLOAD_MB` na wszystkich trasach przyjmujących pliki
  (`read_upload_capped`). Zdjęcia (reklamacje, rozładunek, statki) i awatary są sprawdzane po
  **sygnaturze bajtów**; załączniki kontenerów tylko po **rozszerzeniu** (`ALLOWED_UPLOAD_EXTENSIONS`),
  bez sprawdzania zawartości.
- **Maile**: wartości wstawiane do HTML przechodzą przez `html.escape` (`mail_html.py`).
- **Separacja danych spółek**: zakres per rola i spółka scentralizowany w `backend/app/deps.py`.
- **Logi i Sentry**: tokeny linków publicznych maskowane w logach; przy ustawionym `SENTRY_DSN`
  zdarzenia są czyszczone z haseł, tokenów i danych osobowych kierowców przed wysłaniem (`redaction.py`).

## Znane ograniczenia (otwarte ustalenia audytu)
- Ten sam `SECRET_KEY` podpisuje JWT i jest kluczem szyfrowania danych w bazie (`crypto.py`, SEC-017).
- Załączniki kontenerów bez weryfikacji zawartości (jak wyżej).
