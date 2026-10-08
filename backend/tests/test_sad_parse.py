"""Odczyt draftu SAD (PR 2, spec 2026-09-29-agencja-draft-sad §2): etykiety rubryk → pola,
pozycje od „Kod towaru”, pole nieodczytane jawnie w `unread`, brak tekstu / nie-PDF → błąd
zamiast zgadywania."""
from pypdf import PdfWriter

from app.invoices import extractor, sad_parse, sad_winsad
from app.invoices.extractor import PageData

SAD = """ZGŁOSZENIE CELNE — DRAFT
15a Kod kraju wysyłki/eksportu: CN
Nr kontenera: MSDU0806613
22 Waluta i całkowita kwota fakturowana: USD 1 205,50
44 Dodatkowe informacje/Przedstawione dokumenty: N380 T-1; N380 T-2
Pozycja 1
33 Kod towaru: 9018 39 00 00
34a Kod kraju pochodzenia: CN
38 Masa netto (kg): 12,500
42 Cena pozycji: 950,00
Pozycja 2
33 Kod towaru: 40151900
38 Masa netto (kg): 3
41 Jednostki uzupełniające: 775
42 Cena pozycji: 255,50
"""


def test_parse_text_reads_header_and_items():
    out = sad_parse.parse_text([SAD])
    assert (out["currency"], out["total"]) == ("USD", "1205.5")
    assert (out["country_dispatch"], out["country_origin"]) == ("CN", "CN")
    assert out["container"] == "MSDU0806613" and out["layout"] == "generic"
    assert [(i["cn"], i["value"], i["net_mass"], i["suppl_qty"]) for i in out["items"]] == [
        ("90183900", "950", "12.5", None), ("40151900", "255.5", "3", "775")]
    assert out["unread"] == [] and out["error"] is None and "T-2" in out["text"]


def test_unread_fields_are_explicit_never_guessed():
    out = sad_parse.parse_text(["33 Kod towaru: 90183900\n42 Cena pozycji: 10,00\n"])
    assert out["total"] is None and out["items"][0]["net_mass"] is None
    assert {"item": None, "field": "total"} in out["unread"]
    assert {"item": 1, "field": "net_mass"} in out["unread"]
    assert sad_parse.parse_text([""])["error"] == "no_text"
    reversed_order = sad_parse.parse_text(["22 Waluta i całkowita kwota fakturowana 1 305,50 EUR"])
    assert (reversed_order["currency"], reversed_order["total"]) == ("EUR", "1305.5")
    trailing = sad_parse.parse_text(["33 Kod towaru: 90183900\n38 Masa netto (kg): 12,500.\n"])
    assert trailing["items"][0]["net_mass"] == "12.5"             # kropka kończąca zdanie


def test_parse_file_pages_ocr_flag_and_errors(monkeypatch, tmp_path):
    monkeypatch.setattr(extractor, "read_pages",
                        lambda path: [PageData(text=SAD), PageData(text="", ocr=True)])
    out = sad_parse.parse_file("draft.pdf")
    assert out["pages"] == 2 and out["ocr"] is True and len(out["items"]) == 2
    monkeypatch.undo()
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"to nie jest PDF")
    broken = sad_parse.parse_file(str(bad))
    assert broken["error"] == "unreadable_pdf" and broken["pages"] == 0
    assert sad_parse.page_count(str(bad)) == 0


def test_page_png_renders_real_pdf(tmp_path):
    path = tmp_path / "draft.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with open(path, "wb") as fh:
        writer.write(fh)
    assert sad_parse.page_count(str(path)) == 1
    assert sad_parse.page_png(str(path), 0).startswith(b"\x89PNG")


# --- układ WinSAD (Delta Brokers, PR 5): dane fikcyjne, kształt jak prawdziwy wydruk --------------

# tekst po złożeniu kolumn przez sad_winsad.read_pages: etykiety złamane między liniami
# („[14⏎08]”), kod CN w następnej linii, numer faktury (N935) rozcięty przez koniec linii
WINSAD = """Podgląd danych zgłoszenia celnego importowego nr 1.
Dane z programu WinSAD: Stan AIS:W przygotowaniu
Szczegóły transportu [19 07]: Nr kontenera: MSDU0806613, numery pozycji tow.: 1, 2
Liczba pozycji: 2
Kurs waluty [14 09]: 3,7306
Masa brutto [18 04]: 18.4
Wartość faktur [14
06]: 1205.5 USD
Kraj wysyłki [16 06]: CN
Pozycja 1
Towar: Opis [18 05]: KOMPRESY, kod CN [18 09]:
90183900, kod TARIC: 00
Dokumenty załączone [12 03]: 5DK1-PACKING LIST poz. 0; N935-
T-1 poz. 0; N935-T-2 poz. 0
Wartość fakturowa poz. [14
08]: 950
Kraj pochodzenia [16 08]: CN
Masa netto [18 01]: 12.5
Wartość stat. [99 06]: 3544
Pozycja 2
Towar: Opis [18 05]: RĘKAWICE, kod CN [18 09]: 40151900, kod TARIC: 00
Wartość fakturowa poz. [14
08]: 255.5
Kraj pochodzenia [16 08]: CN
Masa netto [18 01]: 3
Ilość w jedn. uzup. [18 02]:
775
Wydruk z programu firmy Huzar Software"""


