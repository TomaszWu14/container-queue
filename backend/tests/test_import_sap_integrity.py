"""DATA-003: importy SAP nie gubią powiązań, nie wymyślają pozycji i walidują ilości."""
import io

from openpyxl import Workbook
from sqlalchemy import select

from app.models import AuditLog, Company, Container, MaterialUnit, OrderItem, SapImport, SapOrder
from tests.test_import_marm import _xlsx as marm_xlsx
from tests.test_import_sap_orders import _row as ekko_row
from tests.test_import_sap_orders import _xlsx as ekko_xlsx

REF_HEADER = ['Dok.zaopatrz.', 'Pozycja', 'Krótki tekst', 'Materiał', 'Ilość zamówienia',
              'Jedn. miary']


def _ref_xlsx(rows):
    workbook = Workbook()
    workbook.active.append(REF_HEADER)
    for row in rows:
        workbook.active.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _post(client, headers, path, content, dry_run, company=True):
    query = f"dry_run={str(dry_run).lower()}" + ("&company_code=ACME" if company else "")
    return client.post(f"/api/import/{path}?{query}", headers=headers,
                       files={"file": ("f.xlsx", content, "application/vnd.ms-excel")})


def _container(db, order_numbers, no="TEMU1234567"):
    company = db.scalars(select(Company).where(Company.code == "ACME")).one()
    container = Container(company_id=company.id, container_no=no, order_numbers=order_numbers)
    db.add(container)
    db.commit()
    return container


# --- EKKO ---

def test_ekko_reimport_keeps_link_when_auto_match_finds_nothing(client, admin_headers, db_session):
    container = _container(db_session, "4500619612")
    content = ekko_xlsx([ekko_row('4500619612')])
    assert _post(client, admin_headers, "sap-orders", content, False).status_code == 200
    container.order_numbers = ""          # numer zniknął z kontenera (np. poprawka literówki)
    db_session.commit()

    assert _post(client, admin_headers, "sap-orders", content, False).status_code == 200
    db_session.expire_all()
    order = db_session.scalars(select(SapOrder)).one()
    assert order.container_id == container.id      # dawniej: nadpisane na None


def test_ekko_link_change_is_audited(client, admin_headers, db_session):
    first = _container(db_session, "4500619612")
    content = ekko_xlsx([ekko_row('4500619612')])
    _post(client, admin_headers, "sap-orders", content, False)
    first.order_numbers = ""
    second = _container(db_session, "4500619612", no="MSCU1234565")

    _post(client, admin_headers, "sap-orders", content, False)
    db_session.expire_all()
    order = db_session.scalars(select(SapOrder)).one()
    assert order.container_id == second.id
    log = db_session.scalars(select(AuditLog).where(AuditLog.entity_type == "sap_orders",
                                                    AuditLog.field == "container_id")).one()
    assert (log.entity_id, log.old_value, log.new_value) == (order.id, str(first.id), str(second.id))


def test_ekko_preview_counts_orders_missing_from_file_and_keeps_them(
        client, admin_headers, db_session):
    _post(client, admin_headers, "sap-orders",
          ekko_xlsx([ekko_row('4500619612'), ekko_row('4500619617')]), False)
    only_one = ekko_xlsx([ekko_row('4500619612')])

    assert _post(client, admin_headers, "sap-orders", only_one, True) \
        .json()["counts"]["disappeared"] == 1
    _post(client, admin_headers, "sap-orders", only_one, False)
    assert len(db_session.scalars(select(SapOrder)).all()) == 2   # nic nie kasujemy
    assert db_session.scalars(select(SapImport).where(SapImport.kind == "ekko")).all()


# --- EKPO / REF ---

def test_ref_rejects_rows_without_position_instead_of_synthetic_numbers(
        client, admin_headers, db_session):
    content = _ref_xlsx([['4500000001', None, 'Rurka', 'ABC1', 100, 'PCS'],
                         ['4500000001', None, 'Kolanko', 'ABC2', 50, 'PCS']])
    preview = _post(client, admin_headers, "order-items", content, True).json()
    assert preview["counts"]["invalid"] == 2
    assert {e["reason"] for e in preview["errors"]} == {"brak numeru pozycji"}

    _post(client, admin_headers, "order-items", content, False)
    assert db_session.scalars(select(OrderItem)).all() == []      # dawniej: pozycje „#1”, „#2”


