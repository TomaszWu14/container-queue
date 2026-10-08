# Moduł spedycji i agencji celnej — flow, luki i plan uszczelniania

Dokument opisuje **jasne flow procesowe** obu modułów oraz listę zidentyfikowanych
**luk / słabych stron**, z podziałem na to, co już domknięto, i co proponujemy w kolejnych krokach.
Zgodnie z ustaleniem: „w razie niejasności pytamy i uszczelniamy dalej”.

## 1. Agencja celna (agencja celna) — nowy moduł

Agencja celna to **partner zewnętrzny z własnym loginem** (rola `customs`), analogicznie do spedycji.

### Flow (dwustronny, przejrzysty)

1. **Logistyka ZLECA odprawę** wskazanej agencji (przycisk „Zleć odprawę” w module *Agencja celna*
   lub panel na karcie kontenera). Status odprawy → `ZLECONA`. Agencja dostaje powiadomienie.
2. **Agencja WYZNACZA / ZMIENIA agenta** prowadzącego (imię, telefon, e-mail). Nasi pracownicy
   (logistyka spółki + admini) dostają powiadomienie.
3. **Agencja aktualizuje STATUS odprawy** (`DOKUMENTY_KOMPLETNE` / `REWIZJA` / `ODPRAWIONY`).
   Druga strona dostaje powiadomienie. Logistyka też może zmienić status — wtedy powiadamiana jest agencja.
4. **Komunikacja dwustronna** przez wiadomości przy kontenerze (istniejący kanał, teraz obejmuje agencję).
5. **Zmiana agencji** (reassign) czyści poprzedniego agenta i odpina starą agencję (traci dostęp),
   powiadamiając obie strony. **Wycofanie** (unassign) zdejmuje kontener z obiegu celnego.

### Bezpieczeństwo / separacja (domknięte w tym PR)

- Agencja widzi **wyłącznie kontenery jej zlecone** (`Container.customs_agency_id`), egzekwowane
  centralnie w `scope_containers` / `check_container_access` (fail-closed: brak agencji → 403).
- Agencja **nie widzi danych handlowych ani PII kierowcy** (dostawca, zamówienia, notatki, dane SENT,
  numer dowodu/telefon kierowcy) — ukryte przez `_CUSTOMS_HIDDEN`, analogicznie do konta magazynu.
- Agencja **nie edytuje** statusu głównego kontenera ani jego danych (tylko pola odprawy).

## 2. Spedycja (spedycja) — domknięcie

- **Dane kierowcy** uzupełnia sama spedycja po zalogowaniu (panel „Dane kierowcy” na karcie kontenera →
  `PATCH /api/containers/{id}/driver`). Zapis powiadamia obserwujących kontener.
- Import kontenerów i pozycji REF przeniesiony do **panelu administratora** (schowany przed zwykłymi userami).

---

## 3. Zidentyfikowane luki / słabe strony i rekomendacje

### Domknięte
- ✅ Brak realnej „drugiej strony” odprawy → dodano rolę `customs`, panel i dwustronne powiadomienia.
- ✅ Agencja zewnętrzna widziałaby dane handlowe → ukrycie pól (`_CUSTOMS_HIDDEN`).
- ✅ Brak separacji dostępu agencji → filtr po `customs_agency_id` + testy separacji.
- ✅ Rola `customs` bez przypisanej agencji blokowałaby konto → walidacja w panelu admina.
- ✅ **Alert „odprawa się przeciąga”** — cykliczny `check_customs_alerts`: powiadomienie (nasi +
  agencja), gdy odprawa jest `ZLECONA`/`REWIZJA` dłużej niż `CUSTOMS_ALERT_DAYS` (domyślnie 3 dni),
  raz na kontener/dzień.
- ✅ **Powiadamianie magazynu o danych kierowcy** — `PATCH /driver` powiadamia teraz również magazyn
  przyjmujący (np. DLT), nie tylko logistykę i spedycję.
- ✅ **Uzgodnienie agencji z importu** — nowa kolumna `AGENCJA CELNA` w imporcie; nazwa dopasowywana
  do rejestru agencji (`customs_agency_id`), z zachowaniem tekstu źródłowego.

### Rekomendowane w kolejnych krokach (do decyzji)
1. **Powiązanie odprawy z załącznikami** — checklista wymaganych dokumentów (faktura, packing list,
   świadectwa). Dziś `documents_ok`/`DOKUMENTY_KOMPLETNE` to flaga bez powiązania z plikami.
2. **SLA/termin akceptacji zlecenia transportowego** przez spedycję + przypomnienia, gdy brak reakcji.
3. **Onboarding agencji bez konta** — zaproszenie e-mail (jak dla użytkowników) przy pierwszym zleceniu.
4. **Rewizja (`REWIZJA`)** — ustrukturyzowany powód i ewentualny koszt/termin, dziś tylko notatka.
5. **Auto-podpowiedź statusu głównego** po `ODPRAWIONY` (kontener gotowy do awizacji/dostawy).
6. **Retencja PII kierowcy** (`driver_id_no`) — polityka czyszczenia po zrealizowaniu dostawy.
