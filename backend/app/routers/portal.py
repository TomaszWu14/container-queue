"""Klienci (odbiorcy) jako ZNACZNIK: słownik klientów per spółka i przypięcie klienta do
kontenera — sprzedaż, zakupy i logistyka śledzą, kiedy dotrze towar dla klienta.

Odbiorcy nie mają żadnego dostępu do aplikacji (decyzja 2026-10-07): portal kliencki
z linkiem per klient i flaga „plik dla klienta” zostały usunięte (spec dokumenty-dostaw
§4 pkt 25). Tu zostaje też limit i branding stron publicznych (share, logowanie).
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record, record_changes, record_created
from ..config import settings
from ..database import get_db
from ..deps import Editors as editors
from ..deps import get_scoped, resolve_company_id, scope_company
from ..models import (
    Customer,
    User,
)
from ..security import api_limiter, client_ip

router = APIRouter(prefix="/api", tags=["portal"])

# ciaśniejszy limit dla stron publicznych (globalny limiter API dalej obowiązuje)
_PUBLIC_LIMIT_PER_MINUTE = 60


def public_rate_limit(request: Request) -> None:
    retry = api_limiter.hit(f"pub:{client_ip(request)}", _PUBLIC_LIMIT_PER_MINUTE)
    if retry is not None:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "Za dużo żądań. Spróbuj ponownie za chwilę.")


# --- słownik klientów (panel, admin/logistics) ---

class CustomerIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    contact: str = Field(default="", max_length=200)
    company_id: int


class CustomerOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    company_id: int
    name: str
    contact: str


@router.get("/customers", response_model=list[CustomerOut])
def list_customers(db: Session = Depends(get_db), user: User = editors):
    query = scope_company(select(Customer).order_by(Customer.name), Customer.company_id, user)
    return db.scalars(query).all()


@router.post("/customers", response_model=CustomerOut, status_code=201)
def create_customer(body: CustomerIn, db: Session = Depends(get_db),
                    user: User = editors):
    resolve_company_id(db, user, body.company_id)
    customer = Customer(name=body.name.strip(), contact=body.contact.strip(),
                        company_id=body.company_id)
    db.add(customer)
    record_created(db, customer, user)
    db.commit()
    return customer


class CustomerEditIn(BaseModel):
    # spółki NIE zmieniamy edycją — przeniosłoby klienta poza izolację per spółka
    name: str = Field(min_length=1, max_length=160)
    contact: str = Field(default="", max_length=200)


@router.patch("/customers/{customer_id}", response_model=CustomerOut)
def update_customer(customer_id: int, body: CustomerEditIn,
                    db: Session = Depends(get_db), user: User = editors):
    customer = get_scoped(db, Customer, customer_id, user)
    record_changes(db, customer, {"name": body.name.strip(), "contact": body.contact.strip()}, user)
    db.commit()
    return customer


@router.delete("/customers/{customer_id}", status_code=204)
def delete_customer(customer_id: int, db: Session = Depends(get_db), user: User = editors):
    from .dictionaries import guarded_delete
    # access check per spółka; guarded_delete blokuje (409) gdy klient ma kontenery lub linki
    get_scoped(db, Customer, customer_id, user)
    guarded_delete(db, Customer, customer_id, user, "klient")


class ContainerCustomerIn(BaseModel):
    customer_id: int | None = None


@router.put("/containers/{container_id}/customer")
def set_container_customer(container_id: int, body: ContainerCustomerIn,
                           db: Session = Depends(get_db), user: User = editors):
    from .containers import get_container_checked
    container = get_container_checked(db, container_id, user)
    customer = None
    if body.customer_id is not None:
        customer = get_scoped(db, Customer, body.customer_id, user)
        # klient musi należeć do spółki kontenera (izolacja per spółka)
        if customer.company_id != container.company_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "Klient należy do innej spółki niż kontener.")
    record(db, entity_type="containers", entity_id=container.id, field="customer_id",
           old_value=container.customer_id, new_value=body.customer_id, user=user,
           note=f"klient: {customer.name if customer else '—'}")
    container.customer_id = body.customer_id
    db.commit()
    return {"customer_id": container.customer_id}


# --- strony publiczne (bez logowania, rate-limit) ---

@router.get("/public/branding", dependencies=[Depends(public_rate_limit)])
def public_branding():
    """Branding stron publicznych — z konfiguracji, bez hardkodu spółki."""
    return {"name": settings.portal_brand_name or settings.app_name,
            "logo_url": settings.portal_logo_url,
            # tylko instancja portfolio: dane konta demo na ekranie logowania
            "demo_hint": settings.demo_login_hint}
