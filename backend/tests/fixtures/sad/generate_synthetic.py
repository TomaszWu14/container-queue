"""Generator SYNTETYCZNYCH podglądów zgłoszeń SAD (układ wydruku WinSAD) do testów importu SAD.

Wszystkie firmy, numery, kontenery, faktury i kwoty są fikcyjne. Kwoty liczone tymi samymi
regułami co walidator (app/sad_import/validator.py), więc jedynym ostrzeżeniem jest stan AIS.
Odwzorowane pułapki układu parsera: dwie kolumny (x≈27 / x≈441), pozycja przechodząca na
kolejną stronę, numer dokumentu złamany po „-” (także na granicy stron), etykiety „[14⏎08]”.

Uruchomienie (wymaga reportlab i czcionki TTF z polskimi znakami):
    python tests/fixtures/sad/generate_synthetic.py
"""
import pathlib
import sys
import textwrap
from decimal import ROUND_HALF_UP, Decimal

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

OUT = pathlib.Path(__file__).resolve().parent
KURS = Decimal("3.7306")
VAT = Decimal(8)
FONTS = ["C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/Library/Fonts/Arial.ttf"]
LEFT_X, RIGHT_X, TOP_Y, LINE, SIZE = 27, 441, 800, 10.5, 7.2


def rhu(v: Decimal) -> Decimal:
    return v.quantize(Decimal(1), rounding=ROUND_HALF_UP)


def s(v: Decimal) -> str:
    """Decimal bez zbędnych zer i bez notacji wykładniczej („14127.6”, „0”)."""
    t = format(v.normalize(), "f")
    return t


def iso6346(prefix: str) -> str:
    """Numer kontenera z poprawną cyfrą kontrolną (prefix = 4 litery + 6 cyfr)."""
    val = {c: v for c, v in zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                                [10, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 23, 24, 25, 26, 27, 28,
                                 29, 30, 31, 32, 34, 35, 36, 37, 38])}
    total = sum((val[c] if c.isalpha() else int(c)) * 2 ** i for i, c in enumerate(prefix))
    return prefix + str(total % 11 % 10)


COMMON = {"importer_nip": "0000000000", "eori": "PL000000000000000", "zgl_nip": "0000000000",
          "odbiorca": "ACME SP. Z O.O.", "zglaszajacy": "DELTA BROKERS LOGISTICS SA",
          "uc": "PL999999"}

