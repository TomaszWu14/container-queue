"""Słowniki: scalanie duplikatów i bezpieczne usuwanie wpisów (wspólne dla routerów).

Wydzielone z routers/dictionaries.py (limit 500 linii/plik); publiczne nazwy są nadal
importowalne z .dictionaries (guarded_delete, fk_usage, mapy scalania).

`merge_into` to rdzeń scalania bez HTTP i bez commit — woła go też app/supplier_consolidation.py
(ekran „Do rozstrzygnięcia" i komenda).
"""
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from .. import audit
from ..deps import get_scoped
from ..models import (
    AvizoRequest,
    Carrier,
    Container,
    Forwarder,
    FreightInvoice,
    InvoiceBatch,
    Order,
    Port,
    Quote,
    Supplier,
    SupplierAlias,
    SupplierContact,
    SupplierDocProfile,
    SupplierMaterial,
    SupplierMaterialMap,
    TransportOrder,
    User,
    normalize_alias,
)
from ..schemas import MergeIn, MergeOut

# --- scalanie i usuwanie duplikatów słownikowych ---------------------------------
#
# Import z Excela nawiózł duplikaty (SHANGHAI / Shanghai / shangai), do których są już
# podpięte kontenery i zamówienia. Samo przemianowanie ich nie scali — dlatego scalanie
# przepina WSZYSTKIE odwołania na rekord docelowy i dopiero wtedy kasuje duplikat.

@dataclass(frozen=True)
class _Dict:
    model: Any
    label: str
    refs: tuple[tuple[Any, str], ...]   # (model wskazujący, nazwa kolumny FK)
    # fetch po id przez deps.get_scoped (izolacja per rekord: spółka / kartoteka dostawców)
    company_scoped: bool = False
    # tabele-dzieci należące do wpisu (kasowane razem z nim przez cascade), np. sezonowy
    # transit time portu. Nie są odwołaniem do przepięcia: przy scalaniu profil duplikatu
    # ma zniknąć (docelowy port ma własny), a przy usuwaniu nie może blokować kasowania.
    owned: tuple[str, ...] = ()
    # pola przenoszone przy scalaniu, gdy cel ma je PUSTE (duplikat z importu bywa
    # pełniejszy niż rekord docelowy — np. kod SAP z LFA1)
    copy_fields: tuple[str, ...] = ()


# Kompletność tej mapy jest krytyczna: pominięcie choćby jednego FK osieroci dane
# (kontener wskazywałby na skasowany port). Wyprowadzona z Base.metadata — patrz test
# test_merge_map_covers_all_foreign_keys, który pilnuje, by nie rozjechała się z modelem.
PORTS = _Dict(Port, "port", ((Container, "port_id"), (Order, "departure_port_id"),
                             (Supplier, "shipping_port_id")),
              owned=("port_transit_times",))
SUPPLIERS = _Dict(Supplier, "dostawca",
                  ((Container, "supplier_id"), (Order, "supplier_id"),
                   (SupplierContact, "supplier_id"), (InvoiceBatch, "supplier_id"),
                   (SupplierMaterialMap, "supplier_id"), (SupplierAlias, "supplier_id"),
                   (SupplierMaterial, "supplier_id")),
                  company_scoped=True,
                  owned=("supplier_doc_profiles",),
                  copy_fields=("sap_code", "country", "address", "note", "column_map"))
CARRIERS = _Dict(Carrier, "armator", ((Container, "carrier_id"), (Quote, "carrier_id")))
# spedytorzy: forwarder_id wisi na kontach, zleceniach transportowych, wycenach i awizacjach
FORWARDERS = _Dict(Forwarder, "spedytor",
                   ((Container, "forwarder_id"), (User, "forwarder_id"),
                    (TransportOrder, "forwarder_id"), (Quote, "forwarder_id"),
                    (AvizoRequest, "forwarder_id"), (FreightInvoice, "forwarder_id")))


def _usage(db: Session, spec: _Dict, item_id: int) -> dict[str, int]:
    """Ile rekordów wskazuje na dany wpis słownika (per tabela)."""
    used = {}
    for model, column in spec.refs:
        count = db.scalar(select(func.count()).select_from(model)
                          .where(getattr(model, column) == item_id))
        if count:
            used[model.__tablename__] = count
    return used


def fk_usage(db: Session, model: Any, item_id: int) -> dict[str, int]:
    """Ile wierszy w CAŁEJ bazie wskazuje na rekord (po FK z metadanych).

    Dla słowników bez mapy scalania (_Dict.refs) — kompletność gwarantuje samo
    Base.metadata, więc nowa tabela z FK jest liczona automatycznie."""
    from ..models import Base
    table = model.__tablename__
    used: dict[str, int] = {}
    for t in Base.metadata.sorted_tables:
        for column in t.columns:
            for fk in column.foreign_keys:
                if fk.column.table.name == table:
                    count = db.scalar(select(func.count()).select_from(t)
                                      .where(column == item_id))
                    if count:
                        used[t.name] = used.get(t.name, 0) + count
    return used


