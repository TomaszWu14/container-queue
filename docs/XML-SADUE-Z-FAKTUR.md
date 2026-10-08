# XML SADUE z faktur → WinSAD agencji

Decyzje 2026-10-07: format = **SADUE** (ten sam eksport WinSAD, który Delta odsyła z draftem SAD —
`backend/app/invoices/sad_xml.py`, próbka `backend/tests/fixtures/sad/SAD7100005.xml`); pozycje
grupowane po **CN + kraju pochodzenia**; XML idzie **w mailu do agencji + osobne pobranie**.

## Gdzie

- Karta kontenera → sekcja faktur → paczka → **„Pobierz XML (WinSAD)”** (`GET /api/invoice-batches/{id}/sadue.xml`).
- **„Przygotuj maila do agencji”** — `SAD_<kontener>.xml` jako trzeci załącznik (po Excelu i kartotece
  symboli). Gdy XML nie powstaje, mail idzie bez niego, a podgląd mówi dlaczego („Bez XML do WinSAD: …”).

## Co wypełniamy (`backend/app/invoices/sad_export.py`)

| Element | Źródło |
|---|---|
| `SADUE@P15aKodKrajuWys`, `P22WalutaSADu` | kraj dostawcy, waluta z profilu dokumentów dostawcy |
| `P2Nadawca/Firmy` | dostawca (nazwa, ulica, miasto, kod, kraj) |
| `P8Odbiorca/Firmy` | spółka kontenera |
| `P20WarDostawy` | warunki dostawy z faktury („FOB NINGBO”) |
| `ZestawySADu` | suma wartości, opakowań (kartony), masy brutto |
| `PozycjeSADu` (grupa CN8 + TARIC + kraj pochodzenia) | wartość, masa netto/brutto, kartony (`CT`), opis = nazwy PL, kontener, faktury `N935` / proformy `N325` |

Kraj pochodzenia: indeks dostawcy (SAP EINA, `SupplierMaterial.origin_country`), inaczej kraj dostawcy.
CN/TARIC: kartoteka materiałów z nadpisaniem spółki (jak kartoteka symboli).

**Nie wypełniamy** (uzupełnia agencja): identyfikatory i GUID-y WinSAD, dane zgłaszającego, opłaty,
korekty, preferencje, procedura.

## Blokady i ostrzeżenia

- **409 / brak XML:** brak zatwierdzonych faktur; profil dostawcy bez waluty; pozycja niepominięta bez
  dopasowanego REF albo bez 8-cyfrowego CN (lista REF w komunikacie).
- **Ostrzeżenie:** grupa CN bez masy netto / brutto / liczby kartonów.

## Do potwierdzenia z agencją

Czy WinSAD Delta importuje taki niepełny SADUE (bez GUID-ów i kontekstu `P1Kontekst`). Pierwszy plik
z FICTIVA wysłać do próbnego importu; jeśli odrzucą — dopasować pola wg ich odpowiedzi.
