"""Zamówienia specjalnej troski: ręcznie zestawione zamówienia własnej marki,
dopasowywane do kontenerów po numerach zamówień, z wyliczanym ryzykiem
(2 wyzwalacze: przekroczony max_etd, prognoza dotarcia później niż deadline)."""
import datetime
import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..audit import record, record_changes, record_created
from ..database import get_db
from ..deps import CareReaders as care_readers
from ..deps import Editors as editors
from ..deps import company_filter_ids, get_scoped, resolve_company_id, scope_company
from ..models import Container, CustomerOrder, Role, User, today_pl
from ..order_numbers import split_order_numbers

router = APIRouter(prefix="/api", tags=["specjalna troska"])


def _container_refs(order_numbers: str | None) -> set[str]:
    """Numery kontenera do dopasowania refów zamówienia: wspólny podział PLUS dawne
    tokeny rozdzielone tylko przecinkiem/średnikiem/spacją — ref z „/” (np.
    „4500617421/10”) musi dalej trafiać w cały token, nie tylko w jego części."""
    return ({t.lower() for t in split_order_numbers(order_numbers)}
            | {t.lower() for t in re.split(r"[,;\s]+", order_numbers or "") if t})


def _compute(db: Session, order: CustomerOrder, today: datetime.date) -> dict:
    refs = [r.strip() for r in re.split(r"[,\n]", order.order_refs or "") if r.strip()]
    matched = []
    if refs:
        q = select(Container).where(Container.company_id == order.company_id)
        conds = [Container.order_numbers.ilike(f"%{r}%") for r in refs]
        q = q.where(or_(*conds))   # wstępny filtr w SQL; dokładne dopasowanie niżej
        # ref pasuje tylko jako CAŁY numer („4500617421” ≠ „45000174210”)
        wanted = {r.lower() for r in refs}
        matched = [c for c in db.scalars(q).all() if wanted & _container_refs(c.order_numbers)]
    etds = [c.etd for c in matched if c.etd]
    etas = [c.eta for c in matched if c.eta]
    earliest_etd = min(etds) if etds else None
    latest_eta = max(etas) if etas else None
    departed = any((c.atd is not None) or (c.status in Container.FINISHED) for c in matched)
    t1 = bool(order.max_etd and today > order.max_etd and not departed)
    t2 = bool(order.deadline and latest_eta
              and (latest_eta + datetime.timedelta(days=order.buffer_days) > order.deadline))
    return dict(matched=matched, earliest_etd=earliest_etd, latest_eta=latest_eta,
                departed=departed, trigger_etd_missed=t1, trigger_forecast_late=t2,
                at_risk=(t1 or t2))


def care_risk_map(db: Session, containers, today: datetime.date, user: User) -> dict[int, dict]:
    """D13: kontener -> ryzyko T1/T2 zamówienia specjalnej troski (dla silnika sygnałów).
    Zamówienie bez dopasowanych kontenerów nie ma wiersza „Co dziś" (sygnał jest per kontener).
    Tylko role modułu (Editors = admin/logistyka) — reszta dostaje pustą mapę, bez wycieku."""
    cids = {c.id for c in containers}
    risk = care_risk_by_company(db, {c.company_id for c in containers}, today, user)
    return {k: v for k, v in risk.items() if k in cids}


def care_risk_by_company(db: Session, companies: set[int], today: datetime.date,
                         user: User) -> dict[int, dict]:
    """Jak care_risk_map, ale bez listy kontenerów: klucze = WSZYSTKIE dopasowane kontenery
    spółek (także spoza zakresu usera) — wołający sam przecina je ze swoim zakresem."""
    if user.role not in (Role.admin, Role.logistics) or not companies:
        return {}
    out: dict[int, dict] = {}
    # ponytail: _compute = 1 zapytanie na zamówienie; zbiorczo, gdy zamówień będą setki
    for order in db.scalars(select(CustomerOrder).where(
            CustomerOrder.company_id.in_(companies), CustomerOrder.alert_on_delay.is_(True))):
        r = _compute(db, order, today)
        if not r["at_risk"]:
            continue
        t1 = r["trigger_etd_missed"]
        days = (today - order.max_etd).days if t1 else (
            r["latest_eta"] + datetime.timedelta(days=order.buffer_days) - order.deadline).days
        for c in r["matched"]:
            if c.id not in out:
                out[c.id] = {"name": order.name, "t1": t1, "days": days}
    return out


