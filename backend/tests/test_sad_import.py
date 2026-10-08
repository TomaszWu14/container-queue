"""Import SAD z WinSAD (app/sad_import): parser, walidacja, raport Excel, CLI — na czterech
syntetycznych podglądach z tests/fixtures/sad (generate_synthetic.py)."""
import copy
import datetime
import io
import os
import pathlib
import shutil
import subprocess  # nosec B404 — LibreOffice i CLI w teście, argumenty stałe
import sys
from decimal import Decimal

import openpyxl
import pypdf
import pytest
from openpyxl.utils import get_column_letter

from app.sad_import.__main__ import main as cli_main
from app.sad_import.excel import build_workbook
from app.sad_import.parser import SadFormatError, Zgloszenie, parse_sad
from app.sad_import.validator import ERROR, OK, WARN, najgorszy, validate

BACKEND = pathlib.Path(__file__).resolve().parents[1]
FIXTURES = BACKEND / "tests" / "fixtures" / "sad"
NUMERY = ["7100001", "7100002", "7100003", "7100004"]
DZIS = datetime.date(2026, 9, 30)
SHEETS = ["Zgłoszenia", "Pozycje", "Walidacja", "Dokumenty"]
STAN_AIS = "stan AIS: zgłoszenie przyjęte / zwolnione"
EXCEL_ERRORS = ("#VALUE!", "#NAME?", "#REF!", "#DIV/0!", "#N/A", "#NUM!", "#NULL!")


def _pdf(numer: str) -> pathlib.Path:
    return FIXTURES / f"SAD{numer}.pdf"


@pytest.fixture(scope="module")
def parsed() -> dict[str, Zgloszenie]:
    return {n: parse_sad(_pdf(n)) for n in NUMERY}


def _blank_pdf() -> bytes:
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=595, height=842)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# --- parser ------------------------------------------------------------------------------

# SAD, poz., wart. fakt., A00 (podstawa, stawka %, należna, metoda), B00 (podstawa, należna,
# metoda), ΣAK, ΣCA — przepisane ręcznie z PDF
EXPECTED = [
    ("7100001", 1, "23950.40", ("107055", "12", "12847", "R"), ("124502", "9960", "G"),
     "17705.35", "4600.30"),
    ("7100002", 1, "20480.75", ("95594", "6.3", "6022", "R"), ("105916", "8473", "G"),
     "19188.40", "4300.10"),
    ("7100003", 1, "19870.60", ("82915", "0", "0", None), ("88015", "7041", "G"),
     "8785.70", "5100.40"),
    ("7100003", 2, "512.30", ("2044", "0", "0", None), ("2124", "170", "G"),
     "132.80", "80.15"),
    ("7100004", 1, "71200.00", ("281929", "2", "5639", "R"), ("292969", "23438", "G"),
     "16310.25", "5400.80"),
]


@pytest.mark.parametrize("numer,nr,wartosc,a00,b00,ak,ca", EXPECTED)
def test_parser_item_values(parsed, numer, nr, wartosc, a00, b00, ak, ca):
    z = parsed[numer]
    p = next(p for p in z.pozycje if p.nr == nr)
    assert p.wartosc_fakturowa == Decimal(wartosc)
    clo, vat = p.oplata("A00"), p.oplata("B00")
    assert clo is not None and vat is not None
    assert (clo.podstawa, clo.stawka, clo.kwota_nalezna) == tuple(Decimal(v) for v in a00[:3])
    assert clo.metoda == a00[3]
    assert (vat.podstawa, vat.kwota_nalezna, vat.metoda) == (Decimal(b00[0]), Decimal(b00[1]), b00[2])
    assert p.suma_ak == Decimal(ak) and p.suma_ca == Decimal(ca)
    amounts = [p.wartosc_fakturowa, p.masa_netto, p.wartosc_stat, p.kwota_ogolem,
               *p.doliczenia_ak, *p.doliczenia_ca]
    amounts += [v for o in p.oplaty for v in (o.podstawa, o.stawka, o.kwota_wyliczona,
                                              o.kwota_nalezna) if v is not None]
    assert all(isinstance(v, Decimal) for v in amounts)