def guarded_delete(db: Session, model: Any, item_id: int, user: User, label: str,
                   describe: Any = None) -> None:
    """Usuwanie wpisu master data: 404 → guard referencji (409, bez kaskad) → audyt → delete."""
    item = db.get(model, item_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Nie znaleziono: {label}.")
    used = fk_usage(db, model, item_id)
    if used:
        total = sum(used.values())
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Nie można usunąć: rekord używany przez {total} ({used}).")
    old = describe(item) if describe else getattr(item, "name", str(item_id))
    audit.record(db, entity_type=model.__tablename__, entity_id=item_id, field="delete",
                 old_value=old, new_value=None, user=user, note=f"usunięto wpis: {label}")
    db.delete(item)
    db.commit()


def _get_or_404(db: Session, spec: _Dict, item_id: int, user: User):
    # słownik per spółka: cudzy wpis = brak (jednolite 404, bez enumeracji)
    if spec.company_scoped:
        return get_scoped(db, spec.model, item_id, user)
    item = db.get(spec.model, item_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Nie znaleziono: {spec.label}.")
    return item


def _supplier_premerge(db: Session, source, target) -> tuple[bool, set[int]]:
    """Porządki przed przepięciem FK dostawcy. Kolizje unikalności wygrywa cel (to on zostaje),
    profil dokumentów przechodzi na cel bez profilu. Zwraca (czy profil duplikatu przepadł,
    spółki, w których nazwa duplikatu ma zostać aliasem celu)."""
    sid, tid = source.id, target.id
    # mapy indeksów są per spółka — unique (company_id, supplier_id, supplier_code): kod, który
    # cel ma już W TEJ SAMEJ spółce, wygrywa u celu; mapy innych spółek przechodzą
    taken = set(db.execute(select(SupplierMaterialMap.company_id, SupplierMaterialMap.supplier_code)
                           .where(SupplierMaterialMap.supplier_id == tid)).all())
    clash = [mid for mid, cid, code in db.execute(
        select(SupplierMaterialMap.id, SupplierMaterialMap.company_id,
               SupplierMaterialMap.supplier_code).where(SupplierMaterialMap.supplier_id == sid))
        if (cid, code) in taken]
    if clash:
        db.execute(delete(SupplierMaterialMap).where(SupplierMaterialMap.id.in_(clash)))
    # indeksy dostawcy: unique (supplier_id, material_id) — materiał celu wygrywa
    db.execute(delete(SupplierMaterial).where(
        SupplierMaterial.supplier_id == sid,
        SupplierMaterial.material_id.in_(
            select(SupplierMaterial.material_id).where(SupplierMaterial.supplier_id == tid))))
    # kontakty: ten sam e-mail (bez wielkości liter) u celu → zamówienia wskazują kontakt celu,
    # kontakt duplikatu znika (unique supplier_id + lower(email) — migracja kartoteka002)
    target_mail = {email.lower(): cid for cid, email in db.execute(
        select(SupplierContact.id, SupplierContact.email).where(
            SupplierContact.supplier_id == tid, SupplierContact.email != ""))}
    for cid, email in db.execute(select(SupplierContact.id, SupplierContact.email).where(
            SupplierContact.supplier_id == sid, SupplierContact.email != "")).all():
        keep = target_mail.get(email.lower())
        if keep:
            db.execute(update(Order).where(Order.supplier_contact_id == cid)
                       .values(supplier_contact_id=keep))
            db.execute(delete(SupplierContact).where(SupplierContact.id == cid))
    # profil dokumentów (owned, nie w refs) — bez przepięcia zginąłby razem ze źródłem przez
    # ondelete="CASCADE". Cel bez profilu dziedziczy profil duplikatu (z próbkami); cel z własnym
    # profilem go zachowuje, a profil duplikatu ginie — odnotowujemy to w audycie.
    dropped = False
    if db.scalar(select(SupplierDocProfile.id).where(SupplierDocProfile.supplier_id == sid)):
        if db.scalar(select(SupplierDocProfile.id).where(SupplierDocProfile.supplier_id == tid)):
            dropped = True
        else:
            # rdzenne UPDATE (nie atrybut ORM) — widoczne od razu dla SELECT-a, którym cascade
            # delete-orphan (models/dictionaries.py) sprawdza przy flush, czy source nadal ma
            # dziecko; inaczej skasowałby profil jako sierotę
            db.execute(update(SupplierDocProfile).where(SupplierDocProfile.supplier_id == sid)
                       .values(supplier_id=tid))
    # spółki, z których plików kolejki pochodzi nazwa duplikatu (kontenery, aliasy, właściciel)
    companies = set(db.scalars(select(Container.company_id).where(
        Container.supplier_id == sid).distinct()))
    companies |= set(db.scalars(select(SupplierAlias.company_id).where(
        SupplierAlias.supplier_id == sid)))
    if source.client_company_id is not None:
        companies.add(source.client_company_id)
    return dropped, companies


def merge_into(db: Session, spec: _Dict, source, target, user: User | None) -> dict[str, int]:
    """Rdzeń scalania: uzupełnij puste pola celu, przepnij wszystkie FK ze źródła na cel,
    audyt, skasuj źródło. Bez walidacji HTTP i bez commit (transakcję domyka wołający).
    ValueError: dwa różne kody SAP — to różni dostawcy w SAP, kod źródła by przepadł."""
    if (spec is SUPPLIERS and source.sap_code and target.sap_code
            and source.sap_code != target.sap_code):
        raise ValueError(f"Różne kody SAP ({source.sap_code} ≠ {target.sap_code}) — "
                         "to różni dostawcy w SAP; popraw w SAP.")
    # uzupełnij puste pola celu z duplikatu (nic nie nadpisujemy); kod SAP najpierw zdejmujemy
    # z duplikatu — przy unikalnym kodzie w kartotece (kartoteka002) nie mogą go mieć naraz
    moved = {field: getattr(source, field) for field in spec.copy_fields
             if not getattr(target, field) and getattr(source, field)}
    if "sap_code" in moved:
        source.sap_code = ""
        db.flush()
    for field, value in moved.items():
        setattr(target, field, value)

    dropped, alias_companies = (_supplier_premerge(db, source, target)
                                if spec is SUPPLIERS else (False, set()))
    repinned: dict[str, int] = {}
    for model, column in spec.refs:
        result = db.execute(update(model).where(getattr(model, column) == source.id)
                            .values(**{column: target.id}))
        if result.rowcount:
            repinned[model.__tablename__] = result.rowcount

    # nazwa duplikatu zostaje aliasem celu w spółkach jego plików — kolejne importy kolejki
    # trafią od razu do celu. Ta sama nazwa (scalanie kopii z LFA1) aliasu nie potrzebuje:
    # rozwiązuje ją dokładne dopasowanie nazwy (importers/queue.resolve_supplier_id).
    norm = normalize_alias(source.name)[:160]
    if spec is SUPPLIERS and norm and norm != normalize_alias(target.name)[:160]:
        for company_id in sorted(alias_companies):
            if not db.scalar(select(SupplierAlias.id).where(
                    SupplierAlias.company_id == company_id, SupplierAlias.alias_norm == norm)):
                db.add(SupplierAlias(company_id=company_id, supplier_id=target.id,
                                     alias=source.name[:160], alias_norm=norm))

    note = f"scalono duplikat; przepięto: {repinned or 'nic'}"
    if dropped:
        note += "; profil dokumentów duplikatu skasowany (cel miał już własny)"
    audit.record(db, entity_type=spec.model.__tablename__, entity_id=target.id,
                 field="merge", old_value=f"{source.name} (id={source.id})",
                 new_value=f"{target.name} (id={target.id})", user=user, note=note)
    db.delete(source)
    return repinned


def _merge(db: Session, spec: _Dict, source_id: int, body: MergeIn, user: User) -> MergeOut:
    if source_id == body.target_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nie można scalić wpisu z samym sobą.")
    source = _get_or_404(db, spec, source_id, user)
    target = _get_or_404(db, spec, body.target_id, user)
    # kartoteka i nadawca spółki-klienta (albo nadawcy dwóch spółek) to różne byty — scalenie
    # przepięłoby kontenery klienta na kartotekę Acme albo na cudzą spółkę (wyciek)
    if spec is SUPPLIERS and source.client_company_id != target.client_company_id:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Nie można scalić: dostawca z kartoteki i nadawca spółki-klienta "
                            "(albo nadawcy różnych spółek).")
    try:
        repinned = merge_into(db, spec, source, target, user)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    db.commit()
    return MergeOut(target_id=body.target_id, repinned=repinned)


def _delete(db: Session, spec: _Dict, item_id: int, user: User) -> None:
    item = _get_or_404(db, spec, item_id, user)
    used = _usage(db, spec, item_id)
    if used:
        total = sum(used.values())
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Wpis jest w użyciu ({total}: {used}) — scal go z innym albo dezaktywuj.")
    audit.record(db, entity_type=spec.model.__tablename__, entity_id=item_id, field="delete",
                 old_value=item.name, new_value=None, user=user, note="usunięto wpis słownika")
    db.delete(item)
    db.commit()
