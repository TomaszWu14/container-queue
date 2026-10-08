# Agencja: potwierdzenie odbioru i draft SAD — PR 1 (obieg ręczny) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Przy paczce faktur operator oznacza „Agencja potwierdziła odbiór”, wgrywa kolejne wersje draftu SAD (PDF) i podejmuje decyzję „akceptuję / do poprawy” z komentarzem — z audytem, bez automatu i bez porównania (to PR 2–4).

**Architecture:** Dwie nowe tabele (`agency_acks` 1:1 z paczką, `sad_drafts` wersjonowane w paczce) + moduł logiki `app/invoices/sad_drafts.py` (bez HTTP poza HTTPException) + router `app/routers/sad_drafts.py` pod paczką faktur (izolacja przez istniejące `_get_batch`). Plik draftu zapisywany jak załącznik kontenera (typ dokumentu „Draft SAD”). Front: komponent `AgencySadSection` pod paczką w `InvoiceBatchesPanel`.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, pytest (+xdist), React + TypeScript, Vitest.

Spec: `docs/superpowers/specs/2026-09-29-agencja-draft-sad-design.md`.

## Global Constraints

- Max **500 linii** na plik (strażnik `scripts/check_file_lengths.py`).
- Teksty UI w **`frontend/src/i18n/features/<funkcja>.ts`** (`defineFeature({ pl, en, pt })`), nie we wspólnych plikach i18n.
- Każda nowa trasa API → wpis w **`tests/permissions.yaml`** (test `test_permissions_matrix`).
- Nowe tabele przez migrację Alembica od jedynej głowy (**`spmat001`**); kolumny NOT NULL w migracji zgodne z modelem (CI „Dryf schematu” na PostgreSQL).
- Uprawnienia jak „Przygotuj maila do agencji”: `PurchasingReaders` (import w `routers/customs.py` jako `docs_senders`).
- Wejście automatu (n8n) i porównanie **poza zakresem** tego PR — ale logika przyjęcia draftu przyjmuje `source` (`manual` / `automation`), żeby PR 4 wywołał ją bez zmian.
- Pełny pytest przed pushem: `python -m pytest tests/ -q -n auto` (z `backend/`); pełny vitest: `npx vitest run` (z `frontend/`).
- Mypy baseline: nowe pliki bez błędów (`db.get(...)` może zwrócić `None` — sprawdzaj).

---

## File Structure

| Plik | Odpowiedzialność |
|---|---|
| `backend/app/models/sad_drafts.py` (nowy) | modele `AgencyAck`, `SadDraft` |
| `backend/app/models/__init__.py` | re-eksport nowego modułu |
| `backend/migrations/versions/sad001_agencja_draft_sad.py` (nowy) | tabele `agency_acks`, `sad_drafts` |
| `backend/app/invoices/sad_drafts.py` (nowy) | logika: potwierdzenie, przyjęcie wersji (dedupe sha256), decyzja, widok |
| `backend/app/routers/sad_drafts.py` (nowy) | 4 trasy HTTP |
| `backend/app/main.py` | rejestracja routera |
| `tests/permissions.yaml` | wpisy 4 tras |
| `backend/tests/test_sad_drafts.py` (nowy) | testy obiegu |
| `frontend/src/types/invoices.ts` | typy `SadDraft`, `AgencySadState` |
| `frontend/src/AgencySadSection.tsx` (nowy) | sekcja „Agencja” pod paczką |
| `frontend/src/InvoiceBatchesPanel.tsx` | osadzenie sekcji |
| `frontend/src/i18n/features/agencja-sad.ts` (nowy) | teksty PL/EN/PT |
| `frontend/src/AgencySadSection.dom.test.tsx` (nowy) | test ekranu |

---

### Task 1: Modele i migracja

**Files:**
- Create: `backend/app/models/sad_drafts.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/migrations/versions/sad001_agencja_draft_sad.py`
- Test: `backend/tests/test_migration_chain.py` (istniejący — ma przejść bez zmian)

**Interfaces:**
- Produces: `AgencyAck(batch_id, acked_at, source, acked_by_id)`, `SadDraft(id, batch_id, version, attachment_id, sha256, source, decision, comment, created_by_id, created_at, decided_by_id, decided_at)`; stałe `SOURCES = ("manual", "automation")`, `DECISIONS = ("pending", "accepted", "rejected")`.

- [ ] **Step 1: Model**