@pytest.mark.parametrize("numer,kontener", [("7100001", "DEMU1000010"), ("7100002", "QAXU2000028"),
                                            ("7100003", "TSTU3000039"), ("7100004", "ZZZU4000045")])
def test_parser_header(parsed, numer, kontener):
    z = parsed[numer]
    assert z.numer == numer and z.kontenery == [kontener]
    assert z.kurs == Decimal("3.7306") and isinstance(z.kurs, Decimal)
    assert isinstance(z.masa_brutto, Decimal) and isinstance(z.wartosc_faktur, Decimal)
    assert z.liczba_pozycji == len(z.pozycje)
    assert all(isinstance(kwota, Decimal) for kwota, _ in z.podsumowanie.values())


def test_parser_item_continued_on_next_page(parsed):
    z = parsed["7100003"]
    assert z.podsumowanie == {"A00": (Decimal(0), None), "B00": (Decimal(7211), "G")}
    first, second = z.pozycje
    assert second.opis == "OPASKA ELASTYCZNA TKANA-5000 SZT WRAZ Z PROBKAMI"
    # dane pozycji 1 ze strony 2 trafiły do pozycji 1, nie do 2
    assert first.wartosc_stat == Decimal(82915)
    assert first.doliczenia_ak == [Decimal("8700.5"), Decimal("85.20")]
    assert first.doliczenia_ca == [Decimal("5100.4")]
    assert second.wartosc_stat == Decimal(2044)
    assert second.doliczenia_ak == [Decimal("130.60"), Decimal("2.20")]
    assert second.doliczenia_ca == [Decimal("80.15")]


def test_parser_documents(parsed):
    assert parsed["7100003"].pozycje[0].faktury == ["DEMOS2606C01"]
    assert parsed["7100003"].pozycje[0].proformy == ["DEMO2606C01-S"]
    assert parsed["7100004"].pozycje[0].faktury == ["DEMO2622079"]   # złamany w PDF między liniami
    assert parsed["7100004"].pozycje[0].proformy == []
    assert parsed["7100001"].pozycje[0].faktury == ["DEMO2609A01"]
    assert parsed["7100001"].pozycje[0].proformy == ["DEMO2609A01-S"]
    assert parsed["7100002"].pozycje[0].faktury == ["DEMO-2608-050"]


def test_parser_reads_stream_like_path(parsed):
    z = parse_sad(io.BytesIO(_pdf("7100003").read_bytes()))
    assert z == parsed["7100003"]


@pytest.mark.parametrize("data", [_blank_pdf(), b"garbage, not a PDF", b""])
def test_parser_rejects_non_winsad(data):
    with pytest.raises(SadFormatError):
        parse_sad(io.BytesIO(data))


# --- walidacja ---------------------------------------------------------------------------

@pytest.mark.parametrize("numer", NUMERY)
def test_validator_fixtures_only_ais_warning(parsed, numer):
    wyniki = validate(parsed[numer], dzis=DZIS)
    assert not [w for w in wyniki if w.status == ERROR]
    niezgodne = [(w.regula, w.odczytane, w.status) for w in wyniki if w.status != OK]
    assert niezgodne == [(STAN_AIS, "W przygotowaniu", WARN)]
    assert najgorszy(wyniki) == WARN


