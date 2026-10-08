"""Awizacja do spedycji (dwuetapowa): wysyłka z kolejki, publiczny formularz etapu 1
(potwierdzenie dostaw) i etapu 2 (dane kierowców) po jednorazowych tokenach,
informacja do magazynu (np. DLT). Przejścia stanów: app/avizo_workflow.py."""
from ..models import today_pl
import datetime
import logging
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import avizo_workflow as wf
from ..audit import record, record_changes
from ..config import settings
from ..csrf import origin_allowed
from ..database import get_db
from ..date_pl import date_pl
from ..deps import Editors as editors
from ..deps import check_container_access
from ..iso6346 import normalize
from ..html_templates import render
from ..mail_html import table_context
from ..models import (
    AvizoChangeProposal,
    AvizoRequest,
    AvizoStatus,
    Container,
    DeliveryConfirmation,
    Forwarder,
    User,
    Warehouse,
)
from ..notifications import company_watchers, notify, send_html_email
from ..security import ApiRateLimiter, client_ip
from ..slots import free_slots, windows
from .avizo_proposals import _proposal_out, proposals_router  # noqa: F401 — re-eksport (main.py)

router = APIRouter(prefix="/api/avizo", tags=["awizacja"])
logger = logging.getLogger(__name__)

# --- ochrona endpointów publicznych (bez logowania, dostęp po tokenie) ---

PUBLIC_LIMIT_PER_MINUTE = 30
_public_limiter = ApiRateLimiter()   # osobny od globalnego — klucz avz:{ip}


def public_limit(request: Request) -> None:
    retry = _public_limiter.hit(f"avz:{client_ip(request)}", PUBLIC_LIMIT_PER_MINUTE)
    if retry is not None:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "Za dużo żądań. Spróbuj ponownie za chwilę.",
                            headers={"Retry-After": str(int(retry))})