def customer_order_map(db: Session, containers, user: User) -> dict[int, str]:
    """Flaga „pod klienta" w kolejce: kontener -> nazwa klienta (albo zamówienia), gdy
    któryś jego numer zamówienia jest w refach zamówienia specjalnej troski. JEDNO
    zapytanie o zamówienia, dopasowanie w pamięci. Tylko role modułu (jak care_risk_map)."""
    if user.role not in (Role.admin, Role.logistics):
        return {}
    companies = {c.company_id for c in containers}
    if not companies:
        return {}
    orders = [(o.company_id, o.customer_name or o.name,
               {r.strip().lower() for r in re.split(r"[,\n]", o.order_refs or "") if r.strip()})
              for o in db.scalars(select(CustomerOrder).where(CustomerOrder.company_id.in_(companies))
                                  .order_by(CustomerOrder.id))]
    out: dict[int, str] = {}
    for c in containers:
        refs = _container_refs(c.order_numbers) if c.order_numbers else set()
        label = next((lbl for cid, lbl, want in orders if cid == c.company_id and want & refs), None)
        if label:
            out[c.id] = label
    return out


class CustomerOrderIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    customer_name: str = Field(default="", max_length=200)
    order_refs: str = ""
    deadline: datetime.date | None = None
    max_etd: datetime.date | None = None
    buffer_days: int = 5
    responsible_id: int | None = None
    alert_on_delay: bool = True
    note: str = ""
    company_id: int


class CustomerOrderOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    company_id: int
    name: str
    customer_name: str
    order_refs: str
    deadline: datetime.date | None
    max_etd: datetime.date | None
    buffer_days: int
    responsible_id: int | None
    alert_on_delay: bool
    note: str
    matched_count: int
    earliest_etd: datetime.date | None
    latest_eta: datetime.date | None
    departed: bool
    trigger_etd_missed: bool
    trigger_forecast_late: bool
    at_risk: bool
    matched: list[dict]
    responsible_name: str | None


def _to_out(db: Session, order: CustomerOrder) -> CustomerOrderOut:
    computed = _compute(db, order, today_pl())
    return CustomerOrderOut(
        id=order.id, company_id=order.company_id, name=order.name,
        customer_name=order.customer_name, order_refs=order.order_refs,
        deadline=order.deadline, max_etd=order.max_etd, buffer_days=order.buffer_days,
        responsible_id=order.responsible_id, alert_on_delay=order.alert_on_delay,
        note=order.note, matched_count=len(computed["matched"]),
        earliest_etd=computed["earliest_etd"], latest_eta=computed["latest_eta"],
        departed=computed["departed"], trigger_etd_missed=computed["trigger_etd_missed"],
        trigger_forecast_late=computed["trigger_forecast_late"], at_risk=computed["at_risk"],
        matched=[{"id": c.id, "container_no": c.container_no} for c in computed["matched"]],
        responsible_name=order.responsible.full_name if order.responsible else None,
    )


@router.get("/customer-orders", response_model=list[CustomerOrderOut])
def list_customer_orders(db: Session = Depends(get_db), user: User = care_readers):
    query = scope_company(select(CustomerOrder).order_by(CustomerOrder.id.desc()),
                          CustomerOrder.company_id, user)
    return [_to_out(db, o) for o in db.scalars(query).all()]


@router.get("/customer-orders/responsibles")
def list_responsibles(db: Session = Depends(get_db), user: User = editors):
    """Lekka lista osób do pola „Odpowiedzialny” (audyt UI S10): tylko id + imię
    i nazwisko aktywnych pracowników własnych, też sprzedaży (bez firm zewn.), bez e-maili,
    ról i 2FA. Zakres spółek jak reszta modułu; konta bez spółki (admin) widoczne."""
    query = select(User).where(User.is_active.is_(True),
                               User.role.in_((Role.admin, Role.logistics, Role.purchasing, Role.sales)))
    ids = company_filter_ids(user)
    if ids is not None:  # konto jednej spółki: jej ludzie + konta bez spółki
        query = query.where(or_(User.company_id.in_(ids), User.company_id.is_(None)))
    return [{"id": u.id, "name": u.full_name or u.login}
            for u in db.scalars(query.order_by(User.full_name, User.login))]


@router.post("/customer-orders", response_model=CustomerOrderOut, status_code=201)
def create_customer_order(body: CustomerOrderIn, db: Session = Depends(get_db),
                          user: User = editors):
    resolve_company_id(db, user, body.company_id)
    order = CustomerOrder(**body.model_dump(), created_by_id=user.id)
    db.add(order)
    record_created(db, order, user)
    db.commit()
    return _to_out(db, order)


@router.patch("/customer-orders/{order_id}", response_model=CustomerOrderOut)
def update_customer_order(order_id: int, body: CustomerOrderIn,
                          db: Session = Depends(get_db), user: User = editors):
    order = get_scoped(db, CustomerOrder, order_id, user)
    resolve_company_id(db, user, body.company_id)
    record_changes(db, order, body.model_dump(exclude_unset=True), user)
    db.commit()
    return _to_out(db, order)


@router.delete("/customer-orders/{order_id}", status_code=204)
def delete_customer_order(order_id: int, db: Session = Depends(get_db),
                          user: User = editors):
    order = get_scoped(db, CustomerOrder, order_id, user)
    record(db, entity_type="customer_orders", entity_id=order.id, field="delete",
           old_value=order.name, new_value=None, user=user)
    db.delete(order)
    db.commit()
