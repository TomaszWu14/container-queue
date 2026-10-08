"""#38 plaster 2 — asystent wiedzy (kontenery + materiały), 100% lokalny (Ollama).

Wzór: najpierw fakty z bazy (z izolacją per rola — scope_containers,
materiały tylko dla ról z dostępem do master daty), potem mały model tekstowy tylko
formułuje odpowiedź z tych faktów. Bez OLLAMA_URL zwracamy same fakty (answer=None) —
dalej użyteczne, a serwer 4 GB nie musi trzymać modelu.
"""
import json
import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from .. import llm
from ..config import settings
from ..database import get_db
from ..deps import Viewer as viewer
from ..deps import scope_containers
from ..invoices.uom import normalize_ref
from ..models import Container, Material, Role, User
from ..rate_limit import ApiRateLimiter
from .containers_common import hidden_fields

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/assistant", tags=["asystent"])
ask_limiter = ApiRateLimiter()   # audyt AI-002: pytania per użytkownik na minutę

MATERIAL_ROLES = (Role.admin, Role.logistics, Role.purchasing)   # jak GET /api/materials
MAX_HITS = 5
_CONTAINER_NO = re.compile(r"\b([A-Z]{4})\s?(\d{7})\b")
_SYSTEM = ("Jesteś asystentem systemu logistycznego TIMPORYE. Odpowiadasz po polsku, krótko, "
           "WYŁĄCZNIE na podstawie FAKTÓW (JSON) podanych w pytaniu. Jeśli faktów brak albo "
           "nie odpowiadają na pytanie — powiedz wprost, że w systemie tego nie ma. Nie zgaduj.")


class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=500)


def _val(v):
    return getattr(v, "value", v)


# klucz faktu → pole ContainerOut; maskowanie przez hidden_fields (jedno źródło z kartą/listą)
_FACT_FIELD = {
    "kontener": "container_no", "status": "status", "tranzyt": "is_transit", "statek": "vessel",
    "etd": "etd", "eta": "eta", "awizacja": "notify_date", "odprawa": "customs_status",
    "dokumenty": "document_status", "zakupy": "purchasing_status", "dostawca": "supplier_name",
    "magazyn": "warehouse_name", "port": "port_name",
}


def _container_fact(c: Container, user: User) -> dict:
    # audyt AI-001: fakty idą do odpowiedzi JSON wprost — pola ukryte dla roli (np. dostawca dla
    # magazynu i agencji celnej) nie mogą tu wyciec
    hidden = hidden_fields(user)
    fact = {
        "kontener": c.container_no, "status": _val(c.status), "tranzyt": c.is_transit,
        "statek": c.vessel or None, "etd": str(c.etd) if c.etd else None,
        "eta": str(c.eta) if c.eta else None,
        "awizacja": str(c.notify_date) if c.notify_date else None,
        "odprawa": _val(c.customs_status), "dokumenty": _val(c.document_status),
        "zakupy": _val(c.purchasing_status),
        "dostawca": c.supplier.name if c.supplier else None,
        "magazyn": c.warehouse.name if c.warehouse else None,
        "port": c.port.name if c.port else None,
    }
    return {k: v for k, v in fact.items() if _FACT_FIELD[k] not in hidden}


def _material_fact(m: Material) -> dict:
    return {"ref": m.ref_code, "nazwa_pl": m.name_pl, "nazwa_en": m.name_en, "ean": m.ean or None,
            "rodzina": m.family or None, "jm": m.base_uom or None, "cn": m.tariff_cn or None,
            "sent": m.sent, "kody_dostawcy": m.supplier_codes or None}


def gather_facts(db: Session, user: User, question: str) -> dict:
    upper = question.upper()
    numbers = {a + b for a, b in _CONTAINER_NO.findall(upper)}
    containers = []
    if numbers:
        containers = db.scalars(scope_containers(
            select(Container).options(selectinload(Container.supplier),
                                      selectinload(Container.warehouse),
                                      selectinload(Container.port))
            .where(Container.container_no.in_(numbers)), user).limit(MAX_HITS)).all()

    materials = []
    if user.role in MATERIAL_ROLES:
        tokens = [t for t in re.split(r"[\s,;?!]+", question) if len(t) >= 3]
        norms = {normalize_ref(t) for t in tokens} - {""} - numbers
        # ponytail: nazwy tylko dla słów ≥5 znaków (odsiewa „jaki”, „gdzie”); FTS gdy zacznie mylić
        words = [t for t in tokens if len(t) >= 5 and normalize_ref(t) not in numbers]
        conds = [Material.ref_norm.in_(norms), Material.ean.in_(norms)] if norms else []
        conds += [Material.name_pl.ilike(f"%{w}%") for w in words]
        conds += [Material.name_en.ilike(f"%{w}%") for w in words]
        if conds:
            materials = db.scalars(select(Material).where(Material.is_active, or_(*conds))
                                   .order_by(Material.ref_code).limit(MAX_HITS)).all()

    return {"kontenery": [_container_fact(c, user) for c in containers],
            "materialy": [_material_fact(m) for m in materials]}


@router.post("/ask")
def ask(body: AskIn, db: Session = Depends(get_db), user: User = viewer) -> dict:
    limit = settings.assistant_rate_limit_per_minute
    retry = ask_limiter.hit(f"user:{user.id}", limit) if limit > 0 else None
    if retry is not None:
        raise HTTPException(429, "Za dużo pytań do asystenta — spróbuj za chwilę.",
                            headers={"Retry-After": str(int(retry))})
    facts = gather_facts(db, user, body.question)
    answer = None
    if llm.is_configured() and (facts["kontenery"] or facts["materialy"]):
        prompt = f"FAKTY:\n{json.dumps(facts, ensure_ascii=False)}\n\nPYTANIE: {body.question}"
        try:
            answer = llm.chat(settings.assistant_model, prompt, system=_SYSTEM,
                              purpose="assistant").strip() or None
        except llm.LLMBusy as exc:   # slot zajęty → szybka odmowa zamiast wątku w kolejce
            raise HTTPException(503, llm.BUSY_MSG) from exc
        except Exception as exc:  # noqa: BLE001 — model padł/timeout: fakty i tak zwracamy
            logger.warning("asystent: %s", exc)
    return {"answer": answer, "facts": facts, "ai": llm.is_configured()}
