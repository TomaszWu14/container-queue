"""Benchmark pamięci pipeline'u faktur (PDF → strony → OCR/ekstrakcja).

Mierzy szczytowe RSS procesu podczas czytania każdego PDF-a przez
`app.invoices.extractor.read_pages` (ta sama ścieżka, którą idzie realny import:
pdfplumber + OCR Tesseract dla stron bez warstwy tekstowej).

Uruchomienie (z katalogu backend/, wymaga `pip install psutil` — tylko dev):
  python -m scripts.bench_invoice_memory katalog_z_pdfami [--dpi 300]

Wynik: tabela plik | strony | peak RSS Δ | czas — do decyzji o mem_limit kontenera.
"""
import argparse
import pathlib
import sys
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

try:
    import psutil
except ImportError:  # narzędzie deweloperskie — psutil nie jest zależnością aplikacji
    raise SystemExit("Zainstaluj psutil: pip install psutil") from None

from app.invoices.extractor import read_pages  # noqa: E402


class PeakSampler:
    """Próbkuje RSS procesu co 50 ms w tle — peak_wset bywa niedostępny na Linuksie."""

    def __init__(self) -> None:
        self._proc = psutil.Process()
        self._stop = threading.Event()
        self.peak = 0

    def __enter__(self) -> "PeakSampler":
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def _run(self) -> None:
        while not self._stop.is_set():
            self.peak = max(self.peak, self._proc.memory_info().rss)
            time.sleep(0.05)

    def __exit__(self, *exc) -> None:
        self._stop.set()
        self._thread.join(timeout=1)
        self.peak = max(self.peak, self._proc.memory_info().rss)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", help="katalog z plikami .pdf do przemielenia")
    parser.add_argument("--dpi", type=int, default=None,
                        help="nadpisz DPI renderu OCR (domyślnie z config)")
    args = parser.parse_args()
    if args.dpi:
        import os
        os.environ["OCR_DPI"] = str(args.dpi)  # pydantic-settings: pole ocr_dpi

    pdfs = sorted(pathlib.Path(args.folder).glob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"Brak plików .pdf w {args.folder}")

    base_rss = psutil.Process().memory_info().rss
    print(f"RSS startowe: {base_rss / 2**20:.0f} MB")
    print(f"{'plik':40} {'strony':>6} {'peak Δ MB':>10} {'peak MB':>8} {'czas s':>7}")
    worst = 0
    for pdf in pdfs:
        started = time.perf_counter()
        with PeakSampler() as sampler:
            try:
                pages = read_pages(str(pdf))
                n_pages = len(pages)
            except Exception as exc:  # noqa: BLE001 — benchmark raportuje, nie przerywa
                print(f"{pdf.name:40} BŁĄD: {exc}")
                continue
        elapsed = time.perf_counter() - started
        delta = (sampler.peak - base_rss) / 2**20
        worst = max(worst, sampler.peak)
        print(f"{pdf.name:40} {n_pages:>6} {delta:>10.0f} {sampler.peak / 2**20:>8.0f} "
              f"{elapsed:>7.1f}")

    print(f"\nNajwyższy peak RSS: {worst / 2**20:.0f} MB — mem_limit kontenera ustaw "
          f"z zapasem ~2x (baza + FastAPI + współbieżne żądania).")


if __name__ == "__main__":
    main()