def test_validator_detects_tampering(parsed):
    z = copy.deepcopy(parsed["7100001"])
    clo, vat = z.pozycje[0].oplata("A00"), z.pozycje[0].oplata("B00")
    assert clo is not None and clo.podstawa is not None
    assert vat is not None and vat.kwota_nalezna is not None
    clo.podstawa += 5
    vat.kwota_nalezna += 1
    z.kontenery = ["DEMU1000011"]                               # cyfra kontrolna 8 → 9
    z.importer_nip = z.importer_nip[:-1] + str((int(z.importer_nip[-1]) + 1) % 10)
    status = {(w.pozycja, w.regula): w.status for w in validate(z, dzis=DZIS)}
    for rule in [(1, "wartość celna (A00) = wart. fakt. × kurs + ΣAK"),
                 (1, "wartość celna (A00) = wartość stat. [99 06]"),
                 (1, "A00: kwota wyliczona = podstawa × stawka"),
                 (1, "podstawa VAT (B00) = A00 + cło + ΣCA"),
                 (1, "B00: należna = zaokrąglenie kwoty wyliczonej"),
                 (1, "Σ należnych = kwota ogółem [14 16]"),
                 (None, "Σ należnych B00 = podsumowanie opłat"),
                 (None, "kontener: cyfra kontrolna ISO 6346"),
                 (None, "NIP importera: cyfra kontrolna"),
                 (None, "nr VAT FR7 [13 16] = PL + NIP importera")]:
        assert status[rule] == ERROR, rule
    assert status[(None, "Σ należnych A00 = podsumowanie opłat")] == OK
    assert status[(1, "masa netto > 0")] == OK


# --- Excel -------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def xlsx(parsed) -> bytes:
    zgloszenia = [parsed[n] for n in NUMERY]
    return build_workbook(zgloszenia, [validate(z, dzis=DZIS) for z in zgloszenia]).getvalue()


def _headers(ws) -> dict[str, int]:
    return {cell.value: cell.column for cell in ws[1]}


def _row(ws, numer: str, poz: int | None = None) -> int:
    cols = _headers(ws)
    for r in range(2, ws.max_row + 1):
        if ws.cell(r, 1).value == numer and (poz is None or ws.cell(r, cols["Poz."]).value == poz):
            return r
    raise AssertionError(f"brak wiersza {numer}/{poz}")


def test_excel_sheets_and_layout(xlsx):
    wb = openpyxl.load_workbook(io.BytesIO(xlsx))
    assert wb.sheetnames == SHEETS
    for ws in wb:
        assert ws.freeze_panes == "A2"
        assert ws.auto_filter.ref == f"A1:{get_column_letter(ws.max_column)}{ws.max_row}"
        assert all(c.font.bold and c.font.name == "Arial" for c in ws[1])
        assert all(c.font.name == "Arial" and not c.font.bold for c in ws[2])
        assert all((ws.column_dimensions[get_column_letter(c.column)].width or 0) >= 6 for c in ws[1])
    assert wb["Zgłoszenia"].max_row == 1 + 4
    assert wb["Pozycje"].max_row == 1 + 5
    assert wb["Dokumenty"].max_row == 1 + 27


def test_excel_types_and_formats(xlsx):
    wb = openpyxl.load_workbook(io.BytesIO(xlsx))
    ws = wb["Pozycje"]
    c, r = _headers(ws), _row(ws, "7100001", 1)
    cell = ws.cell(r, c["A00 podstawa"])
    assert cell.value == 107055 and isinstance(cell.value, int | float)
    assert cell.number_format == "#,##0.00"
    assert ws.cell(r, c["A00 stawka"]).value == pytest.approx(0.12)
    assert ws.cell(r, c["A00 stawka"]).number_format == "0.0%"
    assert ws.cell(_row(ws, "7100002", 1), c["A00 stawka"]).value == pytest.approx(0.063)
    assert ws.cell(r, c["Kurs [14 09]"]).value == pytest.approx(3.7306)
    assert ws.cell(r, c["Kurs [14 09]"]).number_format == "0.0000"
    assert ws.cell(r, c["ΣAK (doliczenia)"]).value == pytest.approx(17705.35)
    for name, value in [("TARIC", "00"), ("CN [18 09]", "62101092"), ("Nr SAD", "7100001"),
                        ("Kontener(y)", "DEMU1000010"), ("Faktura(y) N935", "DEMO2609A01"),
                        ("Proforma(y) N325", "DEMO2609A01-S"), ("LRN", "26SEPDEMO1")]:
        assert ws.cell(r, c[name]).value == value and ws.cell(r, c[name]).data_type == "s", name

    ws = wb["Zgłoszenia"]
    c, r = _headers(ws), _row(ws, "7100001")
    for name in ("Importer NIP", "Zgłaszający NIP", "Importer EORI", "Nr SAD", "LRN"):
        assert ws.cell(r, c[name]).data_type == "s", name
    assert ws.cell(r, c["Importer NIP"]).value == "0000000000"
    data = ws.cell(r, c["Data zgłoszenia"])
    assert data.is_date and data.value.date() == datetime.date(2026, 9, 18)
    assert data.number_format == "yyyy-mm-dd"
    assert ws.cell(r, c["Data wydruku"]).value == datetime.datetime(2026, 9, 18, 7, 41)
    assert ws.cell(r, c["Σ cło A00 (należne)"]).value == 12847
    assert ws.cell(r, c["Σ VAT B00 (należne)"]).value == 9960
    assert ws.cell(r, c["Masa brutto [18 04]"]).number_format == "#,##0.00"
    assert ws.cell(r, c["Status walidacji"]).value == WARN
    assert ws.cell(r, c["Status walidacji"]).fill.fgColor.rgb.endswith("FFEB9C")


