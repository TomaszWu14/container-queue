# Moduł kontenerów tranzytowych

Ustalenia: 2026-09-02. Zamyka backlog z
`2026-09-02-tracking-powiadomienia-sync-design.md:163`.

## Czym jest tranzyt

Kontener obsługiwany **poza główną kolejką do naszego magazynu** — nie jedzie do nas.
Najczęściej spółki ACME, ale przynależność do spółki go **nie** definiuje; definiuje
go cel. Dziś prowadzone wyłącznie mailowo: **zero rekordów w bazie, zero danych do
migracji, nic do sklasyfikowania wstecz.**

## Decyzje (zamknięte)

| Pytanie | Decyzja |
|---|---|
| Odróżnienie w danych | **`Container.is_transit: bool = False`** + migracja |
| Odprawa celna | **dotyczy** — pełny obieg jak zwykły kontener |
| Demurrage | **dotyczy** — alerty liczone normalnie |
| Dostęp | **jak reszta kolejki** — bez nowej roli, bez zmian w `roles.py`/`deps.py` |
| Wejście danych | ręcznie w panelu, reużycie `POST /api/containers`. Bez arkusza, bez syncu, bez parsowania maili |

### Dlaczego flaga, a nie magazyn „TRANZYT"

Magazyn-atrapa byłby mniejszym diffem (wzorzec DLT = `MODULE_WAREHOUSE`), ale
**zatruwa limity dzienne**: `containers.py:814` liczy `used` z wszystkich kontenerów
danego `notify_date`, a `over_limit` porównuje to z limitem magazynu. Tranzyt, który
się u nas nie rozładowuje, zawyżałby kalendarz i analizę rozładunków — ekrany używane
codziennie. `warehouse_id IS NULL` odpada, bo NULL już dziś znaczy „magazyn jeszcze
nieprzypisany" (świeże zlecenia, placeholdery) — nie da się odróżnić tranzytu od
niedokończonego rekordu.

## Zakres zmian

### Backend

1. **Model + migracja** — `Container.is_transit: Mapped[bool] = mapped_column(Boolean,
   default=False, index=True)` (`models.py`, klasa `Container`). Migracja Alembic:
   dodanie kolumny z `server_default='0'`, wszystkie istniejące rekordy = `False`.
2. **Filtr kolejki** — `GET /api/queue` i `GET /api/containers`: nowy parametr
   `transit: bool | None`. `None` = bez filtra (kompatybilność wsteczna),
   `True`/`False` = `where(Container.is_transit.is_(...))`.
   Miejsce: `containers.py:441` (lista) i `containers.py:~775` (dni kolejki).
3. **Limity dzienne — jedyny wyjątek w logice.** W `containers.py:814` licznik
   `used` musi pomijać tranzyty:
   `sum(1 for c in items if c.status not in Container.FINISHED and not c.is_transit)`.
   Bez tego kalendarz i „analiza rozładunków" liczą kontenery, które u nas nie
   staną. To **jedyne** miejsce, gdzie tranzyt zachowuje się inaczej niż zwykły
   kontener — reszta (odprawa, demurrage, tracking, powiadomienia) działa bez zmian.
4. **Schemas** — `is_transit` w `ContainerOut` i w wejściu create/update
   (`schemas.py`). Zmiana flagi idzie przez zwykły audyt (`record()`), jak każde pole.

### Frontend

5. **Nowa zakładka** — `QueuePage.tsx:30`: `type Module` + `'tranzyt'`. Nie ma wpisu
   w `MODULE_CODE` (tranzyt nie jest spółką) ani w `MODULE_WAREHOUSE` — zamiast tego
   nowa mapa `MODULE_TRANSIT: Partial<Record<Module, boolean>> = { tranzyt: true }`,
   przekładana na `?transit=true` w zapytaniu. Pozostałe zakładki wysyłają
   `?transit=false`, żeby tranzyty nie wpadały do zwykłych kolejek.
6. **Formularz kontenera** — checkbox „tranzyt" na karcie kontenera. Pola wymagane
   bez zmian (numer, spółka); magazyn rozładunku dla tranzytu jest opcjonalny.

### Tracking — działa za darmo

SafeCube pyta po numerze kontenera niezależnie od spółki, magazynu i pliku. Tranzyt
wpięty w kolejkę od razu dostaje śledzenie, ETA, oś zdarzeń i powiadomienia z PR 1.
`tracking/service.py:TRACKABLE` nie wymaga zmian.

## Testy (strażnicy regresji)

- `is_transit=True` **nie** podbija `used`/`over_limit` w `/api/queue` — test na
  jednym dniu z limitem 1 + jeden tranzyt + jeden zwykły.
- `?transit=true` zwraca wyłącznie tranzyty; `?transit=false` wyłącznie resztę;
  brak parametru = wszystko (kompatybilność).
- Kontener tranzytowy przechodzi tracking i dostaje zdarzenia tak samo jak zwykły.

## Poza zakresem

- Import z Excela, sync, parsowanie maili — tranzyty wchodzą tylko ręcznie.
- Osobne role/uprawnienia.
- Retroaktywna klasyfikacja istniejących kontenerów — nie ma czego klasyfikować.
