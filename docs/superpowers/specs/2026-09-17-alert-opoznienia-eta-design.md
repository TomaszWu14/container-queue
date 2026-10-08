# Alert wczesnego ostrzegania o opóźnieniu ETA — design

**Data:** 2026-09-17
**Status:** zaakceptowany do planowania implementacji

## Problem

Dział hurtu dowiaduje się o opóźnieniu dostawy dopiero tuż przed uzgodnionym z klientem
terminem — za późno, żeby uprzedzić klienta. Potrzebny jest alert, który uruchamia się
znacznie wcześniej, gdy widać że statek/kontener realnie spóźni się względem tego, co
historia pokazuje jako normalny czas tranzytu dla danej trasy.

Dotyczy w pierwszej kolejności zamówień pod markę własną klienta (private label) —
ale system nie ma dziś pojęcia "marka własna"; zakres realizowany jest przez ręczne
oznaczanie wybranych, ważnych kontenerów (patrz Zakres).

## Punkt odniesienia: baseline systemowy, nie zamrożone ETA

Rozważano dwa podejścia do "co to znaczy: opóźnienie":
1. dryf ETA armatora względem jego pierwszej zarejestrowanej wartości,
2. rozjazd między **systemowym baseline** (nasza historyczna norma czasu tranzytu dla
   portu załadunku) a aktualnym ETA armatora.

Wybrano (2). Repo ma już policzoną statystykę `avg_days` (ETD→ATD, per port załadunku,
ostatnie 12 mies., kontenery `FINISHED`) w `routers/containers.py:transit_trend`
(endpoint `/stats/transit-trend`). Ten fragment logiki SQL zostaje wydzielony do
reużywalnego helpera:

```python
def avg_transit_days(db: Session, port_id: int, user: User) -> float | None:
    """Średni czas tranzytu (ETD→ATD) dla portu, ostatnie 12 mies., kontenery FINISHED.
    None gdy brak wystarczającej historii — wołający MUSI to obsłużyć (brak baseline)."""
```

`baseline_eta = container.etd + avg_transit_days(port)`.

**Alert:** `container.eta > baseline_eta + settings.delay_watch_alert_days`.

Jeśli `container.etd` jest `None`, albo `avg_transit_days` zwraca `None` (brak
wystarczającej historii dla portu) — kontener jest **pomijany** w tym sprawdzeniu.
Brak baseline = brak możliwości osądu = brak alertu. Nie ma fallbacku do innej metryki.

## Zakres: ręczne oznaczanie

Nowe pole `Container.delay_watch: bool` (default `False`), ustawiane ręcznie przez
usera z rolą `purchasing`/`logistics`/`admin` w UI kontenera. Alert sprawdzany jest
WYŁĄCZNIE dla kontenerów z `delay_watch=True`.

Uwaga: generyczny `update_container`/`ContainerUpdate` jest gated przez `Editors`
(`deps.py`) = tylko `admin`+`logistics`, bez `purchasing` — i faktycznie inne pole
zawężone do purchasing (`demurrage_free_days`) NIE idzie przez ten endpoint: ma
własny, dedykowany endpoint w `routers/purchasing.py` gated przez `purchasing_side`
(`admin`+`logistics`+`purchasing`). `delay_watch` idzie tym samym, już ustalonym
wzorcem — własny mały endpoint (np. `PATCH /api/containers/{id}/delay-watch`) w
`routers/purchasing.py`, gated przez `purchasing_side`, NIE dopisany do
`ContainerUpdate`.

Odrzucono automatyczne objęcie wszystkich kontenerów — przy rosnącej liczbie zleceń
generowałoby szum dla przypadków, gdzie 2-tygodniowe opóźnienie nie ma znaczenia
biznesowego. Odrzucono też próg konfigurowalny per kontener (patrz niżej) — jeden
globalny próg wystarcza, mniej pól do wypełniania przy oznaczaniu.

## Próg

Nowy setting `settings.delay_watch_alert_days: int` (domyślnie `14`), globalny —
analogicznie do istniejącego `settings.tracking_eta_alert_days`. Edytowalny przez
admina w `/api/settings` (wzorzec identyczny jak inne progi alertów w tym pliku).

## Odbiorcy

Suma dwóch źródeł, rozwiązywana na bieżąco przy każdej wysyłce (nie migawka z chwili
oznaczenia kontenera):

1. **Role na stałe** — wszyscy aktywni userzy z rolą `purchasing` lub `logistics` w
   spółce kontenera (`container.company_id`). Nowy helper w `notifications.py`, obok
   `company_watchers`:
   ```python
   def delay_watch_default_recipients(db: Session, company_id: int) -> list[User]:
       """Asystenci zakupów + logistyka spółki — stali odbiorcy alertu opóźnień."""
   ```
   Bez UI do konfiguracji — to stały, wbudowany zestaw ról (jak `company_watchers`
   dla innych alertów).

