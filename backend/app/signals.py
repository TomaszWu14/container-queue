"""Silnik sygnałów: z listy kontenerów liczy pozycje 'Co dziś' (jedna lista działań).

Czysta funkcja — bez DB. Dane wejściowe: kontenery (ze scope), słownik terminów
demurrage (container_id -> date|None) i 'dziś'. Wagi/progi w SIGNAL_WEIGHTS = pokrętło
strojenia (docelowo panel admina, na razie stałe)."""

from typing import NamedTuple

from .models import Container, ContainerStatus, DocumentStatus

SIGNAL_WEIGHTS = {
    # waga bazowa typu (im wyższa, tym wyżej na liście przy równej pilności)
    "weights": {
        "demurrage": 10.0, "delayed": 6.0, "stuck": 5.0,
        "missing_avizo": 4.0, "po_unconfirmed": 3.5, "docs_pre_eta": 3.5,
        "eta_shift": 3.5, "missing_eta": 3.0, "missing_docs": 2.0,
        "special_care": 5.0,
    },
    "demurrage_days": 3,      # ile dni do terminu demurrage odpala sygnał
    # ^ mirror config.demurrage_alert_days — oba muszą pozostać równe (nie importujemy configu tu)
    "avizo_lead_days": 3,     # ETA w ciągu N dni bez awizacji = sygnał
    "docs_pre_eta_days": 5,   # brak dokumentów w oknie N dni przed ETA = mocniejszy sygnał
    "eta_shift_days": 2,      # przesunięcie ETA (vs zdjęcie z chwili awizacji) o ≥N dni
    "po_confirm_days": 5,     # zamówienie niepotwierdzone przez dostawcę po N dniach
    "demurrage_eur_per_day": 150.0,  # brak pola w configu — stała pokrętła
    "cost_scale": 100.0,      # dzielnik kosztu w punktacji (€ -> punkty)
}

# status 'w drodze/w porcie' = kontener aktywny, oczekuje ETA/awizacji/dokumentów
_ACTIVE = (ContainerStatus.W_TRANSPORCIE, ContainerStatus.W_PORCIE)


def _delay_days(c, today):
    ref = c.eta if (c.eta and c.eta < today) else (
        c.notify_date if (c.notify_date and c.notify_date < today) else None)
    return (today - ref).days if ref else 0


class _Ctx(NamedTuple):
    """Dane jednej oceny kontenera wspólne dla reguł sygnałów."""
    today: object
    weights: dict
    delay_days: int
    deadline: object
    order: dict | None
    care: dict | None


# reguła: (kontener, kontekst) -> (typ, pilność_dni, koszt_eur, akcja, klucz_opisu, parametry) | None
def _sig_demurrage(c, x: _Ctx):
    if x.deadline is None or (x.deadline - x.today).days > x.weights["demurrage_days"]:
        return None
    days_over = max(0, (x.today - x.deadline).days)
    cost = max(1, days_over) * x.weights["demurrage_eur_per_day"]
    until = (x.deadline - x.today).days
    return ("demurrage", -until if until < 0 else x.weights["demurrage_days"] - until,
            cost, "container", "sigSum_demurrage", {"cost": round(cost)})


def _sig_delayed(c, x: _Ctx):
    if c.is_delayed and x.delay_days > 0:
        return ("delayed", x.delay_days, None, "container", "sigSum_delayed",
                {"days": x.delay_days})
    return None


def _sig_stuck(c, x: _Ctx):
    return ("stuck", x.delay_days, None, "container", "sigSum_stuck", {}) if c.is_stuck else None


def _sig_missing_avizo(c, x: _Ctx):
    if c.status in _ACTIVE and c.eta and not c.notify_date \
            and (c.eta - x.today).days <= x.weights["avizo_lead_days"]:
        until = (c.eta - x.today).days
        return ("missing_avizo", x.weights["avizo_lead_days"] - until, None,
                "avizo-form", "sigSum_missing_avizo", {"days": until})
    return None


def _sig_missing_eta(c, x: _Ctx):
    if c.status in _ACTIVE and not c.eta:
        return ("missing_eta", x.delay_days, None, "container", "sigSum_missing_eta", {})
    return None


