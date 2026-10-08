"""Moduł Wiedza (W16): pinezki wiedzy, tematy szkoleniowe, noty eskalacyjne."""
import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .dictionaries import User
from .enums import utcnow

# --- Moduł Wiedza (W16): pinezki wiedzy, tematy szkoleniowe, noty eskalacyjne ---

class KnowledgeNote(Base):
    """Pinezka wiedzy przypięta do kontekstu (ekran, port, dostawca, materiał…).

    Wiedza jest globalna (operacyjna, nie per spółka) — widoczna dla wszystkich
    zalogowanych; edycja tylko admin/logistics. Soft-delete przez is_active.
    """
    __tablename__ = "knowledge_notes"
    __table_args__ = (Index("ix_knowledge_scope", "scope_type", "scope_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    # 'screen' | 'port' | 'supplier' | 'customer' | 'material' | 'document_type' | 'process'
    scope_type: Mapped[str] = mapped_column(String(30))
    scope_key: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")     # markdown-lite
    url: Mapped[str] = mapped_column(String(500), default="")  # artykuł / YouTube (link, nie embed)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    created_by: Mapped[User | None] = relationship()


class TrainingTopic(Base):
    """Temat „do omówienia" zgłoszony z panelu wiedzy; głosowanie +1 (1 głos/user)."""
    __tablename__ = "training_topics"
    id: Mapped[int] = mapped_column(primary_key=True)
    scope_type: Mapped[str] = mapped_column(String(30), default="")
    scope_key: Mapped[str] = mapped_column(String(120), default="")
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    # otwarty / zaplanowany / omowiony — zmienia admin/logistics
    status: Mapped[str] = mapped_column(String(20), default="otwarty")
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    created_by: Mapped[User | None] = relationship()


class TrainingVote(Base):
    """Głos „+1" na temat — unikalność pilnuje 1 głosu per user."""
    __tablename__ = "training_votes"
    __table_args__ = (UniqueConstraint("topic_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("training_topics.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)


class KnowledgeBulletin(Base):
    """Nota eskalacyjna do wskazanych ról — baner do potwierdzenia „przeczytałem"."""
    __tablename__ = "knowledge_bulletins"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    roles: Mapped[list] = mapped_column(JSON, default=list)  # lista wartości Role (str)
    # spółka adresatów; NULL = cała grupa (noty sprzed migracji bull001 też)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True,
                                                   index=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    created_by: Mapped[User | None] = relationship()


class BulletinAck(Base):
    """Potwierdzenie przeczytania noty przez użytkownika (raz)."""
    __tablename__ = "bulletin_acks"
    __table_args__ = (UniqueConstraint("bulletin_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    bulletin_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bulletins.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    read_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
