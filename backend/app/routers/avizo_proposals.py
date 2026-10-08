"""Awizacja — propozycje zmiany terminu (#59): serializacja i panel logistyki
(/api/avizo-proposals: lista, akceptacja termin+slot, odrzucenie z powodem).
Publiczne zgłoszenie propozycji zostaje w routers/avizo.py (link z tokenem)."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..audit import record
from ..avizo_workflow import book_date_slot
from ..database import get_db
from ..deps import Editors as editors
from ..deps import check_container_access, get_scoped
from ..models import AvizoChangeProposal, AvizoProposalStatus, AvizoRequest, Container, User, utcnow


def _proposal_out(p: AvizoChangeProposal, with_container: bool = False) -> dict:
    out = {
        "id": p.id, "container_id": p.container_id,
        "proposed_date": p.proposed_date.isoformat(),
        "proposed_time": p.proposed_time, "note": p.note,
        "status": p.status.value, "reject_reason": p.reject_reason,
        "created_at": p.created_at.isoformat(),
    }
    if with_container:
        out["container_no"] = p.container.container_no if p.container else ""
        out["current_notify_date"] = (p.container.notify_date.isoformat()
                                      if p.container and p.container.notify_date else None)
        out["forwarder"] = p.request.forwarder.name \
            if p.request and p.request.forwarder else ""
    return out

proposals_router = APIRouter(prefix="/api/avizo-proposals", tags=["awizacja"])


class ProposalRejectIn(BaseModel):
    reason: str = Field(default="", max_length=1000)


def _get_proposal(db: Session, proposal_id: int, user: User) -> AvizoChangeProposal:
    return get_scoped(db, AvizoChangeProposal, proposal_id, user, options=(
        selectinload(AvizoChangeProposal.container),
        selectinload(AvizoChangeProposal.request).selectinload(AvizoRequest.forwarder)))


@proposals_router.get("")
def list_proposals(db: Session = Depends(get_db), user: User = editors,
                   pending_only: bool = True):
    query = (select(AvizoChangeProposal)
             .options(selectinload(AvizoChangeProposal.container),
                      selectinload(AvizoChangeProposal.request)
                      .selectinload(AvizoRequest.forwarder))
             .order_by(AvizoChangeProposal.created_at.desc()))
    if pending_only:
        query = query.where(AvizoChangeProposal.status == AvizoProposalStatus.pending)
    rows = [p for p in db.scalars(query).all()
            if _visible(user, p.container)]
    return [_proposal_out(p, with_container=True) for p in rows]


def _visible(user: User, container: Container) -> bool:
    try:
        check_container_access(user, container)
        return True
    except HTTPException:
        return False


@proposals_router.post("/{proposal_id}/accept")
def accept_proposal(proposal_id: int, db: Session = Depends(get_db),
                    user: User = editors):
    """Akceptacja jednym klikiem: termin (confirm_plan) + proponowana godzina jako slot,
    ze sprawdzeniem zajętości — ta sama ścieżka co zatwierdzenie etapu 1 awizacji."""
    proposal = _get_proposal(db, proposal_id, user)
    if proposal.status != AvizoProposalStatus.pending:
        raise HTTPException(status.HTTP_409_CONFLICT, "Propozycja już rozstrzygnięta.")
    forwarder_name = proposal.request.forwarder.name \
        if proposal.request and proposal.request.forwarder else "?"
    book_date_slot(db, proposal.container, proposal.proposed_date, proposal.proposed_time or "",
                   user, f"akceptacja propozycji zmiany awizacji ({forwarder_name})")
    proposal.status = AvizoProposalStatus.accepted
    proposal.decided_at = utcnow()
    proposal.decided_by_id = user.id
    record(db, entity_type="containers", entity_id=proposal.container_id,
           field="avizo_proposal", old_value="pending", new_value="accepted",
           user=user, note=f"propozycja #{proposal.id} → {proposal.proposed_date}")
    db.commit()
    return _proposal_out(proposal, with_container=True)


@proposals_router.post("/{proposal_id}/reject")
def reject_proposal(proposal_id: int, body: ProposalRejectIn,
                    db: Session = Depends(get_db), user: User = editors):
    """Odrzucenie z powodem — powód wraca na publiczny link awizacji."""
    proposal = _get_proposal(db, proposal_id, user)
    if proposal.status != AvizoProposalStatus.pending:
        raise HTTPException(status.HTTP_409_CONFLICT, "Propozycja już rozstrzygnięta.")
    proposal.status = AvizoProposalStatus.rejected
    proposal.reject_reason = body.reason.strip()
    proposal.decided_at = utcnow()
    proposal.decided_by_id = user.id
    record(db, entity_type="containers", entity_id=proposal.container_id,
           field="avizo_proposal", old_value="pending", new_value="rejected",
           user=user, note=body.reason.strip())
    db.commit()
    return _proposal_out(proposal, with_container=True)
