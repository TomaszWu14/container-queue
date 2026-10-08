"""Strażnik: każda dosłowna ścieżka `/api/...` we froncie trafia w istniejącą trasę backendu.

Regresja: OrderDetailPage wołał `/api/zamowienia/{id}` (ścieżka SPA, nie API) → zawsze 404.
`${...}` we froncie i `{param}` w trasie pasują do dowolnego segmentu; literał może być
prefiksem trasy (baza, do której front dokleja resztę)."""
import pathlib
import re

from app.main import app

FRONT_SRC = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src"
LITERAL = re.compile(r"""(['"])(/api/[^'"\n]*)\1|`(/api/[^`]*)`""")
# ${...} → "*"; niedomknięte (zagnieżdżony template string) → reszta to "*"
PLACEHOLDER = re.compile(r"\$\{[^{}]*(\}|$)")


def _segments(path: str) -> list[str]:
    return path.strip("/").split("/")


def _matches(front: list[str], route: list[str]) -> bool:
    if len(route) < len(front):
        return False
    for f, r in zip(front, route):
        if f == r or r.startswith("{") or f == "*":
            continue
        if "*" in f and re.fullmatch(re.escape(f).replace(r"\*", ".*"), r):
            continue
        return False
    return True


def test_front_api_literals_hit_backend_routes():
    # openapi: app.routes trzyma dołączone routery jako obiekty bez `path`
    routes = [_segments(p) for p in app.openapi()["paths"] if p.startswith("/api")]
    unknown = set()
    for file in FRONT_SRC.rglob("*.ts*"):
        if ".test." in file.name:
            continue
        for m in LITERAL.finditer(file.read_text(encoding="utf-8")):
            raw = m.group(2) or m.group(3)
            path = re.split(r"[?#]", PLACEHOLDER.sub("*", raw))[0]
            if not any(_matches(_segments(path.rstrip("/")), r) for r in routes):
                unknown.add(f"{file.relative_to(FRONT_SRC).as_posix()}: {raw}")
    assert not unknown, "Ścieżki API bez trasy w backendzie:\n" + "\n".join(sorted(unknown))
