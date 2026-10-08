"""Moduł Wiedza (W16): pinezki wiedzy, tematy do omówienia, noty eskalacyjne.

Wiedza jest wspólna dla spółek grupy (operacyjna, nie per spółka), bez partnerów
zewnętrznych (spedytor, agencja celna — ACL-001). Pinezki dodają admin + logistics,
edytuje/usuwa autor albo admin. Noty eskalacyjne adresowane per rola z potwierdzeniem
„przeczytałem" (BulletinAck) i widokiem kto-przeczytał dla edytorów.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..audit import record, record_changes
from ..database import get_db
from ..deps import Editors as editors
from ..deps import InternalReaders as internal_readers
from ..deps import InternalWriters as internal_writers
from ..deps import ViewerOrSales as viewer_or_sales
from ..deps import own_company_id, scope_company, scope_containers
from ..models import (
    BulletinAck,
    Company,
    Container,
    KnowledgeBulletin,
    KnowledgeNote,
    Role,
    TrainingTopic,
    TrainingVote,
    User,
)
from ..notifications import notify
from ..security import PARTNER_ROLES, can_view_all
from ..schemas import (
    BulletinAckOut,
    BulletinIn,
    BulletinOut,
    KnowledgeNoteIn,
    KnowledgeNoteOut,
    TrainingTopicIn,
    TrainingTopicOut,
)

router = APIRouter(prefix="/api/knowledge", tags=["wiedza"])

TOPIC_STATUSES = ("otwarty", "zaplanowany", "omowiony")


def _note_out(note: KnowledgeNote) -> KnowledgeNoteOut:
    out = KnowledgeNoteOut.model_validate(note)
    out.created_by_name = (note.created_by.full_name or note.created_by.login) \
        if note.created_by else ""
    return out


# --- pinezki wiedzy ---

def _own_note(db: Session, note_id: int, user: User) -> KnowledgeNote:
    """ACL-001: pinezkę zmienia/usuwa autor albo admin."""
    note = db.get(KnowledgeNote, note_id)
    if not note:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono.")
    if user.role != Role.admin and note.created_by_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Pinezkę zmienia autor albo admin.")
    return note


@router.get("/notes", response_model=list[KnowledgeNoteOut])
def list_notes(scope_type: str | None = None, scope_key: str | None = None,
               db: Session = Depends(get_db), user: User = internal_readers):
    query = (select(KnowledgeNote).where(KnowledgeNote.is_active)
             .options(selectinload(KnowledgeNote.created_by))
             .order_by(KnowledgeNote.created_at.desc()))
    if scope_type:
        query = query.where(KnowledgeNote.scope_type == scope_type)
    if scope_key:
        query = query.where(KnowledgeNote.scope_key == scope_key)
    return [_note_out(n) for n in db.scalars(query).all()]


@router.post("/notes", response_model=KnowledgeNoteOut, status_code=201)
def create_note(body: KnowledgeNoteIn, db: Session = Depends(get_db),
                user: User = editors):
    note = KnowledgeNote(**body.model_dump(), created_by_id=user.id)
    db.add(note)
    db.flush()
    record(db, entity_type="knowledge_note", entity_id=note.id, field="created",
           old_value=None, new_value=note.title, user=user)
    db.commit()
    return _note_out(note)


@router.patch("/notes/{note_id}", response_model=KnowledgeNoteOut)
def update_note(note_id: int, body: KnowledgeNoteIn,
                db: Session = Depends(get_db), user: User = editors):
    note = _own_note(db, note_id, user)
    for field, value in body.model_dump(exclude_unset=True).items():
        old = getattr(note, field)
        if old != value:
            record(db, entity_type="knowledge_note", entity_id=note.id,
                   field=field, old_value=old, new_value=value, user=user)
            setattr(note, field, value)
    db.commit()
    return _note_out(note)


@router.delete("/notes/{note_id}", status_code=204)
def delete_note(note_id: int, db: Session = Depends(get_db), user: User = editors):
    """Soft-delete: pinezka znika z paneli, historia i audyt zostają."""
    note = _own_note(db, note_id, user)
    note.is_active = False
    record(db, entity_type="knowledge_note", entity_id=note.id, field="is_active",
           old_value="True", new_value="False", user=user)
    db.commit()


# --- tematy do omówienia ---

def _topics_query():
    return (select(TrainingTopic)
            .options(selectinload(TrainingTopic.created_by))
            .order_by(TrainingTopic.created_at.desc()))


def _topic_out(db: Session, topic: TrainingTopic, user: User,
               votes: int | None = None) -> TrainingTopicOut:
    out = TrainingTopicOut.model_validate(topic)
    out.created_by_name = (topic.created_by.full_name or topic.created_by.login) \
        if topic.created_by else ""
    out.votes = votes if votes is not None else (db.scalar(
        select(func.count(TrainingVote.id))
        .where(TrainingVote.topic_id == topic.id)) or 0)
    out.my_vote = db.scalar(select(TrainingVote.id).where(
        TrainingVote.topic_id == topic.id, TrainingVote.user_id == user.id)) is not None
    return out


@router.get("/topics", response_model=list[TrainingTopicOut])
def list_topics(db: Session = Depends(get_db), user: User = internal_readers):
    topics = db.scalars(_topics_query()).all()
    counts = dict(db.execute(
        select(TrainingVote.topic_id, func.count(TrainingVote.id))
        .group_by(TrainingVote.topic_id)).all())
    result = [_topic_out(db, t, user, votes=counts.get(t.id, 0)) for t in topics]
    # ranking: najpierw wg głosów, świeższe wyżej przy remisie
    result.sort(key=lambda t: (-t.votes, -t.id))
    return result


@router.post("/topics", response_model=TrainingTopicOut, status_code=201)
def create_topic(body: TrainingTopicIn, db: Session = Depends(get_db),
                 user: User = internal_writers):
    topic = TrainingTopic(**body.model_dump(), created_by_id=user.id)
    db.add(topic)
    # zgłaszający automatycznie głosuje na swój temat
    db.flush()
    db.add(TrainingVote(topic_id=topic.id, user_id=user.id))
    db.commit()
    return _topic_out(db, topic, user)


@router.post("/topics/{topic_id}/vote", response_model=TrainingTopicOut)
def vote_topic(topic_id: int, db: Session = Depends(get_db), user: User = internal_writers):
    """+1 na temat; idempotentne — ponowny głos niczego nie dubluje."""
    topic = db.get(TrainingTopic, topic_id)
    if not topic:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono.")
    existing = db.scalar(select(TrainingVote).where(
        TrainingVote.topic_id == topic_id, TrainingVote.user_id == user.id))
    if not existing:
        db.add(TrainingVote(topic_id=topic_id, user_id=user.id))
        db.commit()
    return _topic_out(db, topic, user)


@router.patch("/topics/{topic_id}/status", response_model=TrainingTopicOut)
def set_topic_status(topic_id: int, new_status: str,
                     db: Session = Depends(get_db), user: User = editors):
    if new_status not in TOPIC_STATUSES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Status musi być jednym z: {', '.join(TOPIC_STATUSES)}.")
    topic = db.get(TrainingTopic, topic_id)
    if not topic:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono.")
    record_changes(db, topic, {"status": new_status}, user)
    db.commit()
    return _topic_out(db, topic, user)


# --- noty eskalacyjne ---

def _bulletin_out(bulletin: KnowledgeBulletin) -> BulletinOut:
    out = BulletinOut.model_validate(bulletin)
    out.created_by_name = (bulletin.created_by.full_name or bulletin.created_by.login) \
        if bulletin.created_by else ""
    return out


def _bulletin_companies(db: Session, user: User) -> set[int] | None:
    """Spółki, których noty widzi user (noty całej grupy — company_id NULL — widzą wszyscy).
    None = wszystkie (admin / view_all). Partner zewnętrzny nie należy do spółki — widzi noty
    spółek, których kontenery obsługuje (scope_containers)."""
    if can_view_all(user):
        return None
    if user.role in PARTNER_ROLES:
        try:
            return set(db.scalars(scope_containers(select(Container.company_id).distinct(), user)))
        except HTTPException:   # konto partnera bez przypisanej firmy — tylko noty grupy
            return set()
    own = own_company_id(user)
    return {own} if own is not None else set()


def _sees(bulletin: KnowledgeBulletin, companies: set[int] | None) -> bool:
    return bulletin.company_id is None or companies is None or bulletin.company_id in companies


@router.get("/bulletins", response_model=list[BulletinOut])
def list_bulletins(db: Session = Depends(get_db), user: User = viewer_or_sales):
    """Edytorzy widzą wszystkie noty swojej spółki/grupy; pozostali — adresowane do swojej roli."""
    companies = _bulletin_companies(db, user)
    bulletins = [b for b in db.scalars(
        select(KnowledgeBulletin)
        .options(selectinload(KnowledgeBulletin.created_by))
        .order_by(KnowledgeBulletin.created_at.desc())).all() if _sees(b, companies)]
    if user.role not in (Role.admin, Role.logistics):
        bulletins = [b for b in bulletins if user.role.value in (b.roles or [])]
    return [_bulletin_out(b) for b in bulletins]


@router.post("/bulletins", response_model=BulletinOut, status_code=201)
def create_bulletin(body: BulletinIn, db: Session = Depends(get_db),
                    user: User = editors):
    # konto grupowe wybiera spółkę (albo całą grupę); logistyk jednej spółki — zawsze swoją
    company_id = body.company_id if can_view_all(user) else own_company_id(user)
    if company_id is not None and not db.get(Company, company_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono spółki.")
    bulletin = KnowledgeBulletin(title=body.title, body=body.body, roles=body.roles,
                                 company_id=company_id, created_by_id=user.id)
    db.add(bulletin)
    db.flush()
    recipients = [u for u in db.scalars(select(User).where(
        User.role.in_([Role(r) for r in body.roles]), User.is_active)).all()
        if _sees(bulletin, _bulletin_companies(db, u))]
    notify(db, recipients, kind="bulletin",
           title=f"Nota: {body.title}", body=body.body)
    db.commit()
    return _bulletin_out(bulletin)


@router.get("/bulletins/unread", response_model=list[BulletinOut])
def unread_bulletins(db: Session = Depends(get_db), user: User = viewer_or_sales):
    """Noty adresowane do roli usera bez jego potwierdzenia — zasila baner."""
    acked = set(db.scalars(select(BulletinAck.bulletin_id)
                           .where(BulletinAck.user_id == user.id)))
    companies = _bulletin_companies(db, user)
    bulletins = db.scalars(
        select(KnowledgeBulletin)
        .options(selectinload(KnowledgeBulletin.created_by))
        .order_by(KnowledgeBulletin.created_at.asc())).all()
    return [_bulletin_out(b) for b in bulletins
            if b.id not in acked and user.role.value in (b.roles or []) and _sees(b, companies)]


@router.post("/bulletins/{bulletin_id}/ack")
def ack_bulletin(bulletin_id: int, db: Session = Depends(get_db), user: User = viewer_or_sales):
    """„Przeczytałem" — idempotentne, pierwszy read_at zostaje."""
    bulletin = db.get(KnowledgeBulletin, bulletin_id)
    if not bulletin or not _sees(bulletin, _bulletin_companies(db, user)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono.")
    existing = db.scalar(select(BulletinAck).where(
        BulletinAck.bulletin_id == bulletin_id, BulletinAck.user_id == user.id))
    if not existing:
        db.add(BulletinAck(bulletin_id=bulletin_id, user_id=user.id))
        db.commit()
    return {"ok": True}


@router.get("/bulletins/{bulletin_id}/acks", response_model=list[BulletinAckOut])
def bulletin_acks(bulletin_id: int, db: Session = Depends(get_db),
                  user: User = editors):
    """Kto przeczytał / kto nie — wszyscy aktywni adresaci noty z read_at lub bez."""
    bulletin = db.get(KnowledgeBulletin, bulletin_id)
    if not bulletin or not _sees(bulletin, _bulletin_companies(db, user)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono.")
    # konto jednej spółki widzi adresatów tylko swojej spółki (ACL-002 — bez list kont grupy)
    targets = db.scalars(scope_company(select(User).where(
        User.role.in_([Role(r) for r in (bulletin.roles or [])]),
        User.is_active), User.company_id, user).order_by(User.full_name, User.login)).all()
    acks = {a.user_id: a.read_at for a in db.scalars(
        select(BulletinAck).where(BulletinAck.bulletin_id == bulletin_id))}
    return [BulletinAckOut(user_id=u.id, login=u.login, full_name=u.full_name,
                           role=u.role.value, read_at=acks.get(u.id))
            for u in targets if _sees(bulletin, _bulletin_companies(db, u))]
