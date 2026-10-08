"""Czyszczenie danych demonstracyjnych spółki (np. Borealis wgrane seedem).

Powstało, bo kolejka i zamówienia Borealis pochodzą z jednorazowego seeda
(scripts/import_excel.py → seed_data.json). Skrypt pozwala je usunąć, aby
w systemie zostały wyłącznie realne dane (np. Acme z eksportu SAP/EKPO).

Tryby:
  orders  – usuwa tylko zamówienia (PO) spółki i odpina je od kontenerów
            (container.order_id → NULL); kontenery zostają.
  all     – pełny reset spółki: kontenery, zamówienia, pozycje REF, powiązania
            SENT oraz słowniki demo (dostawcy, magazyny) tej spółki.

Bezpieczeństwo: domyślnie DRY-RUN (tylko podsumowanie, zero zmian).
Zapis następuje wyłącznie z flagą --yes.

Uruchomienie (z katalogu backend/):
  python -m scripts.purge_company --company BOREALIS --mode orders          # podgląd
  python -m scripts.purge_company --company BOREALIS --mode orders --yes    # wykonanie
  python -m scripts.purge_company --company BOREALIS --mode all --yes
"""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Company,
    Container,
    Order,
    OrderItem,
    SentLink,
    Supplier,
    Warehouse,
)


def _count(db, model, **filters) -> int:
    return db.scalar(select(func.count()).select_from(model).filter_by(**filters)) or 0


def purge(company_code: str, mode: str, commit: bool) -> None:
    with SessionLocal() as db:
        company = db.scalar(select(Company).where(Company.code == company_code.upper()))
        if not company:
            print(f"✗ Nie znaleziono spółki o kodzie {company_code!r}.")
            return
        cid = company.id
        containers = _count(db, Container, company_id=cid)
        orders = _count(db, Order, company_id=cid)
        items = _count(db, OrderItem, company_id=cid)
        sent = _count(db, SentLink, company_id=cid)
        suppliers = _count(db, Supplier, client_company_id=cid)
        warehouses = _count(db, Warehouse, company_id=cid)

        print(f"Spółka: {company.name} ({company.code}, id={cid})")
        print(f"  kontenery={containers}  zamówienia={orders}  pozycje REF={items}"
              f"  SENT={sent}  dostawcy={suppliers}  magazyny={warehouses}")

        if mode == "orders":
            # odpięcie zamówień od kontenerów, następnie usunięcie samych zamówień
            unlinked = db.query(Container).filter(
                Container.company_id == cid, Container.order_id.isnot(None)
            ).update({Container.order_id: None}, synchronize_session=False)
            deleted = db.query(Order).filter(Order.company_id == cid).delete(
                synchronize_session=False)
            print(f"  → odpięto zamówień od kontenerów: {unlinked}; "
                  f"usunięto zamówień (PO): {deleted}")
        elif mode == "all":
            db.query(Container).filter(Container.company_id == cid).update(
                {Container.order_id: None}, synchronize_session=False)
            d_cont = db.query(Container).filter(Container.company_id == cid).delete(
                synchronize_session=False)
            d_ord = db.query(Order).filter(Order.company_id == cid).delete(
                synchronize_session=False)
            d_item = db.query(OrderItem).filter(OrderItem.company_id == cid).delete(
                synchronize_session=False)
            d_sent = db.query(SentLink).filter(SentLink.company_id == cid).delete(
                synchronize_session=False)
            d_sup = db.query(Supplier).filter(Supplier.client_company_id == cid).delete(
                synchronize_session=False)
            d_wh = db.query(Warehouse).filter(Warehouse.company_id == cid).delete(
                synchronize_session=False)
            print(f"  → usunięto: kontenery={d_cont} zamówienia={d_ord} REF={d_item}"
                  f" SENT={d_sent} dostawcy={d_sup} magazyny={d_wh}")
        else:
            print(f"✗ Nieznany tryb {mode!r} (dozwolone: orders, all).")
            return

        if commit:
            db.commit()
            print("✓ Zmiany zapisane.")
        else:
            db.rollback()
            print("• DRY-RUN — nic nie zapisano. Dodaj --yes, aby wykonać.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Czyszczenie danych demo spółki.")
    parser.add_argument("--company", default="BOREALIS", help="kod spółki (np. BOREALIS)")
    parser.add_argument("--mode", default="orders", choices=["orders", "all"],
                        help="orders=tylko zamówienia PO, all=pełny reset spółki")
    parser.add_argument("--yes", action="store_true", help="wykonaj zapis (bez tej flagi: podgląd)")
    args = parser.parse_args()
    purge(args.company, args.mode, commit=args.yes)


if __name__ == "__main__":
    main()
