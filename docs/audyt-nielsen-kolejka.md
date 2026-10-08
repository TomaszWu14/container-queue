# Audyt heurystyczny Nielsena — widok kolejki (TIMPORYE)

Stan: 2026-09-03, **po** UI polish. Werdykty: ✅ spełnione / 🟡 częściowo / ❌ brak.
Checklista wielokrotnego użytku — przy ponownym audycie odhaczaj `[ ]` i aktualizuj werdykty.

## H1. Widoczność statusu systemu — **🟡**
- [x] Statusy kontenera/odprawy/planowania widoczne jako badge w wierszu
- [x] Flagi OPÓŹNIONY (inline po polish) i PILNY (odrębna kolorystyka)
- [x] Przełącznik „Edycja: wyłączona/włączona" pokazuje tryb bez klikania (polish D10)
- [x] Licznik zaznaczonych na pasku akcji masowych (polish D19)
- [ ] ❌ Brak spinnera/skeletonu przy ładowaniu listy — przy wolnym API użytkownik widzi pustkę
- [ ] 🟡 Zapis inline (np. przeniesienie daty) — jest modal potwierdzenia, ale brak toastu „zapisano" po sukcesie
- [ ] ❌ Brak wskaźnika świeżości danych trackingu na widoku (kiedy ostatni sync — pole `tracked_at` istnieje w API)