`backend/app/models/sad_drafts.py`:
```python
"""Wymiana z agencją celną po wysłaniu faktur (spec 2026-09-29-agencja-draft-sad): potwierdzenie
odbioru paczki i wersjonowane drafty SAD z decyzją operatora. Agencja nie loguje się do
aplikacji — dane wprowadza operator albo automat (n8n) przez to samo wejście."""
import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .enums import utcnow
from .transport import Attachment

__all__ = ["DECISIONS", "SOURCES", "AgencyAck", "SadDraft"]

SOURCES = ("manual", "automation")
DECISIONS = ("pending", "accepted", "rejected")


class AgencyAck(Base):
    """Agencja potwierdziła odbiór paczki faktur (1:1 z paczką)."""
    __tablename__ = "agency_acks"
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("invoice_batches.id", ondelete="CASCADE"), primary_key=True)
    acked_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    source: Mapped[str] = mapped_column(String(12), default="manual")
    acked_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class SadDraft(Base):
    """Wersja draftu SAD od agencji; plik = załącznik kontenera (typ „Draft SAD”)."""
    __tablename__ = "sad_drafts"
    __table_args__ = (UniqueConstraint("batch_id", "version", name="uq_sad_drafts_batch_version"),
                      UniqueConstraint("batch_id", "sha256", name="uq_sad_drafts_batch_sha"))
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("invoice_batches.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    attachment_id: Mapped[int] = mapped_column(ForeignKey("attachments.id"), index=True)
    sha256: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(12), default="manual")
    decision: Mapped[str] = mapped_column(String(12), default="pending",
                                          server_default=text("'pending'"))
    comment: Mapped[str] = mapped_column(String(1000), default="", server_default=text("''"))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    attachment: Mapped[Attachment] = relationship()
```

W `backend/app/models/__init__.py` dopisz (alfabetycznie, przed `sp_materials`):
```python
from .sad_drafts import *  # noqa: F401,F403
```

- [ ] **Step 2: Migracja**

`backend/migrations/versions/sad001_agencja_draft_sad.py`:
```python
"""Agencja celna: potwierdzenie odbioru paczki faktur i wersjonowane drafty SAD.

Revision ID: sad001
Revises: spmat001
"""
import sqlalchemy as sa
from alembic import op

revision = "sad001"
down_revision = "spmat001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agency_acks",
        sa.Column("batch_id", sa.Integer,
                  sa.ForeignKey("invoice_batches.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("acked_at", sa.DateTime, nullable=False),
        sa.Column("source", sa.String(12), nullable=False),
        sa.Column("acked_by_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_table(
        "sad_drafts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("batch_id", sa.Integer,
                  sa.ForeignKey("invoice_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("attachment_id", sa.Integer, sa.ForeignKey("attachments.id"), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("source", sa.String(12), nullable=False),
        sa.Column("decision", sa.String(12), nullable=False, server_default="pending"),
        sa.Column("comment", sa.String(1000), nullable=False, server_default=""),
        sa.Column("created_by_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("decided_by_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("batch_id", "version", name="uq_sad_drafts_batch_version"),
        sa.UniqueConstraint("batch_id", "sha256", name="uq_sad_drafts_batch_sha"),
    )
    op.create_index("ix_sad_drafts_batch_id", "sad_drafts", ["batch_id"])
    op.create_index("ix_sad_drafts_attachment_id", "sad_drafts", ["attachment_id"])


def downgrade() -> None:
    op.drop_index("ix_sad_drafts_attachment_id", table_name="sad_drafts")
    op.drop_index("ix_sad_drafts_batch_id", table_name="sad_drafts")
    op.drop_table("sad_drafts")
    op.drop_table("agency_acks")
```

- [ ] **Step 3: Łańcuch migracji i import**

Run (z `backend/`): `python -c "import app.main" && python -m pytest tests/test_migration_chain.py tests/test_dev_schema_shim.py -q`
Expected: PASS (jedna głowa `sad001`; nowe tabele nie wymagają wpisu w dev-shimie — create_all zakłada brakujące tabele).

- [ ] **Step 4: Commit**
```bash
git add backend/app/models/sad_drafts.py backend/app/models/__init__.py backend/migrations/versions/sad001_agencja_draft_sad.py
git commit -m "feat(agencja): modele potwierdzenia odbioru i draftów SAD + migracja sad001"
```

---

### Task 2: Logika obiegu (`app/invoices/sad_drafts.py`)

**Files:**
- Create: `backend/app/invoices/sad_drafts.py`
- Test: `backend/tests/test_sad_drafts.py`

**Interfaces:**
- Consumes: `AgencyAck`, `SadDraft`, `DECISIONS`, `SOURCES` (Task 1); `InvoiceBatch`, `Attachment`, `DocumentType`, `User` (`app.models`); `audit.record`; `uploads_dir`, `safe_filename`, `commit_with_file` (`app.routers.forwarding_files`).
- Produces:
  - `acknowledge(db, batch, user: User | None, source: str) -> AgencyAck` — idempotentne (drugie wywołanie zwraca istniejące, nie nadpisuje).
  - `add_draft(db, batch, filename: str, content: bytes, user: User | None, source: str) -> tuple[SadDraft, bool]` — `bool` = utworzono nową wersję; duplikat pliku (ten sam sha256) → istniejąca wersja, `False`; nowa wersja oznacza też potwierdzenie odbioru. Commituje.
  - `decide(db, batch, draft_id: int, decision: str, comment: str, user: User) -> SadDraft` — 404 obcy draft; 409 gdy istnieje nowsza wersja; 422 `rejected` bez komentarza albo nieznana decyzja. Commituje.
  - `state(db, batch) -> dict` — `{"ack": {...} | None, "drafts": [...]}` (najnowsza wersja pierwsza).