# Struktura (liczba pozycji, dokumentów, stawki, podziały stron) jak w prawdziwych drukach,
# wartości wymyślone.
DECLS = [
    {"numer": "7100001", "ref": "EACJC2601", "lrn": "26SEPDEMO1", "data": "2026-09-18",
     "wydruk": "2026-09-18 07:41", "kontener": iso6346("DEMU100001"), "sender": "EASTPORT TEXTILE CO LTD",
     "adres": "NO 1 HARBOUR ROAD, 100001 EASTPORT (CN)", "miejsce": "SHANGHAI, CN", "brutto": "5200",
     "items": [{"opis": "KOMBINEZONY OCHRONNE JEDNORAZOWE-12000 SZT", "cn": "62101092", "wf": "23950.40",
                "ak": ["17610.25", "95.10"], "ca": ["4600.30"], "netto": "4100.5", "opak": 1500,
                "stawka": "12", "metoda": "R",
                "docs": ["1DK7-DEMO26000001", "5DK1-PACKING LIST", "N325-DEMO2609A01-S", "N935-DEMO2609A01",
                         "7P21-DEKL.ZGODNOSCI"]}]},
    {"numer": "7100002", "ref": "EACJC2602", "lrn": "26SEPDEMO2", "data": "2026-09-16",
     "wydruk": "2026-09-16 10:12", "kontener": iso6346("QAXU200002"), "sender": "NORTHBRIDGE MEDICAL CO LTD",
     "adres": "NO 2 LAKE STREET, 200002 LAKESIDE (CN)", "miejsce": "NINGBO, CN", "brutto": "6300",
     "items": [{"opis": "OSŁONY JEDNORAZOWE NIEJAŁOWE-8000 SZT", "cn": "63079098", "wf": "20480.75",
                "ak": ["19100.00", "88.40"], "ca": ["4300.10"], "netto": "5400.25", "opak": 1200,
                "stawka": "6.3", "metoda": "R",
                "docs": ["1DK7-DEMO26000002", "5DK1-PACKING LIST", "N325-DEMO-2608-050-S", "N935-DEMO-2608-050",
                         "7P21-DEKL.ZGODNOSCI"]}]},
    {"numer": "7100003", "ref": "EACJC2603", "lrn": "26SEPDEMO3", "data": "2026-09-24",
     "wydruk": "2026-09-23 16:05", "kontener": iso6346("TSTU300003"), "sender": "DEMO MEDICAL PRODUCTS CO LTD",
     "adres": "NO 3 GARDEN AVE, 300003 EASTPORT (CN)", "miejsce": "WUHAN, CN", "brutto": "6100.4",
     "page_break_in_item": 1,
     "items": [{"opis": "KOMPRESY GAZOWE-6000000 SZT WRAZ Z PROBKAMI", "cn": "30059050", "wf": "19870.60",
                "ak": ["8700.50", "85.20"], "ca": ["5100.40"], "netto": "4980.6", "opak": 2000,
                "stawka": "0", "metoda": None,
                "docs": ["1DK7-DEMO26000003", "5DK1-PACKING LIST", "5DK2-.", "7P21-DEKL.ZGODNOSCI",
                         "N325-DEMO2606C01-S", "N935-DEMOS2606C01"]},
               {"opis": "OPASKA ELASTYCZNA TKANA-5000 SZT WRAZ Z PROBKAMI", "cn": "30059099", "wf": "512.30",
                "ak": ["130.60", "2.20"], "ca": ["80.15"], "netto": "88.4", "opak": 0,
                "stawka": "0", "metoda": None,
                "docs": ["1DK7-DEMO26000003", "5DK1-PACKING LIST", "5DK2-.", "7P21-DEKL.ZGODNOSCI",
                         "N325-DEMO2606C01-S", "N935-DEMOS2606C01"]}]},
    {"numer": "7100004", "ref": "EACJC2604", "lrn": "26SEPDEMO4", "data": "2026-09-26",
     "wydruk": "2026-09-26 09:30", "kontener": iso6346("ZZZU400004"), "sender": "SHIELDCO MEDICAL CO LTD",
     "adres": "NO 4 RIVER ROAD, 400004 EASTPORT (CN)", "miejsce": "XINGANG, CN", "brutto": "15800",
     "broken_invoice": True, "uzup": "1800000",
     "items": [{"opis": "RĘKAWICE NITRYLOWE DIAGNOSTYCZNE - 1800 KARTONÓW wraz z probkami", "cn": "40151200",
                "wf": "71200.00", "ak": ["16000.00", "310.25"], "ca": ["5400.80"], "netto": "14200",
                "opak": 1800, "stawka": "2", "metoda": "R",
                "docs": ["1DK7-DEMO/26/09/OSA", "5DK1-.", "7P21-CERTYFIKAT DEMO-04", "7P21-DEK.Z 01.09.2026",
                         "N935-DEMO2622079"]}]},
]


def compute(d: dict) -> None:
    """Uzupełnia kwoty pozycji i nagłówka (reguły walidatora)."""
    for it in d["items"]:
        wf, ak, ca = Decimal(it["wf"]), sum(map(Decimal, it["ak"])), sum(map(Decimal, it["ca"]))
        a00 = rhu(wf * KURS + ak)
        clo = a00 * Decimal(it["stawka"]) / 100
        b00 = rhu(a00 + rhu(clo) + ca)
        vat = b00 * VAT / 100
        it.update(a00=a00, clo=clo, clo_due=rhu(clo), b00=b00, vat=vat, vat_due=rhu(vat),
                  total=rhu(clo) + rhu(vat))
    d["wart"] = sum(Decimal(i["wf"]) for i in d["items"])
    d["opak"] = sum(i["opak"] for i in d["items"])
    d["sum_a00"] = sum(i["clo_due"] for i in d["items"])
    d["sum_b00"] = sum(i["vat_due"] for i in d["items"])


