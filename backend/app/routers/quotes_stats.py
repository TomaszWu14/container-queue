"""Wyceny (RFQ): statystyki (Q97), raport kosztów (Q98), wydajność spedytorów, eksport CSV (Q86).

Router bez prefiksu — prefiks /api i tag nadaje quotes.router, który go dołącza.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..date_pl import date_pl
from ..deps import (
    Editors as editors,
)
from ..exports import csv_safe
from ..models import TransportJob, TransportJobStatus, User
from .quotes_core import (
    _STATS_LOAD,
    _response_rate,
    _scope_jobs,
    _winning_quote,
)

router = APIRouter()


@router.get("/stats/cost-report")
def cost_report(db: Session = Depends(get_db), user: User = editors):
    """Raport kosztów transportu na żądanie (Q98): suma wygranych ofert per miesiąc
    i waluta (zlecenia ZLECONE)."""
    jobs = db.scalars(_scope_jobs(select(TransportJob).options(*_STATS_LOAD)
                      .where(TransportJob.status == TransportJobStatus.ZLECONE), user)).all()
    buckets: dict[tuple[str, str], dict] = {}
    for j in jobs:
        won = _winning_quote(j)
        stamp = j.chosen_at or j.created_at
        if not won or won.amount is None or not stamp:
            continue
        month = stamp.strftime("%Y-%m")
        key = (month, won.currency)
        b = buckets.setdefault(key, {"month": month, "currency": won.currency,
                                     "total": Decimal("0"), "count": 0})
        b["total"] += won.amount
        b["count"] += 1
    rows = sorted(buckets.values(), key=lambda r: (r["month"], r["currency"]), reverse=True)
    for r in rows:
        r["total"] = float(round(r["total"], 2))
    return rows


@router.get("/stats/forwarders")
def forwarder_performance(db: Session = Depends(get_db), user: User = editors):
    """Raport wydajności spedytorów: ile zapytań, odpowiedzi, wygranych, brak sprzętu,
    rolowania, średni transit. Bazuje na złożonych ofertach (jedna na spedycję/zlecenie)."""
    jobs = db.scalars(_scope_jobs(select(TransportJob).options(*_STATS_LOAD), user)).all()
    stats: dict[int, dict] = {}
    for j in jobs:
        won_id = j.chosen_quote_id if j.status == TransportJobStatus.ZLECONE else None
        for q in j.quotes:
            row = stats.setdefault(q.forwarder_id, {
                "forwarder_id": q.forwarder_id,
                "forwarder": q.forwarder.name if q.forwarder else str(q.forwarder_id),
                "invited": 0, "responded": 0, "won": 0,
                "no_equipment": 0, "rolls": 0, "_transit": []})
            row["invited"] += 1
            if q.submitted_at:
                row["responded"] += 1
            if won_id is not None and q.id == won_id:
                row["won"] += 1
            if q.no_equipment:
                row["no_equipment"] += 1
            if q.can_roll_booking:
                row["rolls"] += 1
            if q.transit_time_days is not None:
                row["_transit"].append(q.transit_time_days)
    rows = []
    for row in stats.values():
        transit = row.pop("_transit")
        row["response_rate"] = _response_rate(row["responded"], row["invited"])
        row["win_rate"] = round(row["won"] * 100 / row["responded"]) if row["responded"] else 0
        row["avg_transit"] = round(sum(transit) / len(transit), 1) if transit else None
        rows.append(row)
    # sortowanie: najwięcej wygranych, potem najlepsza odpowiedzialność
    rows.sort(key=lambda r: (-r["won"], -r["response_rate"], r["forwarder"].lower()))
    return rows


@router.get("/stats/transport-jobs.csv")
def export_jobs_csv(db: Session = Depends(get_db), user: User = editors):
    """Eksport zleceń wyceny do CSV (Q86)."""
    import csv
    import io

    from fastapi.responses import StreamingResponse

    jobs = db.scalars(_scope_jobs(select(TransportJob).options(*_STATS_LOAD)
                      .order_by(TransportJob.id.desc()), user)).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Numer", "Status", "Kontenery", "Zaproszone", "Odpowiedzi",
                "Zwycięzca", "Cena", "Waluta", "Nr przesyłki", "Utworzono"])
    for j in jobs:
        won = _winning_quote(j)
        w.writerow([csv_safe(v) for v in (
            j.number, j.status.value, len(j.items), len(j.quotes),
            sum(1 for q in j.quotes if q.submitted_at),
            won.forwarder.name if won and won.forwarder else "",
            f"{won.amount}" if won and won.amount is not None else "",
            won.currency if won else "", j.shipment_number,
            date_pl(j.created_at, time=True),
        )])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=zlecenia-wyceny.csv"})