## H2. Zgodność ze światem rzeczywistym — **✅**
- [x] Język operacyjny PL: „Awizacja", „Odprawa", „Spedycja", „Nr dostawy", statusy po polsku
- [x] Zakładki = spółki (Acme/DLT/Borealis…) — mentalny model użytkownika, nie struktura bazy
- [x] Dni jako naturalne nagłówki („4 sierpnia 2026 — wtorek"), weekendy/święta odróżnione
- [ ] 🟡 „SENT", „RF", „ETD/ETA/ATD" — skróty branżowe OK dla logistyki, ale brak tooltipów z rozwinięciem dla nowych osób

## H3. Kontrola i swoboda użytkownika — **🟡**
- [x] Modal potwierdzenia przed przeniesieniem daty (nie da się „przeciągnąć przypadkiem")
- [x] Ostrzeżenie przy zmianie POTWIERDZONEJ daty (reset cyklu planowania)
- [x] Filtry w URL — „wstecz" przeglądarki cofa stan, linki udostępnialne
- [x] „Odznacz wszystko" na pasku akcji; chipy filtrów z × (polish D15/D19)
- [ ] ❌ Brak „cofnij" po zmianie statusu/daty — jedyna droga to ręczne przestawienie z powrotem (audyt jest, undo nie ma)
- [ ] 🟡 Brak maszyny stanów statusu głównego = pełna swoboda, ale też brak zabezpieczenia przed omyłkowym cofnięciem statusu (⚠ ryzyko nr 1 z mapy procesów)

## H4. Spójność i standardy — **✅**
- [x] Jedno źródło kolumn (`wideColumns`) = nagłówek, siatka i chowanie kolumn zawsze zgodne
- [x] Wspólny `ColumnFilter` dla wszystkich filtrów kolumnowych
- [x] Badge statusów spójne między kolejką, szczegółami i modułem spedycji
- [x] i18n ×3 (pl/en/pt) — bez mieszania języków w widoku
- [ ] 🟡 Dwa mechanizmy czyszczenia filtrów („Wyczyść filtry" vs „Wyczyść wszystkie") — działają, ale to dwa wzorce na jedną intencję (minor z review)

## H5. Zapobieganie błędom — **🟡**
- [x] ISO 6346 walidowane blokująco przy tworzeniu/edycji
- [x] Potwierdzenie daty nie przyjmie przeszłości (422)
- [x] Przekroczenie limitu dnia = wyraźne ostrzeżenie przy zapisie
- [x] Modal potwierdzenia przy operacjach zmieniających daty
- [ ] ❌ Ręczna zmiana statusu pozwala na dowolny ruch (też wstecz) bez ostrzeżenia — najprostszy fix: ostrzeżenie przy ruchu wstecz, docelowo graf przejść jak ORDER_FLOW
- [ ] 🟡 Przekroczony limit zapisuje się bez śladu „kto zignorował ostrzeżenie" (⚠ nr 5 z mapy)

## H6. Rozpoznawanie zamiast przypominania — **✅** (po polish)
- [x] Mini-etykieta nad wypełnionym filtrem — widać CO filtrujesz (polish D14, koniec placeholder-as-label)
- [x] Pasek chipów aktywnych filtrów — cały stan filtrowania na oku (polish D15)
- [x] Słowniki w filtrach (dostawca/spedytor/magazyn jako listy, nie wpisywanie z pamięci)
- [x] Wyszukiwarka podpowiada zakres („kontener, PO, statek, uwagi…")
- [ ] 🟡 Brak historii ostatnich wyszukiwań/filtrów

## H7. Elastyczność i wydajność — **✅**
- [x] Wybór i kolejność widocznych kolumn per użytkownik (localStorage)
- [x] Gęstość wiersza (Kompakt/Standard/Wysoki) w menu „Widok"
- [x] Akcje masowe (zaznacz dzień/wiersze → przenieś datę) — akcelerator dla power-userów
- [x] Klikalne „N opóźnione" = skrót do filtra (polish D8)
- [x] Drag&drop kontenerów między dniami kalendarza
- [ ] 🟡 Brak skrótów klawiszowych (np. `/` fokus na szukaj) — nice-to-have

## H8. Estetyka i minimalizm — **✅** (po polish)
- [x] Usunięty kryptyczny licznik „0/19 rozwiniętych" (polish D9)
- [x] Pasek per-magazyn ukryty, gdy nie wnosi informacji (<2 magazyny, polish D3)
- [x] Puste dni zbite do cienkiego wiersza (polish D5)
- [x] Tła stonowane — kolor zarezerwowany dla statusów (polish D11)
- [x] Pasek okresu scalony do jednej linii (polish D13)
- [ ] 🟡 Karta mobile pokazuje wszystkie pola bez etykiet (fast-follow z review — pionowy stos surowych wartości)

## H9. Pomoc w rozpoznaniu i naprawie błędów — **🟡**
- [x] Komunikaty walidacji po polsku (ISO 6346, data z przeszłości, limit)
- [x] Błędy przenoszenia dat wymieniają konkretne kontenery, które się nie udały
- [ ] 🟡 Część błędów API leci surowym `detail` — nie zawsze mówi „co dalej"
- [ ] ❌ Błąd sieci/timeout przy ładowaniu listy — brak przyjaznego stanu „nie udało się pobrać, spróbuj ponownie" z przyciskiem retry

## H10. Pomoc i dokumentacja — **❌**
- [ ] ❌ Brak pomocy kontekstowej w widoku (tooltipy „?" przy nietrywialnych mechanikach: cykl potwierdzania daty, limit dzienny, tranzyty)
- [ ] ❌ Brak krótkiego „jak to działa" dla nowych użytkowników (np. 5 kroków cyklu kontenera)
- [x] Dokumentacja procesowa istnieje (`docs/mapa-procesow-szczegolowa.md`), ale tylko dla deweloperów — nie jest dostępna z aplikacji

---

## Podsumowanie

| Heurystyka | Werdykt | Najważniejszy brak |
|---|---|---|
| H1 Widoczność statusu | 🟡 | skeleton/spinner + toast „zapisano" + wiek danych trackingu |
| H2 Język użytkownika | ✅ | tooltipy skrótów branżowych |
| H3 Kontrola i swoboda | 🟡 | undo po zmianie statusu/daty |
| H4 Spójność | ✅ | unifikacja czyszczenia filtrów |
| H5 Zapobieganie błędom | 🟡 | **ostrzeżenie/graf przy cofaniu statusu** |
| H6 Rozpoznawanie | ✅ | — |
| H7 Elastyczność | ✅ | skróty klawiszowe |
| H8 Minimalizm | ✅ | okrojona karta mobile |
| H9 Naprawa błędów | 🟡 | stan błędu ładowania z retry |
| H10 Pomoc | ❌ | tooltipy kontekstowe + mini-przewodnik |

**Top 3 do zrobienia (wpływ/koszt):**
1. **H5/H3:** ostrzeżenie przy cofaniu statusu głównego (krok do maszyny stanów — ⚠ nr 1 z mapy procesów)
2. **H1/H9:** skeleton przy ładowaniu + toast po zapisie + stan błędu z retry (jeden wspólny wzorzec)
3. **H10:** tooltipy „?" przy limicie dziennym, cyklu potwierdzania i tranzytach
