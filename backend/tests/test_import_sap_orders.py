import datetime
import io

from openpyxl import Workbook
from sqlalchemy import select

from app.models import SapOrder
from app.routers.imports import _parse_ekko_rows
from tests.conftest import login

# nagłówek 1:1 z eksportu EKKO (m.in. dwie kolumny „Waluta” i „Dostawca materiałów”,
# które muszą trafić w odpowiednie pola, a nie w pierwszą pasującą kolumnę)
HEADER = ['Dok.zaopatrz.', 'Jednostka gosp.', 'Typ dok. zaopatrzen.', 'Rodzaj dok. zaopat.',
          'Status', 'Data utworzenia', 'Utworzone przez', 'Ostatnia zmiana',
          'Przedział pozycji', 'Ostatnia pozycja', 'Dostawca', 'Klucz języka',
          'Warunki płatności', 'Płatność do', 'Dział zaopatrzenia', 'Grupa zaopatrzeniowa',
          'Waluta', 'Kurs waluty', 'Data dokumentu', 'Dostawca materiałów', 'Incoterms',
          'Incoterms (część 2)', 'Nr warunku dokumentu', 'Schemat', 'Gr. aktual. (stat.)',
          'Wystawca faktury', 'Przedział podpozycji', 'Grupa zatwierdz.',
          'Strategia zatwierdz.', 'Wskaźnik zatwierdz.', 'Status zatwierdzenia',
          'Kr./reg.d.dekl.podat.', 'Kraj/region nru VAT', 'Nr id. pod. VAT',
          'Status przetwarz. dok. zaopatrz.', 'Wart.całk.podczas zatw.',
          'Incoterms - lokal. 1', 'Waluta', 'Data dostawy', 'Wysłane do dostawcy', 'ASAP',
          'Wymagana data wysyłki', 'Planowana data wysyłki', 'Potwierdzone przez dostawcę',
          'Zamówienie dostawcy', 'Zatwierdzone Artworki']


def _row(order_no, amount=63140.17, asap='X'):
    return [order_no, 'ZP01', 'F', 'ZTF', '9', datetime.datetime(2025, 9, 26), 'DSKIBA',
            datetime.datetime(2025, 12, 11), '10', '30', '10009489', 'EN', 'IZ31', 0,
            'DZAR', 'T05', 'USD', ' 3,62950', datetime.datetime(2025, 9, 26), '', 'FOB',
            'SHANGHAI', '1000000431', 'RM0000', 'SAP', '', '1', '', '', '', '', 'PL', 'PL',
            'PL0000000000', '02', amount, 'SHANGHAI', 'PLN', datetime.datetime(2026, 1, 10),
            'X', asap, None, datetime.datetime(2025, 11, 8), 'X', 'SHSY252909-03', 'X']


def _xlsx(rows):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(HEADER)
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_parse_ekko_maps_ambiguous_columns():
    entry, = _parse_ekko_rows(_xlsx([_row('4500619612')]))

    assert entry["order_number"] == "4500619612"
    assert entry["supplier_sap"] == "10009489"      # „Dostawca”, nie „Dostawca materiałów”
    assert entry["currency"] == "USD"               # pierwsza „Waluta”, nie „Kurs waluty”
    assert entry["fx_rate"] == 3.6295
    assert entry["amount"] == 63140.17
    assert entry["incoterms"] == "FOB" and entry["incoterms_place"] == "SHANGHAI"
    assert entry["delivery_date"] == datetime.date(2026, 1, 10)
    assert entry["planned_ship_date"] == datetime.date(2025, 11, 8)
    assert entry["required_ship_date"] is None
    assert entry["is_asap"] is True and entry["supplier_confirmed"] is True
    assert entry["payment_days"] == 0
    assert entry["supplier_order_no"] == "SHSY252909-03"


def _upload(client, headers, content, dry_run):
    return client.post(
        f"/api/import/sap-orders?company_code=ACME&dry_run={str(dry_run).lower()}",
        headers=headers, files={"file": ("EKKO.xlsx", content, "application/vnd.ms-excel")})


def test_import_sap_orders_dry_run_then_commit(client, admin_headers, db_session):
    content = _xlsx([_row('4500619612'), _row('4500619617', amount=25984.0, asap=''),
                     _row('4500619612')])  # duplikat w pliku

    preview = _upload(client, admin_headers, content, True)
    assert preview.status_code == 200, preview.text
    assert preview.json()["counts"] == {"total": 3, "new": 2, "updated": 0,
                                        "linked": 0, "duplicate": 1, "disappeared": 0}
    assert db_session.scalars(select(SapOrder)).all() == []   # dry-run nic nie zapisuje

    done = _upload(client, admin_headers, content, False)
    assert done.status_code == 200, done.text
    stored = db_session.scalars(select(SapOrder).order_by(SapOrder.order_number)).all()
    assert [o.order_number for o in stored] == ["4500619612", "4500619617"]
    assert stored[1].is_asap is False

    # ponowny import tego samego pliku aktualizuje, nie duplikuje
    again = _upload(client, admin_headers, content, False)
    assert again.json()["counts"]["new"] == 0 and again.json()["counts"]["updated"] == 2
    assert len(db_session.scalars(select(SapOrder)).all()) == 2


def test_import_sap_orders_rejects_foreign_sheet(client, admin_headers):
    workbook = Workbook()
    workbook.active.append(["cokolwiek", "innego"])
    buffer = io.BytesIO()
    workbook.save(buffer)

    response = _upload(client, admin_headers, buffer.getvalue(), True)
    assert response.status_code == 422


def test_import_sap_orders_needs_login(client):
    response = _upload(client, {}, _xlsx([_row('4500619612')]), True)
    assert response.status_code == 401
    assert login  # fixture helper used by admin_headers
