# Faza B — dwukierunkowa synchronizacja kolejki Excel ↔ apka

Data: 2026-08-31
Status: zatwierdzony do planu (właściciel: „ROB")
Poprzednik: Faza A (`2026-08-31-excel-sharepoint-sync-design.md`) — Excel→apka, scalona lokalnie.

## Cel

Dołożyć kierunek **apka→Excel** i uzgadnianie, tak by kolejka była jednym zestawem danych
w dwóch edytowalnych widokach (Excel na SharePoincie + aplikacja). Zmiana po dowolnej
stronie propaguje do drugiej, bez pętli echa, z rozstrzyganiem konfliktów.

Kanał bez zmian względem Fazy A: **lokalny agent na maszynie 24h** (bez n8n/Graph/Entra).

## Rdzeń: three-way merge na `baseline`

Nowa kolumna `Container.sync_baseline` (JSON, nullable) = ostatni **uzgodniony** stan pól
synchronizowanych (serializacja jak `_audit_val`: enum→value, date→isoformat, else str/None).

Dla każdego pola z `SYNCED_FIELDS`, oznaczając `B`=baseline, `E`=Excel-teraz, `A`=apka-teraz:

| Sytuacja | Znaczenie | Akcja |
|---|---|---|
| `E≠B, A=B` | zmienił Excel | `A←E`; `B←E`; audyt „sync z Excela" |
| `A≠B, E=B` | zmieniła apka | pole trafia do **pending** (zapis w Excelu); `B←A` po potwierdzeniu |
| `E≠B, A≠B, E=A` | oba tak samo | zgoda → `B←E` (bez akcji) |
| `E≠B, A≠B, E≠A` | **konflikt** | LWW (niżej): zwycięzca na obie strony; `B←zwycięzca` |

Podniesienie `B` po uzgodnieniu kasuje pętlę echa: wartość zapisana do Excela jest już
baseline'em, więc następny snapshot `E'=A=B` nie generuje różnicy.

### Bootstrap (baseline == None)

Kontenery z Fazy A nie mają baseline. Pierwszy sync Fazy B dla takiego kontenera **nie może
zgadywać**, kto co zmienił. Reguła bezpieczna: `baseline is None` → potraktuj jak Fazę A
(Excel wygrywa: `A←E` dla różnic), po czym `B←E`. Od drugiego syncu działa pełny three-way.
Zero zapisów zwrotnych przy bootstrapie.

## Konflikt: last-write-wins (przybliżenie plikowe — zaakceptowane)

- **Czas strony apki (per pole):** najnowszy `AuditLog.created_at` dla
  `(entity_type="containers", entity_id, field)`; fallback `Container.updated_at`.
- **Czas strony Excela:** czas modyfikacji CAŁEGO pliku, przysłany przez agenta w POST
  (`file_mtime`, ISO). Excel nie ma czasu per komórka — to przybliżenie na poziomie pliku,
  świadomie zaakceptowane.
- **Rozstrzygnięcie:** `app_field_time > file_mtime` → apka wygrywa (pole do pending);
  inaczej Excel wygrywa (`A←E`, audyt). `B←zwycięzca`.

## Zapis zwrotny — bez osobnej kolejki, wyprowadzony z baseline

Nie ma tabeli „do zapisania". „Pending" = pola gdzie `A≠B` (zmiany apki jeszcze nie w Excelu),
liczone na żądanie. Cykl agenta:

1. `POST /api/import/sync` (jak w Fazie A) + pole `file_mtime`. Apka robi three-way + LWW.
2. `GET /api/import/sync/pending?company_code=…` → `{container_no: {field: excel_value}}`
   dla pól `A≠B` **i** zapisywalnych do Excela (patrz niżej).
3. Agent otwiera lokalny `.xlsx` (openpyxl, tryb zapisu), wiersz po numerze kontenera,
   kolumna po nagłówku (`HEADER_MAP` odwrotnie), wpisuje **tylko te komórki**, zapisuje →
   OneDrive wypycha. Blokada pliku (Excel otwarty) → backoff+retry; po progu log/skip, bez
   nadpisywania siłą (żadnych „kopii konfliktu").
4. `POST /api/import/sync/applied` z `{container_no: [fields]}` → apka `B[field]←A[field]`.

## Ograniczenie zapisu zwrotnego: `WRITABLE_FIELDS ⊆ SYNCED_FIELDS`

Nie każde pole apki da się czysto zapisać do jednej komórki Excela:
- **Wykluczone (Excel→apka only):** `status` (wyliczane, brak kolumny), `notes` (składane z
  kilku źródeł), pola bez odwracalnego mapowania 1:1.
- **Zapisywalne (dwukierunkowe):** pola z bezpośrednią kolumną w `HEADER_MAP` i prostą
  serializacją do tekstu/daty: `eta`, `notify_date`, `vessel`, `order_numbers`,
  `delivery_note`, `purchase_note`, `document_flow`, `incoming_delivery_no`, `rf_number`,
  `sent_required`, `sent_number`, `sent_status`, `customs_status` (→ „STATUS ODPRAWY"),
  oraz relacje z czytelną nazwą do zapisania (`supplier`, `forwarder`, `warehouse`,
  `customs_agency`) — zapisywana jest **nazwa**, nie id.

`WRITABLE_FIELDS` to jawna lista w kodzie (nie domysł). Pola z `SYNCED_FIELDS` spoza niej
pozostają Excel→apka (jak w Fazie A) — jeśli `A≠B` dla nich, apka i tak podnosi `B←A` bez
zapisu do Excela (apka jest ich jedynym edytorem sensownie).

**Do potwierdzenia przy planie:** czy operatorzy w apce faktycznie edytują te pola, czy
zawężamy pierwszy cut. Domyślnie: pełna lista wyżej.

## Endpointy (rozszerzenie `routers/imports.py`)

| Endpoint | Rola |
|---|---|
| `POST /api/import/sync` (rozszerzony) | + pole `file_mtime`; reconcile robi three-way+LWW zamiast czystego nadpisania |
| `GET /api/import/sync/pending` | zwraca `{container_no: {field: excel_value}}` dla `A≠B` ∩ `WRITABLE_FIELDS` |
| `POST /api/import/sync/applied` | potwierdza zapis; `B←A` dla wskazanych pól |

Auth: ten sam `sync_api_token`.

## Zmiany w agencie (`agent/`)

- Po `push_snapshot`: `GET /pending` → zapis komórek do lokalnego `.xlsx` (openpyxl) →
  `POST /applied`.
- Odwrotne mapowanie `field → nagłówek Excela`, serializacja wartości → tekst/data komórki.
- Znajdowanie wiersza po numerze kontenera (kolumna „NR KONTENERA"), kolumny po nagłówku.
- Blokada pliku: backoff + retry, log; nie nadpisuj siłą.
- `file_mtime` dokładany do `push_snapshot`.

## Testy (TDD, jak Faza A)

Apka:
- każdy z 4 przypadków tabeli three-way (per pole),
- bootstrap `baseline is None` → Excel wygrywa, `B←E`, brak pending,
- konflikt LWW w obie strony (apka nowsza → pending; Excel nowszy → `A←E`),
- echo-loop: apka zmienia pole → pending → applied → kolejny snapshot z tą wartością = 0 różnic,
- `pending` zawiera tylko `WRITABLE_FIELDS`; `status`/`notes` nigdy w pending.

Agent (unit, mock HTTP + tmp xlsx):
- zapis wskazanej komórki do właściwego wiersza/kolumny,
- pominięcie/retry przy zablokowanym pliku,
- pełny cykl push→pending→write→applied (mock endpointów).

## Migracja

Alembic: dodanie kolumny `sync_baseline` (JSON, nullable) do `containers`. `down_revision` =
aktualny head (`alembic heads`). Istniejące kontenery: `sync_baseline = NULL` → bootstrap
załatwia je przy pierwszym syncu.

## Poza zakresem (świadomie)

- Graph/Entra/n8n — dalej wykluczone.
- Usuwanie kontenerów zniknięć z arkusza.
- Zapis zwrotny pól niezapisywalnych (`status`, `notes`) — pozostają Excel→apka.
- Rozstrzyganie konfliktu przez człowieka (wybrano LWW).
