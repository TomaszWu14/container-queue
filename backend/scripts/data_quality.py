"""Kontrole jakości danych (audyt DATA-007): 10 zapytań SQL z `scripts/data_quality/` na bazie
PostgreSQL, w sesji TYLKO DO ODCZYTU, z limitem czasu na zapytanie.

Uruchom z katalogu backend/ (w kontenerze: /app):
    python -m scripts.data_quality                      # raport tekstowy
    python -m scripts.data_quality --json               # raport JSON (np. do n8n / maila)
    python -m scripts.data_quality --fail-on-findings   # kod 1, gdy którakolwiek reguła coś znalazła

Każdy plik ma w nagłówku cel i „Oczekiwany wynik” — raport je przepisuje, bo część zapytań jest
informacyjna (np. rozkład wartości). „Znaleziska” = wiersze z kolumną `ile` > 0, a gdy zapytanie
nie ma kolumny `ile` — liczba zwróconych wierszy. Harmonogram i czytanie wyników:
docs/JAKOSC-DANYCH.md. Zapytania są kopią `audit/sql/data_*.sql` (źródło: audyt 2026-09-28).
"""
import argparse
import json
import pathlib
import re
import sys

from sqlalchemy.engine import make_url

from app.config import settings

CHECKS_DIR = pathlib.Path(__file__).resolve().parent / "data_quality"
STATEMENT_TIMEOUT = "120s"


def check_files(directory: pathlib.Path = CHECKS_DIR) -> list[pathlib.Path]:
    return sorted(directory.glob("data_*.sql"))


def statements(sql: str) -> list[str]:
    """Plik → instrukcje: bez linii-komentarzy `--`, podział na `;` kończącym linię."""
    body = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
    return [s.strip() for s in re.split(r";\s*(?:\n|$)", body) if s.strip()]


def describe(sql: str) -> tuple[str, str]:
    """(cel, oczekiwany wynik) z nagłówka pliku."""
    lines = [ln.lstrip("- ").strip() for ln in sql.splitlines() if ln.startswith("--")]
    goal = lines[0] if lines else ""
    expected = next((ln.split(":", 1)[1].strip() for ln in lines
                     if ln.lower().startswith("oczekiwany wynik")), "")
    return goal, expected


def _findings(columns: list[str], rows: list) -> int:
    if "ile" in columns:
        idx = columns.index("ile")
        return sum(1 for row in rows if (row[idx] or 0) > 0)
    return len(rows)


def run(conn, files: list[pathlib.Path], limit: int = 20) -> list[dict]:
    """Wykonuje kontrole na połączeniu DBAPI. Sesja read-only i timeout ustawiane PRZED
    zapytaniami; każda instrukcja we własnej transakcji — błąd jednej nie blokuje reszty."""
    cur = conn.cursor()
    cur.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
    cur.execute(f"SET statement_timeout = '{STATEMENT_TIMEOUT}'")
    conn.commit()
    report = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        goal, expected = describe(text)
        for number, sql in enumerate(statements(text), 1):
            entry = {"file": path.name, "statement": number, "goal": goal, "expected": expected,
                     "columns": [], "rows": 0, "findings": 0, "sample": [], "error": ""}
            cur = conn.cursor()
            try:
                cur.execute(sql)
                columns = [d[0] for d in cur.description or []]
                rows = cur.fetchall()
                entry.update(columns=columns, rows=len(rows), findings=_findings(columns, rows),
                             sample=[list(r) for r in rows[:limit]])
                conn.rollback()      # tylko odczyt — nic do zatwierdzenia
            except Exception as exc:  # noqa: BLE001 — raportujemy i idziemy dalej
                conn.rollback()
                entry["error"] = f"{type(exc).__name__}: {str(exc).strip()[:300]}"
            finally:
                cur.close()
            report.append(entry)
    return report


def exit_code(report: list[dict], fail_on_findings: bool = False) -> int:
    if any(e.get("error") for e in report):
        return 1
    if fail_on_findings and any(e.get("findings", e.get("rows", 0)) for e in report):
        return 1
    return 0


def _print_text(report: list[dict]) -> None:
    last = None
    for e in report:
        if e["file"] != last:
            print(f"\n=== {e['file']} — {e['goal']}\n    oczekiwane: {e['expected']}")
            last = e["file"]
        if e["error"]:
            print(f"  [{e['statement']}] BŁĄD: {e['error']}")
            continue
        print(f"  [{e['statement']}] wierszy: {e['rows']}, znaleziska: {e['findings']}")
        if e["sample"]:
            print("      " + " | ".join(e["columns"]))
            for row in e["sample"]:
                print("      " + " | ".join(str(v) for v in row))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Kontrole jakości danych (tylko odczyt)")
    parser.add_argument("--json", action="store_true", help="raport w JSON")
    parser.add_argument("--limit", type=int, default=20, help="ile przykładowych wierszy na zapytanie")
    parser.add_argument("--fail-on-findings", action="store_true",
                        help="kod wyjścia 1, gdy którakolwiek reguła coś znalazła")
    args = parser.parse_args(argv)
    if not make_url(settings.database_url).drivername.startswith("postgresql"):
        print("Kontrole wymagają PostgreSQL (DATABASE_URL) — SQL używa funkcji Postgresa.")
        return 2
    from app.database import engine
    conn = engine.raw_connection()
    try:
        report = run(conn, check_files(), limit=args.limit)
    finally:
        conn.close()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, default=str, indent=1))
    else:
        _print_text(report)
    return exit_code(report, args.fail_on_findings)


if __name__ == "__main__":
    sys.exit(main())
