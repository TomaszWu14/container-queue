"""Bramka wgrania dokumentu (2026-10-06): uszkodzony PDF → 422, dokument innego kontenera → 409
z numerem właściwego, brak numeru / skan → wpuszczony z ostrzeżeniem, ten sam plik drugi raz
w tym samym kontenerze → 409 „już jest” (zgłoszony dubel z 15:23)."""
import io

from app.config import settings
from app.document_gate import CONFLICT, OK, UNCERTAIN, UNREADABLE, check_pdf
from app.models import Container
from tests.conftest import pdf_bytes
from tests.test_invoice_conformity import _container
from tests.test_invoices_checks import _setup
from tests.test_sad_parse import _pdf_with_text

OWN = "MSDU0806613"          # numer kontenera z _container (poprawna cyfra kontrolna)
OTHER = "CAIU9756747"        # z realnego B/L, który trafił do złego kontenera


def _text_pdf(tmp_path, text: str) -> bytes:
    path = tmp_path / "doc.pdf"
    _pdf_with_text(path, [[(40, 800 - 12 * i, line) for i, line in enumerate(text.split("\n"))]])
    return path.read_bytes()


def _post(client, headers, cid, data, name="bl.pdf"):
    return client.post(f"/api/containers/{cid}/attachments", headers=headers,
                       files={"file": (name, io.BytesIO(data), "application/pdf")})


def test_check_pdf_statuses(tmp_path):
    body = "BILL OF LADING STS26071107 SHIPPED ON BOARD 1295 CARTONS"
    assert check_pdf(b"%PDF-1.4 atrapa", OWN)["status"] == UNREADABLE
    assert check_pdf(_text_pdf(tmp_path, f"{body}\n{OWN}/FJ28486896 40HQ"), OWN)["status"] == OK
    other = check_pdf(_text_pdf(tmp_path, f"{body}\n{OTHER}/FJ28486896 40HQ"), OWN)
    assert other["status"] == CONFLICT and other["found"] == [OTHER] and OTHER in other["message"]
    # B/L na kilka kontenerów, w tym nasz — dotyczy tego kontenera
    assert check_pdf(_text_pdf(tmp_path, f"{body}\n{OTHER} 40HQ\n{OWN} 40HQ"), OWN)["status"] == OK
    assert check_pdf(_text_pdf(tmp_path, f"{body} bez numeru kontenera"), OWN)["status"] == UNCERTAIN
    assert check_pdf(pdf_bytes("skan"), OWN)["status"] == UNCERTAIN      # bez warstwy tekstowej


def test_upload_gate_and_duplicates(client, admin_headers, db_session, monkeypatch, tmp_path):
    company, sup = _setup(db_session, monkeypatch, tmp_path)
    cid = _container(client, admin_headers, company, sup)
    assert db_session.get(Container, cid).container_no == OWN
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path / "up"))

    bad = _post(client, admin_headers, cid, b"%PDF-1.4 atrapa")
    assert bad.status_code == 422 and "PDF" in bad.json()["detail"]
    wrong = _post(client, admin_headers, cid, _text_pdf(tmp_path, f"BILL OF LADING\n{OTHER} 40HQ"))
    assert wrong.status_code == 409 and OTHER in wrong.json()["detail"]

    ok = _post(client, admin_headers, cid, _text_pdf(tmp_path, f"BILL OF LADING\n{OWN} 40HQ"))
    assert ok.status_code == 201 and ok.json()["gate_warning"] is None
    unsure = _post(client, admin_headers, cid, pdf_bytes("skan"), name="skan.pdf")
    assert unsure.status_code == 201 and "Skan" in unsure.json()["gate_warning"]

    again = _post(client, admin_headers, cid, pdf_bytes("skan"), name="skan (2).pdf")
    assert again.status_code == 409 and "już jest" in again.json()["detail"] and "skan.pdf" in again.json()["detail"]
    files = client.get(f"/api/containers/{cid}/attachments", headers=admin_headers).json()
    assert sorted(f["filename"] for f in files) == ["bl.pdf", "skan.pdf"]
    # inne pliki niż PDF: bez bramki treści, ale dubel nadal wykrywany
    xls = client.post(f"/api/containers/{cid}/attachments", headers=admin_headers,
                      files={"file": ("k.xlsx", io.BytesIO(b"xlsx-1"), "application/octet-stream")})
    assert xls.status_code == 201
    assert client.post(f"/api/containers/{cid}/attachments", headers=admin_headers,
                       files={"file": ("k2.xlsx", io.BytesIO(b"xlsx-1"), "application/octet-stream")}
                       ).status_code == 409


def test_conflict_reads_whole_document(tmp_path):
    """§4 pkt 30 (decyzja 29): inny numer na 1. stronie, nasz dopiero na 6. — dokument dotyczy
    nas (zbiorczy B/L); bez naszego numeru w całości — nadal konflikt."""
    head = [(40, 800, "BILL OF LADING STS26071107 SHIPPED ON BOARD"), (40, 780, f"{OTHER} 40HQ")]
    filler = [[(40, 800, f"strona {n} — warunki przewozu i klauzule armatora")] for n in range(2, 6)]
    ours = tmp_path / "zbiorczy.pdf"
    _pdf_with_text(ours, [head, *filler, [(40, 800, f"ZALACZNIK: {OWN} 40HQ")]])
    assert check_pdf(ours.read_bytes(), OWN)["status"] == OK
    foreign = tmp_path / "obcy.pdf"
    _pdf_with_text(foreign, [head, *filler, [(40, 800, "ZALACZNIK: brak dalszych kontenerow")]])
    result = check_pdf(foreign.read_bytes(), OWN)
    assert result["status"] == CONFLICT and OTHER in result["message"]
