# BUGS-FOUND — błędy aplikacji wykryte przez system testów

Zasada: tu trafiają błędy **w aplikacji** (nie w testach). Nie naprawiamy ich bez zgody właściciela.
Każdy wpis: opis, kroki, waga, test, który go wykrył (albo planowany test potwierdzający).

Wagi: **krytyczna** (utrata/wyciek danych, prod nie działa) · **wysoka** (błędne dane, obejście uprawnień) ·
**średnia** (awaria przy nietypowych danych, ryzyko DoS) · **niska** (niespójność, martwy kod).

Status: `PODEJRZENIE` = wykryte analizą statyczną w Etapie 0, zweryfikowane w kodzie, czeka na test ·
`POTWIERDZONE` = test czerwony · `NAPRAWIONE` = test zielony po poprawce (z numerem PR).

---

## B-001 · Raport błędów importu SAP bez ochrony przed formułami Excela
- **Status:** PODEJRZENIE (kod zweryfikowany) · **Waga:** wysoka
- **Gdzie:** `backend/app/routers/imports_master.py:289` — `sheet.append(...)` z danymi z importowanego pliku,
  z pominięciem `exports.append_row` (używanego w pozostałych eksportach).
- **Kroki:** 1) zaimportuj LFA1 z wierszem, którego nazwa to `=HYPERLINK("http://x","klik")` i który zostanie
  odrzucony; 2) pobierz `GET /api/import/sap-imports/{id}/errors.xlsx`; 3) otwórz w Excelu → formuła aktywna.
- **Test potwierdzający:** Etap 2 — `test_exports_formula_injection.py::test_sap_errors_xlsx_neutralizes_formulas`.

## B-002 · `csv_safe` nie neutralizuje tabulatora i `\r` na początku pola
- **Status:** PODEJRZENIE (kod zweryfikowany) · **Waga:** niska
- **Gdzie:** `backend/app/exports.py:19-22` — sprawdza tylko `= + - @`; OWASP zaleca też `\t` i `\r`.
- **Kroki:** wartość `\t=1+1` w polu eksportowanym do CSV wycen → Excel może ją zinterpretować.
- **Test potwierdzający:** Etap 2 — parametryzowany test `csv_safe` na wszystkie prefiksy OWASP.

## B-003 · Import PAZ i upload analityki bez limitu rozmiaru pliku
- **Status:** PODEJRZENIE (kod zweryfikowany) · **Waga:** średnia
- **Gdzie:** `backend/app/routers/paz.py:54`, `backend/app/routers/analytics.py:18` — `file.file.read()` bez
  `read_upload_capped(..., MAX_UPLOAD_MB)`, którego używają inne importy.
- **Kroki:** wyślij plik 500 MB na `POST /api/paz/import` → cały plik w pamięci procesu (ryzyko OOM całej apki).
- **Test potwierdzający:** Etap 2 — `test_imports_malicious.py::test_upload_over_limit_rejected[paz|analytics]` → oczekiwane 413.

## B-004 · Brak ochrony przed cichym nadpisaniem przy równoczesnej edycji
- **Status:** PODEJRZENIE (kod zweryfikowany: brak `version_id_col` / `If-Match` / porównania `updated_at`) · **Waga:** wysoka
- **Gdzie:** PATCH kontenera i pozostałe edycje encji.
- **Kroki:** dwie karty otwierają ten sam kontener; A zapisuje datę, B zapisuje uwagi ze starym stanem →
  zmiana A może zostać nadpisana bez ostrzeżenia (zależnie od tego, czy front wysyła pełny obiekt).
- **Test potwierdzający:** Etap 2 — `test_concurrency.py::test_concurrent_patch_no_silent_overwrite`; Etap 4 — E2E „dwie karty”.

## B-005 · Produkcja wystartuje na SQLite, gdy zabraknie `DATABASE_URL`
- **Status:** PODEJRZENIE (kod zweryfikowany: `config.py:13` domyślnie `sqlite:///./timporye.db`, `validate_settings` go nie sprawdza) · **Waga:** średnia
- **Kroki:** `ENVIRONMENT=production` bez `DATABASE_URL` → aplikacja startuje na pustej bazie plikowej zamiast odmówić startu.
- **Test potwierdzający:** Etap 2 — `test_config_failfast.py::test_prod_requires_postgres_url`.

## B-006 · Forwarder ma dostęp do `/zamowienia`, ale nie ma linku w menu
- **Status:** POTWIERDZONE decyzją właściciela 2026-09-26 (forwarder MA mieć Zamówienia) · **Waga:** niska
- **Gdzie:** `frontend/src/routing.tsx` (canAccess) vs `frontend/src/Sidebar.tsx:132`.
- **Test potwierdzający:** Etap 4 — spójność `ui-permissions.yaml` (routes vs nav).

## B-007 · „Analiza rozładunków” widoczna wg flagi `view_all_companies`, a nie wg roli
- **Status:** POTWIERDZONE decyzją właściciela 2026-09-26 · **Waga:** średnia
- **Oczekiwane:** widzą tylko admin, logistics i warehouse.
- **Dziś:** `frontend/src/Sidebar.tsx:145` → `role==='admin' || view_all_companies`. Forwarder/customs/purchasing
  z flagą widzą pozycję, a logistics/warehouse bez flagi jej nie widzą.
- **Uwaga do poprawki:** warehouse nigdy nie ma `can_view_all` (deps) — trzeba ustalić, czy analiza dla magazynu
  ma być zawężona do jego magazynu; sprawdzić też bramkę po stronie API (`/kolejka?spolka=analysis`).
- **Test potwierdzający:** Etap 4 — widoczność menu wg `ui-permissions.yaml`.
