"""Strażnik: każda trasa API wymaga zalogowania (zależność get_current_user w drzewie
Depends), chyba że jest świadomie publiczna i wpisana do PUBLIC niżej. Zapomniany
`Depends` = endpoint otwarty dla świata — ten test to łapie w CI, nie na prodzie."""
from app.main import app
from app.security import get_current_user

# Każdy wpis = świadoma decyzja. Linki z {token} chroni sam token (weryfikacja w handlerze).
PUBLIC: set[tuple[str, str]] = {
    # logowanie i odzyskiwanie konta
    ("POST", "/api/auth/login"), ("POST", "/api/auth/logout"), ("POST", "/api/auth/refresh"),
    ("POST", "/api/auth/2fa/verify"), ("POST", "/api/auth/forgot-password"),
    ("POST", "/api/auth/reset-password"),
    # infrastruktura: monitoring, ekran logowania, raport błędów frontu, stary link
    ("GET", "/api/health"), ("GET", "/api/public/branding"), ("POST", "/api/client-error"),
    ("GET", "/api/health/deep"),   # OBS-009: sam status 200/503, szczegóły tylko dla admina
    ("GET", "/dzis"),
    # awizacja przez link dla spedytora/kierowcy
    ("GET", "/api/avizo/{token}"), ("POST", "/api/avizo/{token}"),
    ("GET", "/api/avizo/{token}/slots"), ("POST", "/api/avizo/{token}/propose"),
    ("GET", "/api/avizo/driver/{token}"), ("POST", "/api/avizo/driver/{token}"),
    # link kierowcy
    # link DLT
    ("GET", "/api/dlt/{token}"), ("POST", "/api/dlt/{token}/prepared"),
    ("POST", "/api/dlt/{token}/shipped"),
}


def _authed(dependant) -> bool:
    return any(d.call is get_current_user or _authed(d) for d in dependant.dependencies)


def _walk(routes):
    # FastAPI 0.139 trzyma include_router jako _IncludedRouter — jego trasy (z zależnościami
    # z include) są w effective_candidates(); zwykłe trasy app mają `dependant` wprost.
    for r in routes:
        if hasattr(r, "effective_candidates"):
            yield from _walk(r.effective_candidates())
        elif getattr(r, "dependant", None) is not None:
            yield r


def p_spa(r) -> bool:
    return r.path == "/{full_path:path}" and r.endpoint.__module__ == "app.main"


def _api_routes():
    for r in _walk(app.routes):
        if r.endpoint.__module__.startswith("tests"):
            continue  # trasy dopisane przez inne testy (np. /api/_boom_test w test_applog)
        if p_spa(r):
            continue  # fallback SPA (index.html panelu) — publiczny z założenia, istnieje tylko gdy
            # jest zbudowany frontend (obraz Dockera); bez tego testy w obrazie ≠ testy w CI
        for m in sorted(set(r.methods or ()) - {"HEAD", "OPTIONS"}):
            yield m, r.path, r


def test_walk_sees_all_routes():
    # bezpiecznik: zmiana wewnętrzna FastAPI nie może po cichu wyzerować strażnika
    assert len({(m, p) for m, p, _ in _api_routes()}) >= 300


def test_every_route_requires_auth_or_is_listed_public():
    open_routes = sorted((m, p) for m, p, r in _api_routes()
                         if not _authed(r.dependant) and (m, p) not in PUBLIC)
    assert not open_routes, "Trasy bez logowania (dodaj Depends albo wpis do PUBLIC):\n" + \
        "\n".join(f"  {m} {p}" for m, p in open_routes)


def test_public_list_has_no_stale_entries():
    # usunięta/przemianowana trasa nie może zostać na liście publicznych
    assert PUBLIC <= {(m, p) for m, p, _ in _api_routes()}