- [ ] **Step 1: Test (czerwony)**

`backend/tests/test_sad_drafts.py`:
```python
"""Agencja celna — PR 1 (spec 2026-09-29-agencja-draft-sad): potwierdzenie odbioru, wersje
draftu SAD (duplikat pliku bez nowej wersji), decyzja z blokadą starej wersji, audyt."""
import io

from pypdf import PdfWriter
from sqlalchemy import select

from app.config import settings
from app.models import AuditLog, InvoiceBatch, SadDraft
from tests.test_invoices_api import _container


def _pdf(marker: str = "v1") -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_metadata({"/Title": marker})          # inna treść = inny sha256
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _batch(client, headers, db_session, no="MSDU0806613") -> tuple[int, int]:
    cid = _container(client, headers, no=no)
    batch = InvoiceBatch(container_id=cid)
    db_session.add(batch)
    db_session.commit()
    return cid, batch.id


def _upload(client, headers, bid, content, name="SAD.pdf"):
    return client.post(f"/api/invoice-batches/{bid}/sad-drafts", headers=headers,
                       files={"file": (name, io.BytesIO(content), "application/pdf")})


def test_ack_then_versions_dedupe_and_state(client, admin_headers, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))
    cid, bid = _batch(client, admin_headers, db_session)
    state = client.get(f"/api/invoice-batches/{bid}/sad-drafts", headers=admin_headers).json()
    assert state == {"ack": None, "drafts": []}

    assert client.post(f"/api/invoice-batches/{bid}/agency-ack", headers=admin_headers).status_code == 200
    first = client.post(f"/api/invoice-batches/{bid}/agency-ack", headers=admin_headers).json()
    assert first["ack"]["source"] == "manual"                       # idempotentne

    r1 = _upload(client, admin_headers, bid, _pdf("v1"))
    assert r1.status_code == 201 and r1.json()["created"] is True
    dup = _upload(client, admin_headers, bid, _pdf("v1"), name="kopia.pdf")
    assert dup.status_code == 200 and dup.json()["created"] is False  # ten sam plik
    r2 = _upload(client, admin_headers, bid, _pdf("v2"))
    state = r2.json()["state"]
    assert [d["version"] for d in state["drafts"]] == [2, 1]
    assert state["drafts"][0]["decision"] == "pending" and state["drafts"][0]["attachment_id"]
    logs = db_session.scalars(select(AuditLog).where(AuditLog.field == "sad_draft")).all()
    assert len(logs) == 2 and all(log.entity_id == cid for log in logs)


def test_decision_rules(client, admin_headers, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))
    _, bid = _batch(client, admin_headers, db_session)
    v1 = _upload(client, admin_headers, bid, _pdf("v1")).json()["draft"]["id"]
    url = f"/api/invoice-batches/{bid}/sad-drafts/{v1}/decision"
    bad = client.post(url, headers=admin_headers, json={"decision": "rejected", "comment": " "})
    assert bad.status_code == 422                                    # „do poprawy” wymaga uwag
    ok = client.post(url, headers=admin_headers,
                     json={"decision": "rejected", "comment": "CN 62101092 zamiast 62101098"})
    assert ok.status_code == 200 and ok.json()["drafts"][0]["decision"] == "rejected"

    _upload(client, admin_headers, bid, _pdf("v2"))
    stale = client.post(url, headers=admin_headers, json={"decision": "accepted", "comment": ""})
    assert stale.status_code == 409                                  # jest nowsza wersja
    v2 = db_session.scalar(select(SadDraft).where(SadDraft.version == 2)).id
    done = client.post(f"/api/invoice-batches/{bid}/sad-drafts/{v2}/decision",
                       headers=admin_headers, json={"decision": "accepted", "comment": ""})
    assert done.status_code == 200 and done.json()["drafts"][0]["decision"] == "accepted"


def test_upload_rejects_non_pdf_and_foreign_draft(client, admin_headers, db_session,
                                                  monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))
    _, bid = _batch(client, admin_headers, db_session)
    r = client.post(f"/api/invoice-batches/{bid}/sad-drafts", headers=admin_headers,
                    files={"file": ("sad.xlsx", io.BytesIO(b"x"), "application/octet-stream")})
    assert r.status_code == 422
    _, other = _batch(client, admin_headers, db_session, no="MSCU1234565")
    v1 = _upload(client, admin_headers, other, _pdf("v1")).json()["draft"]["id"]
    r = client.post(f"/api/invoice-batches/{bid}/sad-drafts/{v1}/decision",
                    headers=admin_headers, json={"decision": "accepted", "comment": ""})
    assert r.status_code == 404
```

Run: `python -m pytest tests/test_sad_drafts.py -q`
Expected: FAIL (404 — tras jeszcze nie ma).

- [ ] **Step 2: Logika**

