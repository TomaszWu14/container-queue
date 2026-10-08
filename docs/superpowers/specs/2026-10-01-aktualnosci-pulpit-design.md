# Aktualności na Pulpicie — powiadomienia jak news (design)

Data: 2026-10-01 · Status: zatwierdzony w pytaniach (10) · Zastępuje: dymek dzwonka jako jedyne miejsce czytania

## Problem
Dymek dzwonka jest za ciasny: długie wiadomości (listy kontenerów, statki, importy) czyta się
źle, nie da się filtrować ani przejść do kontenera z treści.

## Decyzje
1. **Dzwonek** zostaje szybkim podglądem ostatnich wiadomości + „Zobacz wszystkie” → Pulpit.
2. **Układ:** lista (oś czasu kart, sekcje dni) + panel czytania obok.
3. **Miejsce:** tylko na Pulpicie (sekcja „Aktualności”), bez osobnej strony.
4. **6 kategorii** z rodzaju (`kind`) + chipy filtrów, „tylko nieprzeczytane”, szukaj:
   Statki/tracking · Odprawa · Zamówienia/zakupy · Dostawy/awizacje · Wiadomości · System.
5. **Panel czytania:** klikalne numery kontenerów z treści, przyciski akcji wg rodzaju,
   mini-karta kontenera (gdy jeden), powiązane powiadomienia (wątek).
6. **Przeczytana** po otwarciu w panelu; „oznacz jako nieprzeczytaną”, „oznacz wszystkie”.
7. **Ważność z rodzaju:** pilne (`system-error`, `vessel_stuck`, `demurrage`, `pallet_urgent`,
   `invoice-mismatch`) — czerwony pasek, przypięte na górze dopóki nieprzeczytane; informacyjne
   (digesty, przypomnienia importów, tracking) — przygaszone; reszta — ważne.
8. **Historia:** sekcje dni, po 50 + „załaduj starsze”. Retencja: istniejący job
   `purge_read_notifications` z progiem 90 dni (było 180) — **nieprzeczytane zostają**,
   żeby nie znikło coś, czego nikt nie widział.
9. **Wątki:** jedna karta na kontener (`container_id`) albo statek (nazwa z tytułu „Statek X …”)
   z „+N wcześniejsze”; w panelu oś zdarzeń wątku.
10. **Klik w dymku dzwonka** → Pulpit z tą wiadomością otwartą w panelu (`?wiadomosc=<id>`).

## API
- `GET /api/notifications/feed?category=&unread_only=&q=&before_id=&limit=50` →
  `{items, pinned, has_more}`; element: pola powiadomienia + `category`, `priority`,
  `thread_key`, `containers` [{id, container_no}] (numery ISO 6346 z treści, w zakresie użytkownika).
- `GET /api/notifications/{id}/thread` → wiadomości z tym samym wątkiem (90 dni).
- `POST /api/notifications/unread?notification_id=` — cofnięcie przeczytania.

## Plan PR-ów
1. Backend: feed (kategorie, ważność, wątek, kontenery z treści, filtry, paginacja), wątek,
   „nieprzeczytana”, retencja 90 dni.
2. Pulpit: sekcja Aktualności (lista + panel czytania, akcje, mini-karta, wątek).
3. Dzwonek: „Zobacz wszystkie”, klik → Pulpit z otwartą wiadomością.