def json_origin_guard(request: Request) -> None:
    """Zamiast tokenu CSRF (brak ciasteczek = brak ambientnych poświadczeń): tylko JSON
    (formularz HTML z obcej strony nie wyśle application/json bez preflightu CORS)
    i Origin/Referer — jeśli jest — musi wskazywać nasz host."""
    if not request.headers.get("content-type", "").lower().startswith("application/json"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Wymagany application/json.")
    source = request.headers.get("origin") or request.headers.get("referer")
    if source and not origin_allowed(request, source):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Niedozwolone źródło żądania.")


PUBLIC = [Depends(public_limit)]
PUBLIC_POST = [Depends(public_limit), Depends(json_origin_guard)]


class AvizoSendIn(BaseModel):
    container_ids: list[int] = Field(min_length=1)
    note: str = ""
    send_warehouse_info: bool = False


def _warehouse_email_html(containers: list[Container], operator: User, note: str) -> str:
    ordered = sorted(containers, key=lambda x: (x.notify_date or datetime.date.max, x.id))
    table = table_context(ordered, ["unload", "container", "supplier", "vessel", "transport",
                                    "orders", "warehouse", "delivery", "rf"])
    return render("mail/warehouse_info.html", note=note,
                  operator=operator.full_name or operator.login, **table)


def base_url(request: Request) -> str:
    return (settings.public_base_url or str(request.base_url)).rstrip("/")


@router.post("/send")
def send_avizo(body: AvizoSendIn, request: Request,
               db: Session = Depends(get_db), user: User = editors):
    """Etap 1: zlecenie awizacji per (spedytor, spółka) + mail z jednorazowym linkiem.
    Mail idzie w tle (MAIL_BACKEND); wynik dostawy — w logu maili zlecenia."""
    containers = db.scalars(
        select(Container)
        .options(selectinload(Container.supplier), selectinload(Container.order),
                 selectinload(Container.warehouse), selectinload(Container.forwarder))
        .where(Container.id.in_(body.container_ids))).all()
    if not containers:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono kontenerów.")
    for c in containers:
        check_container_access(user, c)

    base = base_url(request)
    # grupujemy po (spedytor, spółka): jeden spedytor obsługujący kilka spółek
    # dostaje osobny token/formularz per spółka (separacja spółek, poprawne watcher-y)
    by_group: dict[tuple[int | None, int], list[Container]] = {}
    for c in containers:
        by_group.setdefault((c.forwarder_id, c.company_id), []).append(c)

    sent, missing_email, no_forwarder, failed = [], [], 0, []
    for (forwarder_id, company_id), items in by_group.items():
        forwarder = db.get(Forwarder, forwarder_id) if forwarder_id else None
        if not forwarder:
            no_forwarder += len(items)
            continue
        if not forwarder.email:
            missing_email.append(forwarder.name)
            continue
        req = wf.create_and_send(db, company_id=company_id, forwarder=forwarder,
                                 containers=items, note=body.note, user=user, base=base)
        sent.append({"forwarder": forwarder.name, "email": forwarder.email,
                     "containers": len(items), "request_id": req.id})

    warehouse_info = []
    if body.send_warehouse_info:
        by_warehouse: dict[int | None, list[Container]] = {}
        for c in containers:
            by_warehouse.setdefault(c.warehouse_id, []).append(c)
        for warehouse_id, items in by_warehouse.items():
            warehouse = db.get(Warehouse, warehouse_id) if warehouse_id else None
            if not warehouse:
                continue
            if not warehouse.email:
                missing_email.append(warehouse.name)
                continue
            subject = f"Informacja o dostawach / Incoming deliveries — {len(items)} kont. → {warehouse.name}"
            try:
                send_html_email([warehouse.email], subject,
                                _warehouse_email_html(items, user, body.note),
                                reply_to=user.email or settings.smtp_from)
            except Exception as exc:  # noqa: BLE001 — nie przerywamy pozostałych wysyłek
                logger.warning("awizacja: mail do magazynu %s nie wyszedł", warehouse.name,
                               exc_info=True)
                failed.append({"warehouse": warehouse.name, "error": str(exc)})
                continue
            record(db, entity_type="avizo_requests", entity_id=warehouse.id,
                   field="warehouse_info",
                   old_value=None, new_value=f"{warehouse.name} <{warehouse.email}>",
                   user=user, note=f"paczka {len(items)} kont.")
            warehouse_info.append({"warehouse": warehouse.name, "email": warehouse.email,
                                   "containers": len(items)})
    db.commit()
    return {"sent": sent, "warehouse_info": warehouse_info, "failed": failed,
            "missing_email": missing_email, "no_forwarder": no_forwarder}


_hash_token = wf.hash_token   # zgodność wsteczna (importy w testach)


def _get_request(db: Session, token: str) -> AvizoRequest:
    """Zlecenie po tokenie etapu 1 — dla starych ścieżek (propozycje, sloty), także po wysłaniu."""
    return wf.lookup_token(db, token, 1, allow_used=True).request


def _public_head(req: AvizoRequest, tok, stage: int) -> dict:
    """Wspólna część odpowiedzi publicznej — bez danych innych spedycji/firm i bez dostawcy."""
    return {
        "stage": stage, "request_id": req.id, "status": req.status.value,
        "language": req.language, "forwarder": req.forwarder.name if req.forwarder else "",
        "company": req.company.name if req.company else "",
        "created_at": req.created_at.isoformat(), "expires_at": tok.expires_at.isoformat(),
        "note": req.note,
    }


def _container_out(c: Container) -> dict:
    return {
        "container_id": c.id, "container_no": normalize(c.container_no),
        "vessel": c.vessel or "",
        "notify_date": c.notify_date.isoformat() if c.notify_date else None,
        "warehouse": c.warehouse.name if c.warehouse else "",
        "slot_time": c.slot_time,
    }


# --- etap 1: potwierdzenie dostaw ---

@router.get("/{token}", dependencies=PUBLIC)
def get_avizo(token: str, db: Session = Depends(get_db)):
    """Formularz etapu 1 (dostęp po tokenie z e-maila, bez logowania) — tylko do odczytu
    + wolne sloty. Po wysłaniu: 409 „formularz już wysłany” bez danych."""
    tok = wf.lookup_token(db, token, 1)
    avizo = tok.request
    proposals = db.scalars(
        select(AvizoChangeProposal)
        .where(AvizoChangeProposal.request_id == avizo.id)
        .order_by(AvizoChangeProposal.created_at.desc())).all()
    db.commit()   # utrwala ewentualną adopcję starego linku
    return {
        **_public_head(avizo, tok, 1),
        "reject_comment": avizo.reject_comment,
        "confirmed_at": avizo.confirmed_at.isoformat() if avizo.confirmed_at else None,
        "proposals": [_proposal_out(p) for p in proposals],
        "items": [{
            **_container_out(item.container),
            "planning_status": item.container.planning_status.value,
            # #13: wolne okna na dzień awizacji (puste = magazyn bez slotów)
            "slots": free_slots(db, item.container.warehouse, item.container.notify_date,
                                exclude_container_id=item.container_id),
        } for item in avizo.items],
    }


@router.get("/{token}/slots", dependencies=PUBLIC)
def avizo_slots(token: str, container_id: int, date: datetime.date,
                db: Session = Depends(get_db)):
    """Wolne sloty dla kontenera z tego zaproszenia na wskazany dzień (zmiana daty w formularzu)."""
    avizo = _get_request(db, token)
    item = next((i for i in avizo.items if i.container_id == container_id), None)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kontener spoza tej awizacji.")
    return free_slots(db, item.container.warehouse, date, exclude_container_id=container_id)


_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class Stage1ItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")   # etap 1 NIE przyjmuje danych kierowcy
    container_id: int
    decision: Literal["confirmed", "date_change", "problem"]
    proposed_date: datetime.date | None = None
    slot_time: str = Field(default="", max_length=5)
    comment: str = Field(default="", max_length=1000)

    @field_validator("slot_time")
    @classmethod
    def _slot(cls, value: str) -> str:
        value = value.strip()
        if value and not _HHMM.match(value):
            raise ValueError("Slot w formacie HH:MM.")
        return value


class Stage1In(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[Stage1ItemIn] = Field(min_length=1)


def _same_containers(given: list[int], expected: set[int]) -> None:
    if len(given) != len(set(given)) or set(given) != expected:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Formularz musi zawierać każdy kontener zlecenia dokładnie raz.")


@router.post("/{token}", dependencies=PUBLIC_POST)
def confirm_avizo(token: str, body: Stage1In, request: Request, db: Session = Depends(get_db)):
    """Etap 1: decyzja per kontener (potwierdzam / zmiana terminu / problem). Jednorazowo —
    odpowiedzi czekają na zatwierdzenie przez logistykę (dopiero wtedy zmieniają plan)."""
    tok = wf.lookup_token(db, token, 1)
    used_at = wf.claim_token(db, tok)   # atomowo, w tej transakcji (błąd niżej = rollback)
    return apply_stage1(db, tok.request, body, client_ip(request), used_at, None,
                        f"formularz etapu 1 ({tok.request.forwarder.name})")


def apply_stage1(db: Session, avizo: AvizoRequest, body: Stage1In, ip: str,
                 used_at: datetime.datetime, user: User | None, note: str) -> dict:
    """Etap 1 — wspólne dla formularza z linku i awizacji w aplikacji (spedytor z kontem)."""
    items = {i.container_id: i for i in avizo.items}
    _same_containers([e.container_id for e in body.items], set(items))
    today = today_pl()
    claimed: dict[tuple, int] = {}
    for entry in body.items:
        c = items[entry.container_id].container
        day = entry.proposed_date if entry.decision == "date_change" else c.notify_date
        if entry.decision == "date_change" and (day is None or day < today):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"{c.container_no}: podaj nowy termin (nie z przeszłości).")
        if entry.decision == "problem" and not entry.comment.strip():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"{c.container_no}: opisz problem w komentarzu.")
        slot = entry.slot_time if entry.decision != "problem" else ""
        if slot and (slot != c.slot_time or day != c.notify_date):
            # wolne miejsca minus te zajęte wcześniej w TYM formularzu (rezerwacja przy zatwierdzeniu)
            key = (c.warehouse_id, day, slot)
            free = next((s["free"] for s in free_slots(db, c.warehouse, day, c.id)
                         if s["time"] == slot), 0)
            if free - claimed.get(key, 0) <= 0:
                raise HTTPException(status.HTTP_409_CONFLICT, {
                    "code": "slot_taken",
                    "message": f"Slot {slot} dnia {day} dla {c.container_no} jest już zajęty."})
            claimed[key] = claimed.get(key, 0) + 1
        db.add(DeliveryConfirmation(
            request_id=avizo.id, container_id=c.id, decision=entry.decision,
            proposed_date=day if entry.decision == "date_change" else None,
            proposed_time=slot, comment=entry.comment.strip(), submit_ip=ip))
    avizo.confirmed_at = used_at
    wf.transition(db, avizo, AvizoStatus.CONFIRMED_BY_FORWARDER, user, note=note)
    problems = sum(e.decision == "problem" for e in body.items)
    changes = sum(e.decision == "date_change" for e in body.items)
    notify(db, company_watchers(db, avizo.company_id), kind="avizo",
           title=f"{avizo.forwarder.name}: odpowiedź na awizację #{avizo.id} "
                 f"({len(body.items)} kont., zmiany terminu: {changes}, problemy: {problems})",
           body="Do zatwierdzenia w panelu Awizacje.", exclude_user_id=user.id if user else None)
    db.commit()
    return {"ok": True, "total": len(body.items), "date_changes": changes, "problems": problems}


