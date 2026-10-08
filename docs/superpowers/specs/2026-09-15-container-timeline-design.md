# Timeline kontenera + realistyczna mapa satelitarna

Data: 2026-09-15 · Branch docelowy: nowy `claude/container-timeline` (poza etd-purchase-orders)

## Cel

Plaster 1 większego planu trackingu (timeline → widok kliencki → dashboard floty →
powiadomienia). Ten spec obejmuje **tylko**:

1. **Oś czasu kontenera** — jedna chronologiczna oś zdarzeń na `ContainerPage`,
   sklejająca 4 istniejące źródła danych, z etapami przyszłymi (szacowanymi).
2. **Realistyczna mapa** — podkład satelitarny (NASA Blue Marble) na istniejącej
   mapie SVG w `TrackingPage`.

## 1. Oś czasu kontenera

### Backend

- Nowy moduł `backend/app/tracking/timeline.py`:
  `build_timeline(db, container) -> list[TimelineEntry]`.
- Endpoint `GET /tracking/containers/{id}/timeline` w `routers/tracking.py`,
  autoryzacja przez istniejący `get_container_checked()` (izolacja per-firma za darmo).
- Schemat `TimelineEntryOut` w `schemas.py`:
  `kind` (`order` | `carrier` | `vessel` | `system` | `planned`), `title`,
  `location`, `at: datetime | None`, `estimated: bool`, `source: str`.

### Źródła sklejane w jedną oś

| kind | źródło | co bierzemy |
|---|---|---|
| `order` | `PurchaseOrder.etd` (zamówienia powiązane z kontenerem) | „Zamówienie — planowane wypłynięcie (ETD)" |
| `carrier` | `TrackingEvent` | zdarzenia armatora (LOAD, DEPART, TRANSSHIP, DISCHARGE…); `is_estimated` przenosi się na `estimated` |
| `vessel` | `VesselPortCall` statku kontenera | wejścia/wyjścia z portów po drodze (geofence AIS) |
| `system` | `AuditLog` | **tylko** zmiany pola statusu kontenera, mapowane na polskie etykiety (wejście do kolejki, awizacja, rozładunek, zamknięcie) |
| `planned` | ETA kontenera / `TrackedVessel.ais_eta` / data awizacji | przyszłe etapy: „Przybycie do portu (szac.)", „Planowany rozładunek" — tylko gdy data > teraz |

### Reguły sklejania

- Sort rosnąco po `at`; wpisy bez daty na końcu, oznaczone.
- Deduplikacja nie jest potrzebna między źródłami (różne `kind`); w ramach
  `carrier` unikalność gwarantuje istniejący UniqueConstraint.
- Kontener bez trackingu → oś zawiera samą historię systemową (to poprawny wynik,
  nie błąd).

### Frontend

- Wspólny komponent `frontend/src/pages/ContainerTimeline.tsx` (od razu
  reużywalny w plastrze 2 — widoku klienckim).
- Sekcja „Oś czasu" na `ContainerPage`: pionowa oś, kropki kolorowane po `kind`,
  wpisy `estimated`/`planned` wyszarzone z badge „szac.".
- Stylistyka zgodna z paletą stal+bursztyn (obecny design system).

### Testy

`backend/tests/test_timeline.py`:
- merge sortuje i miesza źródła chronologicznie,
- wpisy `estimated`/`planned` poprawnie oznaczone, przyszłość tylko dla dat > teraz,
- izolacja firm: 403 na cudzy kontener,
- kontener bez trackingu → sama historia systemowa.

Frontend: test DOM komponentu (render wpisów, badge „szac.").

## 2. Realistyczna mapa satelitarna

Mapa w `TrackingPage.tsx` to własny SVG z projekcją równokątną
(`project()` — liniowe lon/lat, viewBox 1000×500), **nie** Leaflet — kafle odpadają.

- Podkład: **NASA Blue Marble** (domena publiczna) w projekcji równokątnej,
  JPG ~1350×675 px (≈0,3–0,5 MB), bundlowany lokalnie w `frontend/src/assets/`
  (żadnych zewnętrznych hostów, spójne z CSP).
- W SVG: `<image href={blueMarble} width={WORLD_W} height={WORLD_H} preserveAspectRatio="none" />`
  zastępuje `<rect>` tła i `WORLD_PATH`; projekcja pasuje 1:1, więc markery,
  trasy AIS, zoom i pan działają bez zmian.
- Czytelność na ciemnym oceanie: markery mają już białą obwódkę; linie tras
  dostają w razie potrzeby jaśniejszy kolor/obwódkę — do weryfikacji wizualnej.
- `worldmap.ts` (WORLD_PATH) zostaje jako fallback/nieużywany eksport — mocki w
  istniejących testach DOM nadal działają.

## Poza zakresem (kolejne plastry)

Widok kliencki „mój kontener", dashboard operacyjny floty, powiadomienia/alerty
(istniejący spec 2026-09-02 do odkurzenia), glob 3D.
