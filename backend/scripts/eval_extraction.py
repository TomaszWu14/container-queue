"""Ewaluacja ekstrakcji faktur offline (audyt AI-004): przypadki wzorcowe → % poprawnych pozycji.

Uruchom z katalogu backend/ (lokalnie albo w kontenerze: /app):
    python -m scripts.eval_extraction                     # przypadki wzorcowe z repo
    python -m scripts.eval_extraction <katalog> --min 95  # własne; kod 1, gdy wynik < progu

Przypadek = plik .json:
    {"name": "…", "column_map": "ref=Item No.; qty=Q'ty" (opcjonalnie),
     "pages": [{"text": "…", "tables": [[["nagłówek", …], [komórki…]]], "ocr": false}]
       ALBO "pdf": "faktura.pdf" (ścieżka względem pliku .json),
     "expected": {"invoice_number": "FV/1", "items": [{"ref": "…", "qty": "…", "net": "…"}]}}

Przypadki z "pages" nie dotykają sieci ani OCR — sprawdzają rozpoznanie kolumn i pozycji
(test CI: tests/test_llm_obserwowalnosc.py). Przypadki z "pdf" czytają prawdziwy plik, więc
przy skanie idą przez Tesseract i — gdy ustawiony OLLAMA_URL — model obrazowy: tak porównuje
się wyniki przed i po zmianie modelu (OCR_VISION_MODEL). Do repo trafiają WYŁĄCZNIE
zanonimizowane dokumenty (bez danych osobowych i cen kontrahentów).
Pozycja jest poprawna, gdy każde pole z "expected" zgadza się co do znaku; wynik =
poprawne / (oczekiwane + nadmiarowe), więc zmyślone pozycje też obniżają ocenę.
"""
import argparse
import json
import pathlib
import sys

DEFAULT_CASES = pathlib.Path(__file__).resolve().parent / "eval_extraction_cases"


def _parse(case: dict, base: pathlib.Path):
    from app.invoices import extractor
    column_map = extractor.parse_column_map(case.get("column_map", "")) or None
    if case.get("pdf"):
        return extractor.parse_pdf(str(base / case["pdf"]), column_map)
    pages = [extractor.PageData(text=p.get("text", ""), tables=p.get("tables", []),
                                ocr=bool(p.get("ocr"))) for p in case.get("pages", [])]
    return extractor.parse_pages(pages, column_map)


def score_case(case: dict, base: pathlib.Path) -> dict:
    doc = _parse(case, base)
    expected = case["expected"]
    found = {item["ref"]: item for item in doc.items}
    failures, correct = [], 0
    for want in expected["items"]:
        got = found.get(want["ref"])
        wrong = ["brak pozycji"] if got is None else [
            f"{k}: {got.get(k)!r} ≠ {v!r}" for k, v in want.items() if str(got.get(k)) != str(v)]
        if wrong:
            failures.append(f"{case['name']} / {want['ref']}: {', '.join(wrong)}")
        else:
            correct += 1
    extra = sorted(set(found) - {w["ref"] for w in expected["items"]})
    failures += [f"{case['name']} / {ref}: pozycja nadmiarowa" for ref in extra]
    number_ok = doc.invoice_number == expected.get("invoice_number", doc.invoice_number)
    if not number_ok:
        failures.append(f"{case['name']}: nr faktury {doc.invoice_number!r} ≠ "
                        f"{expected['invoice_number']!r}")
    return {"expected": len(expected["items"]), "correct": correct, "extra": len(extra),
            "number_ok": number_ok, "failures": failures}


def evaluate(cases_dir) -> dict:
    cases_dir = pathlib.Path(cases_dir)
    results = []
    for path in sorted(cases_dir.glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        case.setdefault("name", path.stem)
        results.append(score_case(case, path.parent))
    expected = sum(r["expected"] for r in results)
    correct = sum(r["correct"] for r in results)
    extra = sum(r["extra"] for r in results)
    denominator = expected + extra
    return {"cases": len(results), "items_expected": expected, "items_correct": correct,
            "items_extra": extra,
            "invoice_numbers_ok": sum(r["number_ok"] for r in results),
            "accuracy_pct": round(100 * correct / denominator, 1) if denominator else 100.0,
            "failures": [f for r in results for f in r["failures"]]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("cases", nargs="?", default=str(DEFAULT_CASES))
    parser.add_argument("--min", type=float, default=0.0, help="próg %% poprawnych pozycji")
    args = parser.parse_args(argv)
    report = evaluate(args.cases)
    for failure in report["failures"]:
        print("  ✗", failure)
    print(f"Przypadki: {report['cases']}, pozycje: {report['items_correct']}/"
          f"{report['items_expected']} poprawne, nadmiarowe: {report['items_extra']}, "
          f"nr faktury OK: {report['invoice_numbers_ok']}/{report['cases']} → "
          f"{report['accuracy_pct']}%")
    return 1 if report["accuracy_pct"] < args.min else 0


if __name__ == "__main__":
    sys.exit(main())
