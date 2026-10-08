"""Zawartość kontenera: pozycje zamówień (REF), wypełnienie 3D (packer) i linki SENT."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..audit import record
from ..database import get_db
from ..deps import CommercialReaders as commercial_readers
from ..deps import ContentsReaders as contents_readers
from ..deps import Editors as editors
from ..deps import get_scoped, scope_containers
from ..models import Container, MaterialUnit, OrderItem, SentLink, User
from ..order_numbers import container_order_numbers  # noqa: F401 — re-eksport (routers.containers)
from ..schemas import OrderItemOut, SentLinkIn, SentLinkOut
from ..serializers import attach_marm_volumes
from .containers_common import get_container_checked

# sub-router bez prefiksu — podpinany w routers/containers.py (prefiks /api, tag kolejka)
router = APIRouter()


# --- zawartość kontenera (REF) i powiązania SENT ---

# ponytail: cache in-memory per proces (dict + TTL) — wystarcza dla jednego workera;
# gdy przyjdzie skalowanie na wiele workerów, przenieś do Redisa
_PACKING_CACHE: dict = {}
_PACKING_TTL = 300  # s


def _packing_result(db: Session, container: Container) -> dict:
    """Wynik packera dla kontenera (z cachem ~5 min). Statusy: ok / no_data /
    no_type / no_dims / no_items — bez wyjątków HTTP (używane też zbiorczo)."""
    import time

    from ..packing import container_inner_dims_cm, pack_container

    ctype = container.order.container_type if container.order else None
    if ctype is None:
        return {"status": "no_type"}
    dims = container_inner_dims_cm(ctype)
    if dims is None:
        return {"status": "no_dims", "type_name": ctype.name}

    numbers = container_order_numbers(container)
    items = db.scalars(select(OrderItem)
                       .where(OrderItem.company_id == container.company_id,
                              OrderItem.order_number.in_(numbers))
                       .order_by(OrderItem.order_number, OrderItem.position)).all() \
        if numbers else []
    if not items:
        return {"status": "no_items"}

    key = (container.id, dims,
           tuple((i.id, i.material, i.quantity, i.unit) for i in items))
    now = time.monotonic()
    cached = _PACKING_CACHE.get(container.id)
    if cached and cached[0] == key and now - cached[1] < _PACKING_TTL:
        return cached[2]

    materials = {i.material for i in items if i.material}
    rows_by_no: dict[str, list] = {m: [] for m in materials}
    if materials:
        for row in db.scalars(select(MaterialUnit)
                              .where(MaterialUnit.material_no.in_(materials))):
            rows_by_no[row.material_no].append(row)
    result = pack_container(items, dims, rows_by_no)
    _PACKING_CACHE[container.id] = (key, now, result)
    return result


@router.get("/containers/fill-summary")
def containers_fill_summary(ids: str, db: Session = Depends(get_db),
                            user: User = commercial_readers):
    """Zagregowane % wypełnienia dla listy kontenerów (kolumna w kolejce).

    Jedno żądanie zamiast N × /packing. Liczone leniwie z budżetem czasu — packer
    jest ciężki; po przekroczeniu budżetu pozostałe (nie-cache'owane) dostają null.
    Brak danych (typ/pozycje/MARM) → null."""
    import time

    id_list: list[int] = []
    for part in ids.split(","):
        part = part.strip()
        if part.isdigit():
            id_list.append(int(part))
    # twardy limit paczki: front pyta tylko o widoczne kontenery, porcjami
    id_list = list(dict.fromkeys(id_list))[:40]
    if not id_list:
        return {}
    containers = db.scalars(scope_containers(
        select(Container).options(selectinload(Container.order))
        .where(Container.id.in_(id_list)), user)).all()
    out: dict[int, float | None] = {c_id: None for c_id in id_list
                                    if any(c.id == c_id for c in containers)}
    deadline = time.monotonic() + 3.0   # ponytail: budżet 3 s na paczkę; reszta = null
    for container in containers:
        if time.monotonic() > deadline and container.id not in _PACKING_CACHE:
            continue
        result = _packing_result(db, container)
        fill = result.get("fill_pct")
        out[container.id] = fill if result.get("status") == "ok" else None
    return out


@router.get("/containers/{container_id}/items", response_model=list[OrderItemOut])
def container_items(container_id: int, db: Session = Depends(get_db),
                    user: User = contents_readers):
    container = get_container_checked(db, container_id, user)
    numbers = container_order_numbers(container)
    if not numbers:
        return []
    items = db.scalars(select(OrderItem)
                       .where(OrderItem.company_id == container.company_id,
                              OrderItem.order_number.in_(numbers))
                       .order_by(OrderItem.order_number, OrderItem.position)).all()
    volumes = attach_marm_volumes(db, items)   # objętość wyliczana z MARM (może być None)
    out = []
    for item in items:
        entry = OrderItemOut.model_validate(item)
        entry.computed_volume_m3 = volumes.get(item.id)
        out.append(entry)
    return out


@router.get("/containers/{container_id}/packing")
def container_packing(container_id: int, db: Session = Depends(get_db),
                      user: User = commercial_readers):
    """Wypełnienie kontenera 3D: pozycje zamówień × wymiary MARM ułożone packerem
    (bloki mono-SKU najpierw, resztki mieszane py3dbp). Cache w pamięci ~5 min."""
    container = get_container_checked(db, container_id, user)
    result = _packing_result(db, container)
    if result.get("status") == "no_dims":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Typ kontenera „{result['type_name']}” nie ma wymiarów "
                            "wewnętrznych — uzupełnij słownik typów kontenerów.")
    return result


@router.get("/containers/{container_id}/sent-links", response_model=list[SentLinkOut])
def container_sent_links(container_id: int, db: Session = Depends(get_db),
                         user: User = commercial_readers):
    container = get_container_checked(db, container_id, user)
    numbers = container_order_numbers(container)
    if not numbers:
        return []
    return db.scalars(select(SentLink)
                      .where(SentLink.company_id == container.company_id,
                             SentLink.order_number.in_(numbers))
                      .order_by(SentLink.order_number, SentLink.id)).all()


@router.post("/containers/{container_id}/sent-links", response_model=SentLinkOut,
             status_code=201)
def add_sent_link(container_id: int, body: SentLinkIn,
                  db: Session = Depends(get_db), user: User = editors):
    container = get_container_checked(db, container_id, user)
    if body.order_number not in container_order_numbers(container):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "To zamówienie nie jest powiązane z tym kontenerem.")
    link = SentLink(company_id=container.company_id, sent_number=body.sent_number,
                    order_number=body.order_number, note=body.note,
                    created_by_id=user.id)
    db.add(link)
    db.flush()
    record(db, entity_type="sent_links", entity_id=link.id, field="sent_number",
           old_value=None, new_value=f"{body.sent_number} ↔ {body.order_number}",
           user=user, note="powiązanie SENT")
    db.commit()
    return link


@router.delete("/sent-links/{link_id}", status_code=204)
def delete_sent_link(link_id: int, db: Session = Depends(get_db), user: User = editors):
    link = get_scoped(db, SentLink, link_id, user)
    record(db, entity_type="sent_links", entity_id=link.id, field="sent_number",
           old_value=f"{link.sent_number} ↔ {link.order_number}", new_value=None,
           user=user, note="usunięcie powiązania SENT")
    db.delete(link)
    db.commit()