`backend/app/invoices/sad_drafts.py`:
```python
"""Obieg wymiany z agencją po wysłaniu faktur: potwierdzenie odbioru, wersje draftu SAD,
decyzja. Jedno wejście dla operatora (router) i automatu (n8n, PR 4) — `source`."""
import hashlib
import secrets

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from ..models import (DECISIONS, SOURCES, AgencyAck, Attachment, DocumentType, InvoiceBatch,
                      SadDraft, User, utcnow)
from ..routers.forwarding_files import commit_with_file, safe_filename, uploads_dir

DOC_TYPE = "Draft SAD"


def _check_source(source: str) -> None:
    if source not in SOURCES:
        raise ValueError(f"nieznane źródło: {source}")


def acknowledge(db: Session, batch: InvoiceBatch, user: User | None, source: str) -> AgencyAck:
    _check_source(source)
    ack = db.get(AgencyAck, batch.id)
    if ack is not None:
        return ack
    ack = AgencyAck(batch_id=batch.id, acked_at=utcnow(), source=source,
                    acked_by_id=user.id if user else None)
    db.add(ack)
    audit.record(db, entity_type="containers", entity_id=batch.container_id, field="agency_ack",
                 old_value=None, new_value=source, user=user,
                 note=f"agencja potwierdziła odbiór faktur (paczka #{batch.id})")
    return ack


def _doc_type(db: Session) -> DocumentType:
    doc_type = db.scalar(select(DocumentType).where(DocumentType.name == DOC_TYPE))
    if doc_type is None:
        doc_type = DocumentType(name=DOC_TYPE, is_active=True, is_required=False)
        db.add(doc_type)
        db.flush()
    return doc_type


def add_draft(db: Session, batch: InvoiceBatch, filename: str, content: bytes,
              user: User | None, source: str) -> tuple[SadDraft, bool]:
    """Nowa wersja draftu SAD; ten sam plik ponownie (np. ponowienie automatu) → istniejąca
    wersja bez duplikatu. Przyjęcie draftu = także potwierdzenie odbioru."""
    _check_source(source)
    digest = hashlib.sha256(content).hexdigest()
    existing = db.scalar(select(SadDraft).where(SadDraft.batch_id == batch.id,
                                                SadDraft.sha256 == digest))
    if existing is not None:
        return existing, False
    acknowledge(db, batch, user, source)
    version = (db.scalar(select(func.max(SadDraft.version))
                         .where(SadDraft.batch_id == batch.id)) or 0) + 1
    safe = safe_filename(filename, "draft_SAD.pdf")
    stored = f"{batch.container_id}_{secrets.token_hex(8)}_{safe}"
    attachment = Attachment(container_id=batch.container_id, filename=safe, stored_name=stored,
                            content_type="application/pdf", size=len(content),
                            uploaded_by_id=user.id if user else None,
                            document_type_id=_doc_type(db).id)
    db.add(attachment)
    db.flush()
    draft = SadDraft(batch_id=batch.id, version=version, attachment_id=attachment.id,
                     sha256=digest, source=source, created_by_id=user.id if user else None)
    db.add(draft)
    audit.record(db, entity_type="containers", entity_id=batch.container_id, field="sad_draft",
                 old_value=None, new_value=f"v{version}", user=user,
                 note=f"draft SAD v{version} od agencji ({source}, {safe})")
    commit_with_file(db, uploads_dir() / stored, content)
    return draft, True


def decide(db: Session, batch: InvoiceBatch, draft_id: int, decision: str, comment: str,
           user: User) -> SadDraft:
    draft = db.get(SadDraft, draft_id)
    if draft is None or draft.batch_id != batch.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie ma takiego draftu SAD w tej paczce.")
    if decision not in DECISIONS or decision == "pending":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Decyzja: accepted albo rejected.")
    comment = (comment or "").strip()
    if decision == "rejected" and not comment:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Przy „do poprawy” wpisz, co agencja ma poprawić.")
    newest = db.scalar(select(func.max(SadDraft.version)).where(SadDraft.batch_id == batch.id))
    if draft.version != newest:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Jest nowsza wersja draftu (v{newest}) — oceń najnowszą.")
    old = draft.decision
    draft.decision, draft.comment = decision, comment[:1000]
    draft.decided_by_id, draft.decided_at = user.id, utcnow()
    audit.record(db, entity_type="containers", entity_id=batch.container_id,
                 field="sad_decision", old_value=old, new_value=decision, user=user,
                 note=f"draft SAD v{draft.version}: {decision}" + (f" — {comment}" if comment else ""))
    db.commit()
    return draft


def _name(db: Session, user_id: int | None) -> str | None:
    user = db.get(User, user_id) if user_id else None
    return (user.full_name or user.login) if user else None


def state(db: Session, batch: InvoiceBatch) -> dict:
    ack = db.get(AgencyAck, batch.id)
    drafts = db.scalars(select(SadDraft).where(SadDraft.batch_id == batch.id)
                        .order_by(SadDraft.version.desc())).all()
    return {
        "ack": None if ack is None else {"at": ack.acked_at.isoformat(), "source": ack.source,
                                         "by": _name(db, ack.acked_by_id)},
        "drafts": [{"id": d.id, "version": d.version, "attachment_id": d.attachment_id,
                    "filename": d.attachment.filename, "source": d.source,
                    "decision": d.decision, "comment": d.comment,
                    "created_at": d.created_at.isoformat(),
                    "decided_at": d.decided_at.isoformat() if d.decided_at else None,
                    "decided_by": _name(db, d.decided_by_id)} for d in drafts],
    }
```