def test_excel_control_formulas(xlsx):
    ws = openpyxl.load_workbook(io.BytesIO(xlsx))["Pozycje"]
    c = _headers(ws)
    col = {k: get_column_letter(c[h]) for k, h in [
        ("fakt", "Wartość fakturowa [14 08]"), ("kurs", "Kurs [14 09]"), ("ak", "ΣAK (doliczenia)"),
        ("ca", "ΣCA (transport w UE)"), ("a00", "A00 podstawa"), ("clo", "A00 należna (cło)"),
        ("b00", "B00 podstawa"), ("celna", "Wartość celna wyliczona"),
        ("vat", "Podstawa VAT wyliczona")]}
    for r in range(2, ws.max_row + 1):
        f = {k: f"{v}{r}" for k, v in col.items()}
        assert ws.cell(r, c["Wartość celna wyliczona"]).value == \
            f"=ROUND({f['fakt']}*{f['kurs']}+{f['ak']},0)"
        assert ws.cell(r, c["Podstawa VAT wyliczona"]).value == \
            f"=ROUND({f['a00']}+{f['clo']}+{f['ca']},0)"
        roznice = [ws.cell(r, i) for h, i in c.items() if h.startswith("Różnica")]
        assert [x.value for x in roznice] == [f"={f['a00']}-{f['celna']}", f"={f['b00']}-{f['vat']}"]
        assert all(x.data_type == "f" for x in roznice)


def test_excel_validation_sheet_fills(xlsx, parsed):
    ws = openpyxl.load_workbook(io.BytesIO(xlsx))["Walidacja"]
    assert [c.value for c in ws[1]] == ["Nr SAD", "Pozycja", "Reguła", "Oczekiwane", "Odczytane",
                                        "Status"]
    assert ws.max_row - 1 == sum(len(validate(parsed[n], dzis=DZIS)) for n in NUMERY)
    colours = {"OK": "C6EFCE", "WARN": "FFEB9C", "ERROR": "FFC7CE"}
    seen = set()
    for r in range(2, ws.max_row + 1):
        cell = ws.cell(r, 6)
        assert cell.fill.fgColor.rgb.endswith(colours[cell.value])
        seen.add(cell.value)
    assert seen == {"OK", "WARN"}


def test_excel_documents_sheet(xlsx):
    ws = openpyxl.load_workbook(io.BytesIO(xlsx))["Dokumenty"]
    rows = {tuple(c.value for c in row) for row in ws.iter_rows(min_row=2)}
    assert ("7100004", 1, "N935", "DEMO2622079") in rows
    assert ("7100003", 2, "N325", "DEMO2606C01-S") in rows


def test_excel_text_from_pdf_is_never_a_formula(parsed):
    z = copy.deepcopy(parsed["7100001"])
    z.pozycje[0].opis = '=HYPERLINK("http://x","klik")'
    ws = openpyxl.load_workbook(build_workbook([z], [[]]))["Pozycje"]
    cell = ws.cell(2, _headers(ws)["Opis [18 05]"])
    assert cell.value == z.pozycje[0].opis and cell.data_type == "s"


