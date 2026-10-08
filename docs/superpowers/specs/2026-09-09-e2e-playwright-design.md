# E2E Playwright (TS) — plaster 1

Data: 2026-09-09
Gałąź: `claude/e2e-playwright` (od `main`)

## Cel

Dowieźć pierwszy sensowny zestaw testów E2E w przeglądarce dla panelu kolejki
kontenerów TIMPORYE, ze szczególnym naciskiem na **potwierdzenie izolacji danych
per-firma** (świeży hardening scopingu w `deps.py`).

## Decyzje (zatwierdzone)

1. **Stack: TypeScript `@playwright/test`** — rozwijamy istniejący setup z #276
   (`frontend/playwright.config.ts`, `frontend/e2e/login.spec.ts`, skrypt `e2e`,
   `.github/workflows/e2e.yml`). NIE dokładamy Python `pytest-playwright` — dwa
   runnery E2E to dług, nie wartość.
2. **Seed danych: global-setup przez API admina.** `bootstrap()` sieje tylko
   admina, więc scoped userów i kontenery A/B tworzymy jako admin przez REST.
   `POST /api/users` zwraca `temp_password` w odpowiedzi → logujemy się
   utworzonym userem bez env.
3. **Selektory: `data-testid` w kluczowych komponentach** (odporne na i18n PL/EN/PT),
   uzupełniane rolowymi tam, gdzie testid to przesada.

## Fakty z repo (grunt projektu)

- Backend: **FastAPI** (nie Flask), SQLAlchemy. Auth: **sesja cookie** (login przez
  pola `#kl-login`/`#kl-pass`).
- Scoping: `deps.py` — `scope_containers`, `check_container_access`,
  `company_filter_ids`; klucz = `user.company_id` (+ `view_all_companies`).
  `company_id=None`/`view_all` = widzi wszystko.
- Role (`models.py` `Role`): admin, logistics, warehouse, forwarder, customs,
  purchasing. `_validate_role_bindings` (admin router): forwarder→forwarder_id,
  customs→agency, warehouse→warehouse_id, nie-admin bez view_all→wymaga company_id.
- Walidacja **ISO 6346 po stronie backendu** (`iso6346.py`, użyta w POST kontenera)
  → zły numer = 4xx z polskim komunikatem, formularz pokazuje `<p class="error">`.
- `playwright.config.ts` odpala **uvicorn (SQLite `e2e.db`) + `vite dev`**,
  `baseURL:5173`, `fullyParallel:false` (wspólna baza → serial).

## Zakres plastra 1 (świadomie wąsko — YAGNI)

1. **Auth per rola** — fixture `loginAs(role)`; istniejący `login.spec.ts` wchłonięty
   do `auth.spec.ts` (login ok / złe hasło / logout).
2. **🔑 Security multi-company** (`scoping.spec.ts`):
   - user firmy A **nie widzi** kontenera firmy B na liście kolejki;
   - wejście na `/kontenery/{id_B}` jako A → **403** (nie render karty).
3. **Kontener add (API) + widoczność na liście** (`container-crud.spec.ts`):
   - kontener utworzony przez `POST /api/containers` (w seedzie) → widoczny na
     liście kolejki po zalogowaniu właściciela.
   - Powód API zamiast UI: **w UI nie ma triggera dodawania** (patrz niżej).
4. **Edycja + ISO 6346 negatywnie przez UI** (`container-crud.spec.ts`):
   - na `ContainerPage` (rola logistics, `canEdit`) edycja numeru na błędny ISO 6346
     → komunikat błędu z backendu w formularzu (`form-error`), rekord niezmieniony;
   - poprawna edycja innego pola → zmiana widoczna po zapisie.

Poza plastrem 1 (dokładane iteracyjnie): tracking/SafeCube, odprawy celne,
awizacje, analityka, pozostałe akcje kolejki.

## Struktura plików

