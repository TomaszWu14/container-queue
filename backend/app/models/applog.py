"""Dziennik serwera: błędne/wolne żądania, liczniki ruchu per minuta, przebiegi zadań tła."""
import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class RequestLog(Base):
    __tablename__ = "request_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime.datetime] = mapped_column(DateTime, index=True)
    method: Mapped[str] = mapped_column(String(8))
    path: Mapped[str] = mapped_column(String(500))
    status: Mapped[int] = mapped_column(Integer, index=True)
    duration_ms: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    ip: Mapped[str] = mapped_column(String(64), default="")
    request_id: Mapped[str] = mapped_column(String(16), default="")
    error: Mapped[str] = mapped_column(Text, default="")


class RequestCounter(Base):
    __tablename__ = "request_counters"
    __table_args__ = (UniqueConstraint("minute", name="uq_request_counters_minute"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    minute: Mapped[datetime.datetime] = mapped_column(DateTime)
    total: Mapped[int] = mapped_column(Integer, default=0)
    c4xx: Mapped[int] = mapped_column(Integer, default=0)
    c5xx: Mapped[int] = mapped_column(Integer, default=0)
    dur_ms_sum: Mapped[int] = mapped_column(Integer, default=0)


class JobRun(Base):
    __tablename__ = "job_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    job: Mapped[str] = mapped_column(String(60), index=True)
    fn: Mapped[str] = mapped_column(String(120))
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime, index=True)
    duration_ms: Mapped[int] = mapped_column(Integer)
    ok: Mapped[bool] = mapped_column(Boolean)
    detail: Mapped[str] = mapped_column(Text, default="")