`User.full_name` i `User.login` istnieją (`backend/app/models/dictionaries.py`).

- [ ] **Step 3: Commit** (testy zazielenieją się w Task 3 — trasy)
```bash
git add backend/app/invoices/sad_drafts.py backend/tests/test_sad_drafts.py
git commit -m "feat(agencja): logika potwierdzenia, wersji draftu SAD i decyzji"
```

---

### Task 3: Trasy HTTP + macierz uprawnień

**Files:**
- Create: `backend/app/routers/sad_drafts.py`
- Modify: `backend/app/main.py` (lista importów routerów i `app.include_router`)
- Modify: `tests/permissions.yaml`
- Test: `backend/tests/test_sad_drafts.py` (z Task 2), `backend/tests/test_permissions_matrix.py`

**Interfaces:**
- Consumes: `acknowledge`, `add_draft`, `decide`, `state` (Task 2); `_get_batch` (`app.routers.invoices`); `docs_senders` (`app.routers.customs`); `read_upload_capped` (`app.routers.forwarding_files`).
- Produces (HTTP, używane przez front w Task 4):
  - `GET  /api/invoice-batches/{batch_id}/sad-drafts` → `state`
  - `POST /api/invoice-batches/{batch_id}/agency-ack` → `state`
  - `POST /api/invoice-batches/{batch_id}/sad-drafts` (multipart `file`, PDF) → `201 {"draft": {...}, "created": true, "state": {...}}` albo `200 … "created": false`
  - `POST /api/invoice-batches/{batch_id}/sad-drafts/{draft_id}/decision` body `{"decision": "accepted"|"rejected", "comment": str}` → `state`

- [ ] **Step 1: Router**

`backend/app/routers/sad_drafts.py`:
```python
"""Agencja celna po wysłaniu faktur: potwierdzenie odbioru i drafty SAD (spec
2026-09-29-agencja-draft-sad, PR 1 — obieg ręczny). Uprawnienia jak szkic maila do agencji."""
from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..invoices import sad_drafts as flow
from ..models import User
from .customs import docs_senders
from .forwarding_files import read_upload_capped
from .invoices import _get_batch

router = APIRouter(prefix="/api", tags=["faktury"])


class DecisionIn(BaseModel):
    decision: str = Field(max_length=12)
    comment: str = Field(default="", max_length=1000)


@router.get("/invoice-batches/{batch_id}/sad-drafts")
def sad_state(batch_id: int, db: Session = Depends(get_db), user: User = docs_senders) -> dict:
    return flow.state(db, _get_batch(db, batch_id, user))


@router.post("/invoice-batches/{batch_id}/agency-ack")
def agency_ack(batch_id: int, db: Session = Depends(get_db), user: User = docs_senders) -> dict:
    batch = _get_batch(db, batch_id, user)
    flow.acknowledge(db, batch, user, "manual")
    db.commit()
    return flow.state(db, batch)


@router.post("/invoice-batches/{batch_id}/sad-drafts", status_code=201)
def upload_sad_draft(batch_id: int, file: UploadFile, response: Response,
                     db: Session = Depends(get_db), user: User = docs_senders) -> dict:
    batch = _get_batch(db, batch_id, user)
    name = file.filename or "draft_SAD.pdf"
    if not name.lower().endswith(".pdf"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Draft SAD: wymagany plik PDF.")
    content = read_upload_capped(file, settings.max_upload_mb, "Draft SAD")
    draft, created = flow.add_draft(db, batch, name, content, user, "manual")
    if not created:
        response.status_code = status.HTTP_200_OK
    current = flow.state(db, batch)
    return {"draft": next(d for d in current["drafts"] if d["id"] == draft.id),
            "created": created, "state": current}


@router.post("/invoice-batches/{batch_id}/sad-drafts/{draft_id}/decision")
def sad_decision(batch_id: int, draft_id: int, body: DecisionIn,
                 db: Session = Depends(get_db), user: User = docs_senders) -> dict:
    batch = _get_batch(db, batch_id, user)
    flow.decide(db, batch, draft_id, body.decision, body.comment, user)
    return flow.state(db, batch)
```

W `backend/app/main.py`: w bloku `from .routers import (` dopisz `sad_drafts,` (kolejność alfabetyczna jak sąsiedzi), a przy rejestracji: `app.include_router(sad_drafts.router)`.

- [ ] **Step 2: Testy obiegu**

Run: `python -m pytest tests/test_sad_drafts.py -q`
Expected: PASS (3 testy).

- [ ] **Step 3: Macierz uprawnień**

Run: `python ../tests/gen_permissions.py` (z `backend/`) — wypisze 4 wpisy. Wklej je do `tests/permissions.yaml` w sekcji `# --- invoice_agency ---` (pod `agency-mail.eml`); wartości `'?'` rozstrzygnij tak jak `GET /api/invoice-batches/{batch_id}/agency-mail.eml` (admin/logistics/purchasing dostęp, reszta 403).

