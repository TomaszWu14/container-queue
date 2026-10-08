# Migracja Azure → Coolify — Plan implementacji

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Przenieść produkcję TIMPORYE z Azure Container Apps na istniejący serwer Coolify (Hetzner) i wyczyścić repo z konfiguracji Azure.

**Architecture:** Coolify pilnuje repo przez GitHub App (auto-deploy po pushu na `main`), buduje z `docker-compose.coolify.yml` + `Dockerfile.coolify`. Dane: dump Azure Postgres → restore na Hetznerze; załączniki: Azure Files → wolumen `uploads`. Po weryfikacji — jeden PR sprzątający Azure z repo.

**Tech Stack:** Coolify, Docker Compose, Postgres (pg_dump/pg_restore), GitHub Actions.

## Global Constraints

- Kolejność deploy-first: nic z Azure nie usuwamy z repo, dopóki Coolify nie serwuje aplikacji poprawnie (Faza 1 zakończona weryfikacją).
- Domena docelowa: `kolejka.example.com` (ta sama co planowana na Azure; nie serwuje jeszcze produkcji).
- Sekrety wyłącznie w panelu Coolify — nigdy w repo.
- Faza 2 na osobnym branchu `chore/migracja-coolify`, jeden PR.

---

## Faza 1 — operacje poza repo (zadania 1–4, wykonywane z użytkownikiem)

### Task 1: Aplikacja TIMPORYE w Coolify

**Files:** brak zmian w repo (panel Coolify).

**Interfaces:**
- Produces: działająca aplikacja Coolify zbudowana z `docker-compose.coolify.yml`, auto-deploy z brancha `main`.

- [ ] **Step 1: Utwórz zasób w Coolify**

W panelu Coolify: *+ New → Docker Compose → GitHub App* (ta sama instalacja GitHub App co inne repozytoria) → wybierz repo `TomaszWu14/container-queue`, branch `main`, plik compose: `docker-compose.coolify.yml`.

- [ ] **Step 2: Włącz auto-deploy**

W ustawieniach zasobu: *Auto Deploy* = ON (webhook push na `main`).

- [ ] **Step 3: Ustaw zmienne środowiskowe**

Przenieś wartości z obecnej konfiguracji Azure (Container App → Environment variables / GitHub Secrets). Checklist zmiennych (z `docker-compose.coolify.yml` i `docs/ARCHITEKTURA.md`):

```
SECRET_KEY            (nowy, wygeneruj: openssl rand -hex 32)
POSTGRES_PASSWORD     (nowy, silny)
DATABASE_URL          (składany przez compose lub jawnie)
CORS_ORIGINS=https://kolejka.example.com
SAFECUBE_API_KEY      (przenieś z Azure)
RESEND_API_KEY        (przenieś z Azure)
SENTRY_DSN            (przenieś z Azure)
UPLOADS_DIR=/data/uploads   (już w compose)
```

- [ ] **Step 4: Pierwszy deploy i health-check**

Kliknij *Deploy*. Sprawdź logi builda i:

```bash
curl -s https://<tymczasowy-adres-coolify>/api/health
```

Expected: HTTP 200. (Jeśli endpoint health nie istnieje, sprawdź `GET /docs` → 200.)

### Task 2: Migracja bazy Postgres

**Files:** brak zmian w repo (użycie istniejących skryptów z `docs/BACKUPY.md`).

**Interfaces:**
- Consumes: działający Postgres w Coolify (Task 1).
- Produces: baza produkcyjna z danymi z Azure.

- [ ] **Step 1: Sprawdź wersje Postgresa**

```bash
# Azure:
psql "$AZURE_DATABASE_URL" -c "SELECT version();"
# Coolify (na serwerze Hetzner):
docker exec <postgres-container> psql -U postgres -c "SELECT version();"
```

Expected: wersja docelowa ≥ wersji źródłowej. Jeśli nie — podnieś obraz Postgresa w Coolify przed restore.

- [ ] **Step 2: Dump z Azure**

```bash
pg_dump "$AZURE_DATABASE_URL" -Fc -f timporye-azure.dump
```

Expected: plik `.dump` bez błędów na stderr.

- [ ] **Step 3: Restore na Hetznerze**

```bash
scp timporye-azure.dump hetzner:/tmp/
ssh hetzner 'docker cp /tmp/timporye-azure.dump <postgres-container>:/tmp/ && \
  docker exec <postgres-container> pg_restore -U postgres -d timporye --clean --if-exists /tmp/timporye-azure.dump'
```

Expected: restore bez błędów FATAL (warningi o istniejących obiektach przy `--clean` są OK).

- [ ] **Step 4: Weryfikacja danych**

```bash
ssh hetzner 'docker exec <postgres-container> psql -U postgres -d timporye -c \
  "SELECT (SELECT count(*) FROM users) AS users, (SELECT count(*) FROM containers) AS containers;"'
```

Expected: liczby zgodne z tym samym zapytaniem na Azure.

### Task 3: Migracja załączników (Azure Files → wolumen uploads)

**Files:** brak zmian w repo.

**Interfaces:**
- Consumes: wolumen `uploads` zamontowany pod `/data/uploads` (Task 1).
- Produces: komplet załączników dostępny dla aplikacji.

- [ ] **Step 1: Pobierz pliki z Azure Files**

```bash
az storage file download-batch \
  --account-name <storage-account> --source <share-name> --destination ./uploads-azure
```

Expected: pobrane wszystkie pliki (porównaj liczbę z portalem Azure).

- [ ] **Step 2: Wgraj do wolumenu na Hetznerze**

```bash
rsync -av ./uploads-azure/ hetzner:/tmp/uploads-azure/
ssh hetzner 'docker cp /tmp/uploads-azure/. <app-container>:/data/uploads/'
```

