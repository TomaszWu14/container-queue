# TIMPORYE — pełny workflow aplikacji (stan kodu 2026-09-16)

Następca `mapa-procesu-timporye.md` (2026-09-02). Zweryfikowane w kodzie (`backend/app`, `frontend/src`).
Cel: podstawa do budowy BPMN — aktorzy, kroki, bramki, powiadomienia, masterdata.

---

## 0. Aktorzy i dostęp

| Rola | Kto | Widzi / może |
|---|---|---|
| `admin` | administrator | wszystko + panel admina |
| `logistics` | logistyka spółki | kontenery swojej spółki (`view_all_companies` = wszystkie); pełna edycja |
| `purchasing` | zakupy | odczyt spółki; edycja TYLKO statusu zakupowego + wysyłka dokumentów celnych; wykluczona z wycen; strony: kolejka/kontener/zamówienia/spedycja |
| `warehouse` | magazyn (DLT) | tylko kontenery swojego magazynu; dane handlowe/PII ukryte (`_WAREHOUSE_HIDDEN`); status może ustawić TYLKO `DOSTARCZONY`/`ZREALIZOWANY`; nie uploaduje plików; brak dashboardu/zamówień |
| `forwarder` | spedycja | tylko kontenery jej zlecone; dane kierowcy, pliki, wiadomości, obieg zlecenia, potwierdzanie planu; w wycenach widzi tylko własną ofertę |
| `customs` | agencja celna | tylko zlecone odprawy; dane handlowe/PII ukryte (`_CUSTOMS_HIDDEN`); zmienia status odprawy, wyznacza agenta |

Egzekwowanie centralne fail-closed: `deps.py` (`scope_containers`, `check_container_access`). Brak przypisania = 403.
Maskowanie działa też w historii audytu i endpointach pozycji/SENT.

**Publiczne bez logowania:** formularz awizacji `/avizo/:token` (14 dni), łącznik kierowcy `/dostawa/:token` (dzień dostawy+2), share kliencki `/k/:token` (30 dni po ZREALIZOWANY), login/reset hasła, `/o-systemie`. Tokeny SHA-256 w bazie.

---

## 1. Masterdata (co jest słownikiem, kto utrzymuje)

- **Company** — spółki (Borealis, Cobalt Sport, Iberia, Acme); admin.
- **User** — konta z rolą + wiązaniem (forwarder_id / customs_agency_id / warehouse_id / company_id — walidowane przy tworzeniu); zaproszenie e-mail z hasłem tymczasowym (`must_change_password`); `watch_only_notifications`; profil widoku `ui_prefs`.
- **Supplier** (+ SupplierContact) — dostawcy per spółka; merge + statystyki on-time/transit.
- **Forwarder** — spedycje (SPEDALFA, Spedgamma, Spedomega, Toll) + dane kontaktowe.
- **CustomsAgency** — agencje celne (partner z kontami roli customs).
- **Warehouse** — magazyny: kraj (PL/PT), `default_daily_limit` (dom. 7), adres, telefon, instrukcje wjazdu (dla kierowcy).
- **Port** — 12 portów CN/HK/TW z czasem tranzytu (standard/long).
- **ContainerType** — 6 typów (20'DV…40'RF) z wymiarami/TEU.
- **Carrier** — armatorzy.
- **DocumentType** — typy dokumentów; `is_required` = wchodzi do checklisty kompletności odprawy.
- **CustomsCaseStatus** — konfigurowalny słownik statusu sprawy celnej (niezależny od enuma!).
- **ProblemType** — słownik problemów reklamacyjnych (9 domyślnych).
- **ProductPaz** — słownik PAZ (szt/paletę).
- **DailyLimit / CalendarDay** — nadpisania limitu dziennego i wyjątki kalendarza (PL/PT + własne).
- **AppSetting** (panel admina, nie ENV): progi przypomnień reklamacji (15/30), docs_reminder_days (7), forecast_alert_days (7), warehouse_eta_buffer_days, e-mail ubezpieczyciela, prefiks reklamacji.

---

## 2. Wejście danych (start procesu)

Trzy drogi powstania kontenera:

1. **Zlecenie spedycyjne (Order)** — `POST /zlecenia`: logistyka/zakupy zakładają Order (dostawca, port, typ kontenera, tryb morze/kolej, towar, wartość, gotowość) → system tworzy N pustych kontenerów `ZAPOWIEDZIANY` dziedziczących dane. Powiadomienie: team Acme + admini.
2. **Ręczne dodanie kontenera** — `POST /containers` (Editors). ETA bez daty dostawy → auto-propozycja `notify_date = ETA+4`. Auto `transport_id` (np. `AT-2026-0001`). Powiadomienie do magazynu.
3. **Import Excela** — `POST /imports/containers` (dry-run, walidacja ISO 6346: invalid/exists/duplicate/new) oraz **queue-sync** (three-way merge na `sync_baseline`; w polach `WRITABLE_FIELDS` apka wygrywa, reszta Excel; zmiana notify_date z Excela resetuje plan).

Równolegle, wcześniejszy etap:
- **PurchaseOrder (arkusz ETD)** — `POST /imports/purchase-orders`: upsert po (spółka, order_no), auto-link do kontenera po numerze; lista `GET /purchase-orders` domyślnie pokazuje NIEPOWIĄZANE (zamówienia przed kontenerem). ETD z PO trafia na oś czasu kontenera.
- **OrderItem (SAP REF)** i **SentLink** (SENT↔zamówienie) — importy pozycji.

**Bramka wejściowa:** numer kontenera walidowany blokująco wg ISO 6346 (import + schematy; uwaga: NIE w bezpośrednim POST /containers).

---

## 3. Główny cykl kontenera (status główny)

`ZAPOWIEDZIANY → W_TRANSPORCIE → W_PORCIE → ODPRAWA → AWIZOWANY → W_DOSTAWIE → DOSTARCZONY → ZREALIZOWANY`

- **Automat (tracking)** podnosi status TYLKO w przód i TYLKO do W_PORCIE.
- `ODPRAWA`, `AWIZOWANY`, `W_DOSTAWIE` — wyłącznie ręcznie (logistyka/admin). Brak twardej maszyny stanów dla editorów (dowolny skok możliwy).
- **Magazyn** może ustawić wyłącznie `DOSTARCZONY`/`ZREALIZOWANY` (bramka w `change_status`). `ZREALIZOWANY` ustawia `completed_at` → archiwum.
- Flaga **opóźniony** (liczona w locie): ETA minęło przy ZAPOWIEDZIANY/W_TRANSPORCIE, albo notify_date minęło bez zakończenia.
- **Audyt** każdej zmiany pola (kto/kiedy/stara/nowa) — maskowany per rola.

### Tranzyt (`is_transit`)
Kontener bezpośrednio do klienta. Jedyny efekt logiczny: NIE liczy się do limitu dziennego. Dane klienta (`customer_name/address/contact`) ręcznie, maskowane dla warehouse/customs. `DOSTARCZONY` potwierdza logistyka ręcznie (magazynu brak w pętli). Odprawa/tracking/demurrage działają normalnie.

---

## 4. Tracking (Etap 2)

> **Stan faktyczny (aktualizacja 2026-09-28):** zewnętrzny provider trackingu kontenerów (SafeCube) został usunięty z kodu — nie ma automatycznej aktualizacji ETA/statusu ani endpointów `POST /containers/{id}/track` / `POST /tracking/sync`. ETA i status wpisuje się ręcznie albo importem; automat zostaje tylko po stronie **statków** (AIS niżej). Historyczny opis (2026-09-16): provider SafeCube co `TRACKING_INTERVAL_HOURS`, aktualizował ETA, status w przód, statek, port, oś zdarzeń i ETD z pierwszego DEPART.

- **AIS (aisstream.io)**: websocket, pozycje statków z kolejki, geofence portu (`near_port`), postoje.
- Śledzony na mapie = kontener z `rf_number` i nie-ZREALIZOWANY.
- **ATD** — NIE automatyczne; ręcznie/importem. Podstawa raportu transit-trend (ETD→ATD).
- **Timeline** (oś czasu, 5 źródeł): PO_ETD z arkusza, zdarzenia armatora, postoje AIS, zmiany statusu z audytu, daty planowane. Publiczny share odfiltrowuje wpisy `order`.