# --- etap 2: dane kierowców ---

_PLATE = re.compile(r"^[A-Z0-9]{4,10}$")


def _phone(value: str) -> str:
    """E.164 albo polski 9-cyfrowy numer → +48…; zwraca postać znormalizowaną."""
    digits = re.sub(r"[\s().-]", "", value or "")
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    if re.fullmatch(r"\d{9}", digits):
        digits = "+48" + digits
    if not re.fullmatch(r"\+[1-9]\d{7,14}", digits):
        raise ValueError("Telefon w formacie +48 600 000 000 (E.164).")
    return digits


def _plate(value: str, required: bool = True) -> str:
    plate = re.sub(r"[\s-]", "", value or "").upper()
    if not plate and not required:
        return ""
    if not _PLATE.match(plate):
        raise ValueError("Numer rejestracyjny: 4–10 liter/cyfr.")
    return plate


class DriverItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    container_id: int
    driver_name: str = Field(min_length=2, max_length=160)
    driver_phone: str = Field(max_length=40)
    truck_no: str = Field(max_length=40)
    trailer_no: str = Field(default="", max_length=40)
    driver_id_no: str = Field(default="", max_length=60)   # opcjonalny

    _v_phone = field_validator("driver_phone")(lambda cls, v: _phone(v))
    _v_truck = field_validator("truck_no")(lambda cls, v: _plate(v))
    _v_trailer = field_validator("trailer_no")(lambda cls, v: _plate(v, required=False))


class DriversIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[DriverItemIn] = Field(min_length=1)


@router.get("/driver/{token}", dependencies=PUBLIC)
def get_driver_form(token: str, db: Session = Depends(get_db)):
    """Formularz etapu 2 — kontenery zatwierdzone w etapie 1 (bez istniejących danych osobowych)."""
    tok = wf.lookup_token(db, token, 2)
    avizo = tok.request
    return {**_public_head(avizo, tok, 2),
            "items": [_container_out(i.container) for i in wf.stage2_items(db, avizo)]}


@router.post("/driver/{token}", dependencies=PUBLIC_POST)
def submit_drivers(token: str, body: DriversIn, db: Session = Depends(get_db)):
    """Etap 2: dane kierowców → Container.driver_* (audyt maskuje telefon/dowód). Jednorazowo."""
    tok = wf.lookup_token(db, token, 2)
    wf.claim_token(db, tok)   # atomowo, w tej transakcji (błąd niżej = rollback)
    return apply_drivers(db, tok.request, body, None,
                         f"formularz kierowców, awizacja #{tok.request.id} ({tok.request.forwarder.name})")


def apply_drivers(db: Session, avizo: AvizoRequest, body: DriversIn, user: User | None,
                  note: str) -> dict:
    """Etap 2 — wspólne dla formularza z linku i awizacji w aplikacji."""
    items = {i.container_id: i for i in wf.stage2_items(db, avizo)}
    _same_containers([e.container_id for e in body.items], set(items))
    for entry in body.items:
        updates = {"driver_name": entry.driver_name.strip(), "driver_phone": entry.driver_phone,
                   "truck_no": entry.truck_no, "trailer_no": entry.trailer_no,
                   "driver_id_no": entry.driver_id_no.strip()}
        record_changes(db, items[entry.container_id].container,
                       {k: v for k, v in updates.items() if v}, user=user, note=note)
    wf.transition(db, avizo, AvizoStatus.DRIVERS_SUBMITTED, user, note=note)
    notify(db, company_watchers(db, avizo.company_id), kind="avizo",
           title=f"{avizo.forwarder.name}: dane kierowców — awizacja #{avizo.id} "
                 f"({len(body.items)} kont.)",
           body="Dane kierowców widoczne przy kontenerach w kolejce.",
           exclude_user_id=user.id if user else None)
    db.commit()
    return {"ok": True, "total": len(body.items)}


