"""Kreator profilu dostawcy (etap 4): próbki, podgląd tabeli, test bez zapisu faktur, role.
Tekst i tabele stron podstawiamy przez szew `extractor.read_pages` (jak test_invoices_api)."""
import io

import pytest
from pypdf import PdfWriter

from app import supplier_profile_lab as lab
from app.config import settings
from app.database import SessionLocal
from app.invoices import extractor
from app.invoices.extractor import PageData
from app.models import InvoiceJob, Material

from .conftest import login

CI_TABLE = [
    ["Pos", "Art. Code", "Goods", "Pieces", "Unit price", "Line total"],
    ["1", "GLV-1", "Gloves", "1,000", "0.25", "250.00"],
    ["2", "GLV-2", "Gloves XL", "20", "10", "200.00"],
    ["", "TOTAL", "", "", "", "450.00"],
]
PL_TABLE = [["Art. Code", "Pieces", "N.W. (kg)"], ["GLV-1", "1,000", "12.5"]]
PAGES = [PageData(text="COMMERCIAL INVOICE No. FV-1", tables=[CI_TABLE]),
         PageData(text="PACKING LIST", tables=[PL_TABLE])]


def _pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


@pytest.fixture()
def lab_env(client, admin_headers, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))
    monkeypatch.setattr(extractor, "read_pages", lambda path: PAGES)
    company = client.get("/api/companies", headers=admin_headers).json()[0]["id"]
    sid = client.post("/api/suppliers", headers=admin_headers,
                      json={"name": "Glove Co", "company_id": company}).json()["id"]
    return sid, tmp_path


def _upload(client, headers, sid, name="ci.pdf"):
    return client.post(f"/api/suppliers/{sid}/doc-profile/samples", headers=headers,
                       files={"file": (name, io.BytesIO(_pdf()), "application/pdf")})


def test_map_variants_and_split():
    assert lab.map_variants({"ref": ["A", "B"], "qty": ["Q"], "net": []}) == [
        {"ref": "A", "qty": "Q"}, {"ref": "B", "qty": "Q"}]
    assert lab.map_variants({}) == [{}]
    assert lab.split_pages(PAGES, "") == {"ci": [0], "pl": [1]}
    assert lab.split_pages(PAGES, "No. FV") == {"ci": [1], "pl": [0]}     # znacznik profilu wygrywa


def test_upload_preview_delete(client, admin_headers, lab_env):
    sid, tmp = lab_env
    r = _upload(client, admin_headers, sid)
    assert r.status_code == 201, r.text
    sample = r.json()
    assert len(list(tmp.iterdir())) == 1
    profile = client.get(f"/api/suppliers/{sid}/doc-profile", headers=admin_headers).json()
    assert profile["status"] == "draft" and [s["id"] for s in profile["samples"]] == [sample["id"]]

    prev = client.get(f"/api/suppliers/{sid}/doc-profile/samples/{sample['id']}/preview",
                      headers=admin_headers).json()
    assert prev["found"] and prev["headers"][1] == "Art. Code" and prev["pages"] == {"ci": [1], "pl": [2]}
    assert prev["detected"]["ref"] == 1 and prev["detected"]["qty"] == 3 and len(prev["rows"]) == 3
    pl = client.get(f"/api/suppliers/{sid}/doc-profile/samples/{sample['id']}/preview?kind=pl",
                    headers=admin_headers).json()
    assert pl["headers"] == ["Art. Code", "Pieces", "N.W. (kg)"]

    assert _upload(client, admin_headers, sid, "x.txt").status_code == 422
    assert client.delete(f"/api/suppliers/{sid}/doc-profile/samples/{sample['id']}",
                         headers=admin_headers).status_code == 204
    assert list(tmp.iterdir()) == []
    assert client.delete(f"/api/suppliers/{sid}/doc-profile/samples/{sample['id']}",
                         headers=admin_headers).status_code == 404


