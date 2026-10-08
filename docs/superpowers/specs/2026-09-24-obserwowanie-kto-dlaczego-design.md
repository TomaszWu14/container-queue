# Obserwowanie: kto, kiedy, dlaczego + awatar użytkownika

Data: 2026-09-24. Status: zaakceptowany projekt (rozmowa 2026-09-24).

## Cel

Gwiazdka „Obserwuj" (dziś `WatchedContainer`: tylko user + kontener) mówi *że* ktoś
obserwuje, ale nie *kto, od kiedy i po co*. Zespół chce widzieć w okienkach kontenera
i statku „Śledzone przez…" z powodem, a na mapie miniaturkę osoby (awatar, fallback
inicjały). Tracking automatyczny (RF + numer kontenera, AIS po nazwie statku) — bez zmian.

## Decyzje

- Rozszerzamy gwiazdkę (nie nowe pojęcie „ręcznego śledzenia").
- Powód **opcjonalny**: szybkie powody + własny tekst; można pominąć.
- Widoczność: role wewnętrzne (**admin, logistics, purchasing**) widzą wszystkich
  obserwujących; pozostałe role (warehouse, forwarder, customs) widzą tylko własny wpis —
  nazwiska i powody pracowników nie wychodzą na zewnątrz. (warehouse traktowany jak
  zewnętrzny, spójnie z odcięciem danych handlowych w `vessel_cargo`.)
- Model: wariant A — rozszerzenie `WatchedContainer` + równoległa `WatchedVessel`
  (nie generyczna tabela `Watch`, nie obserwacja statku po nazwie).

## PR 1 — kto / kiedy / dlaczego

**Model + migracja** (od jedynej głowy alembica):
- `watched_containers`: `reason String(200) default ''`, `created_at DateTime NULL`
  (stare wiersze bez daty → UI „—").
- nowa `watched_vessels`: `id, user_id FK users, vessel_id FK tracked_vessels,
  reason String(200) default '', created_at DateTime`; `UniqueConstraint(user_id, vessel_id)`.

**API**
- `POST /containers/{id}/watch` — body opcjonalne `{reason?: str}` (max 200); nadal toggle,
  odpowiedź `{"watching": bool}` bez zmian. Dostęp: `get_container_checked`.
- `GET /containers/{id}/watchers` → `{watching, watchers: [{user_id, name, reason, created_at}]}` (`has_avatar` dochodzi w PR 2),
  kolejność od najstarszej obserwacji; filtr widoczności wg decyzji wyżej.
- `POST /tracking/vessels/{id}/watch`, `GET /tracking/vessels/{id}/watchers`,
  (pole `watching` w odpowiedzi `/watchers` zastępuje osobną listę id) — dostęp przez `get_vessel_visible`
  (statek bez ładunku w zakresie usera → 404).
- Jeden helper budowy listy obserwujących (kontener i statek), filtr ról w jednym miejscu.

**UI**
- Dodanie gwiazdki (kolejka `TileMenus`, karta statku) otwiera małe okienko: szybkie powody
  *Pilne dla klienta / Ryzyko opóźnienia / Towar specjalny / Reklamacja*, pole tekstowe,
  „Obserwuj" i „Pomiń powód". Zdjęcie gwiazdki — natychmiast, bez okienka.
- Sekcja „Śledzone przez…" w karcie kontenera i `VesselCard`: inicjały (awatar w PR 2),
  imię, data, powód.
- Teksty: `frontend/src/i18n/features/obserwowanie.ts`.

**Testy**: powód i data zapisane; toggle bez body działa jak dotąd; rola zewnętrzna widzi
tylko siebie; statek poza zakresem → 404; DOM: okienko powodu (wybór szybkiego powodu,
„Pomiń powód").

## PR 2 — awatar + mapa

- `User.avatar String(255) default ''` — nazwa pliku w `uploads/avatars/`.
- `POST /me/avatar` (multipart), `DELETE /me/avatar`; zapis wzorem `_store_vessel_photo`:
  walidacja sygnatury obrazu (`_looks_like_image`), limit 2 MB, losowa nazwa, usunięcie
  starego pliku, `commit_with_file`.
- `GET /users/{id}/avatar` — tylko role wewnętrzne (+ własny awatar zawsze); brak → 404.
- `ProfilePage`: podgląd + Zmień / Usuń.
- Komponent `<UserAvatar user>`: zdjęcie albo inicjały na kolorze z hash(user_id).
- Mapa (`FlatMap`/`MapLayers`): przy markerze obserwowanego kontenera/statku stos
  awatarów (max 3 + „+n"). Obserwujący doklejeni w `/tracking/map` i `/tracking/vessels`
  jednym zapytaniem (bez N+1), z tym samym filtrem widoczności.
- Testy: upload odrzuca nie-obraz i >2 MB; GET avatara przez rolę zewnętrzną → 403/404;
  DOM: fallback inicjałów.

## Poza zakresem

Zmiana logiki powiadomień, edycja powodu po fakcie (zdejmij i dodaj ponownie),
kadrowanie/skalowanie awatara.