def test_excel_requires_aligned_results(parsed):
    with pytest.raises(ValueError):
        build_workbook([parsed["7100001"]], [])


def _soffice(src: pathlib.Path, outdir: pathlib.Path, profile: pathlib.Path) -> pathlib.Path | None:
    """xlsx → xlsx przez LibreOffice (przeliczenie formuł); osobny profil = bez kolizji xdist."""
    subprocess.run([shutil.which("soffice") or "soffice", f"-env:UserInstallation={profile.as_uri()}",
                    "--headless", "--calc", "--convert-to", "xlsx", "--outdir", str(outdir), str(src)],
                   capture_output=True, timeout=180, check=False)  # nosec B603
    out = outdir / src.name
    return out if out.exists() else None


@pytest.mark.skipif(not shutil.which("soffice"), reason="brak LibreOffice (soffice)")
def test_excel_formulas_recalculate_in_libreoffice(xlsx, tmp_path):
    src = tmp_path / "raport.xlsx"
    src.write_bytes(xlsx)
    result = _soffice(src, tmp_path / "out", tmp_path / "lo")
    if result is None:
        probe = tmp_path / "probe.xlsx"
        wb = openpyxl.Workbook()
        wb.active["A1"] = "=1+1"
        wb.save(probe)
        if _soffice(probe, tmp_path / "probe_out", tmp_path / "lo") is None:
            pytest.skip("LibreOffice bez modułu Calc — nie otwiera żadnego xlsx")
        pytest.fail("LibreOffice nie otworzył raportu, choć prosty xlsx otwiera")
    formulas = openpyxl.load_workbook(src)
    values = openpyxl.load_workbook(result, data_only=True)
    checked = 0
    for ws in formulas:
        for row in ws.iter_rows():
            for cell in row:
                if cell.data_type != "f":
                    continue
                value = values[ws.title][cell.coordinate].value
                assert value not in EXCEL_ERRORS, (ws.title, cell.coordinate, value)
                assert isinstance(value, int | float), (ws.title, cell.coordinate, value)
                checked += 1
    assert checked == 5 * 4
    ws = values["Pozycje"]
    for header, col in _headers(ws).items():
        if header.startswith("Różnica"):
            assert all(abs(ws.cell(r, col).value) <= 1 for r in range(2, ws.max_row + 1)), header


# --- CLI ---------------------------------------------------------------------------------

def test_cli_subprocess_writes_report(tmp_path):
    out = tmp_path / "r.xlsx"
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run([sys.executable, "-m", "app.sad_import", *(str(_pdf(n)) for n in NUMERY),
                           "-o", str(out)], cwd=BACKEND, env=env, capture_output=True,
                          encoding="utf-8", timeout=180, check=False)  # nosec B603
    assert proc.returncode == 0, proc.stderr
    assert all(f"SAD {n}" in proc.stdout for n in NUMERY)
    assert openpyxl.load_workbook(out).sheetnames == SHEETS


def test_cli_bad_file_reported_and_others_continue(tmp_path, capsys):
    bad = tmp_path / "inny.pdf"
    bad.write_bytes(_blank_pdf())
    out = tmp_path / "r.xlsx"
    code = cli_main([str(bad), str(tmp_path / "brak.pdf"), str(_pdf("7100003")), "-o", str(out)])
    captured = capsys.readouterr()
    assert code == 1
    assert "inny.pdf" in captured.err and "WinSAD" in captured.err and "brak.pdf" in captured.err
    assert "SAD 7100003, pozycji 2, status" in captured.out and "WARN" in captured.out
    wb = openpyxl.load_workbook(out)
    assert wb["Zgłoszenia"].max_row == 2


def test_cli_nothing_parsed_writes_nothing(tmp_path, capsys):
    bad = tmp_path / "inny.pdf"
    bad.write_bytes(b"not a pdf")
    out = tmp_path / "r.xlsx"
    assert cli_main([str(bad), "-o", str(out)]) == 1
    assert not out.exists()
    assert "inny.pdf" in capsys.readouterr().err