def test_run_profile_test_without_saving_invoices(client, admin_headers, lab_env, monkeypatch):
    sid, _ = lab_env
    with SessionLocal() as db:
        db.add(Material(ref_code="GLV-1", ref_norm="GLV1"))
        db.commit()
    _upload(client, admin_headers, sid)
    body = {"ci_map": {"ref": ["Art. Code"], "qty": ["Pieces"], "net": ["Line total"]},
            "pl_map": {"ref": ["Art. Code"], "qty": ["Pieces"]}, "tol_amount_pct": 0.5}
    r = client.post(f"/api/suppliers/{sid}/doc-profile/test", headers=admin_headers, json=body)
    assert r.status_code == 200, r.text
    res = r.json()["results"][0]
    assert r.json()["ok"] and res["ok"]
    assert (res["ci_items"], res["pl_items"], res["matched"]) == (2, 1, 1)
    assert (res["sum_items"], res["total"], res["sum_ok"]) == (450.0, 450.0, True)
    assert res["pages"] == {"ci": [1], "pl": [2]}
    saved = client.get(f"/api/suppliers/{sid}/doc-profile", headers=admin_headers).json()
    assert saved["samples"][0]["last_test"]["ci_items"] == 2 and saved["samples"][0]["last_test_at"]
    with SessionLocal() as db:
        assert db.query(InvoiceJob).count() == 0                       # tryb bez zapisu faktur

    # tolerancja 0 i suma niezgodna → błąd sum_mismatch
    bad_table = [row[:] for row in CI_TABLE]
    bad_table[-1][5] = "500.00"
    monkeypatch.setattr(extractor, "read_pages",
                        lambda path: [PageData(text="COMMERCIAL INVOICE", tables=[bad_table])])
    res = client.post(f"/api/suppliers/{sid}/doc-profile/test", headers=admin_headers,
                      json={**body, "tol_amount_pct": 0}).json()["results"][0]
    assert res["errors"] == ["sum_mismatch"] and not res["ok"]

    # koszt dodatkowy bez indeksu (450 + 50 = 500) domyka sumę faktury
    with_charge = [*CI_TABLE[:-1], ["", "Freight charge", "", "", "", "50.00"], ["", "TOTAL", "", "", "", "500.00"]]
    monkeypatch.setattr(extractor, "read_pages",
                        lambda path: [PageData(text="COMMERCIAL INVOICE", tables=[with_charge])])
    res = client.post(f"/api/suppliers/{sid}/doc-profile/test", headers=admin_headers,
                      json={**body, "tol_amount_pct": 0}).json()["results"][0]
    assert res["sum_ok"] and res["charges"] == [{"desc": "Freight charge", "amount": "50.00"}]

    # kwoty nieczytelne (suma 0) i strona PL bez pozycji → czerwony wynik, nie „przechodzi”
    no_amounts = [row[:5] + ["?"] for row in CI_TABLE]
    monkeypatch.setattr(extractor, "read_pages", lambda path: [
        PageData(text="COMMERCIAL INVOICE", tables=[no_amounts]),
        PageData(text="PACKING LIST", tables=[[["Something"], ["x"]]])])
    res = client.post(f"/api/suppliers/{sid}/doc-profile/test", headers=admin_headers,
                      json=body).json()["results"][0]
    assert res["errors"] == ["no_amounts", "no_pl_items"] and not res["ok"]


def test_test_requires_samples_and_roles(client, admin_headers, lab_env):
    sid, _ = lab_env
    assert client.post(f"/api/suppliers/{sid}/doc-profile/test", headers=admin_headers,
                       json={}).status_code == 422
    for login_, role in (("log.p", "logistics"), ("zak.p", "purchasing")):
        r = client.post("/api/users", headers=admin_headers, json={
            "login": login_, "password": "haslo123", "role": role, "view_all_companies": True,
            "email": f"{login_}@example.com"})
        assert r.status_code == 201, r.text
    log_h, zak_h = login(client, "log.p", "haslo123"), login(client, "zak.p", "haslo123")
    url = f"/api/suppliers/{sid}/doc-profile"
    assert client.get(url, headers=log_h).status_code == 200            # odczyt: logistyka
    assert client.get(url, headers=zak_h).status_code == 200            # odczyt: zakupy
    assert client.put(url, headers=log_h, json={}).status_code == 403   # edycja: tylko admin
    assert _upload(client, log_h, sid).status_code == 403
    assert client.post(f"{url}/test", headers=log_h, json={}).status_code == 403