def test_winsad_fields_items_and_split_labels():
    fields, declared = sad_winsad.parse(WINSAD)
    assert declared == 2
    assert (fields["currency"], fields["total"], fields["country_dispatch"], fields["container"]) \
        == ("USD", "1205.5", "CN", "MSDU0806613")
    assert [(i["no"], i["cn"], i["value"], i["net_mass"], i["suppl_qty"], i["origin"])
            for i in fields["items"]] == [(1, "90183900", "950", "12.5", None, "CN"),
                                          (2, "40151900", "255.5", "3", "775", "CN")]


def test_winsad_missing_item_is_unread():
    text = WINSAD.replace("Liczba pozycji: 2", "Liczba pozycji: 3")
    fields, declared = sad_winsad.parse(text)
    out = sad_parse._finish(fields, text, "winsad", declared)
    assert {"item": None, "field": "items"} in out["unread"]      # zadeklarowane 3, odczytane 2


def _pdf_with_text(path, pages: list[list[tuple[int, int, str]]]) -> None:
    """Minimalny PDF z warstwą tekstową (Helvetica, tylko ASCII) — bez reportlab."""
    objects = {1: b"<< /Type /Catalog /Pages 2 0 R >>",
               3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"}
    kids = []
    for index, texts in enumerate(pages):
        page_id, content_id = 4 + 2 * index, 5 + 2 * index
        stream = "".join(f"BT /F1 8 Tf {x} {y} Td ({t}) Tj ET\n" for x, y, t in texts).encode()
        objects[page_id] = (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 596 842] "
                            b"/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % content_id)
        objects[content_id] = b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream)
        kids.append(b"%d 0 R" % page_id)
    objects[2] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (b" ".join(kids), len(kids))
    out, offsets = bytearray(b"%PDF-1.4\n"), {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += b"%d 0 obj\n%s\nendobj\n" % (number, objects[number])
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offsets[n] for n in sorted(objects))
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    path.write_bytes(bytes(out))


def test_winsad_pdf_two_columns_across_pages(tmp_path):
    """Pełna ścieżka: kolumny czytane osobno, pozycja 1 zaczyna się na stronie 1, a jej pola
    z prawej kolumny i dokumenty kończą się na stronie 2 — przed nagłówkiem pozycji 2."""
    left, right = 30, 440
    page1 = [(left, 800, "Podglad danych zgloszenia celnego importowego nr 1."),
             (left, 790, "Dane z programu WinSAD: Stan AIS:W przygotowaniu"),
             (left, 700, "Szczegoly transportu [19 07]: Nr kontenera: MSDU0806613"),
             (right, 740, "Liczba pozycji: 2"), (right, 720, "Wartosc faktur [14"),
             (right, 712, "06]: 1205.5 USD"), (right, 700, "Kraj wysylki [16 06]: CN"),
             (left, 600, "Pozycja 1"),
             (left, 590, "Towar: Opis [18 05]: KOMPRESY, kod CN [18 09]:"),
             (left, 582, "90183900, kod TARIC: 00"),
             (right, 590, "Wartosc fakturowa poz. [14"), (right, 582, "08]: 950")]
    page2 = [(left, 800, "Dokumenty zalaczone [12 03]: N935-T-1 poz. 0"),
             (right, 800, "Kraj pochodzenia [16 08]: CN"), (right, 790, "Masa netto [18 01]: 12.5"),
             (left, 700, "Pozycja 2"),
             (left, 690, "Towar: Opis [18 05]: REKAWICE, kod CN [18 09]: 40151900"),
             (right, 690, "Wartosc fakturowa poz. [14 08]: 255.5"),
             (right, 680, "Masa netto [18 01]: 3"),
             (right, 670, "Ilosc w jedn. uzup. [18 02]:"), (right, 662, "775"),
             (left, 100, "Wydruk z programu firmy Huzar Software")]
    path = tmp_path / "winsad.pdf"
    _pdf_with_text(path, [page1, page2])
    out = sad_parse.parse_file(str(path))
    assert (out["layout"], out["pages"], out["unread"]) == ("winsad", 2, [])
    assert (out["total"], out["currency"], out["container"]) == ("1205.5", "USD", "MSDU0806613")
    assert [(i["cn"], i["value"], i["net_mass"], i["suppl_qty"]) for i in out["items"]] == [
        ("90183900", "950", "12.5", None), ("40151900", "255.5", "3", "775")]


def test_non_winsad_pdf_goes_generic(tmp_path):
    path = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with open(path, "wb") as fh:
        writer.write(fh)
    assert sad_winsad.read_pages(str(path)) is None
    assert sad_winsad.read_pages(str(tmp_path / "brak.pdf")) is None
