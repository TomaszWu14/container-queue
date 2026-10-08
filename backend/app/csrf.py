"""Ochrona CSRF dla API uwierzytelnianego ciasteczkiem (audyt SEC-004).

SameSite=Lax nie chroni przed stroną z tej samej „witryny” — dla hosta-adresu IP to każda
usługa na tym IP, niezależnie od portu. Dlatego żądanie zmieniające stan (nie GET/HEAD/
OPTIONS), które niesie ciasteczko sesji, musi mieć:
  * nagłówek `X-Requested-With` (front wysyła go zawsze; obca strona nie doda go bez
    preflightu CORS, a CORS przepuszcza tylko jawne CORS_ORIGINS), albo
  * `Origin` (bez niego `Referer`) wskazujący nasz adres (PUBLIC_BASE_URL / Host).
Żądanie bez Origin i bez Referer przechodzi — przeglądarka zawsze dokłada Origin do
żądań zmieniających stan, więc to klient spoza przeglądarki (skrypt, test), nie atak CSRF.
Nagłówek Authorization (Bearer) też zwalnia z kontroli: obca strona go nie ustawi.
"""
from urllib.parse import urlparse

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .config import settings
from .security import ACCESS_COOKIE, REFRESH_COOKIE

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
CSRF_HEADER = "x-requested-with"


def origin_allowed(request, source: str) -> bool:
    """Czy Origin/Referer wskazuje nasz adres (host:port z PUBLIC_BASE_URL albo Host)."""
    allowed = {urlparse(settings.public_base_url).netloc, request.headers.get("host", "")}
    return urlparse(source).netloc in allowed - {""}


def csrf_rejected(request) -> bool:
    """True, gdy żądanie z ciasteczkiem sesji może pochodzić z obcej strony."""
    if request.method in SAFE_METHODS or not request.url.path.startswith("/api"):
        return False
    headers = request.headers
    if "authorization" in headers or CSRF_HEADER in headers:
        return False
    if ACCESS_COOKIE not in request.cookies and REFRESH_COOKIE not in request.cookies:
        return False
    source = headers.get("origin") or headers.get("referer")
    return bool(source) and not origin_allowed(request, source)


class CsrfOriginMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if csrf_rejected(request):
            return JSONResponse(status_code=403,
                                content={"detail": "Niedozwolone źródło żądania."})
        return await call_next(request)