def header(d: dict) -> tuple[list[str], list[tuple[list[str], list[str]]]]:
    top = [f"Podgląd danych zgłoszenia celnego importowego nr {d['numer']}.",
           "Poniższe dane mogą nie być w pełni zgodne z potwierdzonym zgłoszeniem celnym (dane syntetyczne).",
           "Podstawowe dane Dane z programu WinSAD: Stan AIS: W przygotowaniu",
           f"Deklarowana data zgłoszenia: {d['data']}", f"Data wygenerowania wydruku: {d['wydruk']}",
           f"Numer referencyjny {d['ref']}", f"Numer LRN [12 09]: {d['lrn']}", "Firmy",
           f"Nadawca: {d['sender']}", f"Odbiorca: {COMMON['odbiorca']}", f"Zgłaszający: {COMMON['zglaszajacy']}"]
    left = ["Zgłoszenie Declaration [D]", "Importer [13 04]:",
            f"Rodzaj osoby: 2 (osoba prawna). NIP: {COMMON['importer_nip']}, REGON: 00000000000000, nr",
            f"identyfikacyjny: {COMMON['eori']}", "Zgłaszający [13 05]:",
            f"Rodzaj osoby: 2 (osoba prawna). NIP: {COMMON['zgl_nip']}, REGON: 00000000000000, nr",
            "identyfikacyjny: PL000000000000001", "Przedstawiciel [13 06]:",
            "Rodzaj przedstawicielstwa: 3 (pośrednie)", "Przesyłka Goods Shipments [GS]",
            f"Eksporter [13 01]: {d['sender']}. Adres: {d['adres']}",
            f"Szczegóły transportu [19 07]: Nr kontenera: {d['kontener']}, numery pozycji tow.: "
            + ", ".join(str(i + 1) for i in range(len(d["items"]))),
            "Lokalizacja towarów [16 15]: B (miejsce zatwierdzone), typ: Y, nr pozwolenia:",
            "PLTST000000000001, dod. identyfikator: 0", "Towary Goods Item [SI]"]
    right = ["Typ zgł. [11 01/02]: IM, A", f"UC zgłoszenia: {COMMON['uc']}",
             f"Liczba pozycji: {len(d['items'])}", f"Liczba opakowań: {d['opak']}",
             f"Kurs waluty [14 09]: {str(KURS).replace('.', ',')}", f"Masa brutto [18 04]: {d['brutto']}",
             "Wartość faktur [14", f"06]: {s(d['wart'])} USD", "Kontenery [19 01]: Tak",
             "Kraj przeznaczenia [16 03]: PL", "Kraj wysyłki [16 06]: CN", "Rodzaj transakcji [99 05]: 11",
             "Warunki dostawy [14 01]: FOB,", d["miejsce"]]
    return top, [(left, right)]


def doc_lines(docs: list[str], broken_invoice: bool) -> list[str]:
    """[12 03] w zawiniętych liniach; faktura może być złamana tuż po „N935-”."""
    parts = [f"{x} poz. 0" for x in docs]
    if broken_invoice:
        last = parts[-1].split("-", 1)
        return ["Dokumenty załączone [12 03]: " + "; ".join(parts[:-1]) + "; " + last[0] + "-", last[1]]
    head = "Dokumenty załączone [12 03]: " + "; ".join(parts[:3]) + ";"
    return [head, "; ".join(parts[3:])]


def item_blocks(d: dict, n: int, it: dict) -> list[tuple[list[str], list[str]]]:
    left_a = [f"Pozycja {n}", f"Towar: Opis [18 05]: {it['opis']}, kod CN [18 09]: {it['cn']}, kod TARIC: 00,",
              "krajowe kody dod. [18 07]: V020, X091, Z999",
              "Dokumenty poprzednie [12 01]: N337-DEMO0000 2026-09-01 10:00, nr pozycji tow.: 1"]
    docs = doc_lines(it["docs"], d.get("broken_invoice", False))
    met = f" {it['metoda']}" if it["metoda"] else ""
    left_b = ["Dodatkowe informacje [12 02]: DS001-DCT; PCS01-PL000000000000001",
              f"Dodatkowe odniesienia podatkowe [13 16]: Rola: FR7, nr VAT: PL{COMMON['importer_nip']}",
              f"Opakowania [18 06] (Liczba / rodzaj / oznaczenia): {it['opak']}/CT/.", "Cła i podatki [14 03]:",
              "Rodzaj opłaty Podstawa opłaty Kwota należnej Metoda płatn.",
              f"A00 Kwota: {s(it['a00'])} PLN, stawka opł.: {it['stawka']}%, {s(it['clo_due'])} PLN{met}",
              f"kwota opł.: {s(it['clo'])} PLN",
              f"B00 Kwota: {s(it['b00'])} PLN, stawka opł.: {s(VAT)}%, {s(it['vat_due'])} PLN G",
              f"kwota opł.: {s(it['vat'])} PLN", f"Kwota opłat i podatków ogółem [14 16]: {s(it['total'])} PLN"]
    ak = "; ".join(f"AK: {a} PLN" for a in it["ak"])
    ca = "; ".join(f"CA: {c} PLN" for c in it["ca"])
    right_a = ["Wartość fakturowa poz. [14", f"08]: {it['wf']}", "Metoda wyceny [14 10]: 1",
               "Preferencje [14 11]: 100", "Procedura [11 09]: 4000", "Kraj pochodzenia [16 08]: CN",
               f"Masa netto [18 01]: {it['netto']}"]
    if d.get("uzup"):
        right_a += ["Ilość w jedn. uzup. [18 02]:", d["uzup"]]
    right_b = [f"Wartość stat. [99 06]: {s(it['a00'])}", "Doliczenia i odliczenia [14 04]:", ak + ";", ca]
    return [(left_a + docs[:1], right_a), ("PAGE?",), (docs[1:] + left_b, right_b)]


