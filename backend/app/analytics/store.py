from __future__ import annotations

import datetime

from sqlalchemy import func, select

from ..models import MaterialIssue


def save_rows(db, rows: list[dict], source_file: str) -> int:
    existing = {(r.produkt, r.date, r.magazyn) for r in db.query(
        MaterialIssue).filter(MaterialIssue.source_file == source_file).all()}
    n = 0
    for r in rows:
        key = (r["produkt"], r["date"], r["magazyn"])
        if key in existing:
            continue
        db.add(MaterialIssue(source_file=source_file, **r))
        existing.add(key); n += 1
    db.commit()
    return n

def load_series(db, produkt: str) -> dict[datetime.date, float]:
    stmt = (select(MaterialIssue.date, func.sum(MaterialIssue.qty))
            .where(MaterialIssue.produkt == produkt).group_by(MaterialIssue.date))
    return {d: float(q or 0) for d, q in db.execute(stmt)}

def list_products(db) -> list[str]:
    return [p for (p,) in db.execute(
        select(MaterialIssue.produkt).distinct().order_by(MaterialIssue.produkt))]