def test_ref_quantity_parsed_to_number_and_invalid_reported(client, admin_headers, db_session):
    content = _ref_xlsx([['4500000001', '10', 'Rurka', 'ABC1', '1 200,5', 'PCS'],
                         ['4500000002', '10', 'Kolanko', 'ABC2', 'dużo', 'PCS']])
    preview = _post(client, admin_headers, "order-items", content, True).json()
    assert preview["counts"]["invalid"] == 1
    error, = preview["errors"]
    assert error["order_number"] == "4500000002" and "ilość" in error["reason"]

    _post(client, admin_headers, "order-items", content, False)
    items = db_session.scalars(select(OrderItem)).all()
    assert [(i.order_number, i.quantity) for i in items] == [("4500000001", "1200.5")]


def test_ref_order_with_invalid_row_is_left_untouched(client, admin_headers, db_session):
    _post(client, admin_headers, "order-items",
          _ref_xlsx([['4500000001', '10', 'Rurka', 'ABC1', 100, 'PCS'],
                     ['4500000001', '20', 'Kolanko', 'ABC2', 50, 'PCS']]), False)
    broken = _ref_xlsx([['4500000001', '10', 'Rurka', 'ABC1', 100, 'PCS'],
                        ['4500000001', None, 'Kolanko', 'ABC2', 50, 'PCS']])
    _post(client, admin_headers, "order-items", broken, False)
    positions = sorted(i.position for i in db_session.scalars(select(OrderItem)))
    assert positions == ["10", "20"]      # pozycja 20 (z przyjęciem?) nie znika po cichu


def test_ref_reimport_in_other_order_keeps_position_material(client, admin_headers, db_session):
    rows = [['4500000001', '10', 'Rurka', 'ABC1', 100, 'PCS'],
            ['4500000001', '20', 'Kolanko', 'ABC2', 50, 'PCS']]
    _post(client, admin_headers, "order-items", _ref_xlsx(rows), False)
    _post(client, admin_headers, "order-items", _ref_xlsx(rows[::-1]), False)
    by_pos = {i.position: i.material for i in db_session.scalars(select(OrderItem))}
    assert by_pos == {"10": "ABC1", "20": "ABC2"}


def test_ref_orders_linked_uses_whole_tokens(client, admin_headers, db_session):
    _container(db_session, "4500624622")
    content = _ref_xlsx([['4500024', '10', 'Rurka', 'ABC1', 1, 'PCS'],
                         ['4500624622', '10', 'Rurka', 'ABC1', 1, 'PCS']])
    counts = _post(client, admin_headers, "order-items", content, True).json()["counts"]
    assert counts["orders"] == 2 and counts["orders_linked"] == 1


# --- MARM ---

def test_marm_invalid_conversion_reported_not_defaulted_to_one(client, admin_headers, db_session):
    content = marm_xlsx([['100200', 'KAR', 'dziesięć', 1, 120, 'CDM', 5, 'KG'],
                         ['100200', 'SZT', 1, 1, 0, '0', 0.5, 'KG']])
    result = _post(client, admin_headers, "material-units", content, False, company=False).json()
    assert result["counts"]["invalid"] == 1
    assert result["errors"][0]["unit"] == "KAR"
    assert [m.unit for m in db_session.scalars(select(MaterialUnit))] == ["SZT"]


def test_marm_counts_units_missing_from_file(client, admin_headers, db_session):
    _post(client, admin_headers, "material-units",
          marm_xlsx([['100200', 'KAR', 10, 1, 120, 'CDM', 5, 'KG'],
                     ['100200', 'SZT', 1, 1, 0, '0', 0.5, 'KG']]), False, company=False)
    preview = _post(client, admin_headers, "material-units",
                    marm_xlsx([['100200', 'SZT', 1, 1, 0, '0', 0.5, 'KG']]), True, company=False)
    assert preview.json()["counts"]["disappeared"] == 1