2. **Konkretni dodatkowi userzy** — reużycie istniejącej tabeli `WatchedContainer`
   (gwiazdka "moje kontenery"). Dziś endpoint dodawania obserwującego jest czysto
   samoobsługowy (user dodaje wyłącznie siebie). Rozszerzenie: user z rolą
   `purchasing`/`logistics`/`admin` może dodać DOWOLNEGO innego użytkownika jako
   obserwującego danego kontenera (np. konkretną osobę z hurtu); każdy user nadal
   może dodać się sam, bez zmian.

   `PATCH/POST /api/containers/{id}/watch` — dodać opcjonalny parametr `user_id`
   (domyślnie `None` = self). Gdy podany i różny od `current_user.id` — wymaga
   roli `purchasing`/`logistics`/`admin`; inaczej `403`.

   Uwaga: **`Editors` w `deps.py` to tylko `admin`+`logistics`, bez `purchasing`** —
   nie da się tu użyć wprost. Endpoint (`containers.py`, gdzie już mieszka
   self-service watch) importuje istniejący `purchasing_side` z
   `routers/purchasing.py` zamiast duplikować `require_roles(...)`.

Finalna lista odbiorców = `delay_watch_default_recipients(db, container.company_id)`
∪ userzy z `WatchedContainer` dla tego kontenera (deduplikacja po `user.id`, jak w
istniejącej funkcji `notify()`).

## Alert: sprawdzanie i dedup

Nowa funkcja `check_delay_watch_alerts(db, today=None) -> int` w `notifications.py`,
wzorowana strukturalnie na sąsiednim `check_tracking_alerts` (blok `eta_drift`/
`vessel_stuck`):

```python
def check_delay_watch_alerts(db: Session, today: datetime.date | None = None) -> int:
    """Kontenery oznaczone delay_watch=True, gdzie ETA armatora przekracza systemowy
    baseline (ETD + średni czas tranzytu portu) o próg z ustawień. Jeden alert
    na kontener na dobę."""
```

Logika: dla każdego `Container` z `delay_watch=True` i statusem jeszcze nie
`FINISHED`, policz baseline, sprawdź próg, dedup przez identyczny wzorzec co
`eta_drift`/`vessel_stuck` (`Notification.kind == "delay_watch"`,
`Notification.container_id == container.id`, `Notification.created_at >= midnight`
→ pomiń jeśli już wysłano dziś).

Nowy `Notification.kind = "delay_watch"`.

**Cykl:** dopięta do istniejącej pętli `customs_delay_loop` w `main.py` (co 6h),
obok `check_tracking_alerts` — ten sam rytm co siostrzane alerty trackingowe, żadnej
nowej infrastruktury schedulera.

**Treść powiadomienia:** wzorem `vessel_stuck` — numer kontenera, port, ile dni
ponad baseline, link do kontenera.

## UI

Na stronie kontenera (purchasing/logistics/admin): checkbox "monitoruj opóźnienia" obok istniejących
pól trackingu. Gdy zaznaczony — pokazuje listę obserwujących (`WatchedContainer`)
z możliwością dodania kolejnej osoby (dropdown userów spółki) i usunięcia.
Bez oznaczenia domyślnych odbiorców ról w UI — to stały, niewidoczny w konfiguracji
zestaw (purchasing+logistics), tak jak dziś działa `company_watchers` dla innych
alertów.

## Co świadomie pominięto (YAGNI)

- Próg konfigurowalny per kontener — jeden globalny wystarcza.
- Generyczny silnik reguł alertów (patrz „Dwa podejścia" w rozmowie) — brak dziś
  drugiego typu reguły, który by go uzasadnił.
- Automatyczne objęcie wszystkich kontenerów bez oznaczania — zbyt dużo szumu.
- Kanał alertu poza istniejącym (in-app + email + Teams przez `notify()`) — bez
  nowego kanału, reużycie infrastruktury.
- Cotygodniowy przegląd ręczny — zastąpiony w całości przez automat; jeśli w
  praktyce okaże się niewystarczający, temat wraca.

## Testy (do pokrycia w planie implementacji)

- `avg_transit_days`: brak historii → `None`; poprawna średnia z kilku kontenerów.
- `check_delay_watch_alerts`: kontener bez `delay_watch` pomijany; kontener bez
  `etd`/baseline pomijany; alert wysyłany raz na dobę (dedup); alert NIE wysyłany
  gdy ETA mieści się w progu.
- Odbiorcy: rola purchasing+logistics zawsze w środku; dodany obserwujący dochodzi
  bez duplikatów.
- Endpoint dodawania obserwującego: self-add bez zmian; add innego usera wymaga
  `purchasing_side` (admin/logistics/purchasing), 403 dla viewera/warehouse/forwarder.
- Endpoint `delay-watch`: 403 dla ról spoza purchasing/logistics/admin.