Run: `python -m pytest tests/test_permissions_matrix.py -q`
Expected: PASS.

- [ ] **Step 4: Commit**
```bash
git add backend/app/routers/sad_drafts.py backend/app/main.py tests/permissions.yaml
git commit -m "feat(agencja): trasy potwierdzenia odbioru, draftów SAD i decyzji + macierz uprawnień"
```

---

### Task 4: Front — sekcja „Agencja” pod paczką faktur

**Files:**
- Modify: `frontend/src/types/invoices.ts` (dopisz typy na końcu sekcji faktur)
- Create: `frontend/src/AgencySadSection.tsx`
- Modify: `frontend/src/InvoiceBatchesPanel.tsx` (osadzenie pod listą dokumentów paczki)
- Create: `frontend/src/i18n/features/agencja-sad.ts`
- Test: `frontend/src/AgencySadSection.dom.test.tsx`

**Interfaces:**
- Consumes: trasy z Task 3; `api`, `downloadFile`, `errorMessage` (`./api`); `formatDateTime` (`./dates`); `useT` (`./i18n`).
- Produces: `export function AgencySadSection({ batchId }: { batchId: number })`.

- [ ] **Step 1: Typy**

W `frontend/src/types/invoices.ts` dopisz:
```ts
export interface SadDraft {
  id: number
  version: number
  attachment_id: number
  filename: string
  source: 'manual' | 'automation'
  decision: 'pending' | 'accepted' | 'rejected'
  comment: string
  created_at: string
  decided_at: string | null
  decided_by: string | null
}

export interface AgencySadState {
  ack: { at: string; source: 'manual' | 'automation'; by: string | null } | null
  drafts: SadDraft[]   // najnowsza wersja pierwsza
}
```

- [ ] **Step 2: Teksty**

`frontend/src/i18n/features/agencja-sad.ts`:
```ts
// Agencja celna po wysłaniu faktur: potwierdzenie odbioru i draft SAD (AgencySadSection.tsx)
import { defineFeature } from '../feature'

export default defineFeature({
  pl: {
    sadTitle: 'Agencja', sadAcked: 'Potwierdziła odbiór', sadNotAcked: 'Brak potwierdzenia odbioru',
    sadAckBtn: 'Agencja potwierdziła', sadUpload: 'Wgraj draft SAD', sadDuplicate: 'Ten plik już jest (v{v}).',
    sadShowPdf: 'PDF', sadAccept: 'Akceptuję', sadReject: 'Do poprawy',
    sadCommentLabel: 'Co agencja ma poprawić', sadSend: 'Zapisz', sadCancel: 'Anuluj',
    sadDecision_pending: 'do oceny', sadDecision_accepted: 'zaakceptowany', sadDecision_rejected: 'do poprawy',
    sadSource_manual: 'ręcznie', sadSource_automation: 'automat',
  },
  en: {
    sadTitle: 'Customs agency', sadAcked: 'Receipt confirmed', sadNotAcked: 'Receipt not confirmed',
    sadAckBtn: 'Agency confirmed', sadUpload: 'Upload draft SAD', sadDuplicate: 'This file is already here (v{v}).',
    sadShowPdf: 'PDF', sadAccept: 'Accept', sadReject: 'Needs changes',
    sadCommentLabel: 'What the agency should fix', sadSend: 'Save', sadCancel: 'Cancel',
    sadDecision_pending: 'to review', sadDecision_accepted: 'accepted', sadDecision_rejected: 'needs changes',
    sadSource_manual: 'manual', sadSource_automation: 'automation',
  },
  pt: {
    sadTitle: 'Despachante', sadAcked: 'Receção confirmada', sadNotAcked: 'Receção não confirmada',
    sadAckBtn: 'Despachante confirmou', sadUpload: 'Carregar rascunho DAU', sadDuplicate: 'Este ficheiro já existe (v{v}).',
    sadShowPdf: 'PDF', sadAccept: 'Aceitar', sadReject: 'A corrigir',
    sadCommentLabel: 'O que o despachante deve corrigir', sadSend: 'Guardar', sadCancel: 'Cancelar',
    sadDecision_pending: 'a rever', sadDecision_accepted: 'aceite', sadDecision_rejected: 'a corrigir',
    sadSource_manual: 'manual', sadSource_automation: 'automático',
  },
})
```

- [ ] **Step 3: Test (czerwony)**

