from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..analytics.ingest import parse_issues
from ..analytics.store import save_rows
from ..config import settings
from ..database import get_db
from ..deps import Editors as editors
from ..deps import Viewer as viewer
from ..deps import scope_containers
from ..audit import record
from ..models import (
    Container,
    MaterialIssue,
    ProductPaz,
    Supplier,
    User,
    Warehouse,
    today_pl,
)
from .containers_common import hidden_fields
from .forwarding_files import read_upload_capped

router = APIRouter(prefix="/api/analytics", tags=["analityka"])

@router.post("/upload")
def upload(commit: bool = Query(False), file: UploadFile = File(...),
                 user: User = editors, db: Session = Depends(get_db)):
    data = read_upload_capped(file, settings.max_upload_mb, "Plik analityki")
    rep = parse_issues(data, file.filename or "upload.csv")
    known = {p.produkt for p in db.query(ProductPaz).all()}
    unknown = sorted({r["produkt"] for r in rep.rows} - known) if known else []
    saved = 0
    if commit and not rep.errors:
        saved = save_rows(db, rep.rows, file.filename or "upload.csv")
        record(db, entity_type=MaterialIssue.__tablename__, entity_id=0, field="import", old_value=None,
               new_value=f"{saved} wierszy", user=user, note=file.filename or "upload.csv")
        db.commit()
    return {"rows_count": len(rep.rows), "errors": rep.errors,
            "duplicates": rep.duplicates, "unknown_products": unknown, "saved": saved}


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


@router.get("/operational")
def operational(months: int = Query(6, ge=1, le=24),
                user: User = viewer, db: Session = Depends(get_db)):
    """KPI operacyjne kontenerów (W6/W15): rozkład statusów, przepustowość miesięczna,
    średni lead-time i czas rozładunku, top dostawcy/magazyny. Zakres wg roli.

    ponytail: agregacja w Pythonie nad zakresem użytkownika — dla typowych wolumenów
    (tysiące kontenerów) wystarcza; przy dużej skali przenieść liczenie do SQL/cache."""
    stmt = scope_containers(select(
        Container.status, Container.created_at, Container.completed_at,
        Container.unload_started_at, Container.unload_finished_at,
        Container.supplier_id, Container.warehouse_id), user)
    rows = db.execute(stmt).all()

    today = today_pl()
    # klucze YYYY-MM od najstarszego do bieżącego
    buckets: list[str] = []
    y, m = today.year, today.month
    for _ in range(months):
        buckets.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    buckets.reverse()
    bucket_set = set(buckets)

    by_status: dict[str, int] = {}
    throughput = {b: 0 for b in buckets}
    lead_days: list[float] = []
    unload_min: list[float] = []
    by_supplier: dict[int, int] = {}
    by_warehouse: dict[int, int] = {}

    for r in rows:
        by_status[r.status.value] = by_status.get(r.status.value, 0) + 1
        if r.supplier_id:
            by_supplier[r.supplier_id] = by_supplier.get(r.supplier_id, 0) + 1
        if r.warehouse_id:
            by_warehouse[r.warehouse_id] = by_warehouse.get(r.warehouse_id, 0) + 1
        if r.completed_at:
            key = f"{r.completed_at.year:04d}-{r.completed_at.month:02d}"
            if key in bucket_set:
                throughput[key] += 1
            if r.created_at:
                lead_days.append((r.completed_at.date() - r.created_at.date()).days)
        if r.unload_started_at and r.unload_finished_at:
            unload_min.append(
                (r.unload_finished_at - r.unload_started_at).total_seconds() / 60)

    def _named(counts: dict[int, int], model) -> list[dict]:
        top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:5]
        names = {o.id: o.name for o in db.scalars(
            select(model).where(model.id.in_([i for i, _ in top])))} if top else {}
        return [{"name": names.get(i, f"#{i}"), "count": c} for i, c in top]

    return {
        "total": len(rows),
        "by_status": by_status,
        "throughput": [{"month": b, "count": throughput[b]} for b in buckets],
        "avg_lead_time_days": _avg(lead_days),
        "avg_unload_minutes": _avg(unload_min),
        # magazyn/agencja nie widzą dostawcy (hidden_fields) — także w agregacie
        "top_suppliers": ([] if "supplier_name" in hidden_fields(user)
                          else _named(by_supplier, Supplier)),
        "top_warehouses": _named(by_warehouse, Warehouse),
    }