def _wrap(line: str, width: int) -> list[str]:
    """Zawija tylko za długie linie (na spacjach) — celowe złamania („N935-”) zostają."""
    return textwrap.wrap(line, width, break_long_words=False, break_on_hyphens=False) or [line]


def build(d: dict) -> pathlib.Path:
    compute(d)
    top, head_blocks = header(d)
    flow: list = [("TOP", top), *head_blocks]
    for n, it in enumerate(d["items"], start=1):
        blocks = item_blocks(d, n, it)
        flow.append(blocks[0])
        if d.get("page_break_in_item") == n or (len(d["items"]) == 1 and n == 1):
            flow.append(("PAGE",))
        flow.append(blocks[2])
    flow.append((["Podsumowanie opłat:", "Rodzaj opłaty Kwota należnej opłaty Metoda płatności",
                  f"A00 {s(d['sum_a00'])} PLN" + (" R" if d["sum_a00"] else ""),
                  f"B00 {s(d['sum_b00'])} PLN G",
                  "Wydruk z programu firmy Huzar Software przygotowany na podstawie pliku ZC415"], []))
    path = OUT / f"SAD{d['numer']}.pdf"
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setTitle(f"SAD {d['numer']} (syntetyczny)")
    y = TOP_Y
    for block in flow:
        if block[0] == "PAGE":
            c.showPage()
            y = TOP_Y
            continue
        if block[0] == "PAGE?":
            continue
        if block[0] == "TOP":
            for line in block[1]:
                c.setFont("F", SIZE)
                c.drawString(LEFT_X, y, line)
                y -= LINE
            continue
        left = [w for line in block[0] for w in _wrap(line, 95)]
        right = [w for line in block[1] for w in _wrap(line, 34)]
        for i in range(max(len(left), len(right))):
            c.setFont("F", SIZE)
            if i < len(left):
                c.drawString(LEFT_X if not left[i].startswith("Pozycja ") else 274, y, left[i])
            if i < len(right):
                c.drawString(RIGHT_X, y, right[i])
            y -= LINE
        y -= LINE / 2
    c.save()
    return path


XML_DECL = {"numer": "7100005", "kontener": iso6346("DEMU500005"), "faktura": "DEMOS2607E01",
            "items": [("30059050", "9800.40", "1500.20"), ("30059099", "9650.30", "1440.10")]}


def build_xml() -> pathlib.Path:
    x = XML_DECL
    total = s(sum(Decimal(v) for _, v, _ in x["items"]))
    items = "\n".join(
        f'<PozycjeSADu P34KrajPochodz="CN" P38MasaNetto="{m}" P42WartoscPozycji="{v}">'
        f'<P33KodTowaru KodCN="{cn}00"/></PozycjeSADu>' for cn, v, m in x["items"])
    xml = (f'<?xml version="1.0" encoding="utf-8" ?>\n'
           f'<!-- syntetyczny eksport SADUE (dane fikcyjne) -->\n'
           f'<SADUE P15aKodKrajuWys="CN" P17aKodKrajuPrzeznacz="PL" P22WalutaSADu="USD">\n'
           f'<P1Kontekst IDSADu="{x["numer"]}" Dekl1="IM" Dekl2="A"/>\n'
           f'<ZestawySADu P22WartoscZestawu="{total}">\n<Kontenery Numer="{x["kontener"]}"/>\n'
           f'<DokumWymag KodDokum="N935" NrDokum="{x["faktura"]}"/>\n{items}\n</ZestawySADu>\n</SADUE>\n')
    path = OUT / f"SAD{x['numer']}.xml"
    path.write_text(xml, encoding="utf-8")
    return path


if __name__ == "__main__":
    font = next((f for f in FONTS if pathlib.Path(f).exists()), None)
    if not font:
        sys.exit("Brak czcionki TTF z polskimi znakami (FONTS).")
    pdfmetrics.registerFont(TTFont("F", font))
    for d in DECLS:
        print(build(d))
    print(build_xml())
