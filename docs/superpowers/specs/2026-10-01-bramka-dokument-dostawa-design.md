# Bramka zgodności dokumentu z dostawą (design)

Data: 2026-10-01 · Status: zatwierdzony w pytaniach (10+1), do przeglądu · Poprzedza: XML z faktur (WinSAD)

## Problem
Fakturę / packing list można dziś wrzucić do dowolnego kontenera — nic nie sprawdza, czy dokument
dotyczy tej dostawy:
- `Attachment` i `InvoiceBatch` wiszą tylko na `container_id`; upload sprawdza rolę, rozszerzenie,
  rozmiar (`routers/forwarding_files.py:111`, `routers/invoices.py:130`), nie treść.
- Numer kontenera z faktury (`invoices/pipeline.py:116`) nie jest porównywany z kontenerem paczki.
- `orders_link.link_to_container` (`invoices/orders_link.py:30`) **po cichu** przypina do kontenera
  każde PO z faktury, które nie ma kontenera — zła faktura psuje dane zamówień.
- Kontrola dostawcy (LIFNR) i ilości tylko obniżają flagę `ok`; mail do agencji bierze każdą
  potwierdzoną fakturę z paczki (`routers/invoice_agency.py:50`).

Dopóki tak jest, generowanie XML z faktur jest niebezpieczne.

## Zasada
Dowodem jest **treść dokumentu** (tekst PDF, OCR dla skanów — `invoices/extractor.py:242`).
Nazwa pliku nie jest dowodem (nazwy faktur zwykle nie mają nic wspólnego z PO ani kontenerem).

## Zakres
Faktury (CI/CIPL, proforma) i packing list. BL, certyfikaty, zdjęcia — bez zmian.

## Sygnały (z treści)
| Sygnał | Źródło | Twardy? |
|---|---|---|
| Nr kontenera (ISO 6346, cyfra kontrolna) | `extractor.py:425` | tak — inny niż kontener(y) docelowe → odrzuć |
| PO SAP | słowa kluczowe („Order no”, „PO number”, „nr zam.”; wzór `compare/app.py:18244`) + goły `4[5-8]\d{8}` | tak — patrz reguła PO |
| Dostawca (LIFNR z PO vs `Supplier.sap_code`) | `orders_link.supplier_check` | tak |
| Materiał (REF pozycji vs pozycje kontenera) | `master_ref`/`raw_ref` vs `OrderItem.material` | tak — pozycja spoza kontenera → odrzuć |
| Ilość ponad zamówienie | `checks.order_qty` | nie — status „niepewna”; mniej (dostawa częściowa) = OK |

**Reguła PO** (wg `compare`): na dokumencie są PO i żadne nie należy do kontenera(ów) docelowych →
odrzuć. Wyjątek: PO istnieje w SAP, ale nie ma jeszcze kontenera → nie odrzucamy, tylko
**podpowiedź** „przypnij PO X do tego kontenera”; po zatwierdzeniu sygnał liczy się od nowa.
PO przypięte do **innego** kontenera → odrzuć.

## Statusy
- **zgodna** — wszystkie sprawdzalne sygnały pasują.
- **niepewna** — czegoś nie da się sprawdzić (brak nr kontenera/PO na dokumencie, dostawca bez
  `sap_code`, kontener bez pozycji SAP) albo nadwyżka ilości. Brak danych ≠ sprzeczność.
  Wymaga ręcznego potwierdzenia **przez wrzucającego**, z powodem (audyt: kto, kiedy, dlaczego),
  zanim pójdzie do agencji / XML. Sprawdzenie odpala się ponownie, gdy spłyną dane SAP.
- **sprzeczna** — którykolwiek sygnał twardy. Dokument **nie zostaje przypięty** do kontenera.

Moment blokady: sygnały znamy dopiero po odczycie PDF, więc „przy wrzucaniu” = plik się wgrywa,
pipeline go czyta, wynik sprzeczny → brak przypięcia + komunikat.

## Po odrzuceniu
Komunikat z powodem (który sygnał, jakie wartości) i — gdy wykryliśmy właściwy kontener (nr
kontenera z treści albo kontener PO) — przycisk **„wrzuć do X”**: ten sam plik trafia do
właściwego kontenera bez ponownego wybierania.

## Wiele kontenerów
Faktura może obejmować kilka kontenerów: przypięcie do wielu (wzór `FreightInvoice` +
tabela łącząca). Zgodna, jeśli kontener docelowy jest na liście z dokumentu; PO w kilku
kontenerach nie jest sprzecznością; pozycje sprawdzamy wobec sumy tych kontenerów.

## Stare dokumenty
Jednorazowy raport „podejrzane przypięcia” (sygnały liczone wstecz, sprzeczne/niepewne) do
ręcznego przejrzenia. Bez automatycznego przenoszenia.

## Plan PR-ów
1. `link_to_container` → podpowiedź do zatwierdzenia (przestaje psuć dane).
2. Detekcja PO po słowach kluczowych + statusy zgodna/niepewna/sprzeczna + blokada przypięcia
   + potwierdzenie niepewnej z powodem + przycisk „wrzuć do X”. Mail do agencji / XML tylko
   zgodne lub potwierdzone.
3. Faktura przypięta do wielu kontenerów.
4. Raport podejrzanych przypięć.

XML z faktur — po PR 2.

## Otwarte
- Odsetek faktur z nr kontenera / PO / PI per dostawca — zmierzyć na fakturach od wielu
  dostawców (testy z użytkownikiem). Jeśli PI jest częsty, dołożyć sygnał `PurchaseOrder.pi_no`.
