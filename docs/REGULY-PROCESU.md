# Reguły procesu TIMPORYE

Jedno miejsce na reguły biznesowe, które aplikacja egzekwuje. **Zatwierdza: właściciel aplikacji.** Zmiana reguły = zmiana tego pliku w tym samym PR co kod (1 PR = 1 reguła) + test.

| Obszar | Reguła | Od | Ref |
|---|---|---|---|
| Odprawa celna | Odprawia **wyłącznie agencja celna**. Spedycja (wycena i transport, np. port → magazyn) nie ma dostępu do statusów ani dokumentów odprawowych. Firma może być agencją i spedycją jednocześnie (Delta Brokers) — osobne konta i role | 2026-09-28 | — |
| Odprawa celna | Status odprawy zmienia agencja; logistyka/admin awaryjnie | 2026-09-28 | — |
| Odprawa celna | „Odprawiony”/„Rozliczony” cofa tylko logistyka/admin, zawsze z notatką | 2026-09-28 | — |
| Odprawa celna | Agencję przypisuje logistyka ze słownika (bez wolnego tekstu) | 2026-09-28 | — |
| Odprawa celna | „Rewizja” zawsze z notatką (powód / ustalenia kontroli) i datą — bez notatki zapis odrzucony; brak daty = dzień wpisu (spec §2) | 2026-10-02 | — |
| Status kontenera | Wynika ze statusu odprawy, tylko do przodu: odprawa w toku → „Odprawa”; odprawiony + data awizacji → „Awizowany” | 2026-09-28 | — |
| Status kontenera | Magazyn potwierdza tylko rozładunek („Dostarczony”); kontener nieawizowany — z notatką | 2026-09-28 | — |
| Status kontenera | „Zrealizowany” ustawia logistyka po zamknięciu formalności (faktury, dokumenty) | 2026-09-28 | — |
| Status kontenera | Do przodu dowolnie; wstecz o 1 krok z notatką; więcej — tylko admin | wcześniej | — |
| Załączniki | Spedytor widzi tylko CMR i pliki, które sam wgrał; faktury za transport w module spedycji | 2026-09-28 | — |
| Załączniki — magazyn | Magazyn widzi CMR, packing list i pozostałe typy poza handlowymi/odprawowymi (PI, CI, B/L, SAD); plik bez typu dokumentu tylko własny | 2026-10-05 | — |
| Wiadomości przy kontenerze | Jeden wątek, ale wiadomości agencji celnej są ukryte przed spedytorem, a spedytora — przed agencją (także w powiadomieniach i wzmiankach); wiadomości personelu wewnętrznego widzą wszyscy z dostępem do kontenera | 2026-10-05 | ten PR |
| Zlecenia transportowe | Akceptuje spedytor; logistyka może zaakceptować w jego imieniu z notatką; bez anulowania | 2026-09-28 | — |
| Linki publiczne | Każdy publiczny link (udostępnienie kontenera, portal klienta, DLT, strona kierowcy) wygasa najpóźniej `PUBLIC_LINK_MAX_DAYS` (domyślnie 90) dni od wystawienia, niezależnie od własnego terminu; potem nowy link z panelu | 2026-09-28 | SEC-014 |
| Limity rozładunku | Przekroczenie dziennego limitu magazynu = ostrzeżenie (zapis w historii), nie blokada | 2026-09-28 | — |
| Demurrage | Dni wolne: ręcznie przy kontenerze → armator (Master data) → wartość domyślna | 2026-09-28 | — |
| Dane SAP (MARM) | Materiał, który zniknął z pełnego eksportu MARM („brak w SAP”), nadal liczy się w przeliczeniach palet; w Master data ma plakietkę „brak w SAP” | 2026-09-28 | — |
| Dane wspólne grupy | PAZ, cele zapasu, stany DLT, przeliczniki MARM i porty kontenerowe zmienia (także importem) admin, logistyka grupowa („wszystkie spółki”) albo logistyka spółki-właściciela materiałów (`SUPPLIER_COMPANY_CODES`, np. Acme); logistyk innej spółki tylko je czyta | 2026-09-28 | ACL-003 |
| Dane kierowcy (RODO) | Imię, telefon, nr dokumentu, nr auta/naczepy nie trafiają jawnie do historii zmian ani treści powiadomień (e-mail/Teams/n8n); po retencji awizacji czyszczone są też powiadomienia „dane kierowcy” i historia SMS kontenera | 2026-09-28 | — |
| Baza wiedzy | Pinezki i tematy wiedzy są wspólne dla spółek grupy; spedytor i agencja celna nie mają do nich dostępu (komunikaty adresowane do ich roli — tak). Pinezkę edytuje/usuwa autor albo admin | 2026-09-28 | — |
| Separacja spółek | Konto jednej spółki (bez „wszystkie spółki”) w dzienniku zmian widzi w filtrach tylko autorów i typy zmian ze swoich kontenerów, a w „kto przeczytał” notę — tylko adresatów ze swojej spółki; konta grupowe widzą wszystkich | 2026-09-28 | ACL-002 |
| SMS do kierowców | Godzina (czas PL), dni przed dostawą i limit ręcznych SMS spedytora — w panelu admina | 2026-09-28 | — |
| Excel / SharePoint | Okres dwutorowy: synchronizacja tylko ręczna (przycisk); Excel nigdy nie cofa statusu z aplikacji | 2026-09-28 | — |
| Excel / SharePoint | Import i synchronizacja dopasowują kontener po numerze tylko wśród niezrealizowanych rekordów spółki; numer znany wyłącznie z „Zrealizowanego” = nowy kontener z uwagą „powtórny numer — poprzednia dostawa: dd.mm.rrrr”, stary rekord nietknięty (N-20) | 2026-09-28 | — |
| Excel / SharePoint | Doprecyzowanie N-20: wiersz z numerem zrealizowanego kontenera i tą samą datą awizacji lub ETA to ta sama, już zamknięta dostawa — synchronizacja go pomija (bez nowego rekordu i powiadomienia); nowy kontener powstaje tylko dla nowej dostawy | 2026-10-05 | — |
| Sprzedaż | Rola tylko do odczytu, bez kosztów; może obserwować kontener/statek | 2026-09-27/28 | — |
| Kopie zapasowe | Faza testowa: baza co 8 h (6/14/22), załączniki raz na dobę; później kopia na drugą maszynę | 2026-09-28 | — |
| Konta użytkowników | Usunięcie konta = dezaktywacja + anonimizacja (login `usuniety-<id>`, bez e-maila/imienia, sesje unieważnione); historia audytu zostaje, stary login we wpisie `__deleted__` | 2026-09-28 | N-13 |
| Konta użytkowników | Przy `REQUIRE_2FA_ADMIN=true` (domyślnie wyłączone od 2026-09-29) administrator musi mieć włączone 2FA: bez 2FA po zalogowaniu ekran włączania, do tego czasu tylko odczyt. 2FA może włączyć każda rola; wyłącza je inny administrator (z audytem) | 2026-09-28 | SEC-006 |
| Numer kontenera | ISO 6346: reszta 10 z cyfrą kontrolną 0 jest przyjmowana z ostrzeżeniem „sprawdź numer” (nie odrzucana) | 2026-09-28 | DATA-004 |
| Dane kierowcy (RODO) | Anonimizacja danych kierowcy (imię, telefon, nr dokumentu, auta, naczepy + kopie w powiadomieniach i SMS) także dla kontenerów bez awizacji: ZREALIZOWANY i `completed_at` starsze niż `DRIVER_DATA_RETENTION_DAYS` (ta sama retencja co po zamknięciu awizacji); pomija kontenery w aktywnej awizacji | 2026-09-28 | GDPR-002 |
| Kontener aktywny / zakończony | Dwa pojęcia: **otwarty w kolejce** = wszystko poza ZREALIZOWANY (`Container.open_in_queue()`; DOSTARCZONY czeka na rozliczenie — kolejka, wyszukiwarka, skrzynka, liczniki, jakość danych); **fizycznie zakończony** = DOSTARCZONY lub ZREALIZOWANY (`Container.FINISHED` — śledzenie/mapa, „w drodze”, demurrage, limity, SMS, sygnały, opóźnienia) | 2026-09-28 | BIZ-004 |
| Log logowań (RODO) | Wpisy `audit_log` z `entity_type=auth` (logowania, nieudane próby: IP, wpisane loginy) usuwane po `AUDIT_AUTH_RETENTION_DAYS` (domyślnie 90 dni); historia biznesowa zostaje. Nieudane logowanie na nieistniejący login zapisuje tylko skrót (2 znaki + długość) | 2026-09-28 | GDPR-004 |
| Retencja tokenów, SMS i błędów JS (RODO) | Codziennie usuwane: refresh tokeny i tokeny resetu hasła wygasłe dawniej niż `TOKEN_RETENTION_DAYS` (30 dni; ważne sesje zostają), historia SMS starsza niż `SMS_RETENTION_DAYS` (90 dni), błędy JS z beaconu starsze niż `CLIENT_ERROR_RETENTION_DAYS` (30 dni) | 2026-09-28 | OBS-011, GDPR-007 |
| Retencja danych (RODO) | Przeczytane powiadomienia kasowane po 90 dniach (`NOTIFICATION_RETENTION_DAYS`, domyślnie i w compose, od 2026-10-01), nieprzeczytane zostają; błędy JS z przeglądarki zapisywane bez tokenów linków publicznych (awizacja, kierowca, portal, udostępnienie) | 2026-09-28 | OBS-011 |
| Importy SAP (EKKO, MARM, REF) | Rekordy spoza pliku nie są kasowane (tylko liczone w podglądzie); import EKKO nie zrywa dowiązania zamówienia do kontenera, a jego zmianę zapisuje w historii; pozycja REF bez numeru pozycji albo z nieliczbową ilością (i przelicznik MARM nie będący liczbą) trafia do raportu błędów — zamówienie z błędnym wierszem zostaje nietknięte | 2026-09-28 | DATA-003 |
| Importy SAP — pełny eksport (EKKO, MARM) | Przy zaznaczonym „pełny eksport” zamówienie EKKO (per spółka) lub jednostka MARM nieobecne w pliku dostają `sap_status = brak_w_sap` (nie są kasowane); bez zaznaczenia (plik częściowy) nic się nie zmienia; rekord ponownie obecny w pliku wraca na `aktywny` | 2026-09-28 | DATA-003 |
| Kopie zapasowe (zmiana) | Backup raz w tygodniu: sobota 22:00, baza + załączniki; retencja 8 kopii tygodniowych + miesięczne; świadome ryzyko utraty do 7 dni danych | 2026-09-28 | decyzja właściciela |
