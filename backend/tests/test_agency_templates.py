"""Wzory plików dla agencji: domyślny wzór Symbole WinSAD (44 kolumny w kolejności agencji),
edycja z walidacją, nowa próbka od agencji zachowuje mapowanie znanych kolumn."""
import io

import openpyxl

from app.config import settings


def _xlsx(rows) -> bytes:
    wb = openpyxl.Workbook()
    for row in rows:
        wb.active.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _get(client, headers):
    resp = client.get("/api/agency-templates", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_default_winsad_template_matches_agency_layout(client, admin_headers):
    body = _get(client, admin_headers)
    tpl = body["templates"][0]
    names = [c["name"] for c in tpl["columns"]]
    assert tpl["key"] == "winsad_symbole" and len(names) == 44
    assert names[:3] == ["Symbol", "KodPCN", "KodTaric"] and names[-1] == "SaWazneInfWIT"
    assert {c["name"]: c["source"] for c in tpl["columns"]}["NazwaPolska"] == "name_pl"
    assert "const" in body["sources"] and tpl["has_sample"] is False


def test_edit_validates_and_saves(client, admin_headers):
    cols = _get(client, admin_headers)["templates"][0]["columns"]
    bad = [{**cols[0], "source": "nieznane"}, {**cols[1], "name": cols[0]["name"]}]
    resp = client.put("/api/agency-templates/winsad_symbole", headers=admin_headers, json={"columns": bad})
    assert resp.status_code == 422 and "nieznane źródło" in resp.json()["detail"]
    kraj = next(c for c in cols if c["name"] == "KodKrajuPoch")
    kraj["source"] = "supplier_country"
    resp = client.put("/api/agency-templates/winsad_symbole", headers=admin_headers, json={"columns": cols})
    assert resp.status_code == 200, resp.text
    saved = {c["name"]: c for c in _get(client, admin_headers)["templates"][0]["columns"]}
    assert saved["KodKrajuPoch"]["source"] == "supplier_country"
    assert client.put("/api/agency-templates/inny", headers=admin_headers,
                      json={"columns": cols}).status_code == 404


def test_new_sample_keeps_mapping_and_is_downloadable(client, admin_headers, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))
    data = _xlsx([["Symbol", "NowaKolumna", "KodPCN"], ["145851", "x", "48237090"]])
    resp = client.post("/api/agency-templates/winsad_symbole/sample", headers=admin_headers,
                       files={"file": ("SymboleAcme.xlsx", io.BytesIO(data), "application/octet-stream")})
    assert resp.status_code == 200, resp.text
    cols = resp.json()["columns"]
    assert [(c["name"], c["source"], c["example"]) for c in cols] == [
        ("Symbol", "ref", "145851"), ("NowaKolumna", "empty", "x"), ("KodPCN", "cn8", "48237090")]
    assert resp.json()["has_sample"] is True
    down = client.get("/api/agency-templates/winsad_symbole/sample", headers=admin_headers)
    assert down.status_code == 200 and down.content == data
    empty = _xlsx([[None, None]])
    assert client.post("/api/agency-templates/winsad_symbole/sample", headers=admin_headers,
                       files={"file": ("x.xlsx", io.BytesIO(empty), "application/octet-stream")}
                       ).status_code == 422
