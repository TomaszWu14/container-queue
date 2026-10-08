# Onboarding dewelopera — TIMPORYE lokalnie w 30 minut

> Wymagania: Git, Python **3.12** (jak `Dockerfile.coolify` i CI), Node **22.12+** (wymóg vitest; CI używa 24), opcjonalnie Docker.
> Windows: Git Bash lub PowerShell. Właściciel dokumentu: właściciel aplikacji. Źródło: audyt 2026-09-28 (DOC-003, DOC-005).

## 1. Kod (2 min)
```sh
git clone https://github.com/TomaszWu14/container-queue.git && cd container-queue
```
Przeczytaj: `CLAUDE.md` (reguły repo — skrót w pkt 5), `docs/ARCHITEKTURA.md`,
`graphify-out/wiki/index.md` (mapa kodu), `docs/REGULY-PROCESU.md` (reguły biznesowe).

## 2. Backend (10 min) — SQLite, bez Dockera
```sh
cd backend
python -m venv .venv && . .venv/Scripts/activate      # Linux/macOS: . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt   # dev: pytest, ruff (nie ma ich w obrazie)
python -m alembic upgrade head                        # schemat w ./timporye.db
uvicorn app.main:app --reload                         # http://localhost:8000/docs (Swagger — tylko poza produkcją)
```
Konto startowe: `admin` / `admin123` (tylko dev; `ENVIRONMENT=production` tego nie przyjmie). Przy `REQUIRE_2FA_ADMIN=true` (domyślnie wyłączone, SEC-006) konto admina wymaga 2FA — po zalogowaniu włącz je aplikacją TOTP.
Wzór zmiennych: `.env.example`; pełny katalog: `docs/ZMIENNE-SRODOWISKOWE.md`.
Dane przykładowe: `backend/scripts/seed_demo.py` (**kasuje wszystkie dane**; wymaga `DEMO_READONLY_LOGINS`
i flagi `--wyczysc-wszystko` — tylko lokalnie lub na instancji demo). TODO: właściciel — czy jest lżejszy seed deweloperski.

## 3. Frontend (8 min)
```sh
cd frontend
npm ci
npm run dev                                           # http://localhost:5173 (proxy /api → :8000, VITE_API_TARGET)
```
`frontend/dist/` **nie jest w repozytorium** (`.gitignore`) — powstaje z `npm run build`; obraz Dockera buduje go sam.

## 4. Testy (5 min)
```sh
cd backend && python -m pytest tests/ -q              # SQLite, env ustawia tests/conftest.py; CI dokłada --cov (próg: pyproject)
cd frontend && npm run test && npm run typecheck      # vitest + tsc
cd frontend && npm run lint:setup && npm run lint     # ESLint (hooki Reacta, typescript-eslint) — jak CI
python scripts/check_file_lengths.py                  # strażnik 500 linii (jak w CI), z katalogu głównego
```
- **Jeden `pytest` naraz na katalog roboczy** — testy dzielą plik `backend/test_timporye.db`.
  Równoległa praca = osobne `git worktree` (każdy ma własny plik bazy testowej).
- Na słabszym laptopie uruchamiaj tylko dotknięte pliki: `python -m pytest -q tests/test_x.py tests/test_permissions_matrix.py`.
- E2E (opcjonalnie): `cd frontend && npx playwright install chromium && npm run e2e`.

## 5. Jak wygląda zmiana (reguły z `CLAUDE.md`)
1. **1 PR = 1 temat**, mały. Gałąź `claude/<temat>` od świeżego `main` (`git fetch origin main`).
   Równoległe zadania — osobne worktree (`git worktree add ../TIMPORYE-<temat> -b claude/<temat> origin/main`).
2. **Limit 500 linii** na plik (backend `.py`, frontend `src/**/*.ts|tsx|css`) — `scripts/check_file_lengths.py`
   w CI; pliki z `BASELINE` mogą się tylko skracać. Dodając kod, wydziel moduł.
3. **Teksty UI:** nowe klucze w `frontend/src/i18n/features/<funkcja>.ts` (`defineFeature({ pl, en, pt })`),
   nie na końcu wspólnych `i18n/*.modules.ts` / `*.base.ts` — wzór `frontend/src/i18n/features/README.md`.
4. **Migracja:** `python -m alembic revision --autogenerate -m "opis"` → sprawdź `upgrade()` **i** `downgrade()`;
   jedna głowa (`python -m alembic heads`).
5. Przed pushem: `git fetch origin main && git merge origin/main` (merge, nie rebase), testy, push.
6. PR → CI → auto-merge po zielonym „CI OK”. Konflikty z `main` rozwiązujesz sam (`git merge origin/main`) —
   automat `claude-conflicts.yml` obecnie nie startuje (rozliczenia GitHub, `docs/CLAUDE-GITHUB.md`).
7. Wdrożenie: Redeploy w Coolify po merge — `docs/DEPLOY_COOLIFY.md`.

## 6. Gdzie czego szukać
| Potrzebuję… | Miejsce |
|---|---|
| role i izolacja danych | `backend/app/deps.py`, `tests/permissions.yaml` (macierz rola × trasa) |
| statusy i przejścia | `backend/app/models/enums.py`, `routers/containers_common.py`, `avizo_workflow.py`, `routers/forwarding.py` |
| konfiguracja | `backend/app/config.py`, `docs/ZMIENNE-SRODOWISKOWE.md` |
| zadania w tle | `backend/app/jobs.py` |
| logi / monitoring | `backend/app/applog.py`, `monitoring.py`, panel Administracja → Logi/System |
| backup | `backend/scripts/backup.sh`, `docs/BACKUPY.md` |
| bezpieczeństwo | `docs/BEZPIECZENSTWO.md` |

## 7. Dostępy do poproszenia
GitHub (collaborator), konto testowe w aplikacji.
