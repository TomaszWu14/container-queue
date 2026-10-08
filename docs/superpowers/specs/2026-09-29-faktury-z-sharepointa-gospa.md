# Faktury z SharePointa → Excel → agencja (GOSPA)

Data: 2026-09-29 · Status: w realizacji · Metoda: GOSPA (skill `gospa`, tryb „projekt funkcji”)

## G — cel
Faktury wrzucane do folderu zamówienia na SharePoincie same trafiają do kontenera; operator
tylko przegląda pozycje i wysyła mail do agencji.

## O — cele cząstkowe (sprawdzalne)
1. Folder `4700600638` pojawia się jako paczka faktur w kontenerze, do którego należy zamówienie.
2. Dokumenty rozpoznane: faktura / packing list → ekstrakcja, pozostałe (B/L, zdjęcia, xlsx) →
   załączniki kontenera, bez ręcznego przenoszenia.
3. Ponowne pobranie tego samego pliku nie tworzy duplikatu.
4. Od wrzucenia PDF na SharePoint do szkicu maila dla agencji ≤ 5 min pracy operatora.
5. Folder bez dopasowanego kontenera trafia na listę „do przypisania”, nie znika.

## S — strategie
- Pobrane pliki wchodzą tą samą ścieżką co ręczny upload (paczka faktur / załączniki) — bez
  drugiego silnika.
- Folder = numer zamówienia → kontener przez EKKO (`container_id`) i numery PO kontenera.
- Faktura → zamówienie dwiema drogami: „Order no.” z nagłówka faktury oraz numer faktury
  = EKKO „Zamówienie dostawcy” (FICTIVA: `260101E0001` przy 4700600638; „Wystawca faktury”
  = dostawca 10004408) — druga droga działa, gdy PDF nie podaje numeru zamówienia.
- MVP bez Graph (plan B): „Wgraj folder zamówienia” przy kontenerze. Graph (`sharepoint.py`,
  `Sites.Selected` read) podłączy się pod ten sam mechanizm, gdy IT da dostęp do biblioteki.
  Odrzucone na start: automat co N minut — brak potwierdzonego dostępu i okres dwutorowy.

## P — priorytety
1. Dostęp IT do biblioteki z folderami zamówień — **nieznany** (sprawdzenie: Administracja →
   Import → „Synchronizuj teraz z SharePoint”; „nie jest skonfigurowany” = brak danych dostępowych).
2. Plan B: folder zamówienia wgrywany ręcznie (PR `claude/faktury-folder-zamowienia`).
3. Faktura → zamówienie po numerze faktury (EKKO „Zamówienie dostawcy”).
4. Ścieżka biblioteki + przykładowy folder → odczyt przez Graph i przycisk „Pobierz z SharePointa”.
5. Inne PDF-y (B/L) rozpoznane przez splitter → załączniki; lista „do przypisania”; automat.

Nie ruszamy: ekstrakcja faktur, Excel pozycji, kartoteka symboli, szkic `.eml`.

## A — działania
| Kto | Co | Cel (O) |
|---|---|---|
| Użytkownik | sprawdzić dostęp SharePoint (przycisk synchronizacji) | P1 |
| Agent | PR: „Wgraj folder zamówienia” (PDF → faktury, reszta → załączniki, ostrzeżenie o innym numerze) | O2, O4 |
| Agent | PR: faktura → zamówienie po numerze faktury (EKKO) | O1 |
| Użytkownik | ścieżka biblioteki + zrzut przykładowego folderu | O1 |
| Agent | PR: odczyt folderu przez Graph + przycisk przy kontenerze (eTag = bez duplikatów) | O1, O3 |
| Agent | PR: inne PDF-y → załączniki, lista „do przypisania”, opcjonalny automat | O2, O5 |
