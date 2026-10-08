# Migracja deploymentu: Azure Container Apps → Coolify (Hetzner)

Data: 2026-08-21
Status: zatwierdzony

## Kontekst

Rezygnujemy z Azure. Serwer Coolify na Hetznerze już działa i hostuje inne
repozytoria. Domena zostaje ta sama, ale nie serwuje jeszcze produkcji — przepięcie
bez presji czasowej. Dane produkcyjne z Azure Postgres wymagają migracji.

## Decyzje

- **Model deployu:** Coolify sam pilnuje repo (GitHub App, auto-deploy po pushu na
  `main`), buduje z `Dockerfile.coolify` / `docker-compose.coolify.yml`. CI nie
  buduje obrazów deployowych.
- **Dane:** dump Azure Postgres → restore do Postgresa w Coolify (skrypty z
  `docs/BACKUPY.md`).
- **Kolejność:** deploy-first — Azure zostaje w repo i w chmurze jako fallback,
  dopóki Coolify nie zostanie zweryfikowany.

## Faza 1 — uruchomienie na Coolify (poza repo)

1. Nowa aplikacja w Coolify: GitHub App → to repo, branch `main`,
   build z `docker-compose.coolify.yml`, auto-deploy włączony.
2. Zmienne środowiskowe/sekrety w panelu Coolify (compose wymusza bezpieczne
   sekrety w produkcji).
3. Migracja danych: sprawdzić zgodność wersji Postgresa Azure↔Hetzner, potem
   dump → restore.
4. Podpięcie domeny w Coolify (Let's Encrypt automatycznie).
5. Weryfikacja: health-check, logowanie, kluczowe ekrany (kolejka, kontenery,
   zlecenia).

## Faza 2 — sprzątanie repo (jeden PR)

Usunąć:
- `.github/workflows/deploy-azure.yml`
- `.github/workflows/build-image.yml` (Coolify buduje sam; GHCR nieużywany)
- `Dockerfile.azure`
- `infra/` (main.bicep, main.parameters.example.json)
- `docs/DEPLOY_AZURE.md`

Zaktualizować:
- `docs/ARCHITEKTURA.md` — wzmianki o Azure → Coolify
- `README.md` — jeśli wspomina Azure

Weryfikacja: CI zielone po wycięciu workflowów; `grep -ri azure` czysty
(poza historią gita i .venv).

## Faza 3 — poza repo

Po okresie spokoju: wyłączenie i usunięcie zasobów Azure (Container App, baza,
registry).

## Ryzyka

- Różnica wersji Postgresa przy restore — sprawdzić przed dumpem.
- Sekrety przenoszone ręcznie — checklist zmiennych z obecnej konfiguracji Azure
  przed wyłączeniem.