# --- #59 samoobsługa zmiany awizacji (propozycje innego terminu) ---

class AvizoProposeIn(BaseModel):
    container_id: int
    date: datetime.date
    time: str = Field(default="", max_length=5)   # HH:MM lub puste
    note: str = Field(default="", max_length=1000)


@router.post("/{token}/propose", status_code=201, dependencies=PUBLIC_POST)
def propose_change(token: str, body: AvizoProposeIn, db: Session = Depends(get_db)):
    """Dostawca/spedycja proponuje inny dzień/godzinę na publicznym linku awizacji."""
    return apply_proposal(db, _get_request(db, token), body, None)


def apply_proposal(db: Session, avizo: AvizoRequest, body: AvizoProposeIn,
                   user: User | None) -> dict:
    """Propozycja zmiany terminu — wspólne dla linku i awizacji w aplikacji."""
    allowed = {item.container_id: item for item in avizo.items}
    item = allowed.get(body.container_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "Kontener nie należy do tej awizacji.")
    if body.date < today_pl():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Data nie może być z przeszłości.")
    time = body.time.strip()
    if time:  # walidacja HH:MM — publiczny endpoint, nie przyjmujemy dowolnego tekstu
        try:
            datetime.time.fromisoformat(time[:5])
        except ValueError:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "Podaj godzinę w formacie HH:MM.") from None
        wins = windows(item.container.warehouse)   # jak etap 1: tylko okna magazynu
        if wins and time[:5] not in wins:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"Godzina poza oknami rozładunku magazynu: {', '.join(wins)}.")
    proposal = AvizoChangeProposal(
        request_id=avizo.id, container_id=body.container_id,
        proposed_date=body.date, proposed_time=time[:5], note=body.note.strip())
    db.add(proposal)
    db.flush()
    record(db, entity_type="containers", entity_id=body.container_id,
           field="avizo_proposal", old_value=None,
           new_value=f"{body.date.isoformat()} {time}".strip(), user=user,
           note=f"propozycja zmiany awizacji ({avizo.forwarder.name})")
    notify(db, company_watchers(db, avizo.company_id), kind="avizo",
           title=f"{avizo.forwarder.name}: propozycja zmiany awizacji "
                 f"{item.container.container_no} → {date_pl(body.date)}"
                 + (f" {time}" if time else ""),
           body=body.note, container_id=body.container_id,
           exclude_user_id=user.id if user else None)
    db.commit()
    return {"ok": True, "id": proposal.id}