def _sig_eta_shift(c, x: _Ctx):
    """#25 proaktywny alert: ETA przesunęła się względem zdjęcia z chwili awizacji."""
    if not (c.status in _ACTIVE and c.eta and c.planning_eta_at_send):
        return None
    shift = (c.eta - c.planning_eta_at_send).days
    if abs(shift) < x.weights["eta_shift_days"]:
        return None
    return ("eta_shift", abs(shift), None, "container", "sigSum_eta_shift", {"days": shift})


def _sig_po_unconfirmed(c, x: _Ctx):
    """#9 zamówienie niepotwierdzone przez dostawcę po X dniach."""
    if x.order and x.order.get("unconfirmed"):
        days = x.order.get("days", 0)
        return ("po_unconfirmed", days, None, "container", "sigSum_po_unconfirmed",
                {"days": days})
    return None


def _sig_special_care(c, x: _Ctx):
    """D13 specjalna troska: T1 = minął max ETD bez wypłynięcia, T2 = prognoza po terminie."""
    risk = x.care
    if not risk:
        return None
    return ("special_care", risk["days"], None, "container",
            "sigSum_special_care_etd" if risk["t1"] else "sigSum_special_care_late",
            {"name": risk["name"], "days": risk["days"]})


def _sig_docs(c, x: _Ctx):
    """#30 braki dokumentów: mocniejszy sygnał w oknie przed ETA, inaczej zwykły missing_docs."""
    if c.document_status != DocumentStatus.BRAK:
        return None
    until = (c.eta - x.today).days if c.eta else None
    if c.status in _ACTIVE and until is not None \
            and 0 <= until <= x.weights["docs_pre_eta_days"]:
        return ("docs_pre_eta", x.weights["docs_pre_eta_days"] - until, None,
                "documents", "sigSum_docs_pre_eta", {"days": until})
    return ("missing_docs", x.delay_days, None, "documents", "sigSum_missing_docs", {})


# CODE-004: kolejność reguł = kolejność sygnałów przy remisie punktacji (sort stabilny)
_RULES = (_sig_demurrage, _sig_delayed, _sig_stuck, _sig_missing_avizo, _sig_missing_eta,
          _sig_eta_shift, _sig_po_unconfirmed, _sig_special_care, _sig_docs)


def _signal_row(c, weights, type_, urgency_days, cost_eur, action_kind, summary_key,
                summary_params) -> dict:
    cost_factor = (cost_eur or 0) / weights["cost_scale"]
    score = weights["weights"][type_] * (1 + max(0, urgency_days)) + cost_factor
    return {
        "container_id": c.id, "container_no": c.container_no,
        "company_name": c.company.name if c.company else None,
        "supplier_name": c.supplier.name if c.supplier else None,
        "port_name": c.port.name if c.port else None,
        "eta": c.eta.isoformat() if c.eta else None,
        "notify_date": c.notify_date.isoformat() if c.notify_date else None,
        "status": c.status.value, "type": type_, "score": round(score, 2),
        "urgency_days": urgency_days, "cost_eur": cost_eur,
        "action_kind": action_kind, "summary_key": summary_key,
        "summary_params": summary_params,
    }


def compute_signals(containers, deadlines, today, weights=SIGNAL_WEIGHTS, orders=None,
                    care=None):
    """orders: opcjonalna mapa container_id -> {"unconfirmed": bool, "days": int} ze stanu
    potwierdzeń zamówień u dostawcy (liczona z SapOrder poza silnikiem, bo tu bez DB).
    care: mapa container_id -> {"name", "t1", "days"} ryzyka specjalnej troski (D13)."""
    orders = orders or {}
    care = care or {}
    out = []
    for c in containers:
        if c.status in Container.FINISHED:  # zakończony — nic do zrobienia (demurrage, dokumenty)
            continue
        ctx = _Ctx(today, weights, _delay_days(c, today), deadlines.get(c.id),
                   orders.get(c.id), care.get(c.id))
        for rule in _RULES:
            signal = rule(c, ctx)
            if signal:
                out.append(_signal_row(c, weights, *signal))
    out.sort(key=lambda s: (s["score"], s["cost_eur"] or 0, s["container_no"]),
             reverse=True)
    return out
