# Kartoteka dostawców — PR 1: model danych, migracja scalająca, „Do rozstrzygnięcia" — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Przebudować `suppliers` z tabeli per spółka na jedną globalną kartotekę dostawców Acme (z nowymi tabelami pod indeksy SAP, warianty dokumentów i dziennik importów), dać adminowi bezpieczne scalanie dotychczasowych kopii per spółka (podgląd → scal) na ekranie „Do rozstrzygnięcia" i nie złamać żadnej istniejącej funkcji.

**Architecture:**
- **`Supplier.company_id` → `client_company_id` (nullable).** `NULL` = globalna kartoteka Acme (dla spółek z listy `settings.supplier_company_codes`, domyślnie `ACME,PT`). Ustawione = *nadawca kontenerów spółki-klienta* (Borealis, Cobalt) — tak jak dziś, widoczny tylko dla tej spółki. To przejściowe, świadome odstępstwo od spec §1 („nadawcy klientów tylko tekstem"): zlecenia Borealis/Cobalt (`FoundOrderModal`) zakładają dziś dostawcę i jego kontakt, więc ich przepięcie na sam tekst to osobny temat (pytanie otwarte nr 1). Rename kolumny (zamiast zostawienia `company_id` z nową semantyką) jest celowy: każde zapomniane miejsce wywali się w testach `AttributeError`, zamiast po cichu filtrować po złej kolumnie.
- **Migracja na prod bez automatycznego scalania.** `kartoteka001` (alembic) zmienia tylko schemat + kopiuje `supplier_material_maps` → `supplier_materials` (nieniszcząco, idempotentnie). Scalanie dubli (ACME i PT mają dziś te same rekordy z LFA1 — import szedł do każdej spółki) robi **serwis `supplier_consolidation`** wołany z ekranu admina i z komendy `scripts/consolidate_suppliers.py` (podgląd bez `--apply`). Uzasadnienie: (1) `Dockerfile` robi `alembic upgrade head && uvicorn` — każdy błąd migracji danych = aplikacja nie wstaje (2 awarie prod z 2026-09-18); (2) scalanie przepina ~7 tabel i profile — tę logikę mamy przetestowaną w `dictionaries_merge`, nie da się jej sensownie powielić w SQL migracji (migracje nie importują kodu aplikacji); (3) spec wymaga „listy scaleń do przejrzenia" przed zmianą danych — dry-run to daje. Scalanie w serwisie używa **tej samej funkcji** `merge_into` co ręczne „Scal z…".
- **Unikalności zależne od czystych danych — etap B (osobny, mały PR, draft do czasu scalenia na prod).** `UNIQUE(sap_code)` w kartotece i `UNIQUE(supplier_id, lower(email))` kontaktów nie da się założyć przed scaleniem (dziś ten sam `sap_code` jest w ACME i PT). `kartoteka002` zakłada je indeksami częściowymi dopiero po scaleniu; ma twardy precheck z czytelnym komunikatem. PR etapu B jest **draftem** (automerge pomija drafty), oznaczany jako gotowy dopiero gdy `python -m scripts.consolidate_suppliers` na prod pokazuje `Grup do scalenia: 0`. Do tego czasu duble blokuje kod: import LFA1 kluczuje po `sap_code` globalnie. `sap_code` zostaje `NOT NULL DEFAULT ''` (jak dziś); `''` = nadawca klienta albo rekord „do rozstrzygnięcia".
- **Widoczność w jednym miejscu (`deps.py`)**, jak `scope_*`: `scope_suppliers` (listy wyboru), `supplier_catalog_access` (szczegóły kartoteki: admin/logistyka/zakupy z kontem grupowym albo spółki z materiałami), `supplier_clause_for_company` (którego dostawcy wolno użyć w rekordzie danej spółki), gałąź `Supplier` w `_enforce_scope`. Lista kodów spółek „z materiałami" jest w ustawieniach (`SUPPLIER_COMPANY_CODES`), nie w kodzie.
- `SupplierMaterialMap` zostaje w PR1 źródłem prawdy dla dopasowania faktur i ekranu „Mapowania indeksów" (przełączenie na `supplier_materials` i skasowanie starej tabeli = PR2, razem z importem EINA; PR2 ponawia idempotentną kopię). `Supplier.column_map` zostaje (znika w PR5 razem z przeniesieniem map do wariantów).

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Alembic 1.18 (batch mode dla SQLite), PostgreSQL 16 na prod, pytest; React 19 + Vite + TypeScript, vitest + Testing Library.

## Global Constraints

- Limit **500 linii** na plik `backend/**/*.py`, `frontend/src/**/*.{ts,tsx,css}`, `scripts/*.py` — `python scripts/check_file_lengths.py` (BASELINE pusty, nie dopisywać).
- Teksty UI: **nowe klucze tylko w `frontend/src/i18n/features/<funkcja>.ts`** (`defineFeature({ pl, en, pt })`), wszystkie trzy języki; `i18n.unused.test.ts` wymaga użycia każdego klucza, `i18n.features.test.ts` — unikalności.
- Alembic: **jedna głowa**. Aktualna głowa na `origin/main` w chwili pisania: `kontrole001`. Przed Task 1 sprawdź `python -m pytest tests/test_migration_chain.py -q`; jeśli głowa się zmieniła — ustaw `down_revision` i asercję w teście na nową głowę (nie rób merge-migracji).
- Każda kolumna dodana `op.add_column("tabela", ...)` musi być w `ensure_new_columns()` (`tests/test_dev_schema_shim.py`); migracje tu używają `batch_alter_table`, ale i tak dopisujemy shim (spójność dev).
- Izolacja danych tylko przez `deps.py` (CLAUDE.md repo) — routery nie powielają reguł widoczności.
- Spec: „**SAP = jedyne źródło** danych dostawcy", „**Kod SAP (LIFNR) obowiązkowy i unikalny**" (egzekwowane w etapie B), „Dostawca z powiązaniami — tylko nieaktywny; bez powiązań — admin może usunąć", widoczność: „admin, logistyka, zakupy Acme i Iberia; Borealis, Cobalt Sport, DLT, magazyn, spedytor, agencja — brak dostępu do kartoteki".
- **1 PR = 1 temat**: PR1 = Taski 1–9 (gałąź `claude/kartoteka-dostawcy-1-model` od świeżego `main`); etap B = Task 10 (gałąź `claude/kartoteka-dostawcy-1b-unikalnosci`, PR jako **draft**).
- Przed pushem: `git fetch origin main && git merge origin/main` (merge, nie rebase), testy, `npm run build` (main nie ma ochrony — czerwony build przechodzi przez automerge).
- Jeden `pytest` naraz na worktree (wspólny `test_timporye.db` per cwd).
- Bez nowych zależności.
- Commity kończą się trailerami:
  ```
  Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01DuL7wEFJzFdfPbCLUGEMNU
  ```

---

## Mapa plików

| Plik | Odpowiedzialność | Task |
|---|---|---|
| `backend/migrations/versions/kartoteka001_kartoteka_dostawcow.py` (nowy) | schemat PR1 + kopia map → `supplier_materials` | 1 |
| `backend/app/models/dictionaries.py` | `Supplier` (client_company_id, pola SAP/mapy), `SupplierContact` (rola, komunikator, główny) | 1 |
| `backend/app/models/supplier_catalog.py` (nowy) | `SupplierMaterial`, `SupplierDocVariant`, `SapImport` | 1 |
| `backend/app/models/supplier_profiles.py` | `SupplierDocSample` + sha256/doc_type/variant_id/pages/result/status/reason | 1 |
| `backend/app/models/__init__.py` | re-eksport nowego modułu | 1 |
| `backend/app/db_bootstrap.py` | shim dev dla nowych kolumn | 1 |
| `backend/app/routers/dictionaries_merge.py` | mapy FK (Task 1), `merge_into` + porządki przed scaleniem (Task 4) | 1, 4 |
| `backend/tests/test_kartoteka_migration.py` (nowy) | migracje w izolacji | 1, 10 |
| `backend/app/config.py` | `supplier_company_codes` | 2 |
| `backend/app/deps.py` | reguły widoczności/użycia dostawców | 2 |
| `backend/app/schemas/dictionaries.py` | `SupplierIn`/`SupplierOut` | 2 |
| `backend/app/routers/dictionaries.py` | lista/tworzenie/edycja dostawców | 2 |
| `backend/app/routers/dictionaries_ref.py` | kontakty dostawców | 2, 10 |
| `backend/tests/test_supplier_visibility.py` (nowy) | widoczność per rola/spółka | 2 |
| `backend/app/routers/containers_common.py` | `_check_company_fks` | 3 |
| `backend/app/routers/containers_orders.py` | `_resolve_supplier` (zlecenia) | 3 |
| `backend/app/importers/queue.py` | `resolve_supplier_id` (import kolejki) | 3 |
| `backend/app/invoices/profiles.py` | `detect_supplier` | 3 |
| `backend/app/invoices/matching.py`, `backend/app/supplier_profile_lab.py` | `resolve_supplier_ref` bez spółki dostawcy | 3 |
| `backend/app/routers/supplier_aliases.py` | aliasy per spółka pliku, flaga `catalog`, usunięcie „purge" (Task 3); endpointy „Do rozstrzygnięcia" (Task 6) | 3, 6 |
| `backend/tests/test_supplier_company_rules.py` (nowy) | reguły użycia dostawcy w spółce | 3 |
| `backend/tests/test_supplier_merge_dedupe.py` (nowy) | scalanie: kolizje, kontakty, aliasy | 4 |
| `backend/app/importers/master_data.py`, `backend/app/routers/imports_master.py` | import LFA1 do globalnej kartoteki | 5 |
| `backend/app/master_quality.py` | reguły jakości dostawców bez `company_id` | 5 |
| `backend/scripts/import_lfa1.py` (usunięty), `dedupe_dictionaries.py`, `purge_company.py`, `import_excel.py` | skrypty | 5 |
| `backend/tests/test_import_lfa1.py` (przepisany) | import LFA1 globalnie | 5 |
| `backend/app/supplier_consolidation.py` (nowy) | propozycja scaleń (dry-run) + wykonanie | 6 |
| `backend/scripts/consolidate_suppliers.py` (nowy) | komenda prod | 6 |
| `backend/tests/test_supplier_consolidation.py` (nowy) | serwis, komenda, endpointy | 6 |
| `frontend/src/types/core.ts` | `Supplier.client_company_id` | 7 |
| `frontend/src/pages/MasterDataPage.tsx` | zakładka Dostawcy: właściciel zamiast spółki, panel rozstrzygania | 7, 8 |
| `frontend/src/pages/masterdata/UnmappedSuppliersPanel.tsx` | bez „Wyczyść słownik", alias z `company_id` | 7 |
| `frontend/src/i18n/features/dostawcy-mapowanie.ts` | usunięte klucze purge | 7 |
| `frontend/src/i18n/features/kartoteka-dostawcow.ts` (nowy) | teksty kartoteki i „Do rozstrzygnięcia" | 7, 8 |
| `frontend/src/pages/masterdata/SupplierResolvePanel.tsx` (nowy) | ekran „Do rozstrzygnięcia" | 8 |
| `frontend/src/pages/masterdata/resolve.dom.test.tsx` (nowy) | test ekranu | 8 |
| `backend/migrations/versions/kartoteka002_unikalnosci_kartoteki.py` (nowy) | etap B: unikalności | 10 |

## Wszystkie miejsca z `Supplier.company_id` / filtrowaniem dostawców po spółce

| Miejsce | Obsługa |
|---|---|
| `models/dictionaries.py` `Supplier.company_id`, `UniqueConstraint(company_id, name)` | Task 1: `client_company_id`, unique znika |
| `deps.py` docstring `apply_company_code_filter` („Supplier.company_id") + `_enforce_scope` (Supplier szedł gałęzią `company_id`) | Task 2: nowa gałąź `check_supplier_access`, docstring poprawiony |
| `routers/dictionaries.py` `list_suppliers` (`scope_company`, `apply_company_code_filter`), `create_supplier` (`resolve_company_id`, unique per spółka), `update_supplier` (clash per spółka) | Task 2 |
| `routers/dictionaries_ref.py` `list_supplier_contacts` (`scope_company(Supplier.company_id)`) | Task 2 |
| `routers/dictionaries_merge.py` `SUPPLIERS.company_scoped`, blokada scalania „różne spółki", alias `source.company_id`, dedupe map | Task 4 |
| `routers/containers_common.py` `_check_company_fks` (`s.company_id != company_id`) — używany też przez `routers/invoices.py::_resolve_supplier`, `containers_write.py`, `containers_orders.create_order` | Task 3 |
| `routers/containers_orders.py` `_resolve_supplier` (get-or-create per spółka) | Task 3 |
| `importers/queue.py` `resolve_supplier_id` | Task 3 |
| `invoices/profiles.py` `detect_supplier` | Task 3 |
| `invoices/matching.py` `resolve_supplier_ref` + `supplier_profile_lab.py:98` (`supplier.company_id`) | Task 3 |
| `routers/supplier_aliases.py` `create_alias` (`supplier.company_id`), `unmapped`, `purge_suppliers` | Task 3 (purge usunięty) |
| `importers/master_data.py` `_lfa1_upsert` + `routers/imports_master.py` `import_suppliers_lfa1` (pętla po spółkach) | Task 5 |
| `master_quality.py` 3 reguły dostawców | Task 5 |
| `scripts/import_lfa1.py` | Task 5: usunięty (duplikat endpointu), test przeniesiony |
| `scripts/dedupe_dictionaries.py` (`company_scoped`, grupowanie per spółka) | Task 5: dostawcy wyjęci (zastępuje `consolidate_suppliers`) |
| `scripts/purge_company.py`, `scripts/import_excel.py` | Task 5 |
| `SupplierAlias.company_id` | **zostaje świadomie**: alias to nazwa z pliku kolejki *danej spółki* → dostawca |
| `SupplierMaterialMap.company_id` | **zostaje świadomie** do PR2 (tabela wygaszana; dedupe przy scalaniu poprawiony w Task 4) |
| `routers/supplier_maps.py` | bez zmian (operuje na `SupplierMaterialMap.company_id`, dostawca podawany jawnie) |
| `routers/supplier_profiles.py`, `supplier_samples.py`, `dictionaries.supplier_stats` | bez zmian w kodzie — `get_scoped(Supplier)` dostaje nową gałąź w Task 2 |
| `routers/analytics.py`, `search.py`, `complaints.py`, `invoices/checks.py`, `dictionaries_audit.py` | bez zmian (nie filtrują dostawców po spółce) |
| Front: `MasterDataPage.tsx` (kolumna/filtr spółki, cele scalania, `company_id` w body), `UnmappedSuppliersPanel.tsx` (filtr opcji, purge), `types/core.ts` | Task 7 |
| Front: `FoundOrderModal.tsx`, `QueuePage.tsx` (`?company_code=`), `TrackingPage.tsx`, `components.tsx`, `SupplierMapsTab.tsx`, `SupplierPage.tsx` | bez zmian w kodzie — backend zachowuje kształt odpowiedzi (`company_code` = „dostawcy do użycia w tej spółce") |
| Testy z `Supplier(company_id=...)`: `test_analytics_operational.py:15`, `test_deps_get_scoped.py:19`, `test_documents_search.py:56`, `test_invoices_checks.py:47`, `test_invoices_profile.py:37`, `test_supplier_maps.py:13`, `test_import_lfa1.py:63` | Task 1 (rename), Task 5 (`test_import_lfa1` przepisany) |
| Testy zakładające per spółka: `test_supplier_aliases.py` (purge ×3 + asercja purge), `test_import_autodetect.py::test_lfa1_endpoint_imports_to_all_companies` | Task 3, Task 5 |

---

### Task 1: Schemat kartoteki — modele, migracja `kartoteka001`, shim dev

**Files:**
- Create: `backend/migrations/versions/kartoteka001_kartoteka_dostawcow.py`
- Create: `backend/app/models/supplier_catalog.py`
- Create: `backend/tests/test_kartoteka_migration.py`
- Modify: `backend/app/models/dictionaries.py:4-16` (import `Float`), `:79-113` (`Supplier`, `SupplierContact`)
- Modify: `backend/app/models/supplier_profiles.py:7`, `:36-45` (`SupplierDocSample`)
- Modify: `backend/app/models/__init__.py:18`
- Modify: `backend/app/db_bootstrap.py:210-214` (`extra_tables`)
- Modify: `backend/app/routers/dictionaries_merge.py:15-33`, `:60-68` (mapy FK)
- Modify (rename argumentu): `backend/tests/test_analytics_operational.py:15`, `backend/tests/test_deps_get_scoped.py:19`, `backend/tests/test_documents_search.py:56`, `backend/tests/test_invoices_checks.py:47`, `backend/tests/test_invoices_profile.py:37`, `backend/tests/test_supplier_maps.py:13`

**Interfaces:**
- Produces: `Supplier.client_company_id: int | None` (None = kartoteka), `Supplier.street/city/zip/vat/sap_status/lat/lng/geo_source/shipping_port_id`; `SupplierContact.role/messenger/is_primary`; modele `SupplierMaterial(supplier_id, material_id, supplier_code, sap_status, origin_country, tariff_cn, lead_days, unconfirmed)`, `SupplierDocVariant`, `SapImport`; w migracji funkcja `copy_material_maps(conn) -> int`; w teście helpery `_load(name)`, `_apply(eng, mig, fn, monkeypatch)`, `_engine(tmp_path, statements)` (używa ich Task 10).

> Po tym tasku pełna suita backendu jest czerwona aż do końca Tasku 5 (kod wciąż czyta `Supplier.company_id`). Każdy task uruchamia swoje testy; pełna suita — Task 5 krok końcowy.

- [ ] **Step 1: Gałąź i sprawdzenie głowy alembica**

```bash
git fetch origin
git checkout -b claude/kartoteka-dostawcy-1-model origin/main
cd backend && python -m pytest tests/test_migration_chain.py -q
```
Expected: `3 passed`. Sprawdź, czy `kontrole001` jest nadal głową — nic nie może na nią wskazywać:
Grep (narzędzie) wzorca `down_revision = "kontrole001"` w `backend/migrations/versions/`.
Expected: brak trafień. Jest trafienie → głową jest rewizja z tego pliku (i dalej po łańcuchu, aż do rewizji, na którą nic nie wskazuje); użyj jej jako `down_revision` w Step 4 i w asercji testu (Step 2).

- [ ] **Step 2: Napisz test migracji (failing)**

`backend/tests/test_kartoteka_migration.py`:

```python
"""Migracje kartoteki dostawców (spec 2026-09-25-kartoteka-dostawcy) w izolacji na SQLite —
wzorzec jak test_invoices_migration: pełny łańcuch Alembica jest tylko dla PostgreSQL."""
import importlib.util
import pathlib

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

VERSIONS = pathlib.Path(__file__).resolve().parents[1] / "migrations" / "versions"

# stan sprzed kartoteka001: tylko tabele, których migracja dotyka (kształt jak na prod,
# łącznie z ix_suppliers_sap_code z migracji c3f8a1d7e924 i unique(company_id, name))
PRE_001 = [
    "CREATE TABLE companies (id INTEGER PRIMARY KEY, name VARCHAR(120), code VARCHAR(20))",
    "CREATE TABLE users (id INTEGER PRIMARY KEY)",
    "CREATE TABLE ports (id INTEGER PRIMARY KEY, name VARCHAR(80))",
    "CREATE TABLE materials (id INTEGER PRIMARY KEY, ref_code VARCHAR(100) UNIQUE)",
    "CREATE TABLE suppliers (id INTEGER PRIMARY KEY, name VARCHAR(160) NOT NULL, "
    "company_id INTEGER NOT NULL REFERENCES companies(id), is_active BOOLEAN NOT NULL DEFAULT 1, "
    "address VARCHAR(300) DEFAULT '', note TEXT DEFAULT '', sap_code VARCHAR(20) NOT NULL DEFAULT '', "
    "country VARCHAR(2) NOT NULL DEFAULT '', column_map TEXT NOT NULL DEFAULT '', "
    "UNIQUE (company_id, name))",
    "CREATE INDEX ix_suppliers_sap_code ON suppliers (sap_code)",
    "CREATE TABLE supplier_contacts (id INTEGER PRIMARY KEY, supplier_id INTEGER NOT NULL "
    "REFERENCES suppliers(id), full_name VARCHAR(160) NOT NULL, email VARCHAR(200) DEFAULT '', "
    "phone VARCHAR(60) DEFAULT '', is_active BOOLEAN DEFAULT 1)",
    "CREATE TABLE supplier_material_maps (id INTEGER PRIMARY KEY, company_id INTEGER NOT NULL, "
    "supplier_id INTEGER NOT NULL, supplier_code VARCHAR(120) NOT NULL, ref_code VARCHAR(120) NOT NULL, "
    "note VARCHAR(300) DEFAULT '', created_at DATETIME, updated_at DATETIME, "
    "UNIQUE (company_id, supplier_id, supplier_code))",
    "CREATE TABLE supplier_doc_profiles (id INTEGER PRIMARY KEY, supplier_id INTEGER NOT NULL UNIQUE "
    "REFERENCES suppliers(id) ON DELETE CASCADE)",
    "CREATE TABLE supplier_doc_samples (id INTEGER PRIMARY KEY, profile_id INTEGER NOT NULL "
    "REFERENCES supplier_doc_profiles(id) ON DELETE CASCADE, filename VARCHAR(255) NOT NULL, "
    "stored_path TEXT NOT NULL, created_at DATETIME, last_test JSON NOT NULL DEFAULT '{}', "
    "last_test_at DATETIME)",
    "INSERT INTO companies VALUES (1,'Borealis','BOREALIS'),(2,'Acme','ACME'),(3,'Iberia','PT')",
    # ACME z LFA1 w trzech spółkach (import szedł do każdej) + ręczny nadawca Borealis
    "INSERT INTO suppliers (id, name, company_id, sap_code) VALUES "
    "(1,'ACME',2,'100'),(2,'ACME',3,'100'),(3,'Nadawca T',1,''),(4,'ACME',1,'100')",
    "INSERT INTO materials VALUES (1,'REF1'),(2,'REF2')",
    "INSERT INTO supplier_material_maps (company_id, supplier_id, supplier_code, ref_code) VALUES "
    "(2,1,'A1','REF1'),(3,1,'A0','REF1'),(2,1,'B','REF2'),(2,2,'X','NOPE')",
    "INSERT INTO supplier_doc_profiles VALUES (1,1)",
    "INSERT INTO supplier_doc_samples (profile_id, filename, stored_path) VALUES (1,'a.pdf','x')",
]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), VERSIONS / name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _engine(tmp_path, statements):
    eng = create_engine(f"sqlite:///{tmp_path / 'mig.db'}")
    with eng.begin() as conn:
        for sql in statements:
            conn.exec_driver_sql(sql)
    return eng


def _apply(eng, mig, fn, monkeypatch):
    with eng.connect() as conn:
        monkeypatch.setattr(mig, "op", Operations(MigrationContext.configure(conn)))
        fn()
        conn.commit()


def test_kartoteka001_upgrade_and_downgrade(tmp_path, monkeypatch):
    mig = _load("kartoteka001_kartoteka_dostawcow.py")
    assert mig.down_revision == "kontrole001"          # wpina się na aktualną głowę
    eng = _engine(tmp_path, PRE_001)

    _apply(eng, mig, mig.upgrade, monkeypatch)
    cols = {c["name"] for c in inspect(eng).get_columns("suppliers")}
    assert "company_id" not in cols
    assert {"client_company_id", "street", "city", "zip", "vat", "sap_status", "lat", "lng",
            "geo_source", "shipping_port_id"} <= cols
    assert "ix_suppliers_sap_code" in {i["name"] for i in inspect(eng).get_indexes("suppliers")}
    assert {"role", "messenger", "is_primary"} <= {
        c["name"] for c in inspect(eng).get_columns("supplier_contacts")}
    assert {"supplier_materials", "supplier_doc_variants", "sap_imports"} <= set(
        inspect(eng).get_table_names())
    with eng.connect() as c:
        # Acme i PT → kartoteka (NULL); Borealis → nadawca Borealis (także jego kopia z LFA1)
        assert c.exec_driver_sql(
            "SELECT id, client_company_id FROM suppliers ORDER BY id").all() == [
            (1, None), (2, None), (3, 1), (4, 1)]
        # mapy → indeksy dostawcy: kolizja (dostawca, materiał) = najmniejszy kod,
        # ref_code spoza master data pominięty, znacznik unconfirmed
        assert c.exec_driver_sql(
            "SELECT supplier_id, material_id, supplier_code, unconfirmed "
            "FROM supplier_materials ORDER BY 1, 2").all() == [(1, 1, "A0", 1), (1, 2, "B", 1)]
        assert c.exec_driver_sql(
            "SELECT status, doc_type, reason FROM supplier_doc_samples").all() == [("ok", "", "")]
        # unique(company_id, name) zniknął razem z kolumną
        c.exec_driver_sql("INSERT INTO suppliers (name) VALUES ('ACME')")
        assert mig.copy_material_maps(c) == 0          # idempotentne
        c.commit()

    _apply(eng, mig, mig.downgrade, monkeypatch)
    insp = inspect(eng)
    assert "supplier_materials" not in insp.get_table_names()
    assert "client_company_id" not in {c["name"] for c in insp.get_columns("suppliers")}
    with eng.connect() as c:
        # stratnie: kartoteka wraca do Acme (id=2), nadawcy — do swojej spółki
        assert c.exec_driver_sql(
            "SELECT id, company_id FROM suppliers WHERE id <= 4 ORDER BY id").all() == [
            (1, 2), (2, 2), (3, 1), (4, 1)]
    eng.dispose()
```

- [ ] **Step 3: Uruchom — ma paść**

Run: `cd backend && python -m pytest tests/test_kartoteka_migration.py -q`
Expected: FAIL — `FileNotFoundError` / `No such file` dla `kartoteka001_kartoteka_dostawcow.py`.

- [ ] **Step 4: Napisz migrację**

`backend/migrations/versions/kartoteka001_kartoteka_dostawcow.py`:

```python
"""Kartoteka dostawców (PR1, spec 2026-09-25-kartoteka-dostawcy): suppliers globalne —
company_id → client_company_id (ustawione tylko dla nadawców spółek-klientów), pola SAP/mapy,
kontakty z rolą, supplier_materials (kopia supplier_material_maps jako unconfirmed), warianty
układu dokumentów, rozbudowa próbek, dziennik importów SAP.

Scalanie dubli NIE tutaj: podgląd + wykonanie w app/supplier_consolidation.py (ekran „Do
rozstrzygnięcia", scripts/consolidate_suppliers.py). Unikalności — kartoteka002 (etap B).

Revision ID: kartoteka001
Revises: kontrole001
"""
import datetime

import sqlalchemy as sa
from alembic import op

revision = "kartoteka001"
down_revision = "kontrole001"
branch_labels = None
depends_on = None

# spółki pracujące na materiałach Acme w chwili migracji (w aplikacji: settings.supplier_company_codes)
MATERIAL_CODES = ("ACME", "PT")


def upgrade() -> None:
    with op.batch_alter_table("suppliers") as b:
        b.add_column(sa.Column("client_company_id", sa.Integer, nullable=True))
        b.add_column(sa.Column("street", sa.String(160), nullable=False, server_default=""))
        b.add_column(sa.Column("city", sa.String(80), nullable=False, server_default=""))
        b.add_column(sa.Column("zip", sa.String(20), nullable=False, server_default=""))
        b.add_column(sa.Column("vat", sa.String(30), nullable=False, server_default=""))
        b.add_column(sa.Column("sap_status", sa.String(20), nullable=False, server_default="active"))
        b.add_column(sa.Column("lat", sa.Float, nullable=True))
        b.add_column(sa.Column("lng", sa.Float, nullable=True))
        b.add_column(sa.Column("geo_source", sa.String(10), nullable=False, server_default="none"))
        b.add_column(sa.Column("shipping_port_id", sa.Integer, nullable=True))
    # nadawcy spółek-klientów (Borealis, Cobalt…) zostają przy swojej spółce; reszta = kartoteka
    op.execute(sa.text(
        "UPDATE suppliers SET client_company_id = company_id WHERE company_id IN "
        "(SELECT id FROM companies WHERE code NOT IN :codes)"
    ).bindparams(sa.bindparam("codes", MATERIAL_CODES, expanding=True)))
    with op.batch_alter_table("suppliers") as b:
        # PG: DROP COLUMN zdejmuje też FK i unique(company_id, name); SQLite: batch przebudowuje
        # tabelę bez ograniczeń na usuniętej kolumnie. ix_suppliers_sap_code (c3f8a1d7e924) zostaje.
        b.drop_column("company_id")
        b.create_foreign_key("fk_suppliers_client_company_id", "companies",
                             ["client_company_id"], ["id"])
        b.create_foreign_key("fk_suppliers_shipping_port_id", "ports", ["shipping_port_id"], ["id"])
        b.create_index("ix_suppliers_client_company_id", ["client_company_id"])

    with op.batch_alter_table("supplier_contacts") as b:
        b.add_column(sa.Column("role", sa.String(20), nullable=False, server_default="other"))
        b.add_column(sa.Column("messenger", sa.String(120), nullable=False, server_default=""))
        b.add_column(sa.Column("is_primary", sa.Boolean, nullable=False, server_default=sa.false()))

    op.create_table(
        "supplier_materials",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("supplier_id", sa.Integer, sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("material_id", sa.Integer, sa.ForeignKey("materials.id"), nullable=False),
        sa.Column("supplier_code", sa.String(120), nullable=False, server_default=""),
        sa.Column("sap_status", sa.String(20), nullable=False, server_default=""),
        sa.Column("origin_country", sa.String(2), nullable=False, server_default=""),
        sa.Column("tariff_cn", sa.String(30), nullable=False, server_default=""),
        sa.Column("lead_days", sa.Integer, nullable=True),
        sa.Column("unconfirmed", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("supplier_id", "material_id",
                            name="uq_supplier_materials_supplier_material"),
    )
    op.create_index("ix_supplier_materials_supplier_code", "supplier_materials",
                    ["supplier_id", "supplier_code"])
    op.create_index("ix_supplier_materials_material_id", "supplier_materials", ["material_id"])
    copy_material_maps(op.get_bind())

    op.create_table(
        "supplier_doc_variants",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("profile_id", sa.Integer,
                  sa.ForeignKey("supplier_doc_profiles.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("doc_type", sa.String(4), nullable=False),
        sa.Column("fingerprint", sa.JSON, nullable=False),
        sa.Column("column_map", sa.JSON, nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="proposed"),
        sa.Column("docs_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("ok_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("ref_hit_pct", sa.Float, nullable=True),
        sa.Column("approved_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
    )
    with op.batch_alter_table("supplier_doc_samples") as b:
        b.add_column(sa.Column("sha256", sa.String(64), nullable=True))
        b.add_column(sa.Column("doc_type", sa.String(4), nullable=False, server_default=""))
        b.add_column(sa.Column("variant_id", sa.Integer, nullable=True))
        b.add_column(sa.Column("pages", sa.JSON, nullable=True))
        b.add_column(sa.Column("result", sa.JSON, nullable=True))
        b.add_column(sa.Column("status", sa.String(12), nullable=False, server_default="ok"))
        b.add_column(sa.Column("reason", sa.String(300), nullable=False, server_default=""))
    with op.batch_alter_table("supplier_doc_samples") as b:
        b.create_foreign_key("fk_supplier_doc_samples_variant_id", "supplier_doc_variants",
                             ["variant_id"], ["id"], ondelete="SET NULL")
        b.create_unique_constraint("uq_supplier_doc_samples_profile_sha", ["profile_id", "sha256"])

    op.create_table(
        "sap_imports",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False, server_default=""),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("counts", sa.JSON, nullable=False),
        sa.Column("errors", sa.JSON, nullable=False),
    )


def copy_material_maps(conn) -> int:
    """supplier_material_maps (per spółka, ref_code tekstem) → supplier_materials (per dostawca,
    material_id) ze znacznikiem unconfirmed. Idempotentne (PR2 ponawia przed przełączeniem
    dopasowania faktur); mapy bez materiału w master data zostają tylko w starej tabeli.
    Kolizja (dostawca, materiał) z kilku spółek/kodów → najmniejszy kod dostawcy."""
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    return conn.execute(sa.text(
        "INSERT INTO supplier_materials (supplier_id, material_id, supplier_code, sap_status, "
        "origin_country, tariff_cn, unconfirmed, created_at, updated_at) "
        "SELECT m.supplier_id, mat.id, MIN(m.supplier_code), '', '', '', :yes, :now, :now "
        "FROM supplier_material_maps m JOIN materials mat ON mat.ref_code = m.ref_code "
        "WHERE NOT EXISTS (SELECT 1 FROM supplier_materials sm "
        "WHERE sm.supplier_id = m.supplier_id AND sm.material_id = mat.id) "
        "GROUP BY m.supplier_id, mat.id"
    ).bindparams(yes=True, now=now)).rowcount


def downgrade() -> None:
    """Stratne: scalonych dostawców nie da się rozdzielić z powrotem na spółki — kartoteka
    wraca do spółki ACME, nadawcy klientów do swojej spółki (bez unique(company_id, name))."""
    op.drop_table("sap_imports")
    with op.batch_alter_table("supplier_doc_samples") as b:
        b.drop_constraint("uq_supplier_doc_samples_profile_sha", type_="unique")
        b.drop_constraint("fk_supplier_doc_samples_variant_id", type_="foreignkey")
        for col in ("reason", "status", "result", "pages", "variant_id", "doc_type", "sha256"):
            b.drop_column(col)
    op.drop_table("supplier_doc_variants")
    op.drop_table("supplier_materials")
    with op.batch_alter_table("supplier_contacts") as b:
        for col in ("is_primary", "messenger", "role"):
            b.drop_column(col)
    with op.batch_alter_table("suppliers") as b:
        b.add_column(sa.Column("company_id", sa.Integer, nullable=True))
    op.execute("UPDATE suppliers SET company_id = COALESCE(client_company_id, "
               "(SELECT id FROM companies WHERE code = 'ACME'))")
    with op.batch_alter_table("suppliers") as b:
        b.drop_index("ix_suppliers_client_company_id")
        b.drop_constraint("fk_suppliers_shipping_port_id", type_="foreignkey")
        b.drop_constraint("fk_suppliers_client_company_id", type_="foreignkey")
        for col in ("shipping_port_id", "geo_source", "lng", "lat", "sap_status", "vat", "zip",
                    "city", "street", "client_company_id"):
            b.drop_column(col)
        b.create_foreign_key("fk_suppliers_company_id", "companies", ["company_id"], ["id"])
```

- [ ] **Step 5: Modele — `Supplier` i `SupplierContact`**

W `backend/app/models/dictionaries.py` dodaj `Float,` do importu z `sqlalchemy` (alfabetycznie po `Enum,`). Zastąp klasy `Supplier` i `SupplierContact` (linie 79–113):

```python
class Supplier(Base):
    """Dostawca. `client_company_id` NULL = globalna kartoteka dostawców Acme (spółki na jego
    materiałach, settings.supplier_company_codes); ustawione = nadawca kontenerów spółki-klienta
    (Borealis, Cobalt…), widoczny tylko dla tej spółki. Spec 2026-09-25-kartoteka-dostawcy."""
    __tablename__ = "suppliers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    client_company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id"), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # sklejka adresu do wyświetlenia (składowe z SAP niżej); kontakty osobowe w SupplierContact
    address: Mapped[str] = mapped_column(String(300), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    # kod dostawcy z SAP (LIFNR) — klucz importu LFA1. "" = brak (nadawca klienta albo rekord
    # „do rozstrzygnięcia"); unikalność w kartotece zakłada migracja kartoteka002 (etap B)
    sap_code: Mapped[str] = mapped_column(String(20), default="", server_default=text("''"),
                                          index=True)
    country: Mapped[str] = mapped_column(String(2), default="", server_default=text("''"))
    street: Mapped[str] = mapped_column(String(160), default="", server_default=text("''"))
    city: Mapped[str] = mapped_column(String(80), default="", server_default=text("''"))
    zip: Mapped[str] = mapped_column(String(20), default="", server_default=text("''"))
    vat: Mapped[str] = mapped_column(String(30), default="", server_default=text("''"))
    # active | blocked | inactive_in_sap (zniknął z pliku SAP — nigdy nie kasujemy)
    sap_status: Mapped[str] = mapped_column(String(20), default="active",
                                            server_default=text("'active'"))
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    geo_source: Mapped[str] = mapped_column(String(10), default="none",
                                            server_default=text("'none'"))  # geocode|manual|none
    shipping_port_id: Mapped[int | None] = mapped_column(ForeignKey("ports.id"), nullable=True)
    # mapa kolumn faktury tego dostawcy dla ekstrakcji PDF → Excel (invoices/extractor):
    # "ref=Item No.; qty=Q'ty; net=Amount". Puste = auto-detekcja nagłówków. Znika w PR5
    # (mapy przechodzą do wariantów układu dokumentów).
    column_map: Mapped[str] = mapped_column(Text, default="", server_default=text("''"))
    # profil dokumentów (CI + PL) — zastępuje column_map (czytane zapasowo do usunięcia)
    # cascade jak przy Port.transit_rows: bez tego ORM przy delete(supplier) próbowałby
    # wyzerować supplier_id (NOT NULL) zamiast skasować profil — wywalało to scalanie
    # dostawców z profilem dokumentów, patrz dictionaries_merge._supplier_premerge.
    doc_profile: Mapped["SupplierDocProfile | None"] = relationship(  # noqa: F821
        back_populates="supplier", uselist=False, cascade="all, delete-orphan")


class SupplierContact(Base):
    """Kontakt u dostawcy: osoba, rola, e-mail, telefon, komunikator."""
    __tablename__ = "supplier_contacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    role: Mapped[str] = mapped_column(String(20), default="other",
                                      server_default=text("'other'"))  # sales|logistics|quality|other
    email: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(60), default="")
    messenger: Mapped[str] = mapped_column(String(120), default="",
                                           server_default=text("''"))  # np. „WeChat: xxx"
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    supplier: Mapped[Supplier] = relationship()
```

- [ ] **Step 6: Modele — nowy moduł i próbki**

`backend/app/models/supplier_catalog.py`:

```python
"""Kartoteka dostawców (spec 2026-09-25-kartoteka-dostawcy): indeksy dostawcy z SAP (EINA),
warianty układu dokumentów, dziennik importów z SAP. PR1 = schemat; wypełnia je import SAP
(PR2) i masowe dokumenty (PR5)."""
import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .enums import utcnow

__all__ = ["SapImport", "SupplierDocVariant", "SupplierMaterial"]


class SupplierMaterial(Base):
    """Indeks dostawcy: dostawca + nasz materiał + kod artykułu u dostawcy (SAP EINA).
    `unconfirmed` = przeniesione z ręcznego SupplierMaterialMap, czeka na potwierdzenie
    importem EINA. `lead_days` — jedyne pole prowadzone w aplikacji."""
    __tablename__ = "supplier_materials"
    __table_args__ = (
        UniqueConstraint("supplier_id", "material_id",
                         name="uq_supplier_materials_supplier_material"),
        Index("ix_supplier_materials_supplier_code", "supplier_id", "supplier_code"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), index=True)
    supplier_code: Mapped[str] = mapped_column(String(120), default="", server_default=text("''"))
    sap_status: Mapped[str] = mapped_column(String(20), default="", server_default=text("''"))
    origin_country: Mapped[str] = mapped_column(String(2), default="", server_default=text("''"))
    tariff_cn: Mapped[str] = mapped_column(String(30), default="", server_default=text("''"))
    lead_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unconfirmed: Mapped[bool] = mapped_column(Boolean, default=False,
                                              server_default=text("false"))
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow)


class SupplierDocVariant(Base):
    """Wariant układu dokumentu (CI/PL) w profilu dostawcy: odcisk nagłówków + mapa kolumn."""
    __tablename__ = "supplier_doc_variants"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("supplier_doc_profiles.id", ondelete="CASCADE"), index=True)
    doc_type: Mapped[str] = mapped_column(String(4))                     # ci | pl
    fingerprint: Mapped[dict] = mapped_column(JSON, default=dict)
    column_map: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(10), default="proposed",
                                        server_default=text("'proposed'"))  # proposed|approved|rejected
    docs_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    ok_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    ref_hit_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=utcnow)


class SapImport(Base):
    """Dziennik importów z SAP (lfa1 | eina | materials): kto, kiedy, plik, liczniki, błędy."""
    __tablename__ = "sap_imports"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    filename: Mapped[str] = mapped_column(String(255), default="", server_default=text("''"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, default=utcnow)
    counts: Mapped[dict] = mapped_column(JSON, default=dict)
    errors: Mapped[list] = mapped_column(JSON, default=list)
```

W `backend/app/models/__init__.py` po linii `from .supplier_aliases import *  # noqa: F401,F403` dodaj:

```python
from .supplier_catalog import *  # noqa: F401,F403
```

W `backend/app/models/supplier_profiles.py` zmień import na
`from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text, UniqueConstraint`
i zastąp klasę `SupplierDocSample`:

```python
class SupplierDocSample(Base):
    __tablename__ = "supplier_doc_samples"
    # ten sam plik (sha256) raz na dostawcę — profil jest 1:1 z dostawcą
    __table_args__ = (UniqueConstraint("profile_id", "sha256",
                                       name="uq_supplier_doc_samples_profile_sha"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("supplier_doc_profiles.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    last_test: Mapped[dict] = mapped_column(JSON, default=dict)
    last_test_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    # masowe wgrywanie (PR5): deduplikacja, typ dokumentu, wariant układu, wynik, status
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    doc_type: Mapped[str] = mapped_column(String(4), default="", server_default="")   # ci | pl
    variant_id: Mapped[int | None] = mapped_column(
        ForeignKey("supplier_doc_variants.id", ondelete="SET NULL"), nullable=True)
    pages: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # queued | ok | review | rejected | duplicate (dotychczasowe próbki kreatora = ok)
    status: Mapped[str] = mapped_column(String(12), default="ok", server_default="ok")
    reason: Mapped[str] = mapped_column(String(300), default="", server_default="")
    profile: Mapped[SupplierDocProfile] = relationship(back_populates="samples")
```

- [ ] **Step 7: Shim dev + mapy FK scalania**

W `backend/app/db_bootstrap.py`, w słowniku `extra_tables`, zastąp wpis `'suppliers': {...}` i dopisz dwa nowe:

```python
        'suppliers': {'address': "VARCHAR(300) DEFAULT ''",
                      'note': "TEXT DEFAULT ''",
                      'sap_code': "VARCHAR(20) DEFAULT ''",
                      'country': "VARCHAR(2) DEFAULT ''",
                      'column_map': "TEXT DEFAULT ''",
                      # kartoteka dostawców (kartoteka001). Uwaga dev: stara baza SQLite ma
                      # suppliers.company_id NOT NULL — shim go nie zdejmie; usuń timporye.db
                      'client_company_id': "INTEGER",
                      'street': "VARCHAR(160) DEFAULT ''",
                      'city': "VARCHAR(80) DEFAULT ''",
                      'zip': "VARCHAR(20) DEFAULT ''",
                      'vat': "VARCHAR(30) DEFAULT ''",
                      'sap_status': "VARCHAR(20) DEFAULT 'active'",
                      'lat': "FLOAT",
                      'lng': "FLOAT",
                      'geo_source': "VARCHAR(10) DEFAULT 'none'",
                      'shipping_port_id': "INTEGER"},
        'supplier_contacts': {'role': "VARCHAR(20) DEFAULT 'other'",
                              'messenger': "VARCHAR(120) DEFAULT ''",
                              'is_primary': "BOOLEAN DEFAULT 0"},
        'supplier_doc_samples': {'sha256': "VARCHAR(64)",
                                 'doc_type': "VARCHAR(4) DEFAULT ''",
                                 'variant_id': "INTEGER",
                                 'pages': "JSON",
                                 'result': "JSON",
                                 'status': "VARCHAR(12) DEFAULT 'ok'",
                                 'reason': "VARCHAR(300) DEFAULT ''"},
```

W `backend/app/routers/dictionaries_merge.py` dodaj `SupplierMaterial,` do importu z `..models` (po `SupplierDocProfile,`) i zmień mapy:

```python
PORTS = _Dict(Port, "port", ((Container, "port_id"), (Order, "departure_port_id"),
                             (Supplier, "shipping_port_id")),
              owned=("port_transit_times",))
SUPPLIERS = _Dict(Supplier, "dostawca",
                  ((Container, "supplier_id"), (Order, "supplier_id"),
                   (SupplierContact, "supplier_id"), (InvoiceBatch, "supplier_id"),
                   (SupplierMaterialMap, "supplier_id"), (SupplierAlias, "supplier_id"),
                   (SupplierMaterial, "supplier_id")),
                  company_scoped=True,
                  owned=("supplier_doc_profiles",),
                  copy_fields=("sap_code", "country", "address", "note", "column_map"))
```

- [ ] **Step 8: Rename argumentu w testach budujących `Supplier` wprost**

W każdym z plików zamień `company_id=` na `client_company_id=` **tylko w konstruktorze `Supplier(...)`**:
- `backend/tests/test_analytics_operational.py:15` → `Supplier(client_company_id=company.id, name="Dostawca A")`
- `backend/tests/test_deps_get_scoped.py:19` → `Supplier(name="GS-SB", client_company_id=b.id)`
- `backend/tests/test_documents_search.py:56` → `Supplier(name="Tajny Dostawca", client_company_id=co.id)`
- `backend/tests/test_invoices_checks.py:47` → `Supplier(name="Acme", client_company_id=company.id)`
- `backend/tests/test_invoices_profile.py:37` → `Supplier(name=name, client_company_id=company.id, column_map="ref=Old Code; qty=Pieces")`
- `backend/tests/test_supplier_maps.py:13` → `Supplier(name="Dostawca Mapowy", client_company_id=company.id)`

(`test_import_lfa1.py` przepisuje Task 5.)

- [ ] **Step 9: Uruchom testy tasku**

Run: `cd backend && python -m pytest tests/test_kartoteka_migration.py tests/test_migration_chain.py tests/test_dev_schema_shim.py "tests/test_dictionaries.py::test_merge_map_covers_all_foreign_keys" tests/test_missing_indexes.py -q`
Expected: wszystkie PASS (test migracji, jedna głowa `kartoteka001`, mapa scalania zgodna z FK).

- [ ] **Step 10: Commit**

```bash
git add backend/migrations/versions/kartoteka001_kartoteka_dostawcow.py backend/app/models/ backend/app/db_bootstrap.py backend/app/routers/dictionaries_merge.py backend/tests/
git commit -m "feat(dostawcy): schemat globalnej kartoteki dostawców (kartoteka001)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DuL7wEFJzFdfPbCLUGEMNU"
```

---

### Task 2: Widoczność kartoteki w `deps.py` + lista/tworzenie/kontakty

**Files:**
- Modify: `backend/app/config.py` (po linii `invoice_tolerance_pct: float = Field(default=2.0, ge=0)`)
- Modify: `backend/app/deps.py:1-24` (importy, docstring), nowa sekcja po `check_company_access` (linia 148), `_enforce_scope` (linia 199–244)
- Modify: `backend/app/schemas/dictionaries.py:33-48`
- Modify: `backend/app/routers/dictionaries.py:13-34`, `:73-120`
- Modify: `backend/app/routers/dictionaries_ref.py:23`, `:157-170`
- Create: `backend/tests/test_supplier_visibility.py`

**Interfaces:**
- Consumes: `Supplier.client_company_id` (Task 1).
- Produces (w `app/deps.py`): `CATALOG_ROLES`, `material_company_codes() -> set[str]`, `is_material_company(company: Company | None) -> bool`, `supplier_clause_for_company(company: Company)` (klauzula SQL), `supplier_catalog_access(user: User) -> bool`, `scope_suppliers(query, user: User)`, `filter_suppliers_by_company_code(query, db, company_code, exclude_company_code)`, `check_supplier_access(user: User, supplier: Supplier) -> None`; `settings.supplier_company_codes: str`; `SupplierOut.client_company_id: int | None`.

- [ ] **Step 1: Napisz test (failing)**

`backend/tests/test_supplier_visibility.py`:

```python
"""Widoczność kartoteki dostawców (spec 2026-09-25 §2 „Widoczność"): reguła w deps.py,
kody spółek „z materiałami" z ustawień (SUPPLIER_COMPANY_CODES)."""
from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models import Company, Role, Supplier, SupplierContact, User, Warehouse
from app.security import hash_password
from tests.conftest import forwarder, login


def _co(db, code):
    return db.scalar(select(Company).where(Company.code == code))


def _seed():
    with SessionLocal() as db:
        acme, pt, borealis = (_co(db, c) for c in ("ACME", "PT", "BOREALIS"))
        cat = Supplier(name="Kartoteka Co", sap_code="500100", address="Ningbo, CN")
        tim = Supplier(name="Nadawca Borealis", client_company_id=borealis.id, address="Adres T")
        wh = Warehouse(name="WH-Z", company_id=acme.id)
        db.add_all([cat, tim, wh])
        db.flush()
        db.add(SupplierContact(supplier_id=cat.id, full_name="Li", email="li@k.example"))
        for login_, role, cid, whid in (("vis-pt-zak", Role.purchasing, pt.id, None),
                                        ("vis-t-log", Role.logistics, borealis.id, None),
                                        ("vis-z-wh", Role.warehouse, acme.id, wh.id)):
            db.add(User(login=login_, hashed_password=hash_password("pass12345"), role=role,
                        company_id=cid, warehouse_id=whid))
        db.commit()
        return cat.id, tim.id


def _rows(client, hdr):
    return {s["name"]: s for s in client.get("/api/suppliers", headers=hdr).json()}


def test_material_company_purchasing_sees_catalog_with_details(client):
    cat, _ = _seed()
    hdr = login(client, "vis-pt-zak", "pass12345")
    rows = _rows(client, hdr)
    assert "Kartoteka Co" in rows and "Nadawca Borealis" not in rows
    assert rows["Kartoteka Co"]["sap_code"] == "500100"
    assert rows["Kartoteka Co"]["client_company_id"] is None
    assert client.get(f"/api/suppliers/{cat}/stats", headers=hdr).status_code == 200
    contacts = client.get(f"/api/supplier-contacts?supplier_id={cat}", headers=hdr).json()
    assert [c["full_name"] for c in contacts] == ["Li"]


def test_client_company_sees_only_own_senders(client):
    cat, tim = _seed()
    hdr = login(client, "vis-t-log", "pass12345")
    assert set(_rows(client, hdr)) == {"Nadawca Borealis"}
    assert client.get(f"/api/suppliers/{cat}/stats", headers=hdr).status_code == 404
    assert client.get(f"/api/suppliers/{tim}/stats", headers=hdr).status_code == 200
    assert client.get("/api/supplier-contacts", headers=hdr).json() == []


def test_warehouse_of_material_company_gets_names_only(client):
    cat, _ = _seed()
    hdr = login(client, "vis-z-wh", "pass12345")
    row = _rows(client, hdr)["Kartoteka Co"]
    assert row["sap_code"] == "" and row["address"] == ""
    assert client.get(f"/api/suppliers/{cat}/stats", headers=hdr).status_code == 404


def test_forwarder_gets_names_without_details(client, admin_headers):
    _seed()
    spedalfa = forwarder(client, admin_headers, "SPEDALFA")["id"]
    client.post("/api/users", headers=admin_headers, json={
        "login": "vis.fwd", "password": "haslo123", "role": "forwarder",
        "forwarder_id": spedalfa, "email": "vis.fwd@example.com"})
    rows = _rows(client, login(client, "vis.fwd", "haslo123"))
    assert rows["Kartoteka Co"]["sap_code"] == "" and rows["Nadawca Borealis"]["address"] == ""


def test_material_company_codes_come_from_settings(client, monkeypatch):
    _seed()
    monkeypatch.setattr(settings, "supplier_company_codes", "ACME")
    assert "Kartoteka Co" not in _rows(client, login(client, "vis-pt-zak", "pass12345"))


def test_create_maps_company_to_catalog_or_client_sender(client, admin_headers):
    with SessionLocal() as db:
        acme, borealis = _co(db, "ACME").id, _co(db, "BOREALIS").id
    a = client.post("/api/suppliers", headers=admin_headers,
                    json={"name": "Nowy K", "company_id": acme}).json()
    b = client.post("/api/suppliers", headers=admin_headers,
                    json={"name": "Nowy K", "company_id": borealis}).json()
    c = client.post("/api/suppliers", headers=admin_headers, json={"name": "Bez spółki"}).json()
    assert (a["client_company_id"], b["client_company_id"], c["client_company_id"]) == (
        None, borealis, None)
    # ta sama nazwa w kartotece → 409 (spółka z materiałami i brak spółki = ta sama kartoteka)
    assert client.post("/api/suppliers", headers=admin_headers,
                       json={"name": "Nowy K"}).status_code == 409
```

- [ ] **Step 2: Uruchom — ma paść**

Run: `cd backend && python -m pytest tests/test_supplier_visibility.py -q`
Expected: FAIL (`AttributeError: type object 'Supplier' has no attribute 'company_id'` z `list_suppliers`, `client_company_id` brak w odpowiedzi).

- [ ] **Step 3: Ustawienie**

W `backend/app/config.py` po linii `invoice_tolerance_pct: float = Field(default=2.0, ge=0)` dodaj:

```python
    # kartoteka dostawców (spec 2026-09-25): kody spółek (Company.code, CSV) pracujących na
    # materiałach Acme — widzą i używają globalnej kartoteki. Pozostałe (Borealis, Cobalt…)
    # mają tylko własnych nadawców kontenerów (Supplier.client_company_id). Env: SUPPLIER_COMPANY_CODES
    supplier_company_codes: str = "ACME,PT"
```

- [ ] **Step 4: Reguły w `deps.py`**

Zmień nagłówek importów `backend/app/deps.py`:

```python
from fastapi import Depends, HTTPException, status
from sqlalchemy import false, or_, select
from sqlalchemy.orm import Session

from .config import settings
from .models import Company, Container, Role, Supplier, User
from .security import can_view_all, get_current_user, require_roles
```

W docstringu `apply_company_code_filter` zamień zdanie „Wspólne dla kolejki (Container.company_id) i słowników (Supplier.company_id) —" na „Wspólne dla kolejki (Container.company_id) i słowników z company_id (magazyny) — dostawcy mają własny `filter_suppliers_by_company_code` —".

Po funkcji `check_company_access` (przed `get_company_by_code`) wstaw:

```python
# --- kartoteka dostawców (spec 2026-09-25-kartoteka-dostawcy §2 „Widoczność") ---
# Kartoteka (Supplier.client_company_id IS NULL) należy do Acme i spółek pracujących na jego
# materiałach (settings.supplier_company_codes). Nadawcy spółek-klientów (client_company_id =
# spółka) są widoczni tylko dla tej spółki. Routery wołają wyłącznie te funkcje.

CATALOG_ROLES = (Role.admin, Role.logistics, Role.purchasing)


def material_company_codes() -> set[str]:
    return {c.strip().upper() for c in settings.supplier_company_codes.split(",") if c.strip()}


def is_material_company(company: Company | None) -> bool:
    return company is not None and company.code.upper() in material_company_codes()


def supplier_clause_for_company(company: Company):
    """Dostawcy, których wolno użyć w rekordach spółki (kontener, zamówienie, alias, faktura):
    jej nadawcy + kartoteka, gdy spółka pracuje na materiałach Acme."""
    own = Supplier.client_company_id == company.id
    return or_(Supplier.client_company_id.is_(None), own) if is_material_company(company) else own


def supplier_catalog_access(user: User) -> bool:
    """Szczegóły kartoteki (adres, kod SAP, kontakty, profil, statystyki): admin, logistyka,
    zakupy — konta grupowe albo spółki z materiałami. Magazyn, spedytor, agencja, klienci: nie."""
    if user.role not in CATALOG_ROLES:
        return False
    return can_view_all(user) or is_material_company(user.company)


def scope_suppliers(query, user: User):
    """Lista dostawców (listy wyboru, filtry kolejki). Spedytor i konta grupowe — wszyscy
    (spedytor i konta bez dostępu do kartoteki dostają same nazwy — list_suppliers); konto
    spółki — jej nadawcy + kartoteka, gdy spółka pracuje na materiałach Acme."""
    if user.role == Role.forwarder or can_view_all(user):
        return query
    own = Supplier.client_company_id.in_(company_filter_ids(user))
    if is_material_company(user.company):
        return query.where(or_(Supplier.client_company_id.is_(None), own))
    return query.where(own)


def filter_suppliers_by_company_code(query, db: Session, company_code: str | None,
                                     exclude_company_code: str | None):
    """Zakładka/moduł spółki na liście dostawców: `company_code` = dostawcy do użycia w tej
    spółce; `exclude_company_code` = wszyscy poza nimi. Nieznany kod = pusty wynik."""
    if company_code:
        company = db.scalar(select(Company).where(Company.code == company_code))
        query = query.where(supplier_clause_for_company(company) if company else false())
    if exclude_company_code:
        company = db.scalar(select(Company).where(Company.code == exclude_company_code))
        if company:
            query = query.where(Supplier.id.not_in(
                select(Supplier.id).where(supplier_clause_for_company(company))))
    return query


def check_supplier_access(user: User, supplier: Supplier) -> None:
    """Dostęp do jednego dostawcy (404 jak brak — bez enumeracji)."""
    if supplier.client_company_id is not None:
        return check_company_access(user, supplier.client_company_id)
    if not supplier_catalog_access(user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono.")
```

W `_enforce_scope` dopisz gałąź tuż przed `container_id = getattr(obj, "container_id", None)`:

```python
    if isinstance(obj, Supplier):
        # dostawca nie ma company_id: kartoteka (reguła ról/spółek) albo nadawca klienta
        return check_supplier_access(user, obj)
```

oraz w docstringu `_enforce_scope` dodaj punkt: `- Supplier → check_supplier_access (kartoteka / nadawca spółki-klienta),`.

- [ ] **Step 5: Schematy**

W `backend/app/schemas/dictionaries.py` zastąp `SupplierIn` i `SupplierOut`:

```python
class SupplierIn(NamedIn):
    # tylko przy tworzeniu: spółka-klient → nadawca tej spółki; spółka z materiałami Acme
    # albo brak → kartoteka (deps.is_material_company). PATCH ignoruje.
    company_id: int | None = None
    address: str = ""
    note: str = ""
    # mapa kolumn faktur tego dostawcy: "ref=Item No.; qty=Q'ty; net=Amount" (puste = auto)
    column_map: str = Field(default="", max_length=2000)


class SupplierOut(NamedOut):
    # None = kartoteka dostawców Acme; id = nadawca kontenerów tej spółki-klienta
    client_company_id: int | None = None
    is_active: bool
    address: str = ""
    note: str = ""
    column_map: str = ""
    sap_code: str = ""   # LIFNR z importu LFA1 (przeglądarka master data)
    country: str = ""
```

- [ ] **Step 6: Router słowników**

W `backend/app/routers/dictionaries.py` zamień blok `from ..deps import (apply_company_code_filter, get_scoped, resolve_company_id, scope_company, scope_containers,)` na:

```python
from ..deps import (
    apply_company_code_filter,
    filter_suppliers_by_company_code,
    get_scoped,
    is_material_company,
    resolve_company_id,
    scope_company,
    scope_containers,
    scope_suppliers,
    supplier_catalog_access,
)
```

i dodaj `Company,` do importu z `..models` (przed `Container,`). Zastąp `list_suppliers`, `create_supplier`, `update_supplier`:

```python
@router.get("/suppliers", response_model=list[SupplierOut])
def list_suppliers(db: Session = Depends(get_db), user: User = viewer,
                   company_code: str | None = None,
                   exclude_company_code: str | None = None,
                   include_inactive: bool = False):
    # jak przy portach: panel admina musi widzieć też dezaktywowanych, by móc ich przywrócić
    q = select(Supplier).order_by(Supplier.name)
    if not include_inactive:
        q = q.where(Supplier.is_active)
    q = scope_suppliers(q, user)
    # zawężenie do modułu/zakładki spółki (dostawcy do użycia w tej spółce)
    q = filter_suppliers_by_company_code(q, db, company_code, exclude_company_code)
    rows = db.scalars(q).all()
    full = supplier_catalog_access(user)
    # bez dostępu do kartoteki (magazyn, agencja, spedytor) — same nazwy do list wyboru i filtrów;
    # spedytor nie dostaje też szczegółów nadawców klientów
    return [s if (full if s.client_company_id is None else user.role != Role.forwarder)
            else SupplierOut(id=s.id, name=s.name, is_active=s.is_active,
                             client_company_id=s.client_company_id)
            for s in rows]


@router.post("/suppliers", response_model=SupplierOut, status_code=201)
def create_supplier(body: SupplierIn, db: Session = Depends(get_db), user: User = admins):
    client_id = None
    if body.company_id is not None:
        company = db.get(Company, body.company_id)
        if company is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono spółki.")
        client_id = None if is_material_company(company) else company.id
    if db.scalar(select(Supplier.id).where(
            Supplier.client_company_id.is_not_distinct_from(client_id),
            Supplier.name == body.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Taki dostawca już istnieje.")
    supplier = Supplier(name=body.name, client_company_id=client_id,
                        address=body.address, note=body.note, column_map=body.column_map)
    db.add(supplier)
    db.commit()
    return supplier


@router.patch("/suppliers/{supplier_id}", response_model=SupplierOut)
def update_supplier(supplier_id: int, body: SupplierIn,
                    db: Session = Depends(get_db), user: User = admins):
    supplier = _get_or_404(db, SUPPLIERS, supplier_id, user)
    clash = db.scalar(select(Supplier).where(
        Supplier.id != supplier_id,
        Supplier.client_company_id.is_not_distinct_from(supplier.client_company_id),
        Supplier.name == body.name))
    if clash:
        # celowo: nazwa zajęta przez inny wpis tego samego właściciela to najczęściej duplikat
        # do scalenia, a nie pomyłka — podpowiadamy właściwe narzędzie zamiast suchego 409.
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Taki dostawca już istnieje (id={clash.id}) — scal duplikaty.")
    audit.record_changes(db, supplier, {"name": body.name, "is_active": body.is_active,
                                        "address": body.address, "note": body.note,
                                        "column_map": body.column_map}, user)
    db.commit()
    return supplier
```

(`resolve_company_id` i `scope_company` zostają w imporcie — używają ich magazyny.)

- [ ] **Step 7: Kontakty dostawców**

W `backend/app/routers/dictionaries_ref.py` zamień `from ..deps import get_scoped, scope_company` na
`from ..deps import get_scoped, scope_suppliers, supplier_catalog_access`
i w `list_supplier_contacts` zamień linie od `q = (select(SupplierContact)...` do `q = scope_company(q, Supplier.company_id, user)` na:

```python
    q = (select(SupplierContact).join(Supplier, SupplierContact.supplier_id == Supplier.id)
         .where(SupplierContact.is_active))
    q = scope_suppliers(q, user)
    if not supplier_catalog_access(user):
        # kontakty kartoteki to dane Acme — konto bez dostępu widzi tylko swoich nadawców
        q = q.where(Supplier.client_company_id.is_not(None))
```

Popraw też komentarz nad tym blokiem: „pozostali widzą tylko dostawców swojej spółki" → „pozostali — wg reguł kartoteki (deps.scope_suppliers)".

- [ ] **Step 8: Uruchom testy tasku**

Run: `cd backend && python -m pytest tests/test_supplier_visibility.py "tests/test_dictionaries.py::test_suppliers_scoped_by_module" tests/test_deps_get_scoped.py -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/app/config.py backend/app/deps.py backend/app/schemas/dictionaries.py backend/app/routers/dictionaries.py backend/app/routers/dictionaries_ref.py backend/tests/test_supplier_visibility.py
git commit -m "feat(dostawcy): widoczność kartoteki w deps (SUPPLIER_COMPANY_CODES)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DuL7wEFJzFdfPbCLUGEMNU"
```

---

### Task 3: Użycie dostawcy w rekordach spółki — kontenery, zlecenia, import kolejki, aliasy, faktury

**Files:**
- Modify: `backend/app/routers/containers_common.py:9`, `:197-201`
- Modify: `backend/app/routers/containers_orders.py:14`, `:139-157`
- Modify: `backend/app/importers/queue.py:13-27`, `:174-183`
- Modify: `backend/app/invoices/profiles.py:11-15`, `:62-70`
- Modify: `backend/app/invoices/matching.py:53-64`
- Modify: `backend/app/supplier_profile_lab.py:98`
- Modify (przepisany): `backend/app/routers/supplier_aliases.py`
- Modify: `backend/tests/test_supplier_aliases.py` (usunięte testy purge)
- Create: `backend/tests/test_supplier_company_rules.py`

**Interfaces:**
- Consumes: `supplier_clause_for_company`, `is_material_company`, `check_company_access` (Task 2).
- Produces: `GET /api/suppliers/unmapped` → wiersze `{name, company_id, containers, catalog: bool}`; `POST /api/suppliers/{id}/aliases` body `{alias, company_id?}`; `resolve_supplier_ref(db, company_id | None, supplier_id, raw_ref)` (None = mapa dowolnej spółki). Endpoint `POST /api/suppliers/purge` **usunięty**.

- [ ] **Step 1: Napisz test (failing)**

`backend/tests/test_supplier_company_rules.py`:

```python
"""Kartoteka globalna (PR1): którego dostawcy wolno użyć w rekordach której spółki —
kontenery, zlecenia, import kolejki, aliasy, rozpoznanie dostawcy faktury."""
from sqlalchemy import select

from app.database import SessionLocal
from app.importers.queue import resolve_supplier_id
from app.invoices import profiles
from app.models import Company, Container, Supplier, SupplierDocProfile

NOS = ["MSKU5000009", "MSKU5000014", "MSDU0806613", "CSQU3054383", "MEDU9573834"]


def _co(db, code):
    return db.scalar(select(Company).where(Company.code == code))


def _seed():
    with SessionLocal() as db:
        cat = Supplier(name="Kartoteka Co", sap_code="500100")
        tim = Supplier(name="Nadawca Borealis", client_company_id=_co(db, "BOREALIS").id)
        db.add_all([cat, tim])
        db.commit()
        return cat.id, tim.id


def _ids(*codes):
    with SessionLocal() as db:
        return [_co(db, c).id for c in codes]


def test_container_accepts_catalog_only_in_material_company(client, admin_headers):
    cat, tim = _seed()
    acme, pt, borealis = _ids("ACME", "PT", "BOREALIS")

    def post(no, company, supplier):
        return client.post("/api/containers", headers=admin_headers, json={
            "container_no": no, "company_id": company, "supplier_id": supplier}).status_code

    assert post(NOS[0], acme, cat) == 201
    assert post(NOS[1], pt, cat) == 201
    assert post(NOS[2], borealis, cat) == 404
    assert post(NOS[3], borealis, tim) == 201
    assert post(NOS[4], acme, tim) == 404


def test_queue_import_resolves_catalog_name_only_for_material_company(client):
    cat, tim = _seed()
    with SessionLocal() as db:
        acme, borealis = _co(db, "ACME").id, _co(db, "BOREALIS").id
        assert resolve_supplier_id(db, acme, "KARTOTEKA CO") == cat
        assert resolve_supplier_id(db, borealis, "Kartoteka Co") is None
        assert resolve_supplier_id(db, borealis, "nadawca borealis") == tim


def test_found_order_by_name_creates_catalog_or_client_sender(client, admin_headers):
    for code, number in (("ACME", "ZL-K1"), ("BOREALIS", "ZL-K2")):
        r = client.post("/api/zlecenia", headers=admin_headers, json={
            "number": number, "company_code": code, "supplier_name": "Nowy Nadawca",
            "container_count": 1})
        assert r.status_code == 201, r.text
    with SessionLocal() as db:
        owners = sorted(str(s.client_company_id) for s in db.scalars(
            select(Supplier).where(Supplier.name == "Nowy Nadawca")))
        assert owners == sorted(["None", str(_co(db, "BOREALIS").id)])


def test_detect_supplier_sees_catalog_only_for_material_company(client):
    cat, _ = _seed()
    with SessionLocal() as db:
        db.add(SupplierDocProfile(supplier_id=cat, status="active",
                                  keywords=["KARTOTEKA CO LTD"], ci_map={}, pl_map={}))
        db.commit()
        text = "COMMERCIAL INVOICE — KARTOTEKA CO LTD"
        assert profiles.detect_supplier(db, text, _co(db, "ACME").id).id == cat
        assert profiles.detect_supplier(db, text, _co(db, "BOREALIS").id) is None


def test_alias_for_catalog_supplier_needs_file_company(client, admin_headers):
    cat, _ = _seed()
    acme, borealis = _ids("ACME", "BOREALIS")
    url = f"/api/suppliers/{cat}/aliases"
    assert client.post(url, headers=admin_headers, json={"alias": "KART CO"}).status_code == 422
    assert client.post(url, headers=admin_headers,
                       json={"alias": "KART CO", "company_id": borealis}).status_code == 404
    r = client.post(url, headers=admin_headers, json={"alias": "KART CO", "company_id": acme})
    assert r.status_code == 201, r.text
    with SessionLocal() as db:
        assert resolve_supplier_id(db, acme, "Kart Co.") == cat


def test_unmapped_rows_flag_catalog_companies(client, admin_headers):
    with SessionLocal() as db:
        db.add_all([Container(container_no=NOS[0], company_id=_co(db, "ACME").id,
                              supplier_raw="Plik Z"),
                    Container(container_no=NOS[1], company_id=_co(db, "BOREALIS").id,
                              supplier_raw="Plik T")])
        db.commit()
    rows = {r["name"]: r["catalog"]
            for r in client.get("/api/suppliers/unmapped", headers=admin_headers).json()}
    assert rows == {"Plik Z": True, "Plik T": False}


def test_purge_endpoint_is_gone(client, admin_headers):
    r = client.post("/api/suppliers/purge?company_code=BOREALIS", headers=admin_headers,
                    json={"confirm": "BOREALIS"})
    assert r.status_code in (404, 405)
```

- [ ] **Step 2: Uruchom — ma paść**

Run: `cd backend && python -m pytest tests/test_supplier_company_rules.py -q`
Expected: FAIL (`AttributeError: ... 'company_id'` w `_check_company_fks` / `resolve_supplier_id`, brak klucza `catalog`, purge zwraca 400/200).

- [ ] **Step 3: `_check_company_fks`**

W `backend/app/routers/containers_common.py` zamień `from ..deps import get_scoped, scope_containers` na
`from ..deps import get_scoped, scope_containers, supplier_clause_for_company`
i w `_check_company_fks` zastąp blok `if supplier_id is not None:`:

```python
    if supplier_id is not None:
        # dostawca musi być do użycia w spółce: jej nadawca albo kartoteka (spółki z materiałami)
        company = db.get(Company, company_id)
        if company is None or db.scalar(select(Supplier.id).where(
                Supplier.id == supplier_id, supplier_clause_for_company(company))) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono dostawcy.")
```

Popraw docstring funkcji: „Walidacja, że wskazane rekordy należą do spółki kontenera (dostawca — do użycia w tej spółce: deps.supplier_clause_for_company) — …".

- [ ] **Step 4: Zlecenia — `_resolve_supplier`**

W `backend/app/routers/containers_orders.py` zamień `from ..deps import get_scoped, resolve_company_id, scope_company` na

```python
from ..deps import (
    get_scoped,
    is_material_company,
    resolve_company_id,
    scope_company,
    supplier_clause_for_company,
)
```

i zastąp `_resolve_supplier`:

```python
def _resolve_supplier(db: Session, company_id: int, supplier_id: int | None,
                      supplier_name: str | None) -> int | None:
    """Dostawca po id (musi być do użycia w spółce) albo po nazwie (get-or-create): spółka
    z materiałami Acme → kartoteka, spółka-klient → jej nadawca."""
    if supplier_id is not None:
        _check_company_fks(db, company_id, supplier_id, None, None)
        return supplier_id
    name = (supplier_name or "").strip()
    if not name:
        return None
    company = db.get(Company, company_id)
    supplier = db.scalar(select(Supplier).where(
        supplier_clause_for_company(company), Supplier.name == name)
        .order_by(Supplier.id).limit(1))
    if supplier is None:
        supplier = Supplier(name=name, client_company_id=(
            None if is_material_company(company) else company.id))
        db.add(supplier)
        db.flush()
    return supplier.id
```

- [ ] **Step 5: Import kolejki**

W `backend/app/importers/queue.py` dodaj `Company,` do importu z `..models` (po `AuditLog,`) i dodaj linię `from ..deps import supplier_clause_for_company` po `from ..audit import record`. Zastąp `resolve_supplier_id`:

```python
def resolve_supplier_id(db: Session, company_id: int, name: str) -> int | None:
    """Nazwa z pliku → dostawca do użycia w spółce (kartoteka dla spółek z materiałami Acme
    + własni nadawcy): dokładna nazwa (bez wielkości liter), potem alias spółki. Import NIE
    tworzy dostawców (kartoteka przychodzi z SAP, nadawców prowadzi się ręcznie)."""
    if not name:
        return None
    company = db.get(Company, company_id)
    sid = db.scalar(select(Supplier.id).where(
        supplier_clause_for_company(company), func.lower(Supplier.name) == name.lower())
        .order_by(Supplier.id).limit(1))
    return sid or db.scalar(select(SupplierAlias.supplier_id).where(
        SupplierAlias.company_id == company_id,
        SupplierAlias.alias_norm == normalize_alias(name)))
```

- [ ] **Step 6: Rozpoznanie dostawcy faktury i mapy indeksów**

W `backend/app/invoices/profiles.py` zamień `from ..models import Supplier, SupplierDocProfile` na:

```python
from ..deps import supplier_clause_for_company
from ..models import Company, Supplier, SupplierDocProfile
```

i w `detect_supplier` zastąp część od `if not (text or "").strip()...` do `.all()`:

```python
    if not (text or "").strip() or company_id is None:
        return None
    company = db.get(Company, company_id)
    if company is None:
        return None
    rows = db.execute(select(SupplierDocProfile.keywords, Supplier)
                      .join(Supplier, Supplier.id == SupplierDocProfile.supplier_id)
                      .where(SupplierDocProfile.status == "active", Supplier.is_active,
                             supplier_clause_for_company(company))).all()
```

(docstring: „Dostawca do użycia w spółce z AKTYWNYM profilem…").

W `backend/app/invoices/matching.py` zastąp `resolve_supplier_ref`:

```python
def resolve_supplier_ref(db: Session, company_id: int | None, supplier_id: int | None,
                         raw_ref) -> str | None:
    """Nasz ref_code ze słownika mapowań indeksów dostawcy (kod artykułu → ref_code).
    Najwyższy priorytet: operator ustalił to na stałe. None = brak wpisu. `company_id=None`
    (test próbki profilu dostawcy z kartoteki — bez kontenera) = mapa dowolnej spółki."""
    code = str(raw_ref or "").strip()
    if not code or not supplier_id:
        return None
    query = select(SupplierMaterialMap.ref_code).where(
        SupplierMaterialMap.supplier_id == supplier_id,
        SupplierMaterialMap.supplier_code == code)
    if company_id is not None:
        query = query.where(SupplierMaterialMap.company_id == company_id)
    return db.scalar(query.order_by(SupplierMaterialMap.id).limit(1))
```

W `backend/app/supplier_profile_lab.py:98` zamień `supplier.company_id` na `supplier.client_company_id`.

- [ ] **Step 7: Router aliasów (bez „purge")**

Zastąp całą zawartość `backend/app/routers/supplier_aliases.py`:

```python
"""Mapowanie nazw dostawców z pliku kolejki (Container.supplier_raw) na słownik przez aliasy.
Alias należy do spółki pliku kolejki (nazwa → dostawca w tej spółce). Import kolejki nie
tworzy dostawców — nazwy bez dopasowania trafiają na listę „Do zmapowania"."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .. import audit
from ..database import get_db
from ..deps import Editors as editors
from ..deps import (
    apply_company_code_filter,
    check_company_access,
    get_scoped,
    is_material_company,
    scope_containers,
    supplier_clause_for_company,
)
from ..models import Company, Container, Supplier, SupplierAlias, User, normalize_alias

router = APIRouter(prefix="/api/suppliers", tags=["słowniki"])


class AliasIn(BaseModel):
    alias: str = Field(min_length=1, max_length=160)
    # spółka pliku kolejki; domyślnie spółka nadawcy klienta (dostawca z kartoteki jej nie ma)
    company_id: int | None = None


def _alias_out(a: SupplierAlias) -> dict:
    return {"id": a.id, "alias": a.alias, "supplier_id": a.supplier_id}


@router.get("/unmapped")
def unmapped(company_code: str | None = None, db: Session = Depends(get_db),
             user: User = editors):
    """Nazwy z pliku bez dostawcy w słowniku (w zakresie usera), najczęstsze najpierw.
    `catalog` = spółka pracuje na materiałach Acme (mapujemy na kartotekę)."""
    n = func.count(Container.id)
    q = (select(Container.company_id, Container.supplier_raw, n)
         .where(Container.supplier_id.is_(None), Container.supplier_raw != "")
         .group_by(Container.company_id, Container.supplier_raw)
         .order_by(n.desc(), Container.supplier_raw))
    q = apply_company_code_filter(scope_containers(q, user), db, Container.company_id,
                                  company_code, None)
    catalog = {c.id: is_material_company(c) for c in db.scalars(select(Company))}
    return [{"name": name, "company_id": cid, "containers": cnt, "catalog": catalog.get(cid, False)}
            for cid, name, cnt in db.execute(q)]


@router.get("/{supplier_id}/aliases")
def list_aliases(supplier_id: int, db: Session = Depends(get_db), user: User = editors):
    get_scoped(db, Supplier, supplier_id, user)
    return [_alias_out(a) for a in db.scalars(select(SupplierAlias).where(
        SupplierAlias.supplier_id == supplier_id).order_by(SupplierAlias.alias))]


@router.post("/{supplier_id}/aliases", status_code=201)
def create_alias(supplier_id: int, body: AliasIn, db: Session = Depends(get_db),
                 user: User = editors):
    """Alias nazwy → dostawca w spółce pliku + przypięcie kontenerów tej spółki z tą nazwą
    bez dostawcy. Dostawca musi być do użycia w tej spółce (deps.supplier_clause_for_company)."""
    supplier = get_scoped(db, Supplier, supplier_id, user)
    company_id = body.company_id if body.company_id is not None else supplier.client_company_id
    if company_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Wskaż spółkę pliku kolejki (company_id).")
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono spółki.")
    check_company_access(user, company.id)
    if db.scalar(select(Supplier.id).where(
            Supplier.id == supplier.id, supplier_clause_for_company(company))) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono dostawcy.")
    norm = normalize_alias(body.alias)
    if not norm:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Pusta nazwa aliasu.")
    alias = db.scalar(select(SupplierAlias).where(
        SupplierAlias.company_id == company.id, SupplierAlias.alias_norm == norm))
    if alias and alias.supplier_id != supplier.id:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Ta nazwa jest już przypisana do innego dostawcy (id={alias.supplier_id}).")
    if not alias:
        alias = SupplierAlias(company_id=company.id, supplier_id=supplier.id,
                              alias=body.alias.strip(), alias_norm=norm)
        db.add(alias)
    # ponytail: normalizacja w Pythonie po kontenerach bez dostawcy (zwykle setki), kolumna
    # supplier_raw_norm z indeksem gdyby urosło
    rows = db.execute(select(Container.id, Container.supplier_raw).where(
        Container.company_id == company.id, Container.supplier_id.is_(None),
        Container.supplier_raw != "")).all()
    ids = [cid for cid, raw in rows if normalize_alias(raw) == norm]
    if ids:
        db.execute(update(Container).where(Container.id.in_(ids)).values(supplier_id=supplier.id))
    for cid in ids:
        audit.record(db, entity_type="containers", entity_id=cid, field="supplier_id",
                     old_value=None, new_value=str(supplier.id), user=user,
                     note=f"mapowanie nazwy z pliku: {alias.alias}")
    db.commit()
    return {"alias": _alias_out(alias), "assigned": len(ids)}


@router.delete("/aliases/{alias_id}", status_code=204)
def delete_alias(alias_id: int, db: Session = Depends(get_db), user: User = editors):
    """Usuwa alias (przyszłe importy tej nazwy wrócą na listę); kontenery już przypięte zostają."""
    alias = get_scoped(db, SupplierAlias, alias_id, user)
    audit.record(db, entity_type="supplier_aliases", entity_id=alias.id, field="delete",
                 old_value=alias.alias, new_value=None, user=user, note="usunięto alias dostawcy")
    db.delete(alias)
    db.commit()
```

- [ ] **Step 8: Testy aliasów — usuń zakładające „Wyczyść słownik"**

W `backend/tests/test_supplier_aliases.py`:
- usuń całe funkcje `test_purge_keeps_names_and_removes_suppliers`, `test_purge_nulls_order_supplier_contact_before_deleting_contact`, `test_admin_role_bypasses_company_scope_by_design` (endpoint usunięty — spec §3 „Znikają: panel Wyczyść słownik dostawców");
- w `test_other_company_logistics_cannot_map` usuń ostatnią asercję (`client.post("/api/suppliers/purge?...") ... == 403`);
- z importu `from app.models import (...)` usuń nieużywane już `Order`, `SupplierContact` (zostają `Company, Container, Role, Supplier, SupplierAlias, User, normalize_alias`).

- [ ] **Step 9: Uruchom testy tasku**

Run: `cd backend && python -m pytest tests/test_supplier_company_rules.py tests/test_supplier_aliases.py "tests/test_api.py::test_container_fk_cross_company_rejected" tests/test_invoices_profile.py tests/test_zlecenia.py tests/test_supplier_stats.py tests/test_supplier_samples.py -q`
Expected: PASS — z wyjątkiem `test_supplier_aliases.py::test_merge_moves_aliases_and_adds_source_name` (scalanie → Task 4). Jeśli pada tylko ten jeden — OK.

- [ ] **Step 10: Commit**

```bash
git add backend/app/routers/containers_common.py backend/app/routers/containers_orders.py backend/app/importers/queue.py backend/app/invoices/profiles.py backend/app/invoices/matching.py backend/app/supplier_profile_lab.py backend/app/routers/supplier_aliases.py backend/tests/test_supplier_company_rules.py backend/tests/test_supplier_aliases.py
git commit -m "feat(dostawcy): dostawca do użycia w spółce — kartoteka lub nadawca klienta; bez czyszczenia słownika

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DuL7wEFJzFdfPbCLUGEMNU"
```

---

### Task 4: Scalanie — `merge_into` (rdzeń bez HTTP) i porządki kolizji

**Files:**
- Modify: `backend/app/routers/dictionaries_merge.py:126-208` (od `_get_or_404` do końca `_merge`), docstring modułu, pole `company_scoped` (komentarz), import `Supplier*`
- Create: `backend/tests/test_supplier_merge_dedupe.py`

**Interfaces:**
- Consumes: `SupplierMaterial` (Task 1), `Supplier.client_company_id`.
- Produces: `merge_into(db: Session, spec: _Dict, source, target, user: User | None) -> dict[str, int]` (bez commit, bez walidacji HTTP; zwraca `repinned`) — używa go Task 6. `_merge` (HTTP) zwraca 409, gdy `source.client_company_id != target.client_company_id`.

- [ ] **Step 1: Napisz test (failing)**

`backend/tests/test_supplier_merge_dedupe.py`:

```python
"""Scalanie dostawców w kartotece globalnej (PR1): kolizje unikalności wygrywa cel, kontakty
po e-mailu, mapy indeksów per spółka, alias nazwy w spółkach, z których pochodzą pliki."""
from sqlalchemy import select

from app.database import SessionLocal
from app.models import (
    Company,
    Container,
    Material,
    Order,
    Supplier,
    SupplierAlias,
    SupplierContact,
    SupplierMaterial,
    SupplierMaterialMap,
)


def _co(db, code):
    return db.scalar(select(Company).where(Company.code == code))


def _pair():
    with SessionLocal() as db:
        acme, pt = _co(db, "ACME"), _co(db, "PT")
        src = Supplier(name="ACME TRADING", sap_code="100")
        dst = Supplier(name="Acme Trading Co.", sap_code="100")
        m1, m2 = Material(ref_code="REF-M1", ref_norm="REFM1"), Material(ref_code="REF-M2", ref_norm="REFM2")
        db.add_all([src, dst, m1, m2])
        db.flush()
        db.add_all([
            SupplierMaterial(supplier_id=src.id, material_id=m1.id, supplier_code="S-1"),
            SupplierMaterial(supplier_id=src.id, material_id=m2.id, supplier_code="S-2"),
            SupplierMaterial(supplier_id=dst.id, material_id=m1.id, supplier_code="D-1"),
            SupplierMaterialMap(company_id=acme.id, supplier_id=src.id, supplier_code="X", ref_code="R-SRC"),
            SupplierMaterialMap(company_id=pt.id, supplier_id=src.id, supplier_code="X", ref_code="R-PT"),
            SupplierMaterialMap(company_id=acme.id, supplier_id=dst.id, supplier_code="X", ref_code="R-DST"),
        ])
        c_src = SupplierContact(supplier_id=src.id, full_name="Li", email="LI@acme.example")
        c_dst = SupplierContact(supplier_id=dst.id, full_name="Li Wei", email="li@acme.example")
        db.add_all([c_src, c_dst])
        db.flush()
        order = Order(number="PO-M1", company_id=pt.id, supplier_id=src.id,
                      supplier_contact_id=c_src.id)
        db.add_all([order, Container(container_no="MSKU5000009", company_id=pt.id,
                                     supplier_id=src.id)])
        db.commit()
        return src.id, dst.id, c_dst.id, order.id, pt.id, acme.id


def test_merge_resolves_unique_collisions_in_favour_of_target(client, admin_headers):
    src, dst, c_dst, order_id, pt, acme = _pair()
    r = client.post(f"/api/suppliers/{src}/merge", headers=admin_headers, json={"target_id": dst})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        codes = {m.supplier_code for m in db.scalars(
            select(SupplierMaterial).where(SupplierMaterial.supplier_id == dst))}
        assert codes == {"D-1", "S-2"}                       # materiał celu wygrał
        maps = {(m.company_id, m.ref_code) for m in db.scalars(
            select(SupplierMaterialMap).where(SupplierMaterialMap.supplier_id == dst))}
        assert maps == {(acme, "R-DST"), (pt, "R-PT")}      # kolizja tylko w tej samej spółce
        contacts = db.scalars(select(SupplierContact).where(SupplierContact.supplier_id == dst)).all()
        assert [c.id for c in contacts] == [c_dst]           # ten sam e-mail = jeden kontakt
        assert db.get(Order, order_id).supplier_contact_id == c_dst
        aliases = {(a.company_id, a.alias) for a in db.scalars(
            select(SupplierAlias).where(SupplierAlias.supplier_id == dst))}
        assert aliases == {(pt, "ACME TRADING")}             # spółka kontenerów duplikatu


def test_merge_of_same_name_adds_no_alias(client, admin_headers):
    with SessionLocal() as db:
        pt = _co(db, "PT")
        a, b = Supplier(name="Same Co", sap_code="7"), Supplier(name="SAME CO.", sap_code="7")
        db.add_all([a, b])
        db.flush()
        db.add(Container(container_no="MSKU5000014", company_id=pt.id, supplier_id=a.id))
        db.commit()
        a_id, b_id = a.id, b.id
    r = client.post(f"/api/suppliers/{a_id}/merge", headers=admin_headers, json={"target_id": b_id})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        assert db.scalars(select(SupplierAlias)).all() == []
```

- [ ] **Step 2: Uruchom — ma paść**

Run: `cd backend && python -m pytest tests/test_supplier_merge_dedupe.py -q`
Expected: FAIL (`AttributeError: 'Supplier' object has no attribute 'company_id'` w `_merge`).

- [ ] **Step 3: Implementacja**

W `backend/app/routers/dictionaries_merge.py`:

1. Docstring modułu — dopisz na końcu: „`merge_into` to rdzeń scalania bez HTTP i bez commit — woła go też app/supplier_consolidation.py (ekran „Do rozstrzygnięcia" i komenda)."
2. Komentarz pola `company_scoped` w `_Dict` (dodaj nad polem): `# fetch po id przez deps.get_scoped (izolacja per rekord: spółka / kartoteka dostawców)`.
3. Zastąp funkcje od `def _merge(` do końca `_merge` (linie 136–208) poniższym kodem (`_get_or_404` i `_delete` bez zmian):

```python
def _supplier_premerge(db: Session, source, target) -> tuple[bool, set[int]]:
    """Porządki przed przepięciem FK dostawcy. Kolizje unikalności wygrywa cel (to on zostaje),
    profil dokumentów przechodzi na cel bez profilu. Zwraca (czy profil duplikatu przepadł,
    spółki, w których nazwa duplikatu ma zostać aliasem celu)."""
    sid, tid = source.id, target.id
    # mapy indeksów są per spółka — unique (company_id, supplier_id, supplier_code): kod, który
    # cel ma już W TEJ SAMEJ spółce, wygrywa u celu; mapy innych spółek przechodzą
    taken = set(db.execute(select(SupplierMaterialMap.company_id, SupplierMaterialMap.supplier_code)
                           .where(SupplierMaterialMap.supplier_id == tid)).all())
    clash = [mid for mid, cid, code in db.execute(
        select(SupplierMaterialMap.id, SupplierMaterialMap.company_id,
               SupplierMaterialMap.supplier_code).where(SupplierMaterialMap.supplier_id == sid))
        if (cid, code) in taken]
    if clash:
        db.execute(delete(SupplierMaterialMap).where(SupplierMaterialMap.id.in_(clash)))
    # indeksy dostawcy: unique (supplier_id, material_id) — materiał celu wygrywa
    db.execute(delete(SupplierMaterial).where(
        SupplierMaterial.supplier_id == sid,
        SupplierMaterial.material_id.in_(
            select(SupplierMaterial.material_id).where(SupplierMaterial.supplier_id == tid))))
    # kontakty: ten sam e-mail (bez wielkości liter) u celu → zamówienia wskazują kontakt celu,
    # kontakt duplikatu znika (unique supplier_id + lower(email) — migracja kartoteka002)
    target_mail = {email.lower(): cid for cid, email in db.execute(
        select(SupplierContact.id, SupplierContact.email).where(
            SupplierContact.supplier_id == tid, SupplierContact.email != ""))}
    for cid, email in db.execute(select(SupplierContact.id, SupplierContact.email).where(
            SupplierContact.supplier_id == sid, SupplierContact.email != "")).all():
        keep = target_mail.get(email.lower())
        if keep:
            db.execute(update(Order).where(Order.supplier_contact_id == cid)
                       .values(supplier_contact_id=keep))
            db.execute(delete(SupplierContact).where(SupplierContact.id == cid))
    # profil dokumentów (owned, nie w refs) — bez przepięcia zginąłby razem ze źródłem przez
    # ondelete="CASCADE". Cel bez profilu dziedziczy profil duplikatu (z próbkami); cel z własnym
    # profilem go zachowuje, a profil duplikatu ginie — odnotowujemy to w audycie.
    dropped = False
    if db.scalar(select(SupplierDocProfile.id).where(SupplierDocProfile.supplier_id == sid)):
        if db.scalar(select(SupplierDocProfile.id).where(SupplierDocProfile.supplier_id == tid)):
            dropped = True
        else:
            # rdzenne UPDATE (nie atrybut ORM) — widoczne od razu dla SELECT-a, którym cascade
            # delete-orphan (models/dictionaries.py) sprawdza przy flush, czy source nadal ma
            # dziecko; inaczej skasowałby profil jako sierotę
            db.execute(update(SupplierDocProfile).where(SupplierDocProfile.supplier_id == sid)
                       .values(supplier_id=tid))
    # spółki, z których plików kolejki pochodzi nazwa duplikatu (kontenery, aliasy, właściciel)
    companies = set(db.scalars(select(Container.company_id).where(
        Container.supplier_id == sid).distinct()))
    companies |= set(db.scalars(select(SupplierAlias.company_id).where(
        SupplierAlias.supplier_id == sid)))
    if source.client_company_id is not None:
        companies.add(source.client_company_id)
    return dropped, companies


def merge_into(db: Session, spec: _Dict, source, target, user: User | None) -> dict[str, int]:
    """Rdzeń scalania: uzupełnij puste pola celu, przepnij wszystkie FK ze źródła na cel,
    audyt, skasuj źródło. Bez walidacji HTTP i bez commit (transakcję domyka wołający)."""
    # uzupełnij puste pola celu z duplikatu (nic nie nadpisujemy); kod SAP najpierw zdejmujemy
    # z duplikatu — przy unikalnym kodzie w kartotece (kartoteka002) nie mogą go mieć naraz
    moved = {field: getattr(source, field) for field in spec.copy_fields
             if not getattr(target, field) and getattr(source, field)}
    if "sap_code" in moved:
        source.sap_code = ""
        db.flush()
    for field, value in moved.items():
        setattr(target, field, value)

    dropped, alias_companies = (_supplier_premerge(db, source, target)
                                if spec is SUPPLIERS else (False, set()))
    repinned: dict[str, int] = {}
    for model, column in spec.refs:
        result = db.execute(update(model).where(getattr(model, column) == source.id)
                            .values(**{column: target.id}))
        if result.rowcount:
            repinned[model.__tablename__] = result.rowcount

    # nazwa duplikatu zostaje aliasem celu w spółkach jego plików — kolejne importy kolejki
    # trafią od razu do celu. Ta sama nazwa (scalanie kopii z LFA1) aliasu nie potrzebuje:
    # rozwiązuje ją dokładne dopasowanie nazwy (importers/queue.resolve_supplier_id).
    norm = normalize_alias(source.name)[:160]
    if spec is SUPPLIERS and norm and norm != normalize_alias(target.name)[:160]:
        for company_id in sorted(alias_companies):
            if not db.scalar(select(SupplierAlias.id).where(
                    SupplierAlias.company_id == company_id, SupplierAlias.alias_norm == norm)):
                db.add(SupplierAlias(company_id=company_id, supplier_id=target.id,
                                     alias=source.name[:160], alias_norm=norm))

    note = f"scalono duplikat; przepięto: {repinned or 'nic'}"
    if dropped:
        note += "; profil dokumentów duplikatu skasowany (cel miał już własny)"
    audit.record(db, entity_type=spec.model.__tablename__, entity_id=target.id,
                 field="merge", old_value=f"{source.name} (id={source.id})",
                 new_value=f"{target.name} (id={target.id})", user=user, note=note)
    db.delete(source)
    return repinned


def _merge(db: Session, spec: _Dict, source_id: int, body: MergeIn, user: User) -> MergeOut:
    if source_id == body.target_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nie można scalić wpisu z samym sobą.")
    source = _get_or_404(db, spec, source_id, user)
    target = _get_or_404(db, spec, body.target_id, user)
    # kartoteka i nadawca spółki-klienta (albo nadawcy dwóch spółek) to różne byty — scalenie
    # przepięłoby kontenery klienta na kartotekę Acme albo na cudzą spółkę (wyciek)
    if spec is SUPPLIERS and source.client_company_id != target.client_company_id:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Nie można scalić: dostawca z kartoteki i nadawca spółki-klienta "
                            "(albo nadawcy różnych spółek).")
    repinned = merge_into(db, spec, source, target, user)
    db.commit()
    return MergeOut(target_id=body.target_id, repinned=repinned)
```

- [ ] **Step 4: Uruchom testy tasku**

Run: `cd backend && python -m pytest tests/test_supplier_merge_dedupe.py tests/test_supplier_merge_copy.py tests/test_dictionaries.py tests/test_supplier_aliases.py tests/test_supplier_profiles.py -q`
Expected: PASS (w tym `test_merge_supplier_across_companies_is_blocked` — 409 z nowym komunikatem, `test_merge_supplier_repins_material_maps_and_drops_colliding`, `test_merge_error_rolls_back_everything`, `test_merge_moves_aliases_and_adds_source_name`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/dictionaries_merge.py backend/tests/test_supplier_merge_dedupe.py
git commit -m "feat(dostawcy): merge_into — scalanie w kartotece globalnej z porządkami kolizji

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DuL7wEFJzFdfPbCLUGEMNU"
```

---

### Task 5: Import LFA1 do globalnej kartoteki, jakość master data, skrypty + pełna suita

**Files:**
- Modify: `backend/app/importers/master_data.py:241-270` (`_lfa1_upsert`)
- Modify: `backend/app/routers/imports_master.py:248-280` (`import_suppliers_lfa1`)
- Modify: `backend/app/master_quality.py:10-66`
- Delete: `backend/scripts/import_lfa1.py`
- Modify: `backend/scripts/dedupe_dictionaries.py`, `backend/scripts/purge_company.py:56,83`, `backend/scripts/import_excel.py:82`
- Modify (przepisany): `backend/tests/test_import_lfa1.py`
- Modify: `backend/tests/test_import_autodetect.py:74-84`

**Interfaces:**
- Consumes: `supplier_catalog_access`, `material_company_codes` (Task 2).
- Produces: `_lfa1_upsert(db: Session, rows: list[dict]) -> dict` (bez spółki; klucz `sap_code`); `POST /api/import/suppliers-lfa1` → `{"dry_run", "total", "counts": {total,new,updated,skipped_duplicate}}` (zamiast `companies`); 403 dla konta bez dostępu do kartoteki.

- [ ] **Step 1: Przepisz test importu LFA1 (failing)**

Zastąp całą zawartość `backend/tests/test_import_lfa1.py`:

```python
"""Import kartoteki dostawców z eksportu SAP LFA1 (importers.master_data): jedna globalna
kartoteka, klucz = kod SAP (spec 2026-09-25-kartoteka-dostawcy)."""
import io

from openpyxl import Workbook
from sqlalchemy import select

from app.importers.master_data import _lfa1_upsert, _parse_lfa1_rows
from app.models import Company, Supplier

HEADER = ["Dostawca", "Klucz kraju/regionu", "Nazwa 1", "Nazwa 2", "Nazwa 3", "Nazwa 4",
          "Miasto", "Kod pocztowy", "Szukany ciąg zn.", "Ulica", "Adres", "Miejscowość",
          "Grupa uprawnień", "Utworzono dnia", "Utworzone przez", "Klucz języka"]

ROWS = [
    ["10000085", "DE", "TRANSLOG GMBH", "", "", "", "Hamburg", "21107", "TRANSLOG G",
     "Stenzelring 33", "51426", "HAMBURG", "", None, "JNOWAK", "PL"],
    ["10000189", "FR", "NORDMED CARDIO", "EUROPE GMBH", "", "", "Cologne", "00000",
     "NORDMED COL", "", "51576", "COLOGNE", "", None, "JNOWAK", "PL"],
    # ta sama nazwa, inny kod SAP — osobny dostawca (możliwy dubel w SAP, jakość danych PR6)
    ["10000999", "CN", "NORDMED CARDIO", "EUROPE GMBH", "", "", "Shanghai", "200000",
     "NORDMED SH", "Nanjing Road", "51577", "SHANGHAI", "", None, "JNOWAK", "EN"],
    ["", "CN", "BEZ KODU", "", "", "", "", "", "", "", "", "", "", None, "", "EN"],
    # powtórzony kod SAP w pliku — pomijany
    ["10000085", "DE", "TRANSLOG GMBH", "", "", "", "Hamburg", "21107", "TRANSLOG G",
     "Stenzelring 33", "51426", "HAMBURG", "", None, "JNOWAK", "PL"],
]


def _xlsx() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(HEADER)
    for row in ROWS:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_parse_rows():
    rows = _parse_lfa1_rows(_xlsx())
    assert [r["sap_code"] for r in rows] == ["10000085", "10000189", "10000999", "10000085"]
    assert rows[1]["name"] == "NORDMED CARDIO EUROPE GMBH"   # Nazwa 1 + Nazwa 2
    assert rows[0]["address"] == "Stenzelring 33, 21107 Hamburg, DE"
    assert rows[0]["country"] == "DE"


def test_import_is_idempotent_and_skips_repeated_sap_code(db_session):
    rows = _parse_lfa1_rows(_xlsx())
    counts = _lfa1_upsert(db_session, rows)
    db_session.commit()
    assert counts == {"total": 4, "new": 3, "updated": 0, "skipped_duplicate": 1}
    stored = db_session.scalars(select(Supplier).where(Supplier.sap_code == "10000085")).one()
    assert stored.client_company_id is None and stored.country == "DE"
    assert stored.address.startswith("Stenzelring 33")

    again = _lfa1_upsert(db_session, rows)
    db_session.commit()
    assert again["new"] == 0 and again["updated"] == 0


def test_import_fills_sap_code_on_catalog_record_not_on_client_sender(db_session):
    borealis = db_session.scalar(select(Company).where(Company.code == "BOREALIS"))
    db_session.add_all([Supplier(name="TRANSLOG GMBH"),
                        Supplier(name="TRANSLOG GMBH", client_company_id=borealis.id)])
    db_session.commit()

    counts = _lfa1_upsert(db_session, _parse_lfa1_rows(_xlsx()))
    db_session.commit()

    assert counts["new"] == 2 and counts["updated"] == 1
    catalog = db_session.scalars(select(Supplier).where(
        Supplier.name == "TRANSLOG GMBH", Supplier.client_company_id.is_(None))).one()
    assert catalog.sap_code == "10000085"
    sender = db_session.scalars(select(Supplier).where(
        Supplier.client_company_id == borealis.id)).one()
    assert sender.sap_code == ""
```

W `backend/tests/test_import_autodetect.py` zastąp funkcję `test_lfa1_endpoint_imports_to_all_companies`:

```python
def test_lfa1_endpoint_imports_to_global_catalog(client, admin_headers):
    response = client.post("/api/import/suppliers-lfa1?dry_run=false", headers=admin_headers,
                           files={"file": ("lfa1.xlsx", LFA1, "application/vnd.ms-excel")})
    assert response.status_code == 200, response.text
    assert response.json()["counts"]["new"] == 1
    suppliers = client.get("/api/suppliers?include_inactive=true",
                           headers=admin_headers).json()
    match = [s for s in suppliers if s["sap_code"] == "30001"]
    assert len(match) == 1 and match[0]["client_company_id"] is None
    assert match[0]["country"] == "CN" and match[0]["name"] == "Shanghai Tools Co."
```

- [ ] **Step 2: Uruchom — ma paść**

Run: `cd backend && python -m pytest tests/test_import_lfa1.py tests/test_import_autodetect.py -q`
Expected: FAIL (`TypeError: _lfa1_upsert() missing 1 required positional argument` / `KeyError: 'counts'`).

- [ ] **Step 3: `_lfa1_upsert` globalnie**

W `backend/app/importers/master_data.py` zastąp `_lfa1_upsert`:

```python
def _lfa1_upsert(db: Session, rows: list[dict]) -> dict:
    """Upsert globalnej kartoteki dostawców (client_company_id IS NULL) z LFA1. Klucz: kod SAP;
    rekord kartoteki BEZ kodu (sprzed importu) dopasowany po nazwie dostaje kod. Nadawców
    spółek-klientów nie dotyka. Puste wartości z SAP nie kasują danych wpisanych ręcznie;
    powtórzony kod w pliku — pomijany. Nie commituje. Pełny import z podglądem zmian: PR2
    spec 2026-09-25-kartoteka-dostawcy."""
    existing = db.scalars(select(Supplier).where(Supplier.client_company_id.is_(None))
                          .order_by(Supplier.id)).all()
    by_code: dict[str, Supplier] = {}
    for supplier in existing:
        if supplier.sap_code:
            by_code.setdefault(supplier.sap_code, supplier)
    by_name = {s.name.strip().upper(): s for s in existing if not s.sap_code}
    counts = {"total": len(rows), "new": 0, "updated": 0, "skipped_duplicate": 0}
    seen: set[str] = set()
    for row in rows:
        if row["sap_code"] in seen:
            counts["skipped_duplicate"] += 1
            continue
        seen.add(row["sap_code"])
        supplier = by_code.get(row["sap_code"]) or by_name.pop(row["name"].strip().upper(), None)
        if supplier is None:
            supplier = Supplier(**row)
            db.add(supplier)
            by_code[row["sap_code"]] = supplier
            counts["new"] += 1
            continue
        changed = False
        for field in ("sap_code", "country", "address"):
            if row[field] and getattr(supplier, field) != row[field]:
                setattr(supplier, field, row[field])
                changed = True
        by_code[row["sap_code"]] = supplier
        counts["updated"] += changed
    return counts
```

Popraw też komentarz sekcji nad `LFA1_HEADERS`: `# --- import kartoteki dostawców (LFA1) z eksportu SAP ---`.

- [ ] **Step 4: Endpoint importu LFA1**

W `backend/app/routers/imports_master.py` zastąp `import_suppliers_lfa1`:

```python
@router.post("/suppliers-lfa1")
def import_suppliers_lfa1(
    file: UploadFile,
    dry_run: bool = Query(default=True),
    db: Session = Depends(get_db),
    user: User = editors,
):
    """Import kartoteki dostawców z eksportu SAP LFA1 — jedna globalna kartoteka (spec
    2026-09-25-kartoteka-dostawcy); nadawców spółek-klientów nie dotyka."""
    from ..deps import supplier_catalog_access
    if not supplier_catalog_access(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Import kartoteki dostawców — tylko konta z dostępem do kartoteki.")
    rows = _parse_lfa1_rows(
        read_upload_capped(file, app_config.max_upload_mb, "Plik LFA1"))
    counts = _lfa1_upsert(db, rows)
    if dry_run:
        db.rollback()
        return {"dry_run": True, "total": len(rows), "counts": counts}
    record(db, entity_type="suppliers", entity_id=0, field="import", old_value=None,
           new_value=f"{counts['new']} nowych / {counts['updated']} zaktualizowanych",
           user=user, note=f"import LFA1 ({file.filename})")
    db.commit()
    return {"dry_run": False, "total": len(rows), "counts": counts}
```

(Front `QualityTab.tsx:67` już czyta `r.counts ?? r.companies` — bez zmian.)

- [ ] **Step 5: Jakość master data**

W `backend/app/master_quality.py`:
- import: `from sqlalchemy import func, or_, select`; `from .deps import company_filter_ids, material_company_codes`; do importu modeli dodaj `Company,` (po `AuditLog,`).
- zastąp trzy funkcje dostawców (`suppliers_without_sap`, `suppliers_without_country`, `duplicate_supplier_names`) i dodaj helper:

```python
def _supplier_scope(db: Session, query, company_ids):
    """Dostawcy w zakresie konta: nadawcy jego spółek + kartoteka, gdy któraś z nich pracuje
    na materiałach Acme (ta sama reguła co deps.scope_suppliers)."""
    if company_ids is None:
        return query
    own = Supplier.client_company_id.in_(company_ids)
    codes = {c.upper() for c in db.scalars(select(Company.code).where(Company.id.in_(company_ids)))}
    if codes & material_company_codes():
        return query.where(or_(Supplier.client_company_id.is_(None), own))
    return query.where(own)


def suppliers_without_sap(db: Session, company_ids) -> list[tuple[int, str]]:
    rows = db.execute(_supplier_scope(db, select(Supplier.id, Supplier.name).where(
        Supplier.is_active, Supplier.sap_code == ""), company_ids)).all()
    return [(i, n) for i, n in rows]


def suppliers_without_country(db: Session, company_ids) -> list[tuple[int, str]]:
    rows = db.execute(_supplier_scope(db, select(Supplier.id, Supplier.name).where(
        Supplier.is_active, Supplier.country == ""), company_ids)).all()
    return [(i, n) for i, n in rows]


def duplicate_supplier_names(db: Session, company_ids) -> list[tuple[int, str]]:
    """Duplikaty nazw w obrębie właściciela (kartoteka / nadawcy spółki), bez wielkości liter."""
    dup = db.execute(_supplier_scope(db, select(Supplier.client_company_id, func.lower(Supplier.name))
                                     .where(Supplier.is_active)
                                     .group_by(Supplier.client_company_id, func.lower(Supplier.name))
                                     .having(func.count() > 1), company_ids)).all()
    out: list[tuple[int, str]] = []
    for owner, lname in dup:
        rows = db.execute(select(Supplier.id, Supplier.name).where(
            Supplier.client_company_id.is_not_distinct_from(owner), Supplier.is_active,
            func.lower(Supplier.name) == lname)).all()
        out.extend((i, n) for i, n in rows)
    return out
```

- [ ] **Step 6: Skrypty**

```bash
git rm backend/scripts/import_lfa1.py
```

`backend/scripts/dedupe_dictionaries.py`:
- zamień `SPECS = {"ports": PORTS, "suppliers": SUPPLIERS, "carriers": CARRIERS}` na
  ```python
  # dostawcy: scripts/consolidate_suppliers.py (kartoteka globalna, scalanie po kodzie SAP)
  SPECS = {"ports": PORTS, "carriers": CARRIERS}
  ```
- import: `from app.routers.dictionaries import CARRIERS, PORTS, _Dict  # noqa: E402`
- w `load_entries` usuń dwie linie `if spec.company_scoped: entry["company_id"] = item.company_id`;
- `group_key` zastąp przez:
  ```python
  def group_key(entry: dict, spec: _Dict) -> tuple:
      return (normalize(entry["name"]),)
  ```
- w `propose` usuń dwie linie `if spec.company_scoped and a.get("company_id") != b.get("company_id"): continue`.

`backend/scripts/purge_company.py`: `_count(db, Supplier, company_id=cid)` → `_count(db, Supplier, client_company_id=cid)`; `Supplier.company_id == cid` → `Supplier.client_company_id == cid` (usuwa tylko nadawców tej spółki-klienta; kartoteka jest wspólna).

`backend/scripts/import_excel.py:82`: `get_or_create(db, Supplier, company_id=borealis.id, name=rec["supplier"])` → `get_or_create(db, Supplier, client_company_id=borealis.id, name=rec["supplier"])`.

- [ ] **Step 7: Sprawdź, że nic już nie czyta `Supplier.company_id`**

Run (z katalogu repo): użyj narzędzia Grep (nie `git grep` — patrz pamięć „git grep pathspec fałszywy") na wzorzec `Supplier\.company_id|supplier\.company_id|Supplier\(company_id|source\.company_id` w `backend/`.
Expected: brak trafień.

- [ ] **Step 8: Pełna suita backendu**

Run: `cd backend && python -m pytest tests/ -q` (jeden pytest naraz w tym worktree)
Expected: wszystko PASS. Typowe czerwone i co z nimi zrobić:
- test tworzy dwóch dostawców o tej samej nazwie w ACME i PT (obie → kartoteka) i dostaje 409 → zmień drugą spółkę na BOREALIS/COBALT albo nazwę; zapisz w commicie, który test i dlaczego.
- test oczekuje szczegółów dostawcy dla konta magazynu/spedytora → to zamierzona zmiana spec (§2 widoczność) — zaktualizuj asercję na pusty `sap_code`/`address`.

- [ ] **Step 9: Commit**

```bash
git add -A backend/app/importers/master_data.py backend/app/routers/imports_master.py backend/app/master_quality.py backend/scripts/ backend/tests/
git commit -m "feat(dostawcy): import LFA1 do globalnej kartoteki; jakość i skrypty bez company_id

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DuL7wEFJzFdfPbCLUGEMNU"
```

---

### Task 6: Serwis scalania dubli — propozycja (dry-run), wykonanie, komenda, endpointy

**Files:**
- Create: `backend/app/supplier_consolidation.py`
- Create: `backend/scripts/consolidate_suppliers.py`
- Modify: `backend/app/routers/supplier_aliases.py` (importy, 2 endpointy)
- Create: `backend/tests/test_supplier_consolidation.py`

**Interfaces:**
- Consumes: `merge_into`, `SUPPLIERS` (Task 4).
- Produces: `proposal(db) -> {"merge_groups": [{"sap_code", "target": Brief, "sources": [Brief]}], "unresolved": [Brief & {"suggestion": Brief | None}]}` gdzie `Brief = {id, name, sap_code, country, is_active, usage}`; `apply_groups(db, user | None) -> {"groups": int, "merged": int}` (bez commit); `GET /api/suppliers/resolve` (admin) → `proposal`; `POST /api/suppliers/resolve/apply` (admin) → wynik `apply_groups` po commit; `scripts.consolidate_suppliers.run(apply: bool) -> dict`.

- [ ] **Step 1: Napisz test (failing)**

`backend/tests/test_supplier_consolidation.py`:

```python
"""Scalanie dubli dostawców po przejściu na globalną kartotekę (spec 2026-09-25 §3):
propozycja = dry-run, wykonanie = te same scalenia co ręczne „Scal z…"."""
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Company, Container, Supplier
from app.supplier_consolidation import apply_groups, proposal
from tests.conftest import login


def _seed():
    with SessionLocal() as db:
        pt = db.scalar(select(Company).where(Company.code == "PT"))
        rows = {
            "z": Supplier(name="Ningbo Tools", sap_code="200"),     # kopia z importu do Acme
            "p": Supplier(name="Ningbo Tools", sap_code="200"),     # kopia z importu do PT
            "lone": Supplier(name="Solo Ltd", sap_code="300"),
            "nosap": Supplier(name="NINGBO TOOLS", sap_code=""),    # ręczny, bez kodu SAP
            "orphan": Supplier(name="Nikt", sap_code=""),
        }
        db.add_all([*rows.values(), Supplier(name="Stary", sap_code="", is_active=False)])
        db.flush()
        db.add(Container(container_no="MSKU5000009", company_id=pt.id, supplier_id=rows["p"].id))
        db.commit()
        return {k: v.id for k, v in rows.items()}


def test_proposal_groups_same_sap_code_and_lists_unresolved(db_session):
    ids = _seed()
    plan = proposal(db_session)
    assert len(plan["merge_groups"]) == 1
    group = plan["merge_groups"][0]
    assert group["sap_code"] == "200"
    assert group["target"]["id"] == ids["p"]                 # używany (kontener) zostaje
    assert [s["id"] for s in group["sources"]] == [ids["z"]]
    unresolved = {u["id"]: u for u in plan["unresolved"]}
    assert set(unresolved) == {ids["nosap"], ids["orphan"]}  # nieaktywny nie wraca na listę
    assert unresolved[ids["nosap"]]["suggestion"]["id"] == ids["p"]
    assert unresolved[ids["orphan"]]["suggestion"] is None
    assert unresolved[ids["orphan"]]["usage"] == 0


def test_apply_merges_groups_and_is_idempotent(db_session):
    ids = _seed()
    assert apply_groups(db_session, None) == {"groups": 1, "merged": 1}
    db_session.commit()
    assert db_session.get(Supplier, ids["z"]) is None
    assert proposal(db_session)["merge_groups"] == []
    assert apply_groups(db_session, None) == {"groups": 0, "merged": 0}


def test_cli_dry_run_changes_nothing_then_applies(client):
    ids = _seed()
    from scripts.consolidate_suppliers import run
    assert run(apply=False) == {"groups": 1, "merged": 0}
    with SessionLocal() as db:
        assert db.get(Supplier, ids["z"]) is not None
    assert run(apply=True) == {"groups": 1, "merged": 1}


def test_resolve_endpoints_admin_only_and_single_decisions(client, admin_headers):
    ids = _seed()
    client.post("/api/users", headers=admin_headers, json={
        "login": "log.res", "password": "haslo123", "role": "logistics",
        "view_all_companies": True})
    log_h = login(client, "log.res", "haslo123")
    assert client.get("/api/suppliers/resolve", headers=log_h).status_code == 403
    assert client.post("/api/suppliers/resolve/apply", headers=log_h).status_code == 403

    plan = client.get("/api/suppliers/resolve", headers=admin_headers).json()
    assert [g["sap_code"] for g in plan["merge_groups"]] == ["200"]
    applied = client.post("/api/suppliers/resolve/apply", headers=admin_headers)
    assert applied.status_code == 200 and applied.json()["merged"] == 1
    # pojedyncze decyzje — istniejące endpointy: scal z podpowiedzią, usuń bez powiązań
    assert client.post(f"/api/suppliers/{ids['nosap']}/merge", headers=admin_headers,
                       json={"target_id": ids["p"]}).status_code == 200
    assert client.delete(f"/api/suppliers/{ids['orphan']}", headers=admin_headers).status_code == 204
    assert client.get("/api/suppliers/resolve", headers=admin_headers).json() == {
        "merge_groups": [], "unresolved": []}
```

- [ ] **Step 2: Uruchom — ma paść**

Run: `cd backend && python -m pytest tests/test_supplier_consolidation.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.supplier_consolidation'`).

- [ ] **Step 3: Serwis**

`backend/app/supplier_consolidation.py`:

```python
"""Scalanie dubli dostawców po przejściu na globalną kartotekę (spec 2026-09-25 §3, PR1).

Import LFA1 szedł dotąd do KAŻDEJ spółki, więc ten sam dostawca SAP istnieje w kartotece
kilka razy (dawne kopie Acme i Iberia). `proposal` = dry-run: grupy tego samego kodu
SAP („pewne") + aktywni w kartotece bez kodu SAP („do rozstrzygnięcia", z podpowiedzią po
nazwie). `apply_groups` scala grupy tą samą funkcją co ręczne „Scal z…" (merge_into), więc
przepina wszystkie FK. Wołają: ekran Master data → Dostawcy i scripts/consolidate_suppliers.py.
"""
from collections import Counter, defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import (
    Container,
    InvoiceBatch,
    Order,
    Supplier,
    SupplierDocProfile,
    User,
    normalize_alias,
)
from .routers.dictionaries_merge import SUPPLIERS, merge_into


def _usage(db: Session) -> dict[int, int]:
    """Kontenery + zamówienia + paczki faktur per dostawca (3 zapytania, nie N)."""
    out: dict[int, int] = defaultdict(int)
    for model in (Container, Order, InvoiceBatch):
        for supplier_id, count in db.execute(
                select(model.supplier_id, func.count()).where(model.supplier_id.is_not(None))
                .group_by(model.supplier_id)):
            out[supplier_id] += count
    return out


def _brief(s: Supplier, usage: dict[int, int]) -> dict:
    return {"id": s.id, "name": s.name, "sap_code": s.sap_code, "country": s.country,
            "is_active": s.is_active, "usage": usage.get(s.id, 0)}


def proposal(db: Session) -> dict:
    """Dry-run: nic nie zmienia."""
    usage = _usage(db)
    with_profile = set(db.scalars(select(SupplierDocProfile.supplier_id)))
    catalog = db.scalars(select(Supplier).where(Supplier.client_company_id.is_(None))
                         .order_by(Supplier.id)).all()
    by_code: dict[str, list[Supplier]] = defaultdict(list)
    for supplier in catalog:
        if supplier.sap_code:
            by_code[supplier.sap_code].append(supplier)

    def rank(s: Supplier) -> tuple:
        # zostaje: z profilem dokumentów > aktywny > najczęściej używany > najstarszy
        return (s.id in with_profile, s.is_active, usage.get(s.id, 0), -s.id)

    groups, leaders = [], {}
    for code, members in sorted(by_code.items()):
        target = max(members, key=rank)
        leaders[code] = target
        if len(members) > 1:
            groups.append({"sap_code": code, "target": _brief(target, usage),
                           "sources": [_brief(s, usage) for s in members if s.id != target.id]})
    # podpowiedź po nazwie tylko jednoznaczna (ta sama nazwa pod dwoma kodami = „dubel w SAP")
    names = Counter(normalize_alias(t.name) for t in leaders.values())
    by_name = {normalize_alias(t.name): t for t in leaders.values()
               if names[normalize_alias(t.name)] == 1}
    unresolved = []
    for supplier in catalog:
        if supplier.sap_code or not supplier.is_active:
            continue
        hint = by_name.get(normalize_alias(supplier.name))
        unresolved.append({**_brief(supplier, usage),
                           "suggestion": _brief(hint, usage) if hint else None})
    return {"merge_groups": groups, "unresolved": unresolved}


def apply_groups(db: Session, user: User | None) -> dict:
    """Scala wszystkie grupy tego samego kodu SAP. Bez commit — transakcję domyka wołający
    (jedna transakcja: błąd w środku = nic nie zapisane)."""
    groups = proposal(db)["merge_groups"]
    merged = 0
    for group in groups:
        target = db.get(Supplier, group["target"]["id"])
        for source in group["sources"]:
            merge_into(db, SUPPLIERS, db.get(Supplier, source["id"]), target, user)
            merged += 1
    return {"groups": len(groups), "merged": merged}
```

- [ ] **Step 4: Komenda**

`backend/scripts/consolidate_suppliers.py`:

```python
"""Scalanie dubli dostawców po przejściu na globalną kartotekę (spec 2026-09-25, PR1).

Uruchomienie (z katalogu backend/, na prod: docker exec w kontenerze backendu):
  python -m scripts.consolidate_suppliers            → podgląd, NIC nie zapisuje
  python -m scripts.consolidate_suppliers --apply    → scala grupy tego samego kodu SAP

Dostawców bez kodu SAP rozstrzyga admin: Master data → Dostawcy → „Do rozstrzygnięcia".
PRZED --apply na produkcji zrób kopię bazy (sh scripts/backup.sh).
"""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.database import SessionLocal  # noqa: E402
from app.supplier_consolidation import apply_groups, proposal  # noqa: E402


def run(apply: bool) -> dict:
    with SessionLocal() as db:
        plan = proposal(db)
        for group in plan["merge_groups"]:
            # ASCII w wydruku: konsola Windows (cp1250) nie zakoduje strzałki unicode
            sources = ", ".join(f"{s['name']!r} (id={s['id']}, uzyc: {s['usage']})"
                                for s in group["sources"])
            print(f"SAP {group['sap_code']}: {sources} -> {group['target']['name']!r} "
                  f"(id={group['target']['id']})")
        print(f"Grup do scalenia: {len(plan['merge_groups'])}; "
              f"do rozstrzygniecia (bez kodu SAP): {len(plan['unresolved'])}")
        if not apply:
            print("Podglad - nic nie zapisano. Dodaj --apply, zeby scalic.")
            return {"groups": len(plan["merge_groups"]), "merged": 0}
        result = apply_groups(db, None)
        db.commit()
        print(f"Scalono: {result['merged']}")
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true",
                        help="scal grupy (bez tego tylko podglad)")
    run(parser.parse_args().apply)
```

- [ ] **Step 5: Endpointy „Do rozstrzygnięcia"**

W `backend/app/routers/supplier_aliases.py`:
- docstring modułu: dopisz zdanie „Tu też ekran „Do rozstrzygnięcia" kartoteki (spec 2026-09-25 §3): podgląd i scalenie dubli kodu SAP."
- importy: dodaj `from ..deps import AdminOnly as admins` (obok `Editors as editors`) oraz `from ..supplier_consolidation import apply_groups, proposal` (po imporcie modeli).
- przed `@router.get("/{supplier_id}/aliases")` wstaw:

```python
@router.get("/resolve")
def resolve_list(db: Session = Depends(get_db), user: User = admins):
    """„Do rozstrzygnięcia" (dry-run): grupy tego samego kodu SAP + kartoteka bez kodu SAP."""
    return proposal(db)


@router.post("/resolve/apply")
def resolve_apply(db: Session = Depends(get_db), user: User = admins):
    """Scala wszystkie grupy tego samego kodu SAP w jednej transakcji (audyt per scalenie).
    Pojedyncze decyzje: POST /{id}/merge, PATCH /{id} (nieaktywny), DELETE /{id}."""
    result = apply_groups(db, user)
    db.commit()
    return result
```

- [ ] **Step 6: Uruchom testy tasku**

Run: `cd backend && python -m pytest tests/test_supplier_consolidation.py tests/test_supplier_aliases.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/supplier_consolidation.py backend/scripts/consolidate_suppliers.py backend/app/routers/supplier_aliases.py backend/tests/test_supplier_consolidation.py
git commit -m "feat(dostawcy): scalanie dubli kartoteki — podgląd, komenda, endpointy Do rozstrzygnięcia

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DuL7wEFJzFdfPbCLUGEMNU"
```

---

### Task 7: Front — zakładka Dostawcy bez spółki, „Do zmapowania" bez czyszczenia słownika

**Files:**
- Modify: `frontend/src/types/core.ts:140-148`
- Modify: `frontend/src/pages/MasterDataPage.tsx:50-178` (`SuppliersTab`)
- Modify (przepisany): `frontend/src/pages/masterdata/UnmappedSuppliersPanel.tsx`
- Modify (przepisany): `frontend/src/i18n/features/dostawcy-mapowanie.ts`
- Create: `frontend/src/i18n/features/kartoteka-dostawcow.ts`
- Modify (przepisany): `frontend/src/pages/masterdata/unmapped.dom.test.tsx`
- Modify: `frontend/src/pages/masterdata/merge.dom.test.tsx:17-20`, `frontend/src/pages/MasterDataPage.dom.test.tsx:15-16` (fixtury)

**Interfaces:**
- Consumes: `GET /api/suppliers` (`client_company_id`), `GET /api/suppliers/unmapped` (`catalog`), `POST /api/suppliers/{id}/aliases` (`company_id`).
- Produces: `Supplier.client_company_id?: number | null`; `UnmappedSuppliersPanel` props `{ suppliers, isAdmin, onNew }`; `UnmappedRow.catalog: boolean`; klucze i18n `supCatalog`, `supOwner` (plik `kartoteka-dostawcow.ts`, rozszerzany w Task 8).

- [ ] **Step 1: Napisz test (failing)**

Zastąp `frontend/src/pages/masterdata/unmapped.dom.test.tsx`:

```tsx
// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import UnmappedSuppliersPanel from './UnmappedSuppliersPanel'

vi.mock('../../i18n', () => ({ useT: () => (key: string) => key }))
const { showToast } = vi.hoisted(() => ({ showToast: vi.fn() }))
vi.mock('../../feedback', () => ({ useToast: () => ({ showToast }) }))

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }))
vi.mock('../../api', () => ({
  api: { get: apiGet, post: apiPost, patch: vi.fn(), del: vi.fn(), upload: vi.fn() },
  errorMessage: (e: unknown) => String(e),
}))

// kartoteka (client_company_id null) + nadawcy spółek-klientów 1 i 2
const suppliers = [
  { id: 11, name: 'Shanghai Co', client_company_id: null, is_active: true },
  { id: 12, name: 'Obcy', client_company_id: 2, is_active: true },
  { id: 13, name: 'Nadawca T', client_company_id: 1, is_active: true },
]

afterEach(() => { cleanup(); apiGet.mockReset(); apiPost.mockReset(); showToast.mockReset() })

describe('panel Do zmapowania', () => {
  it('spółka z materiałami mapuje na kartotekę, klient na swoich nadawców; alias z company_id', async () => {
    apiGet.mockResolvedValue([
      { name: 'SHANGHAI CO., LTD', company_id: 3, containers: 3, catalog: true },
      { name: 'T-plik', company_id: 1, containers: 1, catalog: false },
    ])
    apiPost.mockResolvedValue({ alias: {}, assigned: 3 })
    const onNew = vi.fn()
    render(<UnmappedSuppliersPanel suppliers={suppliers as never} isAdmin onNew={onNew} />)
    await screen.findByText('SHANGHAI CO., LTD')
    expect(apiGet).toHaveBeenCalledWith('/api/suppliers/unmapped')

    const sel = screen.getByLabelText('supPick: SHANGHAI CO., LTD') as HTMLSelectElement
    expect([...sel.options].map(o => o.value)).toEqual(['', '11'])
    const selT = screen.getByLabelText('supPick: T-plik') as HTMLSelectElement
    expect([...selT.options].map(o => o.value)).toEqual(['', '13'])

    fireEvent.change(sel, { target: { value: '11' } })
    fireEvent.click(screen.getAllByText('supMap')[0])
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      '/api/suppliers/11/aliases', { alias: 'SHANGHAI CO., LTD', company_id: 3 }))
    await waitFor(() => expect(showToast).toHaveBeenCalledWith('supMappedN'))

    fireEvent.click(screen.getAllByText('supNewFromName')[0])
    expect(onNew).toHaveBeenCalledWith(
      { name: 'SHANGHAI CO., LTD', company_id: 3, containers: 3, catalog: true })
  })

  it('bez nazw do zmapowania panel znika (czyszczenie słownika usunięte)', async () => {
    apiGet.mockResolvedValue([])
    const { container } = render(<UnmappedSuppliersPanel suppliers={[]} isAdmin onNew={() => {}} />)
    await waitFor(() => expect(apiGet).toHaveBeenCalled())
    expect(container.textContent).toBe('')
    expect(screen.queryByText('supPurgeBtn')).toBeNull()
  })
})
```

W `frontend/src/pages/masterdata/merge.dom.test.tsx` zamień fixturę:

```tsx
const suppliers = [
  { id: 10, name: 'shangai', client_company_id: null, sap_code: '', country: '', address: '' },
  { id: 11, name: 'Shanghai', client_company_id: null, sap_code: '30001', country: 'CN', address: '' },
]
```

W `frontend/src/pages/MasterDataPage.dom.test.tsx` w fixturze `suppliers` (linie 15–16) zamień `company_id: 1` na `client_company_id: null` (tylko w tych dwóch wierszach).

- [ ] **Step 2: Uruchom — ma paść**

Run: `cd frontend && npx vitest run src/pages/masterdata/unmapped.dom.test.tsx`
Expected: FAIL (opcje `['', '11', …]` nie pasują / `company_id` brak w body / przycisk `supPurgeBtn` istnieje).

- [ ] **Step 3: Typ `Supplier`**

W `frontend/src/types/core.ts` zastąp interfejs:

```ts
export interface Supplier extends Named {
  // null/brak = kartoteka dostawców Acme; liczba = nadawca kontenerów tej spółki-klienta
  client_company_id?: number | null
  is_active?: boolean
  address?: string
  note?: string
  column_map?: string
  sap_code?: string
  country?: string
}
```

- [ ] **Step 4: i18n**

Zastąp `frontend/src/i18n/features/dostawcy-mapowanie.ts`:

```ts
// Dostawcy: mapowanie nazw z pliku kolejki (aliasy per spółka pliku)
import { defineFeature } from '../feature'

export default defineFeature({
  pl: {
    supUnmappedTitle: 'Do zmapowania',
    supUnmappedHint: 'Nazwy dostawców z pliku kolejki bez dopasowania w słowniku — zmapuj na dostawcę, a kolejne importy trafią same.',
    supContainersN: '{n} kont.',
    supPick: 'wybierz dostawcę',
    supMap: 'Mapuj',
    supNewFromName: '+ Nowy dostawca',
    supMappedN: 'Przypisano kontenerów: {n}',
    supRawHint: 'Nazwa z pliku — do zmapowania',
  },
  en: {
    supUnmappedTitle: 'To map',
    supUnmappedHint: 'Supplier names from the queue file with no dictionary match — map them to a supplier and future imports will follow.',
    supContainersN: '{n} cont.',
    supPick: 'pick a supplier',
    supMap: 'Map',
    supNewFromName: '+ New supplier',
    supMappedN: 'Containers assigned: {n}',
    supRawHint: 'Name from file — to be mapped',
  },
  pt: {
    supUnmappedTitle: 'Por mapear',
    supUnmappedHint: 'Nomes de fornecedores do ficheiro da fila sem correspondência no dicionário — mapeie-os e as próximas importações seguirão.',
    supContainersN: '{n} cont.',
    supPick: 'escolha o fornecedor',
    supMap: 'Mapear',
    supNewFromName: '+ Novo fornecedor',
    supMappedN: 'Contentores atribuídos: {n}',
    supRawHint: 'Nome do ficheiro — por mapear',
  },
})
```

Utwórz `frontend/src/i18n/features/kartoteka-dostawcow.ts` (Task 8 dopisze klucze `supRes*`):

```ts
// Kartoteka dostawców (spec 2026-09-25): jedna kartoteka Acme + nadawcy spółek-klientów
import { defineFeature } from '../feature'

export default defineFeature({
  pl: {
    supCatalog: 'Kartoteka (Acme)',
    supOwner: 'Kartoteka / spółka',
  },
  en: {
    supCatalog: 'Catalogue (Acme)',
    supOwner: 'Catalogue / company',
  },
  pt: {
    supCatalog: 'Cadastro (Acme)',
    supOwner: 'Cadastro / empresa',
  },
})
```

- [ ] **Step 5: `UnmappedSuppliersPanel` bez czyszczenia słownika**

Zastąp całą zawartość `frontend/src/pages/masterdata/UnmappedSuppliersPanel.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { api, errorMessage } from '../../api'
import { useToast } from '../../feedback'
import { useT } from '../../i18n'
import type { Supplier } from '../../types'

// „Do zmapowania": import kolejki nie tworzy dostawców — nazwy z pliku bez dopasowania
// mapujemy tu na dostawcę (alias w spółce pliku). Spółka na materiałach Acme (catalog)
// mapuje na kartotekę, spółka-klient — na swoich nadawców. Backend przypina od razu
// kontenery z tą nazwą, a kolejne importy rozwiązują ją same.

export interface UnmappedRow { name: string; company_id: number; containers: number; catalog: boolean }

export default function UnmappedSuppliersPanel({ suppliers, isAdmin, onNew }: {
  suppliers: Supplier[]
  isAdmin: boolean
  onNew: (row: UnmappedRow) => void
}) {
  const t = useT()
  const { showToast } = useToast()
  const [rows, setRows] = useState<UnmappedRow[]>([])
  const [pick, setPick] = useState<Record<string, string>>({})
  const load = () =>
    api.get<UnmappedRow[]>('/api/suppliers/unmapped')
      .then(r => setRows(Array.isArray(r) ? r : [])).catch(() => setRows([]))
  useEffect(() => { load() }, [suppliers])

  const keyOf = (r: UnmappedRow) => `${r.company_id}|${r.name}`
  const options = (r: UnmappedRow) => suppliers.filter(s =>
    s.client_company_id === r.company_id || (r.catalog && s.client_company_id == null))
  const map = (r: UnmappedRow) =>
    api.post<{ assigned: number }>(`/api/suppliers/${pick[keyOf(r)]}/aliases`,
                                   { alias: r.name, company_id: r.company_id })
      .then(res => { showToast(t('supMappedN').replace('{n}', String(res.assigned))); load() })
      .catch(err => showToast(errorMessage(err), 'error'))

  if (!rows.length) return null
  return (
    <div className="panel" style={{ margin: '8px 0' }} aria-label={t('supUnmappedTitle')}>
      <b>{t('supUnmappedTitle')} ({rows.length})</b>
      <p className="muted" style={{ margin: '4px 0 8px' }}>{t('supUnmappedHint')}</p>
      {rows.map(r => (
        <div key={keyOf(r)} className="row" style={{ gap: 8, flexWrap: 'wrap', padding: '3px 0' }}>
          <span style={{ minWidth: 220, flex: '1 1 220px' }}>{r.name}</span>
          <span className="muted mono" style={{ width: 70 }}>
            {t('supContainersN').replace('{n}', String(r.containers))}</span>
          <select aria-label={`${t('supPick')}: ${r.name}`} value={pick[keyOf(r)] ?? ''}
                  onChange={e => setPick(p => ({ ...p, [keyOf(r)]: e.target.value }))}>
            <option value="">— {t('supPick')} —</option>
            {options(r).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <button className="btn small" disabled={!pick[keyOf(r)]} onClick={() => map(r)}>
            {t('supMap')}</button>
          {isAdmin && (
            <button className="btn small secondary" onClick={() => onNew(r)}>
              {t('supNewFromName')}</button>
          )}
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Step 6: `SuppliersTab` — właściciel zamiast spółki**

W `frontend/src/pages/MasterDataPage.tsx` zastąp całą funkcję `SuppliersTab` (od `function SuppliersTab(` do jej zamykającego `}` przed `function PortsTab()`):

```tsx
function SuppliersTab({ companies }: { companies: Company[] }) {
  const t = useT()
  const isAdmin = useIsAdmin()
  const { showToast } = useToast()
  const [rows, setRows] = useState<Supplier[]>([])
  const [q, setQ] = useState('')
  // właściciel: '' = wszyscy, 'catalog' = kartoteka Acme, id = nadawcy spółki-klienta
  const [owner, setOwner] = useState('')
  const [act, setAct] = useState<ActiveFilter>('')
  // scalanie duplikatów: źródło znika, jego kontenery/zamówienia/kontakty
  // przechodzą na cel, brakujące pola celu uzupełniane z duplikatu
  const [mergeSource, setMergeSource] = useState<Supplier | null>(null)
  const [mergeTarget, setMergeTarget] = useState('')
  // „+ Nowy dostawca" z panelu Do zmapowania: wiersz dodawania z nazwą i właścicielem z pliku
  const [addPrefill, setAddPrefill] = useState<{ name: string; company: string } | null>(null)
  const [addSignal, setAddSignal] = useState(0)
  const doMerge = () => {
    if (!mergeSource || !mergeTarget) return
    api.post(`/api/suppliers/${mergeSource.id}/merge`, { target_id: Number(mergeTarget) })
      .then(() => { showToast(t('mdMergeDone')); setMergeSource(null); load() })
      .catch(err => showToast(errorMessage(err), 'error'))
  }
  const load = () => {
    setAddPrefill(null)
    return api.get<Supplier[]>('/api/suppliers?include_inactive=true').then(setRows).catch(() => {})
  }
  useEffect(() => { load() }, [])

  const ownerOf = (s: Supplier) => s.client_company_id ?? null
  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return filterActive(rows, act).filter(s =>
      (!owner || (owner === 'catalog' ? ownerOf(s) === null : ownerOf(s) === Number(owner)))
      && (!needle || s.name.toLowerCase().includes(needle)
          || (s.sap_code ?? '').toLowerCase().includes(needle)))
  }, [rows, q, owner, act])

  const ownerName = (s: Supplier) => {
    const id = ownerOf(s)
    return id === null ? t('supCatalog') : companies.find(c => c.id === id)?.name ?? String(id)
  }
  const cols: Col<Supplier>[] = [
    { key: 'sap', label: t('sapCode'), get: s => s.sap_code ?? '', width: '110px' },
    { key: 'name', label: t('name'), get: s => s.name,
      render: s => <Link to={`/dostawcy/${s.id}`}>{s.name}</Link>,
      edit: { type: 'text', width: 180 } },
    { key: 'country', label: t('mdCountry'), get: s => s.country ?? '', width: '70px' },
    { key: 'address', label: t('mdAddress'), get: s => s.address ?? '',
      edit: { type: 'text', width: 220 } },
    { key: 'company', label: t('supOwner'), get: ownerName, width: '150px',
      // właściciela nie zmieniamy po utworzeniu; spółka z materiałami Acme → kartoteka (backend)
      edit: { type: 'select', createOnly: true, value: () => '',
              options: [{ value: '', label: t('supCatalog') },
                        ...companies.map(c => ({ value: String(c.id), label: c.name }))] } },
    { key: 'active', label: t('active'), get: s => (s.is_active !== false ? 1 : 0), width: '80px',
      render: s => (s.is_active !== false ? '✓' : '—'),
      edit: { type: 'check' } },
  ]
  if (isAdmin) {
    // pola z dawnej Administracji → Dostawcy (scalone w jedną sekcję)
    cols.push(
      { key: 'note', label: t('mdNote'), get: s => s.note ?? '', edit: { type: 'text', width: 160 } },
      { key: 'colmap', label: t('columnMap'),
        get: s => s.column_map ?? '', edit: { type: 'text', width: 200 } })
    cols.push({ key: 'merge', label: '', get: () => '', width: '90px',
      render: s => (
        <button className="btn small secondary" title={t('mergeHint')}
                onClick={() => { setMergeSource(s); setMergeTarget('') }}>
          {t('mdMerge')}</button>
      ) })
  }
  // scalać można tylko w obrębie właściciela (kartoteka z kartoteką, nadawcy jednej spółki)
  const mergeTargets = mergeSource
    ? rows.filter(s => s.id !== mergeSource.id && ownerOf(s) === ownerOf(mergeSource))
    : []
  return (
    <div className="panel">
      {isAdmin && <p className="muted" style={{ margin: '0 0 6px' }}>
        {t('columnMap')}: {t('columnMapHint')}</p>}
      <UnmappedSuppliersPanel suppliers={rows} isAdmin={isAdmin}
        onNew={r => {
          setAddPrefill({ name: r.name, company: r.catalog ? '' : String(r.company_id) })
          setAddSignal(n => n + 1)
        }} />
      {mergeSource && (
        <div className="panel" role="dialog" aria-label={t('mdMergeTitle')}
             style={{ margin: '8px 0', display: 'flex', gap: 8, alignItems: 'center',
                      flexWrap: 'wrap' }}>
          <b>{t('mdMergeTitle')}</b>
          <span>{mergeSource.name} →</span>
          <select value={mergeTarget} onChange={e => setMergeTarget(e.target.value)}>
            <option value="">— {t('mdMergePick')} —</option>
            {mergeTargets.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <button className="btn small" disabled={!mergeTarget} onClick={doMerge}>
            {t('mdMergeDo')}</button>
          <button className="btn small secondary" onClick={() => setMergeSource(null)}>
            {t('cancel')}</button>
          <span className="muted">{t('mergeHint')}</span>
        </div>
      )}
      <EditableTable cols={cols} rows={filtered} csvName="dostawcy.csv" refresh={load}
        canEdit={isAdmin} editPath="/api/suppliers" createPath="/api/suppliers"
        deletePath="/api/suppliers" entityType="suppliers" nameOf={s => s.name}
        addDefaults={{ active: true, company: '', ...addPrefill }}
        addSignal={addSignal}
        buildBody={(row, v) => ({
          name: str(v.name), is_active: v.active === true,
          address: str(v.address),
          note: v.note === undefined ? row?.note ?? '' : str(v.note),
          column_map: v.colmap === undefined ? row?.column_map ?? '' : str(v.colmap),
          company_id: row ? null : num(v.company),
        })}
        leftControls={<>
          <input placeholder={t('mdSearch')} value={q} onChange={e => setQ(e.target.value)} />
          <select aria-label={t('supOwner')} value={owner} onChange={e => setOwner(e.target.value)}>
            <option value="">— {t('supOwner')} —</option>
            <option value="catalog">{t('supCatalog')}</option>
            {companies.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <ActivePills rows={rows} value={act} onChange={setAct} />
        </>} />
    </div>
  )
}
```

- [ ] **Step 7: Uruchom testy tasku**

Run: `cd frontend && npx vitest run src/pages/masterdata src/pages/MasterDataPage.dom.test.tsx src/i18n.unused.test.ts src/i18n.features.test.ts && npx tsc -b --noEmit`
Expected: PASS, `tsc` bez błędów.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/types/core.ts frontend/src/pages/MasterDataPage.tsx frontend/src/pages/masterdata/UnmappedSuppliersPanel.tsx frontend/src/pages/masterdata/unmapped.dom.test.tsx frontend/src/pages/masterdata/merge.dom.test.tsx frontend/src/pages/MasterDataPage.dom.test.tsx frontend/src/i18n/features/dostawcy-mapowanie.ts frontend/src/i18n/features/kartoteka-dostawcow.ts
git commit -m "feat(dostawcy): zakładka Dostawcy — kartoteka/nadawca zamiast spółki, bez czyszczenia słownika

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DuL7wEFJzFdfPbCLUGEMNU"
```

---

### Task 8: Front — ekran „Do rozstrzygnięcia"

**Files:**
- Create: `frontend/src/pages/masterdata/SupplierResolvePanel.tsx`
- Create: `frontend/src/pages/masterdata/resolve.dom.test.tsx`
- Modify: `frontend/src/i18n/features/kartoteka-dostawcow.ts`
- Modify: `frontend/src/pages/MasterDataPage.tsx` (import + render panelu w `SuppliersTab`)

**Interfaces:**
- Consumes: `GET /api/suppliers/resolve`, `POST /api/suppliers/resolve/apply`, `POST /api/suppliers/{id}/merge`, `PATCH /api/suppliers/{id}`, `DELETE /api/suppliers/{id}` (Task 6 / istniejące).
- Produces: `SupplierResolvePanel({ suppliers: Supplier[], onChanged: () => void })`.

- [ ] **Step 1: Napisz test (failing)**

`frontend/src/pages/masterdata/resolve.dom.test.tsx`:

```tsx
// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import SupplierResolvePanel from './SupplierResolvePanel'

vi.mock('../../i18n', () => ({ useT: () => (key: string) => key }))
const { showToast } = vi.hoisted(() => ({ showToast: vi.fn() }))
vi.mock('../../feedback', () => ({ useToast: () => ({ showToast }) }))
const { apiGet, apiPost, apiPatch, apiDel } = vi.hoisted(() => ({
  apiGet: vi.fn(), apiPost: vi.fn(), apiPatch: vi.fn(), apiDel: vi.fn() }))
vi.mock('../../api', () => ({
  api: { get: apiGet, post: apiPost, patch: apiPatch, del: apiDel, upload: vi.fn() },
  errorMessage: (e: unknown) => String(e),
}))

const brief = (id: number, name: string, sap = '', usage = 0) =>
  ({ id, name, sap_code: sap, country: 'CN', is_active: true, usage })
const plan = {
  merge_groups: [{ sap_code: '200', target: brief(2, 'Ningbo Tools', '200', 3),
                   sources: [brief(1, 'Ningbo Tools', '200', 1)] }],
  unresolved: [{ ...brief(5, 'NINGBO TOOLS'), suggestion: brief(2, 'Ningbo Tools', '200', 3) },
               { ...brief(6, 'Nikt', '', 2), suggestion: null }],
}
const suppliers = [
  { id: 2, name: 'Ningbo Tools', sap_code: '200', client_company_id: null, address: 'A', note: '', column_map: '' },
  { id: 6, name: 'Nikt', sap_code: '', client_company_id: null, address: 'Adres 6', note: 'n', column_map: '' },
]

afterEach(() => { cleanup(); vi.clearAllMocks() })

describe('Do rozstrzygnięcia', () => {
  it('scala wszystkie grupy i pojedynczego z podpowiedzią', async () => {
    apiGet.mockResolvedValue(plan)
    apiPost.mockResolvedValue({})
    const onChanged = vi.fn()
    render(<SupplierResolvePanel suppliers={suppliers as never} onChanged={onChanged} />)
    fireEvent.click(await screen.findByText('supResShow'))
    fireEvent.click(screen.getByText('supResMergeAll'))
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/suppliers/resolve/apply', {}))
    await waitFor(() => expect(onChanged).toHaveBeenCalled())

    const pick = screen.getByLabelText('mdMergePick: NINGBO TOOLS') as HTMLSelectElement
    expect(pick.value).toBe('2')
    fireEvent.click(screen.getAllByText('supResMerge')[0])
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/suppliers/5/merge', { target_id: 2 }))
  })

  it('nieaktywny zachowuje pola wiersza; usuwanie tylko bez powiązań', async () => {
    apiGet.mockResolvedValue(plan)
    apiPatch.mockResolvedValue({})
    render(<SupplierResolvePanel suppliers={suppliers as never} onChanged={() => {}} />)
    fireEvent.click(await screen.findByText('supResShow'))
    fireEvent.click(screen.getAllByText('supResInactive')[1])
    await waitFor(() => expect(apiPatch).toHaveBeenCalledWith('/api/suppliers/6', {
      name: 'Nikt', is_active: false, address: 'Adres 6', note: 'n', column_map: '' }))
    const del = screen.getAllByText('supResDelete') as HTMLButtonElement[]
    expect(del[0].disabled).toBe(false)   // NINGBO TOOLS: 0 użyć
    expect(del[1].disabled).toBe(true)    // Nikt: 2 użycia — tylko nieaktywny
  })

  it('nieoczekiwany kształt odpowiedzi (ogólny mock listy dostawców) → brak panelu', async () => {
    apiGet.mockResolvedValue([{ id: 1, name: 'x' }])
    const { container } = render(<SupplierResolvePanel suppliers={[]} onChanged={() => {}} />)
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith('/api/suppliers/resolve'))
    expect(container.textContent).toBe('')
  })
})
```

- [ ] **Step 2: Uruchom — ma paść**

Run: `cd frontend && npx vitest run src/pages/masterdata/resolve.dom.test.tsx`
Expected: FAIL (`Failed to resolve import "./SupplierResolvePanel"`).

- [ ] **Step 3: Teksty**

Zastąp `frontend/src/i18n/features/kartoteka-dostawcow.ts`:

```ts
// Kartoteka dostawców (spec 2026-09-25): jedna kartoteka Acme + nadawcy spółek-klientów,
// ekran „Do rozstrzygnięcia" (scalanie dawnych kopii per spółka)
import { defineFeature } from '../feature'

export default defineFeature({
  pl: {
    supCatalog: 'Kartoteka (Acme)',
    supOwner: 'Kartoteka / spółka',
    supResTitle: 'Do rozstrzygnięcia',
    supResSummary: '{g} grup tego samego kodu SAP · {u} bez kodu SAP',
    supResShow: 'Pokaż',
    supResHide: 'Ukryj',
    supResGroupsHint: 'Ten sam kod SAP w kilku rekordach (dawne kopie per spółka). Scalenie przepina kontenery, zamówienia, faktury, profile i kontakty na rekord, który zostaje.',
    supResMergeAll: 'Scal wszystkie ({n})',
    supResMergedAll: 'Scalono duplikatów: {n}',
    supResKeep: 'Zostaje',
    supResDuplicates: 'Duplikaty (użycia)',
    supResMore: '…i {n} kolejnych',
    supResNoSapHint: 'Dostawcy bez kodu SAP: scal z dostawcą z SAP, oznacz jako nieaktywnego (ma powiązania) albo usuń (bez powiązań).',
    supResUsage: 'Użycia',
    supResMerge: 'Scal',
    supResInactive: 'Nieaktywny',
    supResDelete: 'Usuń',
    supResDone: 'Zapisano',
  },
  en: {
    supCatalog: 'Catalogue (Acme)',
    supOwner: 'Catalogue / company',
    supResTitle: 'To resolve',
    supResSummary: '{g} groups with the same SAP code · {u} without SAP code',
    supResShow: 'Show',
    supResHide: 'Hide',
    supResGroupsHint: 'The same SAP code in several records (former per-company copies). Merging moves containers, orders, invoices, profiles and contacts to the record that stays.',
    supResMergeAll: 'Merge all ({n})',
    supResMergedAll: 'Duplicates merged: {n}',
    supResKeep: 'Stays',
    supResDuplicates: 'Duplicates (uses)',
    supResMore: '…and {n} more',
    supResNoSapHint: 'Suppliers without SAP code: merge with a SAP supplier, mark inactive (has links) or delete (no links).',
    supResUsage: 'Uses',
    supResMerge: 'Merge',
    supResInactive: 'Inactive',
    supResDelete: 'Delete',
    supResDone: 'Saved',
  },
  pt: {
    supCatalog: 'Cadastro (Acme)',
    supOwner: 'Cadastro / empresa',
    supResTitle: 'Por resolver',
    supResSummary: '{g} grupos com o mesmo código SAP · {u} sem código SAP',
    supResShow: 'Mostrar',
    supResHide: 'Ocultar',
    supResGroupsHint: 'O mesmo código SAP em vários registos (antigas cópias por empresa). A fusão move contentores, encomendas, faturas, perfis e contactos para o registo que fica.',
    supResMergeAll: 'Fundir todos ({n})',
    supResMergedAll: 'Duplicados fundidos: {n}',
    supResKeep: 'Fica',
    supResDuplicates: 'Duplicados (utilizações)',
    supResMore: '…e mais {n}',
    supResNoSapHint: 'Fornecedores sem código SAP: fundir com um fornecedor SAP, marcar como inativo (tem ligações) ou eliminar (sem ligações).',
    supResUsage: 'Utilizações',
    supResMerge: 'Fundir',
    supResInactive: 'Inativo',
    supResDelete: 'Eliminar',
    supResDone: 'Guardado',
  },
})
```

- [ ] **Step 4: Komponent**

`frontend/src/pages/masterdata/SupplierResolvePanel.tsx`:

```tsx
// „Do rozstrzygnięcia" (kartoteka dostawców, spec 2026-09-25 §3): po przejściu na jedną
// globalną kartotekę — grupy tego samego kodu SAP (dawne kopie per spółka) do scalenia jednym
// przyciskiem oraz dostawcy bez kodu SAP do decyzji: scal / nieaktywny / usuń (bez powiązań).
import { useEffect, useState } from 'react'
import { api, errorMessage } from '../../api'
import { useToast } from '../../feedback'
import { useT } from '../../i18n'
import type { Supplier } from '../../types'

interface Brief { id: number; name: string; sap_code: string; country: string; is_active: boolean; usage: number }
interface Group { sap_code: string; target: Brief; sources: Brief[] }
interface Unresolved extends Brief { suggestion: Brief | null }
interface Proposal { merge_groups: Group[]; unresolved: Unresolved[] }

const SHOWN = 50   // ponytail: pierwsze 50 wierszy + licznik; paginacja, gdyby lista realnie tyle miała

// kształt sprawdzany: ogólne mocki api w testach stron zwracają listę dostawców pod /api/suppliers*
const isProposal = (x: unknown): x is Proposal =>
  typeof x === 'object' && x !== null
  && Array.isArray((x as Proposal).merge_groups) && Array.isArray((x as Proposal).unresolved)

export default function SupplierResolvePanel({ suppliers, onChanged }: {
  suppliers: Supplier[]
  onChanged: () => void
}) {
  const t = useT()
  const { showToast } = useToast()
  const [plan, setPlan] = useState<Proposal | null>(null)
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [pick, setPick] = useState<Record<number, string>>({})
  const load = () => api.get<unknown>('/api/suppliers/resolve')
    .then(r => setPlan(isProposal(r) ? r : null)).catch(() => setPlan(null))
  useEffect(() => { load() }, [])

  if (!plan || (!plan.merge_groups.length && !plan.unresolved.length)) return null
  const sapTargets = suppliers.filter(s => s.client_company_id == null && s.sap_code)
  const dupCount = plan.merge_groups.reduce((n, g) => n + g.sources.length, 0)
  const act = (call: Promise<unknown>, msg: string) => {
    setBusy(true)
    call.then(() => { showToast(msg); load(); onChanged() })
      .catch(err => showToast(errorMessage(err), 'error'))
      .finally(() => setBusy(false))
  }
  const targetOf = (r: Unresolved) => pick[r.id] ?? (r.suggestion ? String(r.suggestion.id) : '')
  // PATCH podmienia wszystkie pola — reszta z wiersza słownika, żeby nie wyczyścić adresu/notatki
  const deactivate = (r: Unresolved) => {
    const s = suppliers.find(x => x.id === r.id)
    act(api.patch(`/api/suppliers/${r.id}`, {
      name: r.name, is_active: false, address: s?.address ?? '', note: s?.note ?? '',
      column_map: s?.column_map ?? '' }), t('supResDone'))
  }
  const remove = (r: Unresolved) => {
    if (window.confirm(`${t('confirmDeleteEntry')} „${r.name}"?`))
      act(api.del(`/api/suppliers/${r.id}`), t('supResDone'))
  }
  return (
    <div className="panel" style={{ margin: '8px 0' }} aria-label={t('supResTitle')}>
      <div className="row" style={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <b>{t('supResTitle')}</b>
        <span className="muted">{t('supResSummary')
          .replace('{g}', String(plan.merge_groups.length))
          .replace('{u}', String(plan.unresolved.length))}</span>
        <button className="btn small secondary" onClick={() => setOpen(o => !o)}>
          {open ? t('supResHide') : t('supResShow')}</button>
      </div>
      {open && plan.merge_groups.length > 0 && (
        <section style={{ marginTop: 8 }}>
          <div className="row" style={{ gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <span className="muted" style={{ flex: '1 1 320px' }}>{t('supResGroupsHint')}</span>
            <button className="btn small" disabled={busy}
                    onClick={() => act(api.post('/api/suppliers/resolve/apply', {}),
                                       t('supResMergedAll').replace('{n}', String(dupCount)))}>
              {t('supResMergeAll').replace('{n}', String(dupCount))}</button>
          </div>
          <table className="grid">
            <thead><tr>
              <th>{t('sapCode')}</th><th>{t('supResKeep')}</th><th>{t('supResDuplicates')}</th>
            </tr></thead>
            <tbody>{plan.merge_groups.slice(0, SHOWN).map(g => (
              <tr key={g.sap_code}>
                <td className="mono">{g.sap_code}</td><td>{g.target.name}</td>
                <td>{g.sources.map(s => `${s.name} (${s.usage})`).join(', ')}</td>
              </tr>))}</tbody>
          </table>
          {plan.merge_groups.length > SHOWN && <p className="muted">
            {t('supResMore').replace('{n}', String(plan.merge_groups.length - SHOWN))}</p>}
        </section>
      )}
      {open && plan.unresolved.length > 0 && (
        <section style={{ marginTop: 8 }}>
          <p className="muted">{t('supResNoSapHint')}</p>
          <table className="grid">
            <thead><tr>
              <th>{t('name')}</th><th>{t('mdCountry')}</th><th>{t('supResUsage')}</th><th />
            </tr></thead>
            <tbody>{plan.unresolved.slice(0, SHOWN).map(r => (
              <tr key={r.id}>
                <td>{r.name}</td><td>{r.country}</td><td className="mono">{r.usage}</td>
                <td><div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
                  <select aria-label={`${t('mdMergePick')}: ${r.name}`} value={targetOf(r)}
                          onChange={e => setPick(p => ({ ...p, [r.id]: e.target.value }))}>
                    <option value="">— {t('mdMergePick')} —</option>
                    {sapTargets.map(s => (
                      <option key={s.id} value={s.id}>{s.sap_code} · {s.name}</option>))}
                  </select>
                  <button className="btn small" disabled={busy || !targetOf(r)}
                          onClick={() => act(api.post(`/api/suppliers/${r.id}/merge`,
                                                      { target_id: Number(targetOf(r)) }),
                                             t('mdMergeDone'))}>
                    {t('supResMerge')}</button>
                  <button className="btn small secondary" disabled={busy}
                          onClick={() => deactivate(r)}>{t('supResInactive')}</button>
                  <button className="btn small danger" disabled={busy || r.usage > 0}
                          onClick={() => remove(r)}>{t('supResDelete')}</button>
                </div></td>
              </tr>))}</tbody>
          </table>
          {plan.unresolved.length > SHOWN && <p className="muted">
            {t('supResMore').replace('{n}', String(plan.unresolved.length - SHOWN))}</p>}
        </section>
      )}
    </div>
  )
}
```

- [ ] **Step 5: Wpięcie w zakładkę Dostawcy**

W `frontend/src/pages/MasterDataPage.tsx`:
- po `import UnmappedSuppliersPanel from './masterdata/UnmappedSuppliersPanel'` dodaj `import SupplierResolvePanel from './masterdata/SupplierResolvePanel'`;
- w `SuppliersTab`, bezpośrednio przed `<UnmappedSuppliersPanel`, dodaj:

```tsx
      {isAdmin && <SupplierResolvePanel suppliers={rows} onChanged={load} />}
```

- [ ] **Step 6: Uruchom testy + typy + długości plików**

Run: `cd frontend && npx vitest run src/pages/masterdata src/pages/MasterDataPage.dom.test.tsx src/i18n.unused.test.ts src/i18n.features.test.ts && npx tsc -b --noEmit && cd .. && python scripts/check_file_lengths.py`
Expected: PASS, brak błędów `tsc`, `check_file_lengths` bez wyjścia (exit 0).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/masterdata/SupplierResolvePanel.tsx frontend/src/pages/masterdata/resolve.dom.test.tsx frontend/src/i18n/features/kartoteka-dostawcow.ts frontend/src/pages/MasterDataPage.tsx
git commit -m "feat(dostawcy): ekran Do rozstrzygnięcia — scalanie dubli kodu SAP i dostawców bez SAP

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DuL7wEFJzFdfPbCLUGEMNU"
```

---

### Task 9: Weryfikacja całości, wizualnie, PR i procedura prod

**Files:** brak nowych (ewentualne poprawki po testach).

- [ ] **Step 1: Świeży main i pełne suity**

```bash
git fetch origin main && git merge origin/main
cd backend && python -m pytest tests/ -q
cd ../frontend && npm run test && npm run build
cd .. && python scripts/check_file_lengths.py
```
Expected: backend i frontend PASS, `npm run build` bez błędów, długości OK. Po merge'u `main` ponownie sprawdź `tests/test_migration_chain.py` — jeśli na main pojawiła się nowa migracja, przepnij `down_revision` w `kartoteka001` (i asercję w `test_kartoteka_migration.py`) na nową głowę.

- [ ] **Step 2: Weryfikacja wizualna (Playwright, jak w pamięci „Weryfikacja wizualna Playwright")**

Backend na porcie 8010 (świeża baza SQLite w katalogu tymczasowym — stara `timporye.db` ma `suppliers.company_id NOT NULL`), Vite 5180, admin/admin123. Zasiej przez API: dwóch dostawców z tym samym `sap_code` (import LFA1 dwukrotnie się nie zdubluje — użyj `POST /api/suppliers` + ręcznego `sap_code` przez `db`), jednego bez kodu. Zrzuty `/master-data/dostawcy` 1366 i 1920 px oraz w trybie ciemnym: panel „Do rozstrzygnięcia" zwinięty i rozwinięty, kolumna „Kartoteka / spółka", brak przycisku „Wyczyść słownik dostawców". Pokaż zrzuty użytkownikowi.

- [ ] **Step 3: Push i PR**

```bash
git push -u origin claude/kartoteka-dostawcy-1-model
gh pr create --base main --title "Kartoteka dostawców PR1: globalna kartoteka, scalanie dubli, Do rozstrzygnięcia" --body-file -
```

Treść PR (stdin) — zawiera procedurę prod:

```markdown
Spec: docs/superpowers/specs/2026-09-25-kartoteka-dostawcy-design.md (§9 pkt 1). Plan: docs/superpowers/plans/2026-09-25-kartoteka-dostawcy-1-model.md

## Co
- `suppliers` globalne: `company_id` → `client_company_id` (NULL = kartoteka Acme; ustawione = nadawca spółki-klienta Borealis/Cobalt), pola SAP/mapy, kontakty z rolą/komunikatorem, `supplier_materials` (kopia map jako unconfirmed), `supplier_doc_variants`, próbki z sha256/statusem, `sap_imports` — migracja `kartoteka001`.
- Widoczność w `deps.py`, lista spółek „z materiałami" w `SUPPLIER_COMPANY_CODES` (domyślnie `ACME,PT`).
- Scalanie dubli: podgląd + wykonanie (`scripts/consolidate_suppliers.py`, ekran Master data → Dostawcy → „Do rozstrzygnięcia"); ta sama funkcja co „Scal z…".
- Import LFA1 do jednej kartoteki (klucz kod SAP). Usunięte: „Wyczyść słownik dostawców", `scripts/import_lfa1.py`.

## Zmiany zachowania
- Magazyn, agencja, spedytor: na listach dostawców same nazwy (bez adresu/kodu SAP); karta dostawcy z kartoteki → 404. Warstwa „fabryki" na mapie trackingu znika dla tych ról.
- Borealis/Cobalt: widzą tylko swoich nadawców (jak dziś).

## Wdrożenie na prod (kolejność!)
1. Kopia bazy (`sh scripts/backup.sh` w kontenerze backendu) i próba na kopii lokalnie: `alembic upgrade head` + `python -m scripts.consolidate_suppliers` (podgląd).
2. Merge → deploy (migracja `kartoteka001` — tylko schemat + kopia map; bez scalania). Deploy poza godzinami pracy: stare kontenery przez chwilę czytają `suppliers.company_id`.
3. Na prod: `docker exec <backend> python -m scripts.consolidate_suppliers` → przejrzyj listę → `--apply` (albo przycisk „Scal wszystkie" na ekranie).
4. Admin rozstrzyga dostawców bez kodu SAP na ekranie „Do rozstrzygnięcia".
5. Gdy podgląd pokazuje `Grup do scalenia: 0` — oznacz PR etapu B (unikalności) jako gotowy.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01DuL7wEFJzFdfPbCLUGEMNU
```

- [ ] **Step 4: Obserwuj CI/automerge**

`gh pr checks --watch`; po merge'u potwierdź, że commit jest na `origin/main` (`git fetch && git log origin/main --oneline -3`). Deploy zgodnie z procedurą wyżej — kroki 3–5 wykonuje użytkownik/admin (dotyka danych prod).

---

### Task 10 (etap B — OSOBNY PR jako draft, gotowy dopiero po scaleniu na prod): unikalności kartoteki

**Files:**
- Create: `backend/migrations/versions/kartoteka002_unikalnosci_kartoteki.py`
- Modify: `backend/app/models/dictionaries.py` (`Supplier`, `SupplierContact` — `__table_args__`; import `Index`)
- Modify: `backend/app/routers/dictionaries_ref.py` (`create_supplier_contact` — 409 na zdublowany e-mail; import `func`)
- Modify: `backend/tests/test_kartoteka_migration.py` (nowy test)
- Create: `backend/tests/test_supplier_uniques.py`

**Interfaces:**
- Consumes: `_load`, `_engine`, `_apply` z `test_kartoteka_migration.py` (Task 1); `merge_into` przenoszący `sap_code` bez kolizji (Task 4).
- Produces: indeksy `uq_suppliers_sap_code` (`sap_code` WHERE `sap_code <> '' AND client_company_id IS NULL`) i `uq_supplier_contacts_email` (`supplier_id, lower(email)` WHERE `email <> ''`); funkcja migracji `check_duplicates(conn) -> list[str]`.

- [ ] **Step 1: Gałąź po merge'u PR1**

```bash
git fetch origin && git checkout -b claude/kartoteka-dostawcy-1b-unikalnosci origin/main
```

- [ ] **Step 2: Napisz testy (failing)**

Dopisz na końcu `backend/tests/test_kartoteka_migration.py` (i dodaj `import pytest` oraz `from sqlalchemy.exc import IntegrityError` do importów):

```python
PRE_002 = [
    "CREATE TABLE orders (id INTEGER PRIMARY KEY, supplier_contact_id INTEGER)",
    "CREATE TABLE suppliers (id INTEGER PRIMARY KEY, sap_code VARCHAR(20) NOT NULL DEFAULT '', "
    "client_company_id INTEGER)",
    "CREATE TABLE supplier_contacts (id INTEGER PRIMARY KEY, supplier_id INTEGER NOT NULL, "
    "email VARCHAR(200) NOT NULL DEFAULT '')",
    # 100 dwa razy w kartotece (blokuje) + raz u nadawcy klienta (poza unikalnością)
    "INSERT INTO suppliers VALUES (1,'100',NULL),(2,'100',NULL),(3,'100',7),(4,'',NULL),(5,'',NULL)",
    "INSERT INTO supplier_contacts VALUES (1,1,'A@x'),(2,1,'a@x'),(3,2,'a@x'),(4,1,''),(5,1,'')",
    "INSERT INTO orders VALUES (1,2)",
]


def test_kartoteka002_refuses_sap_duplicates_then_dedupes_contacts(tmp_path, monkeypatch):
    mig = _load("kartoteka002_unikalnosci_kartoteki.py")
    assert mig.down_revision == "kartoteka001"
    eng = _engine(tmp_path, PRE_002)
    with pytest.raises(RuntimeError, match="kodów SAP"):
        _apply(eng, mig, mig.upgrade, monkeypatch)
    with eng.begin() as c:
        c.exec_driver_sql("UPDATE suppliers SET sap_code = '101' WHERE id = 2")
    _apply(eng, mig, mig.upgrade, monkeypatch)
    with eng.connect() as c:
        # ten sam e-mail u tego samego dostawcy = jeden kontakt; zamówienie na pozostały
        assert c.exec_driver_sql("SELECT supplier_contact_id FROM orders").scalar() == 1
        assert [r[0] for r in c.exec_driver_sql(
            "SELECT id FROM supplier_contacts ORDER BY id")] == [1, 3, 4, 5]
    with pytest.raises(IntegrityError), eng.begin() as c:
        c.exec_driver_sql("INSERT INTO suppliers VALUES (6,'100',NULL)")
    with eng.begin() as c:   # nadawca klienta i puste kody — poza unikalnością
        c.exec_driver_sql("INSERT INTO suppliers VALUES (7,'100',9),(8,'',NULL)")
    with pytest.raises(IntegrityError), eng.begin() as c:
        c.exec_driver_sql("INSERT INTO supplier_contacts VALUES (9,1,'A@X')")
    _apply(eng, mig, mig.downgrade, monkeypatch)
    with eng.begin() as c:
        c.exec_driver_sql("INSERT INTO suppliers VALUES (10,'100',NULL)")
    eng.dispose()
```

`backend/tests/test_supplier_uniques.py`:

```python
"""Etap B kartoteki: unikalny kod SAP w kartotece i e-mail kontaktu per dostawca (model =
create_all w testach) + scalanie przenoszące kod SAP bez kolizji."""
import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Supplier, SupplierContact


def test_catalog_sap_code_unique_but_client_senders_free(db_session):
    db_session.add_all([Supplier(name="A", sap_code="900"), Supplier(name="T", sap_code="900",
                                                                      client_company_id=1)])
    db_session.commit()
    db_session.add(Supplier(name="B", sap_code="900"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_contact_create_rejects_duplicate_email(client, admin_headers, db_session):
    sup = Supplier(name="Mail Co", sap_code="901")
    db_session.add(sup)
    db_session.flush()
    db_session.add(SupplierContact(supplier_id=sup.id, full_name="Li", email="li@m.example"))
    db_session.commit()
    r = client.post("/api/supplier-contacts", headers=admin_headers, json={
        "supplier_id": sup.id, "full_name": "Li 2", "email": "LI@m.example"})
    assert r.status_code == 409


def test_merge_moves_sap_code_without_unique_clash(client, admin_headers, db_session):
    src, dst = Supplier(name="Z kodem", sap_code="902"), Supplier(name="Bez kodu")
    db_session.add_all([src, dst])
    db_session.commit()
    r = client.post(f"/api/suppliers/{src.id}/merge", headers=admin_headers,
                    json={"target_id": dst.id})
    assert r.status_code == 200, r.text
    db_session.expire_all()
    assert db_session.get(Supplier, dst.id).sap_code == "902"
```

- [ ] **Step 3: Uruchom — ma paść**

Run: `cd backend && python -m pytest tests/test_kartoteka_migration.py tests/test_supplier_uniques.py -q`
Expected: FAIL (brak pliku `kartoteka002…`, brak `IntegrityError` dla duplikatu, kontakt zwraca 201).

- [ ] **Step 4: Migracja**

`backend/migrations/versions/kartoteka002_unikalnosci_kartoteki.py`:

```python
"""Unikalności kartoteki dostawców (etap B PR1, spec 2026-09-25 §7): kod SAP w kartotece,
e-mail kontaktu per dostawca (bez wielkości liter). Kontakty z tym samym e-mailem u jednego
dostawcy scalane mechanicznie (to ta sama osoba). Duble kodu SAP — NIE: wymagają decyzji
(scalenie przez „Do rozstrzygnięcia" / scripts.consolidate_suppliers) — precheck zatrzymuje.

Revision ID: kartoteka002
Revises: kartoteka001
"""
import sqlalchemy as sa
from alembic import op

revision = "kartoteka002"
down_revision = "kartoteka001"
branch_labels = None
depends_on = None

SAP_WHERE = "sap_code <> '' AND client_company_id IS NULL"
MAIL_WHERE = "email <> ''"


def check_duplicates(conn) -> list[str]:
    """Duble kodu SAP w kartotece blokujące unikalność (pusty = można zakładać indeks)."""
    dup = conn.execute(sa.text(
        f"SELECT sap_code FROM suppliers WHERE {SAP_WHERE} "
        "GROUP BY sap_code HAVING COUNT(*) > 1")).scalars().all()
    return [f"{len(dup)} kodów SAP zdublowanych w kartotece, np. {', '.join(dup[:5])}"] if dup else []


def upgrade() -> None:
    problems = check_duplicates(op.get_bind())
    if problems:
        raise RuntimeError(
            "kartoteka002: najpierw scal duble dostawców (Master data → Dostawcy → Do "
            "rozstrzygnięcia albo `python -m scripts.consolidate_suppliers --apply`): "
            + "; ".join(problems))
    # ten sam e-mail u tego samego dostawcy = ta sama osoba: zamówienia na najstarszy kontakt
    op.execute(
        "UPDATE orders SET supplier_contact_id = (SELECT MIN(c2.id) FROM supplier_contacts c1 "
        "JOIN supplier_contacts c2 ON c2.supplier_id = c1.supplier_id "
        "AND lower(c2.email) = lower(c1.email) WHERE c1.id = orders.supplier_contact_id) "
        "WHERE supplier_contact_id IN (SELECT id FROM supplier_contacts WHERE email <> '')")
    op.execute(
        "DELETE FROM supplier_contacts WHERE email <> '' AND id NOT IN "
        "(SELECT MIN(id) FROM supplier_contacts WHERE email <> '' GROUP BY supplier_id, lower(email))")
    op.create_index("uq_suppliers_sap_code", "suppliers", ["sap_code"], unique=True,
                    postgresql_where=sa.text(SAP_WHERE), sqlite_where=sa.text(SAP_WHERE))
    op.create_index("uq_supplier_contacts_email", "supplier_contacts",
                    ["supplier_id", sa.text("lower(email)")], unique=True,
                    postgresql_where=sa.text(MAIL_WHERE), sqlite_where=sa.text(MAIL_WHERE))


def downgrade() -> None:
    op.drop_index("uq_supplier_contacts_email", table_name="supplier_contacts")
    op.drop_index("uq_suppliers_sap_code", table_name="suppliers")
```

- [ ] **Step 5: Model i endpoint kontaktu**

W `backend/app/models/dictionaries.py` dodaj `Index,` do importu z `sqlalchemy` (po `ForeignKey,`). W klasie `Supplier` pod `__tablename__` dodaj:

```python
    # kod SAP unikalny w kartotece (etap B, migracja kartoteka002); nadawcy klientów i "" poza
    __table_args__ = (Index("uq_suppliers_sap_code", "sap_code", unique=True,
                            postgresql_where=text("sap_code <> '' AND client_company_id IS NULL"),
                            sqlite_where=text("sap_code <> '' AND client_company_id IS NULL")),)
```

W `SupplierContact` pod `__tablename__`:

```python
    __table_args__ = (Index("uq_supplier_contacts_email", "supplier_id", text("lower(email)"),
                            unique=True, postgresql_where=text("email <> ''"),
                            sqlite_where=text("email <> ''")),)
```

W `backend/app/routers/dictionaries_ref.py` zmień `from sqlalchemy import select` na `from sqlalchemy import func, select` i w `create_supplier_contact` przed `contact = SupplierContact(...)` dodaj:

```python
    if body.email and db.scalar(select(SupplierContact.id).where(
            SupplierContact.supplier_id == body.supplier_id,
            func.lower(SupplierContact.email) == body.email.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Kontakt z tym e-mailem już istnieje u tego dostawcy.")
```

- [ ] **Step 6: Testy + pełna suita**

Run: `cd backend && python -m pytest tests/test_kartoteka_migration.py tests/test_supplier_uniques.py tests/test_migration_chain.py -q && python -m pytest tests/ -q`
Expected: PASS. Czerwony test tworzący dwóch dostawców z tym samym kodem SAP w kartotece → to już niedozwolone (spec §7) — zmień kod w teście.

- [ ] **Step 7: Commit, push, PR jako DRAFT**

```bash
git add backend/migrations/versions/kartoteka002_unikalnosci_kartoteki.py backend/app/models/dictionaries.py backend/app/routers/dictionaries_ref.py backend/tests/test_kartoteka_migration.py backend/tests/test_supplier_uniques.py
git commit -m "feat(dostawcy): unikalny kod SAP w kartotece i e-mail kontaktu (kartoteka002)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DuL7wEFJzFdfPbCLUGEMNU"
git push -u origin claude/kartoteka-dostawcy-1b-unikalnosci
gh pr create --draft --base main --title "Kartoteka dostawców PR1b: unikalności (po scaleniu na prod)" --body "Draft do czasu, aż na prod \`python -m scripts.consolidate_suppliers\` pokaże \`Grup do scalenia: 0\`. Migracja kartoteka002 ma precheck: przy dublach kodu SAP zatrzyma start aplikacji (Dockerfile: alembic upgrade head && uvicorn).

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01DuL7wEFJzFdfPbCLUGEMNU"
```

Oznaczenie jako gotowy (`gh pr ready`) — dopiero po potwierdzeniu użytkownika, że podgląd na prod pokazuje 0 grup.

---

## Self-review (wykonany)

**1. Pokrycie spec (§9 pkt 1 + zakres z polecenia):**
- `suppliers` globalne, bez `company_id` w unikalności/semantyce → Task 1 (+ `client_company_id` dla nadawców klientów — odstępstwo nazwane w Architecture i pytaniach); `sap_code` unikalny → Task 10 (etap B, częściowy indeks); nowe kolumny street/city/zip/vat/sap_status/lat/lng/geo_source/shipping_port_id/note (note już istnieje) → Task 1. `column_map` zostaje do PR5 (świadomie).
- `supplier_contacts` role/messenger/is_primary → Task 1; UNIQUE(supplier, lower(email)) → Task 10.
- `supplier_materials` + przeniesienie map z unconfirmed → Task 1 (kopia w migracji), dedupe przy scalaniu → Task 4; przełączenie dopasowania faktur → PR2 (świadomie).
- `supplier_doc_variants`, rozbudowa `supplier_doc_samples` (sha256 unikalny per profil = per dostawca, doc_type, variant_id, pages, result, status, reason), `sap_imports` → Task 1.
- Migracja scalająca reużywająca `dictionaries_merge` (kontenery, zamówienia, paczki faktur, kontakty, mapy, aliasy, indeksy dostawcy, profile+próbki) → Task 4 (`merge_into`) + Task 6 (serwis, komenda, endpointy, dry-run).
- Ekran „Do rozstrzygnięcia" (scal / nieaktywny / usuń-bez-powiązań) → Task 8; usunięcie „Wyczyść słownik dostawców" → Task 3 (backend) + Task 7 (front).
- Widoczność w `deps.py` z konfigurowalnymi kodami spółek → Task 2 (+ `master_quality` Task 5).
- Wszystkie miejsca z `Supplier.company_id` → tabela wyżej, każde z taskiem albo świadomie pozostawione.
- Limit 500 linii, i18n w `features/`, jedna głowa alembica → Global Constraints + kroki weryfikacji.
- Audyt zmian z importu z użytkownikiem „import SAP <plik>" i wpisy w `sap_imports` → PR2 (tabela gotowa w PR1).

**2. Placeholdery:** brak „TBD/TODO/…"; każdy krok z kodem ma pełny kod. Kroki „zaktualizuj czerwony test" w Task 5/10 opisują konkretną klasę przypadku i konkretną poprawkę (nie da się przewidzieć przyszłych testów z `main`).

**3. Spójność nazw:** `client_company_id` (model, schemat, front), `supplier_clause_for_company`, `supplier_catalog_access`, `scope_suppliers`, `filter_suppliers_by_company_code`, `check_supplier_access`, `is_material_company`, `material_company_codes` (Task 2 → używane w 3, 5); `merge_into(db, spec, source, target, user)` (Task 4 → 6); `proposal`/`apply_groups` (Task 6 → router, komenda, front); `UnmappedRow.catalog` (Task 3 backend → Task 7 front); indeksy `uq_suppliers_sap_code`, `uq_supplier_contacts_email` (migracja = model, Task 10).

## Ryzyka

- **Deploy PR1**: `kartoteka001` usuwa `suppliers.company_id` — stare kontenery aplikacji w trakcie przełączania dostają błędy SQL przez chwilę; wdrażać poza godzinami pracy. Downgrade jest stratny po scaleniu (opisane w migracji).
- **`apply_groups` na dużym słowniku** (LFA1 × 2 spółki = potencjalnie tysiące grup): ~15 zapytań na scalenie — przez HTTP może przekroczyć timeout proxy; na prod zalecana komenda (`docker exec`), przycisk na ekranie — dla mniejszych porcji/po komendzie.
- **Etap B zatrzymuje start aplikacji**, jeśli zostanie wdrożony przed scaleniem (precheck) — dlatego draft + ręczne „ready" po potwierdzeniu 0 grup.
- **Dev SQLite**: stara `timporye.db` ma `company_id NOT NULL` — shim tego nie naprawi; trzeba usunąć plik bazy dev.
- **Zawężenie widoczności** (spec): magazyn/agencja/spedytor tracą szczegóły dostawców (w tym warstwę „fabryki" na mapie trackingu).

## Decyzje usera (2026-09-25, po planie) — WIĄŻĄCE dla tasków

1. Nadawcy Borealis/Cobalt zostają rekordami z `client_company_id` w PR1 (przepięcie na tekst = osobny PR).
2. **Masowe usuwanie kopii bez powiązań** (tysiące kopii LFA1 w słownikach Borealis/Cobalt i inne rekordy bez żadnych powiązań): Task 6 dodaje do serwisu `supplier_consolidation` funkcje `orphans_preview(db) -> {"count": int, "by_company": {code: int}, "sample": [{"id","name","company_code"}] (max 50)}` i `delete_orphans(db, user) -> int` (usuwa tylko rekordy bez ŻADNYCH powiązań — te same sprawdzenia co istniejący DELETE dostawcy — w jednej transakcji, audyt zbiorczy `entity_type="suppliers", field="__orphans_deleted__"` z licznikami i listą id), endpointy `GET /api/suppliers/resolve/orphans` i `POST /api/suppliers/resolve/orphans/delete` (tylko admin), flaga `--delete-orphans` w `scripts/consolidate_suppliers.py` (bez `--apply` = tylko podgląd). Task 8 dodaje w `SupplierResolvePanel` sekcję „Kopie bez powiązań (N)” z podglądem (liczniki per spółka, próbka nazw) i przyciskiem „Usuń N kopii bez powiązań” z potwierdzeniem (wpisanie liczby N). Testy: backend (rekord z kontenerem/zamówieniem/aliasem/profilem NIE jest usuwany; bez powiązań — usuwany; tylko admin), frontend (podgląd, potwierdzenie, wywołanie).
3. Zawężenie dla magazyn/agencja/spedytor (tylko nazwy, bez karty i warstwy fabryk na mapie) — zaakceptowane.
4. PR2: przed usunięciem `supplier_material_maps` eksport do xlsx (kopia) — poza PR1.
5. `column_map` zostaje do PR5.
6. Kod spółki Iberia = `PT` (potwierdzone w `db_bootstrap.py`) — domyślne `SUPPLIER_COMPANY_CODES=ACME,PT` poprawne.
7. (2026-09-25, po review Task 6) Masowe usuwanie kopii bez powiązań CHRONI dostawców z profilem dokumentów (profil = blokada), choć pojedyncze DELETE kasuje profil kaskadowo — świadoma różnica, decyzja usera.
8. (2026-09-25, po final review) Masowe usuwanie kopii bez powiązań obejmuje WYŁĄCZNIE rekordy nadawców spółek-klientów (`client_company_id IS NOT NULL`) bez powiązań. Kartoteka Acme (z kodem SAP i bez) nigdy masowo; rekordy kartoteki bez kodu SAP tylko ręcznie. Audyt zbiorczy zawiera nazwę + kod SAP + spółkę każdego usuniętego.
9. (2026-09-25, po final review) „Scal wszystkie” pomija grupy, w których ≥2 rekordy mają profil dokumentów; w podglądzie oznaczone „2 profile — scal ręcznie”.
