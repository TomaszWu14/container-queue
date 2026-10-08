# Kontekst projektu - timporye

## Baza wiedzy (Graphify)
Ten projekt ma graf wiedzy zbudowany narzędziem graphify (w tym repo):
- Wiki (start tutaj): `graphify-out/wiki/index.md`
- Raport audytu: `graphify-out/GRAPH_REPORT.md`
- Graf źródłowy: `graphify-out/graph.json`

## Kluczowy kontekst architektoniczny
- Graf dzieli się na 3 niezależne rdzenie: backend, frontend, docs
- `Container` (models.py) to najszerszy hub (~21 społeczności), ale NIE punkt krytyczny
- `check_container_access()` to prawdziwy punkt krytyczny (cut-vertex) — usunięcie go realnie rozłącza system
- Izolacja per-zasób jest scentralizowana w `deps.py` (`_enforce_scope`/`get_scoped`, `scope_containers`/`scope_transport_orders`) — nie powielaj reguł w routerach

## Wskazówka dla Claude Code
Przed analizą architektury lub odpowiedzią na pytania o strukturę projektu, sprawdź `graphify-out/wiki/index.md` zamiast czytać kod od podstaw.

## Limit długości pliku
- Max **500 linii** na plik (backend `.py`, frontend `src/**/*.ts|tsx|css`). Pilnuje tego
  `scripts/check_file_lengths.py` w CI. Pliki już za długie są w jego `BASELINE` i mogą się
  tylko skracać — dodając kod, wydziel moduł zamiast podnosić próg; po refaktorze obniż wpis.

## Teksty interfejsu (i18n) — plik na funkcję
- Nowe klucze tłumaczeń dodawaj w **`frontend/src/i18n/features/<funkcja>.ts`** (`defineFeature({ pl, en, pt })`),
  NIE na końcu wspólnych `i18n/{pl,en,pt}.modules.ts` / `*.base.ts` — dopiski na końcu tych plików
  zderzały się w każdej parze równoległych PR-ów. Wzór: `frontend/src/i18n/features/README.md`.
- Test `i18n.features.test.ts` pilnuje unikalności kluczy; `i18n.unused.test.ts` — że każdy klucz jest używany.

## Jak unikać konfliktów między gałęziami
- **1 PR = 1 temat**, mały i szybko scalany (godziny, nie dni). Nie dokładaj niezwiązanych zmian
  do otwartego PR-a — nowy temat = nowa gałąź od świeżego `main`.
- Przed pushem i przed oznaczeniem PR jako gotowy: `git fetch origin main && git merge origin/main`
  (merge, nie rebase), testy, push.
- Teksty interfejsu: plik na funkcję (sekcja „Teksty interfejsu” wyżej). Stare wspólne
  `frontend/src/i18n/*.ts` mają dodatkowo `merge=union` (.gitattributes) — duplikat klucza zgłosi `tsc` (TS1117).
- Nie przenoś/nie formatuj masowo kodu, którego nie zmieniasz (to generuje konflikty w cudzych PR-ach).
- Konflikt z `main` na otwartym PR: rozwiązuje go `.github/workflows/claude-conflicts.yml`
  (automatycznie po pushu do main albo komentarz `/konflikty`); szczegóły `docs/CLAUDE-GITHUB.md`.