`frontend/src/AgencySadSection.dom.test.tsx`:
```tsx
// @vitest-environment jsdom
// Strażnik (2026-09-29, spec agencja-draft-sad PR 1): potwierdzenie, wersje draftu, decyzja.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('./i18n', () => ({ useT: () => (key: string) => key }))
const get = vi.fn(), post = vi.fn(), upload = vi.fn()
vi.mock('./api', () => ({
  api: { get: (p: string) => get(p), post: (p: string, b: unknown) => post(p, b),
         upload: (p: string, f: File) => upload(p, f) },
  downloadFile: vi.fn(), errorMessage: String,
}))

import { AgencySadSection } from './AgencySadSection'

const draft = (version: number, decision = 'pending') => ({
  id: version, version, attachment_id: 10 + version, filename: `SAD_v${version}.pdf`,
  source: 'manual', decision, comment: '', created_at: '2026-09-29T14:05:00',
  decided_at: null, decided_by: null })

afterEach(() => { cleanup(); get.mockReset(); post.mockReset(); upload.mockReset() })

describe('AgencySadSection', () => {
  it('bez potwierdzenia: przycisk potwierdza odbiór', async () => {
    get.mockResolvedValue({ ack: null, drafts: [] })
    post.mockResolvedValue({ ack: { at: '2026-09-29T14:05:00', source: 'manual', by: 'Anna' }, drafts: [] })
    render(<AgencySadSection batchId={7} />)
    fireEvent.click(await screen.findByRole('button', { name: 'sadAckBtn' }))
    await waitFor(() => expect(post).toHaveBeenCalledWith('/api/invoice-batches/7/agency-ack', {}))
    expect(await screen.findByText(/sadAcked/)).toBeTruthy()
  })

  it('decyzja tylko dla najnowszej wersji; „do poprawy” wymaga komentarza', async () => {
    get.mockResolvedValue({ ack: { at: '2026-09-29T14:05:00', source: 'manual', by: null },
                            drafts: [draft(2), draft(1, 'rejected')] })
    post.mockResolvedValue({ ack: null, drafts: [draft(2, 'rejected'), draft(1, 'rejected')] })
    render(<AgencySadSection batchId={7} />)
    expect(await screen.findAllByRole('button', { name: 'sadAccept' })).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: 'sadReject' }))
    const save = screen.getByRole('button', { name: 'sadSend' }) as HTMLButtonElement
    expect(save.disabled).toBe(true)                                  // pusty komentarz
    fireEvent.change(screen.getByLabelText('sadCommentLabel'), { target: { value: 'zły CN' } })
    fireEvent.click(save)
    await waitFor(() => expect(post).toHaveBeenCalledWith(
      '/api/invoice-batches/7/sad-drafts/2/decision', { decision: 'rejected', comment: 'zły CN' }))
  })
})
```

Run (z `frontend/`): `npx vitest run src/AgencySadSection`
Expected: FAIL (brak modułu `./AgencySadSection`).

- [ ] **Step 4: Komponent**

`frontend/src/AgencySadSection.tsx`:
```tsx
// Sekcja „Agencja” pod paczką faktur (spec 2026-09-29-agencja-draft-sad, PR 1): potwierdzenie
// odbioru, wersje draftu SAD z maila agencji, decyzja „akceptuję / do poprawy” (najnowsza wersja).
import { useCallback, useEffect, useState } from 'react'
import { api, downloadFile, errorMessage } from './api'
import { formatDateTime } from './dates'
import { useT } from './i18n'
import type { AgencySadState, SadDraft } from './types'

interface UploadResult { draft: SadDraft; created: boolean; state: AgencySadState }

export function AgencySadSection({ batchId }: { batchId: number }) {
  const t = useT()
  const base = `/api/invoice-batches/${batchId}`
  const [state, setState] = useState<AgencySadState | null>(null)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [rejecting, setRejecting] = useState(false)
  const [comment, setComment] = useState('')

  const load = useCallback(() => {
    api.get<AgencySadState>(`${base}/sad-drafts`).then(setState).catch(err => setError(errorMessage(err)))
  }, [base])
  useEffect(() => { load() }, [load])

  const act = async (fn: () => Promise<AgencySadState>) => {
    setBusy(true)
    setError('')
    try {
      setState(await fn())
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  const upload = (file: File) => act(async () => {
    const res = await api.upload<UploadResult>(`${base}/sad-drafts`, file)
    setNote(res.created ? '' : t('sadDuplicate').replace('{v}', String(res.draft.version)))
    return res.state
  })
  const decide = (draft: SadDraft, decision: 'accepted' | 'rejected') => act(async () => {
    const next = await api.post<AgencySadState>(`${base}/sad-drafts/${draft.id}/decision`,
      { decision, comment: decision === 'rejected' ? comment.trim() : '' })
    setRejecting(false)
    setComment('')
    return next
  })

  if (!state) return error ? <p className="error">{error}</p> : null
  const newest = state.drafts[0]
  return (
    <div className="agency-sad" style={{ marginTop: 8 }}>
      <b>{t('sadTitle')}</b>{' · '}
      {state.ack
        ? <span>✓ {t('sadAcked')} {formatDateTime(state.ack.at)} ({t(`sadSource_${state.ack.source}`)}{state.ack.by ? `, ${state.ack.by}` : ''})</span>
        : <span className="muted">{t('sadNotAcked')}</span>}
      <div className="row" style={{ gap: 8, marginTop: 6 }}>
        {!state.ack && (
          <button className="btn small secondary" disabled={busy}
                  onClick={() => act(() => api.post<AgencySadState>(`${base}/agency-ack`, {}))}>
            {t('sadAckBtn')}
          </button>
        )}
        <label className="btn small secondary" style={{ cursor: 'pointer' }}>
          {t('sadUpload')}
          <input type="file" accept="application/pdf" style={{ display: 'none' }} disabled={busy}
                 onChange={e => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = '' }} />
        </label>
      </div>
      {note && <p className="muted" role="status">{note}</p>}
      {error && <p className="error">{error}</p>}
      {state.drafts.length > 0 && (
        <ul style={{ margin: '6px 0 0 18px', fontSize: 14 }}>
          {state.drafts.map(d => (
            <li key={d.id}>
              v{d.version} · {formatDateTime(d.created_at)} · <span className="badge">{t(`sadDecision_${d.decision}`)}</span>
              {' '}<button type="button" className="btn small secondary"
                      onClick={() => downloadFile(`/api/attachments/${d.attachment_id}/download`, d.filename)}>
                {t('sadShowPdf')}</button>
              {d.comment && <span className="muted"> · „{d.comment}”</span>}
              {d.decided_by && <span className="muted"> · {d.decided_by}</span>}
            </li>
          ))}
        </ul>
      )}
      {newest && newest.decision === 'pending' && !rejecting && (
        <div className="row" style={{ gap: 8, marginTop: 6 }}>
          <button className="btn small" disabled={busy} onClick={() => decide(newest, 'accepted')}>{t('sadAccept')}</button>
          <button className="btn small secondary" disabled={busy} onClick={() => setRejecting(true)}>{t('sadReject')}</button>
        </div>
      )}
      {newest && rejecting && (
        <div className="row" style={{ gap: 8, marginTop: 6 }}>
          <label>{t('sadCommentLabel')}
            <input value={comment} onChange={e => setComment(e.target.value)} maxLength={1000} />
          </label>
          <button className="btn small" disabled={busy || !comment.trim()} onClick={() => decide(newest, 'rejected')}>{t('sadSend')}</button>
          <button className="btn small secondary" onClick={() => { setRejecting(false); setComment('') }}>{t('sadCancel')}</button>
        </div>
      )}
    </div>
  )
}
```