- [ ] **Step 3: Weryfikacja**

```bash
ssh hetzner 'docker exec <app-container> sh -c "ls /data/uploads | wc -l"'
```

Expected: liczba plików = liczba pobranych z Azure. Dodatkowo: otwórz w aplikacji dowolny stary załącznik (np. przy zleceniu) — pobiera się poprawnie.

### Task 4: Domena i weryfikacja końcowa Fazy 1

**Files:** brak zmian w repo.

**Interfaces:**
- Consumes: działająca aplikacja z danymi (Taski 1–3).
- Produces: `https://kolejka.example.com` serwuje TIMPORYE z Coolify. **Bramka wejściowa do Fazy 2.**

- [ ] **Step 1: DNS**

U rejestratora domeny: rekord A `kolejka.example.com` → IP serwera Hetzner.

- [ ] **Step 2: Domena w Coolify**

W ustawieniach zasobu: *Domains* = `https://kolejka.example.com`. Redeploy. Coolify wystawi certyfikat Let's Encrypt automatycznie.

- [ ] **Step 3: Smoke test produkcji**

Ręcznie na `https://kolejka.example.com`: logowanie istniejącym kontem → kolejka kontenerów → szczegóły kontenera → zlecenia transportowe → pobranie załącznika. Wszystko działa, HTTPS bez ostrzeżeń.

- [ ] **Step 4: Test auto-deployu**

Wypchnij trywialny commit na `main` (np. literówka w README). Expected: Coolify sam buduje i wdraża, aplikacja dalej działa.

---

## Faza 2 — sprzątanie repo (Task 5, dopiero po zakończeniu Task 4)

### Task 5: Usunięcie konfiguracji Azure z repo

**Files:**
- Delete: `.github/workflows/deploy-azure.yml`
- Delete: `.github/workflows/build-image.yml`
- Delete: `Dockerfile.azure`
- Delete: `infra/main.bicep`, `infra/main.parameters.example.json` (cały katalog `infra/`)
- Delete: `docs/DEPLOY_AZURE.md`
- Modify: `docs/ARCHITEKTURA.md` (linie 22, 27, 52–53, 76, 190, 205–208, 214)

**Interfaces:**
- Consumes: potwierdzenie z Task 4, że Coolify serwuje produkcję.
- Produces: repo bez śladów Azure; CI zielone.

- [ ] **Step 1: Branch**

```bash
git checkout main && git pull && git checkout -b chore/migracja-coolify
```

- [ ] **Step 2: Usuń pliki Azure**

```bash
git rm .github/workflows/deploy-azure.yml .github/workflows/build-image.yml \
  Dockerfile.azure docs/DEPLOY_AZURE.md
git rm -r infra/
```

- [ ] **Step 3: Zaktualizuj docs/ARCHITEKTURA.md**

Zamień wzmianki Azure na Coolify:
- L22: `subgraph Kontener["Jeden kontener Docker (Azure Container Apps)"]` → `subgraph Kontener["Jeden kontener Docker (Coolify / Hetzner)"]`
- L27: `FILES[["Azure Files<br/>załączniki/uploady"]]` → `FILES[["Wolumen uploads<br/>załączniki/uploady"]]`
- L52: `| Pliki | Excel — openpyxl; załączniki na Azure Files |` → `| Pliki | Excel — openpyxl; załączniki na wolumenie Docker (uploads) |`
- L53: `| CI/CD | GitHub Actions, obraz w GHCR, hosting Azure Container Apps |` → `| CI/CD | GitHub Actions (testy); build i hosting: Coolify na Hetznerze |`
- L76: `Dockerfile.azure / Dockerfile.coolify   # obrazy wdrożeniowe` → `Dockerfile.coolify   # obraz wdrożeniowy`
- L190: `GitHub Secrets / Azure — nigdy w kodzie.` → `GitHub Secrets / panel Coolify — nigdy w kodzie.`
- L205–208: diagram deployu — zamień węzły `deploy-azure`/`Azure Container App`/`Azure Files` na `Coolify (webhook push)` → `Aplikacja na Hetznerze (kolejka.example.com, HTTPS)` → `wolumen uploads`
- L214: usuń `AZURE_CREDENTIALS` z listy sekretów

- [ ] **Step 4: Weryfikacja czystości**

```bash
grep -rin azure --exclude-dir=.git --exclude-dir=.venv --exclude-dir=node_modules --exclude-dir=graphify-out .
```

Expected: brak trafień (poza ewentualnie specami/planami w `docs/superpowers/`, które są zapisem historycznym).

- [ ] **Step 5: Commit i PR**

```bash
git add -A
git commit -m "chore(deploy): usuń konfigurację Azure — produkcja na Coolify"
git push -u origin chore/migracja-coolify
gh pr create --title "chore(deploy): usuń konfigurację Azure" \
  --body "Produkcja działa na Coolify (kolejka.example.com). Usuwa deploy-azure.yml, build-image.yml, Dockerfile.azure, infra/, DEPLOY_AZURE.md; aktualizuje ARCHITEKTURA.md."
```

- [ ] **Step 6: CI zielone**

Sprawdź w PR: `ci-backend`, `ci-frontend`, `security`, `codeql` — wszystkie PASS (usunięte workflowy nie są w required checks; jeśli `Required Checks Gate` w `automerge.yml` wymienia usunięte workflowy — usuń je z gate'a w tym samym PR).

---

## Faza 3 — po okresie spokoju (poza planem, checklist)

- [ ] Wyłącz Azure Container App, usuń bazę Postgres i Storage Account (po min. 2 tygodniach stabilnej pracy Coolify i po zrobieniu finalnego backupu).
- [ ] Usuń sekrety `AZURE_CREDENTIALS` z GitHub Secrets.