---

## 5. Planowanie dostawy (planning_status) + awizacja + limity

`notify_date` = jedyna data dostawy i klucz dnia kolejki. `planning_status` mówi, ile jest warta:

1. **PROPOZYCJA** (domyślna): data = ETA+4; tracking może ją przesuwać, dopóki nikt nie tknął ręcznie (`notify_date_manual` zamraża przed automatem).
2. **WYSLANE**: logistyka wysyła plan (`POST /containers/plan/send`) → data zamrożona, zapisane `planning_eta_at_send` (baza do alertu „ETA przesunięta o X dni"). Pomija kontenery bez spedytora i już potwierdzone.
3. **POTWIERDZONE**: dwie drogi, jedna funkcja `confirm_plan`:
   - portal: admin/logistyka/**spedytor** (`POST /containers/{id}/plan/confirm`);
   - publiczny formularz awizacji `POST /avizo/{token}` (spedycja bez konta; wpisuje też dane kierowcy).
   - Bramka: data nie może być z przeszłości (422). Inna data od spedycji → nadpisuje notify_date.
4. **Reset → PROPOZYCJA**: zmiana uzgodnionej daty (ręcznie lub z Excela) cofa plan i czyści potwierdzenia.

**Awizacja (avizo):** logistyka wysyła zbiorczo (`POST /avizo/send`), grupowanie spedytor×spółka, link 14 dni, opcjonalny mail do magazynu; powiadomienie tylko przy pierwszym potwierdzeniu.

**Limit dzienny:** `used` liczy WYŁĄCZNIE `POTWIERDZONE`, nie-zakończone, nie-tranzyt. Limit = DailyLimit (nadpisanie dnia) lub `default_daily_limit` magazynu (7). Przekroczenie = ostrzeżenie `over_limit`, nie blokada. `suggest-notify-date` proponuje pierwszy roboczy dzień po ETA+bufor z wolnym slotem (kalendarz PL/PT + wyjątki).

**Konflikt dostaw:** ostrzeżenie `notify_conflict`, gdy ten sam dostawca ma ≥2 kontenery na tę samą datę.

---

## 6. Tor odprawy celnej (równoległy, 3 niezależne wymiary)

1. **CustomsStatus (enum):** `BRAK → DOKUMENTY_KOMPLETNE → ZLECONA → DRAFT_WYSLANY → DRAFT_POTWIERDZONY → ODPRAWIONY`, boczna `REWIZJA` (data+notatka, kontener wstrzymany).
   - Zlecenie agencji (`assign`) ustawia ZLECONA (z BRAK/DOKUMENTY_KOMPLETNE), wycofanie cofa na BRAK i odpina agencję (traci dostęp).
   - `update_status`: obie strony (logistyka i agencja) mogą ustawić dowolny status — brak twardej maszyny; DRAFT_* ręcznie.
2. **DocumentStatus:** `BRAK → ZALACZONE` (pierwszy otypowany upload) `→ WYSLANE` (wysyłka dokumentów do agencji: wymaga agencji + ≥1 załącznika; braki checklisty `DocumentType.is_required` → 409, chyba że `force`). Wysyłać mogą admin/logistyka/**zakupy**.
3. **CustomsCaseStatus:** słownik admina — agencja prowadzi własny stan sprawy.

Agencja wyznacza/zmienia **agenta** (imię/tel/e-mail) → powiadomienie. Obie strony komunikują się wiadomościami przy kontenerze.
Alert „odprawa się przeciąga": ZLECONA/REWIZJA > `CUSTOMS_ALERT_DAYS` (3), raz/dobę.

---

## 7. Spedycja — dwa osobne byty

### 7a. TransportOrder (pojedyncze zlecenie transportowe) — maszyna stanów z rolami
`WYSTAWIONE → ZAAKCEPTOWANE/ODRZUCONE (spedytor; odrzucenie wymaga powodu) → W_REALIZACJI (spedytor) → WYKONANE (spedytor) → POTWIERDZONE (logistyka/admin)`.
Przy kontenerze: dane kierowcy (`PATCH /driver` → powiadomienie logistyka+spedycja+magazyn), pliki (CMR, kwity; walidacja rozszerzeń, `UPLOADS_DIR`, limit MB), wiadomości, wskazanie agenta celnego. Flaga `needs_forwarding` + kolejka `/containers/to-forward`. Mail „kolejka dnia" z prośbą o dane kierowców (`/forwarding/queue-email`).

### 7b. TransportJob (RFQ — paczka kontenerów do wyceny)
`SZKIC → WYSLANE (deadline = wysyłka + response_hours, dom. 24) → ZLECONE`, plus `ANULOWANE`/reopen.
Oferty (**Quote**): `ZAPYTANIE → WYCENIONA → WYBRANA / ODRZUCONA / WYGASLA`. Spedytor wycenia (kwota, waluta, ważność, armator, ETD/ETA, transit); może zgłosić **pilną zmianę ceny** (revised_amount) → logistyka akceptuje. Wybór: ranking ważony (cena 0.60 / czas 0.25 / elastyczność 0.15); wybór gorszej od rekomendacji wymaga uzasadnienia. Spedytor nigdy nie widzi ofert konkurencji/SCFI/KPI. Zwycięzca podaje agenta. Statystyki RFQ/koszty/KPI spedytorów. Zakupy wykluczone z całego modułu.

---

## 8. Łącznik kierowcy i share kliencki

- **Kierowca:** logistyka wysyła SMS z linkiem (`POST /containers/{id}/driver-sms`; świeży link wygasza stare). Kierowca bez logowania widzi dane dostawy + magazyn (adres, instrukcje wjazdu) i klika **„Jestem na miejscu"** (dedup 10 min) lub zgłasza **opóźnienie** (HH:MM) → dzwonek do magazynu+logistyki. BEZ auto-zmiany statusu. Auto-SMS na jutro: pętla `send_tomorrow_sms` (po 13:00 UTC, dedup po dacie dostawy).
- **Share kliencki:** publiczny link `POST /containers/{id}/share-link` — status, ETA, data dostawy, timeline (bez wpisów zamówieniowych); wygasa 30 dni po ZREALIZOWANY.

---

## 9. Zakupy i status zakupowy

- **PurchasingStatus:** `BRAK / DO_ZAMOWIENIA / ZAMOWIONE / POTWIERDZONE / ZREALIZOWANE / WSTRZYMANE` — edycja: admin/logistyka/zakupy (jedyny zapis roli purchasing), dowolne przejścia, audyt, powiadomienie company_watchers.
- Zakupy: podgląd kolejki/kontenerów/zamówień/spedycji, wysyłka dokumentów celnych, weekly digest (poniedziałek rano, obserwowane kontenery).
- Automat pilności ze słownika materiałów — wg mapy 2026-09-02 decyzja podjęta, w kodzie NIE ma jeszcze modułu zapotrzebowania/przeliczników (jest tylko słownik PAZ i MaterialIssue z uploadu).

---

## 10. Reklamacje

- Tworzy: każdy z dostępem do kontenera (w praktyce admin/logistyka/magazyn), typ PROBLEM/REKLAMACJA, zaznaczone problemy ze słownika, opis, zdjęcia (walidacja sygnatury obrazu).
- Numer: `REK-NRKONTENERA-RRRRMMDD` (+`-2/-3`), prefiks w ustawieniach.
- Obieg: `NOWA → ZGLOSZONA` (zgłoszenie do magazyniera → powiadomienie in-app+mail+Teams) `→ WYSLANA` (logistyka wysyła do spedycji/ubezpieczyciela mailem; reset licznika) `→ ODPOWIEDZ → ZAMKNIETA` (archiwum).
- Reklamacja kontenera spedycji → powiadomienie spedycji.
- Przypomnienia: pętla co 6h; WYSLANA bez odpowiedzi po 15 i 30 dniach (ustawialne) → przypomnienie logistyce, każdy próg raz.

---

## 11. Wywołania DLT / palety / analityka

- **PalletCall:** `draft → sent → confirmed → delivered / cancelled`; edycja tylko w draft; linie (produkt, ilość palet, data dostawy); eksport xlsx. Strona `/wywolania-dlt` (admin/logistyka).
- **PowerBI/PalletStockCache** + alert pilnych palet (pętla 12h, próg 2.0, target 14 dni — tylko gdy PowerBI skonfigurowane).
- **PAZ:** słownik szt/paletę + import. **MaterialIssue:** upload analityczny. Karta rozładunku per kontener; proxy do serwisu paletyzacji.

---

## 12. Powiadomienia (przekrojowo)

Kanały: in-app (zawsze) + e-mail (Bcc, w tle) + Teams/Slack webhook — nigdy nie blokują operacji. Osobny kanał SMTP dla zaproszeń.
Grupy odbiorców: company_watchers (logistyka spółki+admini), acme_team (Acme obsługuje transport wszystkich), new_order_watchers, forwarder_users, customs_agency_users, warehouse_users, container_watchers (gwiazdki). `watch_only_notifications` zawęża do obserwowanych.

Zdarzenia: zmiana ETA/opóźnienie, auto-status, nowe zlecenie i każdy krok obiegu, wiadomość, plik, demurrage, odprawa (zlecenie/agent/status/przeciąganie), dokumenty brakujące, prognoza przeciążenia dnia, kierowca (dane/na miejscu/opóźnienie), reklamacje+przypomnienia, awizacja potwierdzona, alerty trackingu (ETA minęło bez ATD, dryf ETA AIS, statek stoi >48h), pilne palety, weekly digest.

## 13. Pętle w tle (asyncio w procesie)

| Pętla | Interwał | Progi |
|---|---|---|
| tracking_loop | TRACKING_INTERVAL_HOURS (12h) | provider≠off; breaker 10 błędów |
| ais_loop | websocket, resub 900s | klucz aisstream; kotwica 48h |
| demurrage_loop | 6h | DEMURRAGE_ALERT_DAYS=3 (termin = przybycie/ETA + dni wolne) |
| customs_delay_loop | 6h | odprawa 3 dni; docs 7; prognoza 7; ETA-alert 2; SMS ≥13:00 UTC |
| complaint_reminder_loop | 6h | 15/30 dni |
| pallet_urgent_loop | 12h | próg 2.0 / 14 dni |
| weekly_digest_loop | 24h (okno pon. 6-7 UTC) | rola purchasing |

## 14. Wyjścia / raporty

Eksport kolejki xlsx (widok/całość), dashboard (nie dla warehouse), raport miesięczny, transit-trend ETD→ATD, prognoza obłożenia rozładunków, analiza rozładunków, digest zmian, statystyki RFQ/kosztów/spedytorów (CSV), statystyki dostawców (on-time/transit), mapa statków, pogoda na trasie.

---

## 15. Punkty do uzgodnienia przy budowie BPMN (rozjazdy i luki)

1. Statusy `ODPRAWA`/`AWIZOWANY`/`W_DOSTAWIE` nikt nie ustawia automatycznie — czy w workflow są obowiązkowe kroki, czy opcjonalne etykiety? (dziś: dowolny skok przez logistykę).
2. Brak maszyny stanów statusu głównego dla editorów i statusu celnego (`update_status` dowolny) — czy BPMN ma to zaostrzyć?
3. ISO 6346 nie jest walidowane w bezpośrednim `POST /containers` (tylko import/schematy) — luka bramki wejściowej.
4. Automat pilności z zakupów (słownik materiałów + zapotrzebowanie) — zdecydowany, ale niezaimplementowany.
5. RF: w kodzie `rf_number` to id śledzenia, NIE saldo puli — saldo z decyzji 2026-09-02 nie istnieje w kodzie.
6. Faktura M:N ↔ kontener — brak w kodzie (decyzja z 2026-09-02 niewdrożona).
7. Wyszukiwarka globalna i mapa Google — mapa jest (AIS, `/sledzenie`), wyszukiwarki globalnej brak.
8. `warehouse` z `view_all_companies=True` nadal dopuszczalne (błędna konfiguracja).
9. Tranzyt: kto widzi dane klienta docelowego — spedycja widzi (musi), warehouse/customs maskowane; zgodne z założeniem.
10. Kierowca „na miejscu" nie zmienia statusu kontenera — świadome? (magazyn i tak potwierdza DOSTARCZONY).
