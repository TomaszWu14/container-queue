"""Strażnik granicy doby: `created_at` itp. są naiwnym UTC (utcnow), a „dziś” to kalendarz PL.
`datetime.combine(dzień, time.min)` bez strefy daje północ UTC — między 00:00 a 02:00 czasu PL
alerty się dublowały, a terminy i filtry dat przesuwały o dobę (2026-09-28). Granice dnia licz
przez `pl_midnight_utc(dzień)` / `to_pl_date(at)`; wyjątek = świadomy wpis w ALLOWED z powodem."""
import pathlib
import re

APP = pathlib.Path(__file__).resolve().parents[1] / "app"
ALLOWED = {
    "models/enums.py",             # sam helper (podaje PL_TZ)
    "tracking/timeline.py",        # data → klucz sortowania osi czasu, bez porównań z UTC
}
NAIVE_DAY_BOUND = re.compile(r"combine\([^)]*time\.(min|max)\)")  # bez argumentu strefy


def test_no_naive_day_bounds_outside_helpers():
    offenders = []
    for path in APP.rglob("*.py"):
        rel = path.relative_to(APP).as_posix()
        if rel in ALLOWED:
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if NAIVE_DAY_BOUND.search(line):
                offenders.append(f"{rel}:{n}: {line.strip()}")
    assert not offenders, "Naiwna granica doby (użyj pl_midnight_utc / to_pl_date):\n" + "\n".join(offenders)
