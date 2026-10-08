# Publiczny link kliencki „mój kontener"

Data: 2026-09-15 · Plaster 2 planu trackingu (po osi czasu z PR #305) · Branch: `claude/container-share-link`

## Cel

Klient końcowy dostaje link (bez logowania) pokazujący status i oś czasu swojego
kontenera. Link generuje admin/logistyka z ContainerPage; da się go unieważnić
(rotacja) i wygasa po zamknięciu kontenera.

## Zakres danych publicznych

Wyłącznie: `container_no`, `status`, `eta`, `notify_date`, `timeline`
(z istniejącego `build_timeline()`). **Nie ujawniamy**: dostawcy, magazynu,
danych kierowcy, zamówień/wartości, pozycji statku ani żadnych pól handlowych.
Wpisy timeline typu "order" (numery zamówień, port wysyłki) są filtrowane
i nigdy nie trafiają do publicznej odpowiedzi — pozostałe wpisy (carrier,
vessel, system, planned) przechodzą bez zmian w treści.

## Backend

- Model `ContainerShareLink` (wzorzec 1:1 z awizo / linku kierowcy —
  hash SHA-256 w bazie, surowy token tylko w URL):
  - `container_id` FK, **unique** — jeden aktywny link per kontener,
  - `token: String(64)` unique+index (SHA-256 hex),
  - `created_by_id` FK users, `created_at`.
  - Migracja alembic + kolumny w dev-shimie nie trzeba (nowa tabela, create_all
    w dev ją tworzy).
- `POST /api/containers/{id}/share-link` — role admin/logistics, autoryzacja
  przez `get_container_checked()`. Generuje `secrets.token_urlsafe(32)`,
  upsert po `container_id` (nadpisanie hashu = stary link martwy), zwraca
  `{token}` — URL `/k/{token}` składa frontend z `window.location.origin`.
- Publiczny `GET /api/public/containers/{token}` (bez auth, router jak avizo):
  - 404 — token nieznany (po hashu),
  - **410** — kontener w statusie ZREALIZOWANY dłużej niż 30 dni (data z
    ostatniego wpisu AuditLog o zmianie statusu na ZREALIZOWANY; brak wpisu →
    link ważny),
  - 200 — `{container_no, status, eta, notify_date, timeline}`.

## Frontend

- `ContainerTimeline` dostaje opcjonalny prop `entries?: TimelineEntry[]` —
  jeśli podany, komponent nie fetchuje (reużycie na stronie bez auth).
  Zachowanie dotychczasowych użyć bez zmian.
- Publiczna strona `/k/:token` — route poza guardem logowania (wzorzec strony
  kierowcy): nagłówek z `container_no`, badge statusu, ETA/awizacja, oś czasu.
  Stany: loading, 404 („link nieprawidłowy"), 410 („link wygasł").
  Stylistyka stal+bursztyn, Polish-first, bez topnavu aplikacji.
- ContainerPage: przycisk „Link dla klienta" (widoczny dla admin/logistics) —
  POST, kopiuje URL do schowka, toast z potwierdzeniem i informacją, że
  poprzedni link przestał działać.

## Testy

Backend (`tests/test_share_link.py`):
- generowanie: 200 dla admin/logistics, 403 dla viewer; rotacja — stary token
  po ponownym POST daje 404,
- publiczny odczyt: poprawny token → 200 z dokładnie 5 polami (asercja na
  zbiór kluczy — strażnik przed wyciekiem), zły token → 404,
- wygaśnięcie: ZREALIZOWANY + wpis audytu starszy niż 30 dni → 410,
- izolacja: token działa bez nagłówków auth.

Frontend: test DOM strony publicznej (render statusu i osi z mockiem,
komunikaty 404/410); test, że `ContainerTimeline` z prop `entries` nie woła api.

## Poza zakresem

Widok „moje kontenery" dla zalogowanych viewerów, mini-mapa AIS na stronie
publicznej, wysyłka linku e-mailem z aplikacji, dashboard floty, powiadomienia.
