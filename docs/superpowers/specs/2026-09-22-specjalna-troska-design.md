# Spec: Zamówienia specjalnej troski (marka własna) — v1

*Data: 2026-09-22*

## Cel
Osobny moduł do pilnowania kluczowych zamówień (marka własna): ręcznie składane
„zamówienie specjalnej troski" z deadline dotarcia i must-departure, automatycznie
dopasowane do kontenerów po numerach zamówień, z wyliczanym ryzykiem (2 wyzwalacze).

## Decyzje (zatwierdzone)
- Powiązanie z kontenerami: **po numerach zamówień** (`order_refs` ↔ `Container.order_numbers`, `ilike`).
- Wyzwalacz 2: **najpóźniejsza ETA dopasowanych kontenerów + stały narzut dni** (`buffer_days`).
- **Nowy moduł/strona**, rola logistyka/admin.
- v1: ryzyko liczone i pokazywane w module (badge/filtr). **Push (email/job dzienny) + wpięcie w „Co dziś" = follow-up.**

## Model `CustomerOrder`
`id, company_id (FK, izolacja), name (nazwa/marka), customer_name (str), order_refs (Text, CSV/nl numerów),
deadline (Date, dotarcie), max_etd (Date, musi wypłynąć do), buffer_days (Int, default 5),
responsible_id (FK users, nullable), alert_on_delay (Bool, default True), note (Text),
created_by_id (FK users, nullable), created_at (DateTime)`.

## Wyliczane (na odczyt, nie zapisywane)
- `matched` = kontenery, których `order_numbers` zawiera którykolwiek token z `order_refs` (ilike, po spółce).
- `earliest_etd`, `latest_eta` (z matched, ignorując puste), `departed` = któryś matched ma `atd` != null LUB status po wypłynięciu.
- `trigger_etd_missed` = `today > max_etd and not departed` (gdy `max_etd` ustawione).
- `trigger_forecast_late` = `latest_eta is not None and latest_eta + buffer_days > deadline` (gdy `deadline` i `latest_eta`).
- `at_risk = trigger_etd_missed or trigger_forecast_late`.

## Backend
- Migracja `customer_orders`.
- `/api/customer-orders` CRUD (list/create/update/delete), scope per spółka (jak klienci: `can_view_all` / `company_id`).
- Rola: logistyka/admin (editors; warehouse/customs/forwarder bez dostępu).
- Każdy zwrócony rekord niesie wyliczone pola (`matched_count, earliest_etd, latest_eta, departed, trigger_etd_missed, trigger_forecast_late, at_risk` + lista `matched` skrócona: id+container_no).
- Nowy router `backend/app/routers/customer_orders.py` (wpięty w main).

## Frontend
- Nowy moduł „Specjalna troska": strona `SpecialCarePage` (lista z badge ryzyka + filtr „tylko zagrożone" + formularz add/edit/delete, wybór opiekuna z użytkowników).
- Route `/specjalna-troska` z `Guarded ok={admin||logistics}` (wzór `/zlecenia-spedycyjne`).
- NavLink w menu (grupa jak Zamówienia/Spedycja).
- i18n PL/EN/PT.

## Testy
- Backend `test_customer_orders`: dopasowanie po refach; T1 (po max_etd, nie wypłynął); T2 (eta+buffer>deadline); brak ryzyka; izolacja spółki; delete.
- Frontend: lista renderuje badge „zagrożone" dla rekordu at_risk.

## Poza zakresem v1
Push (email/powiadomienie do opiekuna), dzienny job monitorujący, wpięcie ryzyka w „Co dziś", pre-alert 10 dni + asystent (Faza 3).
