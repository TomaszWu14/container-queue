"""Import słownika portów kontenerowych + dopasowanie współrzędnych UN/LOCODE
+ endpoint mapy (with_coords) + delete z guardem."""
import io
from pathlib import Path

from openpyxl import Workbook
from sqlalchemy import select

from app.locode import match_coords, norm_name
from app.models import AuditLog, ContainerPort
from app.routers.imports import _parse_cport_rows

FIXTURE = Path(__file__).parent / "data" / "probka-porty-kontenerowe.tsv"

HEADER = ["CODE", "PORT NAME", "COUNTRY", "COUNTRY NAME"]


def _tsv(rows, header=HEADER) -> bytes:
    lines = ["\t".join(header)] + ["\t".join(str(c) for c in r) for r in rows]
    return "\n".join(lines).encode("utf-8")


def _xlsx(rows, header=HEADER) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(header)
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _upload(client, headers, content, dry_run, filename="porty.tsv"):
    return client.post(
        f"/api/import/container-ports?dry_run={str(dry_run).lower()}",
        headers=headers, files={"file": (filename, content, "text/tab-separated-values")})


# --- parsowanie ---

def test_parse_tsv_and_xlsx_same_result():
    rows = [["ESIBZ", "IBIZA", "ES", "Spain"], ["ZZIBS", "IBSTOCK", "GB", "United Kingdom"]]
    parsed_tsv = _parse_cport_rows(_tsv(rows), "porty.tsv")
    parsed_xlsx = _parse_cport_rows(_xlsx(rows), "porty.xlsx")
    assert parsed_tsv == parsed_xlsx
    assert parsed_tsv[0] == {"code": "ESIBZ", "name": "IBIZA",
                             "country_code": "ES", "country_name": "Spain"}


def test_parse_sample_fixture():
    parsed = _parse_cport_rows(FIXTURE.read_bytes(), FIXTURE.name)
    assert len(parsed) == 188
    assert parsed[0]["code"] == "ZZIME"


# --- dopasowanie współrzędnych ---

def test_match_by_full_code():
    coords = match_coords("ESIBZ", "IBIZA", "ES")
    assert coords is not None
    lat, lon = coords
    assert 38 < lat < 40 and 0 < lon < 2          # Ibiza


def test_zz_code_not_matched_by_code_itself():
    # kod ZZ*** istnieje tylko u klienta — nie może trafić po samym kodzie
    # (ZZGDY nie jest kodem UN/LOCODE), ale GDYNIA/PL łapie się po nazwie
    coords = match_coords("ZZGDY", "GDYNIA", "PL")
    assert coords is not None
    lat, lon = coords
    assert 54 < lat < 55 and 18 < lon < 19


def test_match_by_country_and_name_normalized():
    assert match_coords("ZZXXX", "GÖTEBORG", "SE") is not None


def test_no_cross_country_guess():
    # śmieciowe dane wejściowe: ICD AHMEDABAD z krajem ID (Indonezja) — brak dopasowania
    assert match_coords("ZZICB", "ICD AHMEDABAD", "ID") is None
    assert match_coords("ZZ123", "NIEISTNIEJĄCY PORT XYZW", "PL") is None


def test_norm_name_strips_diacritics_and_parens():
    assert norm_name("Łódź (terminal)") == "LODZ"
    assert norm_name("I-Meduna di Livenza") == "I MEDUNA DI LIVENZA"


# --- endpoint importu: upsert + audyt ---

def test_import_upsert_and_counts(client, admin_headers, db_session):
    content = _tsv([
        ["ESIBZ", "IBIZA", "ES", "Spain"],
        ["ZZICB", "ICD AHMEDABAD", "ID", "Indonesia"],   # bez współrzędnych
        ["ESIBZ", "IBIZA", "ES", "Spain"],               # duplikat w pliku
    ])
    preview = _upload(client, admin_headers, content, True)
    assert preview.status_code == 200, preview.text
    assert preview.json()["counts"] == {"total": 3, "new": 2, "updated": 0,
                                        "with_coords": 1, "without_coords": 1,
                                        "duplicate": 1}
    assert db_session.scalars(select(ContainerPort)).all() == []   # dry-run bez zapisu

    done = _upload(client, admin_headers, content, False)
    assert done.status_code == 200, done.text
    stored = db_session.scalars(select(ContainerPort).order_by(ContainerPort.code)).all()
    assert [(p.code, p.lat is not None) for p in stored] == [("ESIBZ", True), ("ZZICB", False)]

    again = _upload(client, admin_headers, content, False)
    assert again.json()["counts"]["new"] == 0 and again.json()["counts"]["updated"] == 2
    assert len(db_session.scalars(select(ContainerPort)).all()) == 2

    logs = db_session.scalars(select(AuditLog).where(
        AuditLog.entity_type == "container_ports")).all()
    assert logs and "porty" in (logs[0].note or "").lower()


def test_import_needs_login(client):
    assert _upload(client, {}, _tsv([["ESIBZ", "IBIZA", "ES", "Spain"]]), True).status_code == 401


def test_import_sample_coverage(client, admin_headers):
    done = _upload(client, admin_headers, FIXTURE.read_bytes(), False,
                   filename=FIXTURE.name)
    assert done.status_code == 200, done.text
    counts = done.json()["counts"]
    assert counts["new"] == 188
    # większość realnych portów musi dostać współrzędne (śmieciowe ZZ/złe kraje nie)
    assert counts["with_coords"] > 100


# --- endpoint listy + with_coords + delete ---

def test_list_with_coords_only(client, admin_headers):
    _upload(client, admin_headers, _tsv([
        ["ESIBZ", "IBIZA", "ES", "Spain"],
        ["ZZICB", "ICD AHMEDABAD", "ID", "Indonesia"],
    ]), False)
    full = client.get("/api/container-ports", headers=admin_headers).json()
    assert [p["code"] for p in full] == ["ESIBZ", "ZZICB"]
    only = client.get("/api/container-ports?with_coords=true", headers=admin_headers).json()
    assert [p["code"] for p in only] == ["ESIBZ"]
    assert only[0]["lat"] and only[0]["lon"]


def test_delete_with_guard(client, admin_headers, db_session):
    _upload(client, admin_headers, _tsv([["ESIBZ", "IBIZA", "ES", "Spain"]]), False)
    port = db_session.scalar(select(ContainerPort).where(ContainerPort.code == "ESIBZ"))
    resp = client.delete(f"/api/container-ports/{port.id}", headers=admin_headers)
    assert resp.status_code == 204
    assert client.delete(f"/api/container-ports/{port.id}",
                         headers=admin_headers).status_code == 404