```
frontend/e2e/
  global-setup.ts        # kasuje e2e.db, seed przez API admina, zapis credów+id do e2e/.seed.json
  fixtures.ts            # test.extend: loginAs(role), seeded (odczyt .seed.json)
  pages/
    LoginPage.ts
    QueuePage.ts         # form kontenera, wiersze, akcje
    TopNav.ts            # sekcje wg roli
    ContainerPage.ts     # karta kontenera (dla asercji 403)
  auth.spec.ts
  scoping.spec.ts
  container-crud.spec.ts
```

## Seed (global-setup, kolejność)

1. Skasuj `backend/e2e.db` (świeży stan; bootstrap odtworzy admina).
2. Poczekaj na `/api/health` (webServer w configu już to robi — global-setup łączy
   się przez `request` context do `http://localhost:8000`).
3. Zaloguj admina (`admin`/`admin123`) — `POST /api/auth/login` (form: username,
   password), cookie sesji trzymane w `request` context.
4. Firmy A/B: reuse dwóch domyślnych z `DEFAULT_COMPANIES` (pobierz
   `GET /api/companies`, weź dwie różne).
5. `POST /api/users` — user **logistics** scoped do firmy A i user **logistics**
   scoped do firmy B. **Hasło podajemy jawnie** w body (`password`, ≥8 znaków,
   `send_invite:false`) — `temp_password` wraca tylko przy zaproszeniu, którego nie
   używamy (wymaga e-maila/SMTP).
6. `POST /api/containers` — po ≥1 kontenerze dla A i dla B (numery ISO 6346 poprawne,
   `company_id` odpowiedniej firmy).
7. Zapisz `frontend/e2e/.seed.json` (gitignore) z loginami+hasłem E2E i id/numerami
   kontenerów A/B.

## data-testid — celowane dodania (minimalnie)

- **Tylko `ContainerFormModal`** (`components.tsx`): `container-form`,
  `container-no-input`, `container-submit`, `form-error`.
- Wiersze kolejki i sekcje TopNav **bez testid** — asercje po unikalnym numerze
  kontenera (`getByText(container_no)`) i po URL/403. Mniej zmian w produkcji.

## Znany bug UI (poza zakresem naprawy w plastrze 1)

`QueuePage` montuje modal dodawania (`showAdd`) i importu (`showImport`), ale
`setShowAdd(true)`/`setShowImport(true)` **nigdzie nie są wołane** — przyciski
zniknęły (prawdopodobnie przy reskinie topnavu). Dodanie kontenera przez UI jest
niewykonalne. W plastrze 1 obchodzimy to (add przez API). Przywrócenie przycisku =
osobne zadanie, decyzja użytkownika.

## Artefakty i uruchamianie

- `playwright.config.ts`: `trace:'on-first-retry'`, `screenshot:'only-on-failure'`,
  `video:'retain-on-failure'`, `outputDir:'test-results/'`,
  `globalSetup:'./e2e/global-setup.ts'`.
- CI: headless, `e2e.yml` zostaje `workflow_dispatch` (non-blocking) — nie blokujemy
  merge’y długim E2E.
- Lokalnie: `npm run e2e` (headless), `npm run e2e -- --headed` / `--debug`.

## Sprostowania do pierwotnego promptu

- **SafeCube nie wymaga mocka** w plastrze 1 — `tracking_provider="off"` i pusty
  `safecube_api_key` = provider nieaktywny (`get_provider()==None`), zero wywołań
  zewnętrznych. Mock dokładamy dopiero przy testach trackingu.
- **Rebuild `dist/` nieistotny dla E2E** — Playwright serwuje z `vite dev`, nie z
  commitowanego `dist/`. Notka do README: rebuild dotyczy tylko ręcznego podglądu
  prod-builda, nie E2E.

## Poza zakresem (nie robimy teraz)

- Python/pytest E2E.
- Równoległość testów (wspólna baza → serial; równoległość dopiero przy izolacji baz).
- Mock SafeCube/AIS/PowerBI.
- Blokujące E2E w CI na każdym PR.
