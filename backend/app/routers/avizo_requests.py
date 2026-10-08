"""Panel „Awizacje”: lista zleceń awizacji ze statusami, szczegóły (odpowiedzi etapu 1,
tokeny bez hashy, log maili) i akcje: zatwierdź / odrzuć / unieważnij / wyślij ponownie / anuluj.
Izolacja spółek: scope_company (lista) i get_scoped (szczegóły/akcje)."""
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import avizo_workflow as wf
from ..database import get_db
from ..deps import Editors as editors
from ..deps import get_scoped, scope_company
from ..models import (
    AvizoFormToken,
    AvizoItem,
    AvizoMailLog,
    AvizoRequest,
    AvizoStatus,
    User,
)
from .avizo import base_url

router = APIRouter(prefix="/api/avizo-requests", tags=["awizacja"])

_LOAD = (selectinload(AvizoRequest.forwarder), selectinload(AvizoRequest.company),
         selectinload(AvizoRequest.items).selectinload(AvizoItem.container))


def _dt(value):
    return value.isoformat() if value else None


def _summary(req: AvizoRequest, last_mail: AvizoMailLog | None) -> dict:
    return {
        "id": req.id, "status": req.status.value, "language": req.language,
        "forwarder_id": req.forwarder_id,
        "forwarder": req.forwarder.name if req.forwarder else "",
        "company_id": req.company_id, "company": req.company.name if req.company else "",
        "containers": [i.container.container_no for i in req.items],
        "created_at": _dt(req.created_at), "confirmed_at": _dt(req.confirmed_at),
        "approved_at": _dt(req.approved_at), "closed_at": _dt(req.closed_at),
        "reject_comment": req.reject_comment, "note": req.note,
        "last_mail": {"status": last_mail.status, "stage": last_mail.stage,
                      "error": last_mail.error, "sent_at": _dt(last_mail.sent_at)}
        if last_mail else None,
    }


def _last_mails(db: Session, ids: list[int]) -> dict[int, AvizoMailLog]:
    out: dict[int, AvizoMailLog] = {}
    if ids:
        for log in db.scalars(select(AvizoMailLog).where(AvizoMailLog.request_id.in_(ids))
                              .order_by(AvizoMailLog.id)):
            out[log.request_id] = log
    return out


@router.get("")
def list_requests(status: AvizoStatus | None = None, forwarder_id: int | None = None,
                  limit: int = Query(200, ge=1, le=1000),
                  db: Session = Depends(get_db), user: User = editors):
    query = select(AvizoRequest).options(*_LOAD).order_by(AvizoRequest.id.desc()).limit(limit)
    query = scope_company(query, AvizoRequest.company_id, user)
    if status is not None:
        query = query.where(AvizoRequest.status == status)
    if forwarder_id is not None:
        query = query.where(AvizoRequest.forwarder_id == forwarder_id)
    rows = db.scalars(query).all()
    mails = _last_mails(db, [r.id for r in rows])
    return [_summary(r, mails.get(r.id)) for r in rows]


def _get(db: Session, request_id: int, user: User) -> AvizoRequest:
    return get_scoped(db, AvizoRequest, request_id, user, options=_LOAD)


def _detail(db: Session, req: AvizoRequest) -> dict:
    mails = db.scalars(select(AvizoMailLog).where(AvizoMailLog.request_id == req.id)
                       .order_by(AvizoMailLog.id)).all()
    tokens = db.scalars(select(AvizoFormToken).where(AvizoFormToken.request_id == req.id)
                        .order_by(AvizoFormToken.id)).all()
    answers = {c.container_id: c for c in wf.latest_confirmations(db, req)}
    return {
        **_summary(req, mails[-1] if mails else None),
        "items": [{
            "container_id": i.container_id, "container_no": i.container.container_no,
            "notify_date": _dt(i.container.notify_date), "slot_time": i.container.slot_time,
            "confirmed": i.confirmed,
            "driver_submitted": bool(i.container.driver_name),
            "answer": {"decision": a.decision, "proposed_date": _dt(a.proposed_date),
                       "slot_time": a.proposed_time, "comment": a.comment,
                       "submitted_at": _dt(a.submitted_at)}
            if (a := answers.get(i.container_id)) else None,
        } for i in req.items],
        # tokeny BEZ hashy — tylko metadane (etap, ważność, użycie, unieważnienie)
        "tokens": [{"id": t.id, "stage": t.stage, "created_at": _dt(t.created_at),
                    "expires_at": _dt(t.expires_at), "used_at": _dt(t.used_at),
                    "revoked_at": _dt(t.revoked_at)} for t in tokens],
        "mails": [{"id": m.id, "stage": m.stage, "kind": m.kind, "recipients": m.recipients,
                   "cc": m.cc, "backend": m.backend, "status": m.status,
                   "attempts": m.attempts, "error": m.error, "sent_at": _dt(m.sent_at)}
                  for m in mails],
    }


@router.get("/{request_id}")
def get_request(request_id: int, db: Session = Depends(get_db), user: User = editors):
    return _detail(db, _get(db, request_id, user))


class RejectIn(BaseModel):
    comment: str = Field(min_length=3, max_length=2000)


@router.post("/{request_id}/approve")
def approve(request_id: int, request: Request, db: Session = Depends(get_db),
            user: User = editors):
    req = _get(db, request_id, user)
    wf.approve(db, req, user, base_url(request))
    return _detail(db, req)


@router.post("/{request_id}/reject")
def reject(request_id: int, body: RejectIn, request: Request,
           db: Session = Depends(get_db), user: User = editors):
    req = _get(db, request_id, user)
    wf.reject(db, req, user, body.comment.strip(), base_url(request))
    return _detail(db, req)


@router.post("/{request_id}/revoke")
def revoke(request_id: int, db: Session = Depends(get_db), user: User = editors):
    req = _get(db, request_id, user)
    wf.revoke(db, req, user)
    return _detail(db, req)


@router.post("/{request_id}/resend")
def resend(request_id: int, request: Request, stage: int = Query(ge=1, le=2),
           db: Session = Depends(get_db), user: User = editors):
    req = _get(db, request_id, user)
    wf.resend(db, req, stage, user, base_url(request))
    return _detail(db, req)


@router.post("/{request_id}/cancel")
def cancel(request_id: int, db: Session = Depends(get_db), user: User = editors):
    req = _get(db, request_id, user)
    wf.cancel(db, req, user)
    return _detail(db, req)
