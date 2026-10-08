"""Awizacja w aplikacji — spedytor z kontem odpowiada na awizację bez linku z maila
(decyzja 2026-10-07: nic bez logowania; przewoźnik = rola forwarder).

Te same reguły co formularze z linku (avizo.apply_stage1 / apply_drivers / apply_proposal):
etap 1 (termin, slot, problem), etap 2 (dane kierowców), propozycja zmiany terminu.
Wysłanie w aplikacji unieważnia link z maila tego etapu — odpowiedź liczy się raz.
Logistyka może odpowiedzieć w imieniu spedytora (np. po telefonie) — wpis z jej kontem."""
import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import avizo_workflow as wf
from ..database import get_db
from ..deps import ForwarderOrEditors as forwarder_or_editors
from ..deps import get_scoped, scope_avizo_requests
from ..models import AvizoChangeProposal, AvizoRequest, AvizoStatus, User, utcnow
from ..security import client_ip
from ..slots import free_slots
from .avizo import (AvizoProposeIn, DriversIn, Stage1In, _container_out, apply_drivers,
                    apply_proposal, apply_stage1)
from .avizo_proposals import _proposal_out

router = APIRouter(prefix="/api/avizo-forwarder", tags=["awizacja"])

_STAGE = {AvizoStatus.SENT_STAGE1: 1, AvizoStatus.SENT_STAGE2: 2}
_OPEN = (AvizoStatus.SENT_STAGE1, AvizoStatus.CONFIRMED_BY_FORWARDER, AvizoStatus.APPROVED_BY_US,
         AvizoStatus.SENT_STAGE2)


def _out(db: Session, req: AvizoRequest) -> dict:
    stage = _STAGE.get(req.status, 0)
    items = wf.stage2_items(db, req) if stage == 2 else req.items
    proposals = db.scalars(select(AvizoChangeProposal).where(AvizoChangeProposal.request_id == req.id)
                           .order_by(AvizoChangeProposal.created_at.desc())).all()
    return {
        "id": req.id, "status": req.status.value, "stage": stage,
        "company": req.company.name if req.company else "",
        "forwarder": req.forwarder.name if req.forwarder else "",
        "note": req.note, "reject_comment": req.reject_comment,
        "created_at": req.created_at.isoformat(),
        "proposals": [_proposal_out(p) for p in proposals],
        "items": [{
            **_container_out(i.container),
            "driver_name": i.container.driver_name, "driver_phone": i.container.driver_phone,
            "truck_no": i.container.truck_no, "trailer_no": i.container.trailer_no,
            "slots": free_slots(db, i.container.warehouse, i.container.notify_date,
                                exclude_container_id=i.container_id) if stage == 1 else [],
        } for i in items],
    }


def _request(db: Session, request_id: int, user: User, expected: AvizoStatus | None = None) -> AvizoRequest:
    req = get_scoped(db, AvizoRequest, request_id, user)
    if expected is not None and req.status != expected:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Ta awizacja nie czeka teraz na tę odpowiedź — odśwież listę.")
    return req


@router.get("")
def my_avizos(db: Session = Depends(get_db), user: User = forwarder_or_editors) -> list[dict]:
    """Otwarte awizacje: spedytor — swoje, logistyka — swoich spółek."""
    query = scope_avizo_requests(select(AvizoRequest).where(AvizoRequest.status.in_(_OPEN))
                                 .order_by(AvizoRequest.created_at.desc()), user)
    return [_out(db, req) for req in db.scalars(query)]


@router.get("/{request_id}")
def one(request_id: int, db: Session = Depends(get_db), user: User = forwarder_or_editors) -> dict:
    """Formularz etapu 1 / 2 w aplikacji (ten sam kształt co z linku); 409 = nic do wysłania."""
    req = _request(db, request_id, user)
    if req.status not in _STAGE:
        raise HTTPException(status.HTTP_409_CONFLICT, {"code": "already_submitted",
                                                      "message": "Awizacja nie czeka na odpowiedź."})
    return {**_out(db, req), "language": req.language}


@router.get("/{request_id}/slots")
def slots(request_id: int, container_id: int, date: datetime.date,
          db: Session = Depends(get_db), user: User = forwarder_or_editors) -> list[dict]:
    req = _request(db, request_id, user)
    item = next((i for i in req.items if i.container_id == container_id), None)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kontener spoza tej awizacji.")
    return free_slots(db, item.container.warehouse, date, exclude_container_id=container_id)


def _who(user: User) -> str:
    return f"w aplikacji ({user.full_name or user.login})"


@router.post("/{request_id}/confirm")
def confirm(request_id: int, body: Stage1In, request: Request, db: Session = Depends(get_db),
            user: User = forwarder_or_editors) -> dict:
    req = _request(db, request_id, user, AvizoStatus.SENT_STAGE1)
    wf.revoke_tokens(db, req, 1)   # link z maila tego etapu przestaje działać
    return apply_stage1(db, req, body, client_ip(request), utcnow(), user,
                        f"etap 1 {_who(user)}")


@router.post("/{request_id}/drivers")
def drivers(request_id: int, body: DriversIn, db: Session = Depends(get_db),
            user: User = forwarder_or_editors) -> dict:
    req = _request(db, request_id, user, AvizoStatus.SENT_STAGE2)
    wf.revoke_tokens(db, req, 2)
    return apply_drivers(db, req, body, user, f"dane kierowców, awizacja #{req.id} {_who(user)}")


@router.post("/{request_id}/propose", status_code=201)
def propose(request_id: int, body: AvizoProposeIn, db: Session = Depends(get_db),
            user: User = forwarder_or_editors) -> dict:
    req = _request(db, request_id, user)
    if req.status not in _OPEN:
        raise HTTPException(status.HTTP_409_CONFLICT, "Awizacja jest zamknięta.")
    return apply_proposal(db, req, body, user)