`formatDateTime` jest eksportowany z `frontend/src/dates.ts` (używa go już `InvoiceBatchesPanel.tsx`).

- [ ] **Step 5: Osadzenie w panelu**

W `frontend/src/InvoiceBatchesPanel.tsx`: import `import { AgencySadSection } from './AgencySadSection'`; zaraz po zamknięciu listy dokumentów paczki (`</ul>` po `batch.jobs.map(...)`) dodaj:
```tsx
          {/* po wysłaniu faktur (jest Excel) — odpowiedź agencji: potwierdzenie i draft SAD */}
          {batch.attachment_id && <AgencySadSection batchId={batch.id} />}
```

- [ ] **Step 6: Testy frontu**

Run (z `frontend/`): `npx tsc -b --noEmit && npx vitest run`
Expected: PASS (w tym nowy `AgencySadSection.dom.test.tsx`, strażniki a11y/i18n).

- [ ] **Step 7: Commit**
```bash
git add frontend/src/types/invoices.ts frontend/src/AgencySadSection.tsx frontend/src/AgencySadSection.dom.test.tsx frontend/src/InvoiceBatchesPanel.tsx frontend/src/i18n/features/agencja-sad.ts
git commit -m "feat(agencja): sekcja Agencja pod paczką faktur — potwierdzenie, drafty SAD, decyzja"
```

---

### Task 5: Weryfikacja całości i PR

- [ ] **Step 1:** z `backend/`: `python -m pytest tests/ -q -n auto` → wszystko PASS (lokalnie na Windows pomiń `tests/test_healthcheck_watchdog.py::test_po_zawieszeniu_sigterm_potem_sigkill` — `SIGKILL` nie istnieje na Windows).
- [ ] **Step 2:** z repo: `python scripts/check_file_lengths.py` → OK; `cd backend && python -m ruff check .` → czysto.
- [ ] **Step 3:** `git fetch origin main && git merge origin/main` (merge, nie rebase), ponownie `test_migration_chain`.
- [ ] **Step 4:** push gałęzi `claude/agencja-draft-sad-pr1`, PR na `main` z opisem: zakres PR 1 ze spec, wyniki testów.

---

## Kolejne PR-y (osobne plany)
2. Odczyt draftu SAD + porównanie ↔ faktury + okno porównania (kolumny `parsed`/`comparison` JSON w `sad_drafts`).
3. Szkic `.eml` odpowiedzi „Akceptuję” / „Do poprawy” (reużycie `app/eml.py`, adresaci jak `invoice_agency.py`) + stan odprawy na kafelku kolejki („SAD do akceptacji” / „SAD OK”).
4. Wejście automatu (n8n): endpoint z tokenem automatyzacji → `add_draft(..., source="automation")`; nieznany kontener → 404; draft dla paczki bez wygenerowanego Excela → przyjęty z ostrzeżeniem w odpowiedzi.
5. Dostrojenie odczytu do przykładowego draftu SAD od Deltaa.
