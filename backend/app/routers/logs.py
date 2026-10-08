"""API dziennika serwera (admin-only): żądania, ruch, zadania tła, błędy frontu."""
import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import applog
from ..database import get_db
from ..deps import AdminOnly as admin_only
from ..models import ClientError, JobRun, RequestCounter, RequestLog, User, utcnow

router = APIRouter(prefix="/api", tags=["monitor"])


@router.get("/admin/logs/requests")
def list_request_logs(status: str = "", q: str = "", user_id: int | None = None,
                      date_from: datetime.date | None = None,
                      date_to: datetime.date | None = None,
                      page: int = Query(default=1, ge=1),
                      per_page: int = Query(default=50, ge=1, le=200),
                      db: Session = Depends(get_db), user: User = admin_only):
    conds = []
    if status == "4xx":
        conds += [RequestLog.status >= 400, RequestLog.status < 500]
    elif status == "5xx":
        conds.append(RequestLog.status >= 500)
    elif status == "slow":
        conds.append(RequestLog.duration_ms > applog.SLOW_MS)
    elif status:
        try:
            conds.append(RequestLog.status == int(status))
        except ValueError:
            raise HTTPException(422, "Nieznany filtr statusu.") from None
    if q:
        conds.append(RequestLog.path.ilike(f"%{q}%"))
    if user_id is not None:
        conds.append(RequestLog.user_id == user_id)
    if date_from:
        conds.append(RequestLog.at >= date_from)
    if date_to:
        conds.append(RequestLog.at < date_to + datetime.timedelta(days=1))
    total = db.scalar(select(func.count(RequestLog.id)).where(*conds))
    stmt = (select(RequestLog, User.login).outerjoin(User, User.id == RequestLog.user_id)
           .where(*conds))
    rows = db.execute(stmt.order_by(RequestLog.at.desc())
                      .offset((page - 1) * per_page).limit(per_page)).all()
    return {"total": total, "items": [
        {"id": r.id, "at": r.at.isoformat(), "method": r.method, "path": r.path,
         "status": r.status, "duration_ms": r.duration_ms, "user_id": r.user_id,
         "user_login": login, "ip": r.ip, "request_id": r.request_id, "error": r.error}
        for r, login in rows]}


@router.get("/admin/logs/traffic")
def traffic(hours: int = Query(default=24, ge=1, le=168),
           db: Session = Depends(get_db), user: User = admin_only):
    since = utcnow() - datetime.timedelta(hours=hours)
    rows = db.scalars(select(RequestCounter).where(RequestCounter.minute >= since)
                      .order_by(RequestCounter.minute)).all()
    buckets: dict[datetime.datetime, list[int]] = {}
    for r in rows:
        bucket = r.minute.replace(minute=r.minute.minute - r.minute.minute % 5,
                                  second=0, microsecond=0)
        b = buckets.setdefault(bucket, [0, 0, 0, 0])
        for i, v in enumerate((r.total, r.c4xx, r.c5xx, r.dur_ms_sum)):
            b[i] += v
    return [{"at": at.isoformat(), "total": total, "c4xx": c4, "c5xx": c5,
             "avg_ms": round(dur / total) if total else 0}
            for at, (total, c4, c5, dur) in sorted(buckets.items())]


@router.get("/admin/logs/jobs")
def jobs(db: Session = Depends(get_db), user: User = admin_only):
    history = db.scalars(select(JobRun).order_by(JobRun.started_at.desc())
                         .limit(200)).all()
    last_per_pair = (select(JobRun.job, JobRun.fn, func.max(JobRun.started_at).label("mx"))
                     .group_by(JobRun.job, JobRun.fn).subquery())
    latest_rows = db.scalars(select(JobRun).join(
        last_per_pair,
        (JobRun.job == last_per_pair.c.job) & (JobRun.fn == last_per_pair.c.fn)
        & (JobRun.started_at == last_per_pair.c.mx))).all()
    latest: dict[tuple[str, str], JobRun] = {}
    for j in latest_rows:
        latest.setdefault((j.job, j.fn), j)
    item = lambda j: {"job": j.job, "fn": j.fn, "started_at": j.started_at.isoformat(),  # noqa: E731
                      "duration_ms": j.duration_ms, "ok": j.ok, "detail": j.detail}
    return {"latest": [item(j) for j in latest.values()], "history": [item(j) for j in history]}


@router.get("/admin/logs/client-errors")
def client_errors(db: Session = Depends(get_db), user: User = admin_only):
    rows = db.scalars(select(ClientError).order_by(ClientError.created_at.desc())
                      .limit(200)).all()
    return [{"id": r.id, "created_at": r.created_at.isoformat(), "name": r.name,
             "message": r.message, "stack": r.stack, "url": r.url,
             "user_agent": r.user_agent} for r in rows]
