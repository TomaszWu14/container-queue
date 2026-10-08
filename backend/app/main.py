import asyncio
import logging
import os
import pathlib
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from starlette.middleware.base import BaseHTTPMiddleware

from . import master_quality
from .applog import RequestLogMiddleware, applog_loop
from .config import settings
from .csrf import CsrfOriginMiddleware
from .database import SessionLocal
from .db_errors import integrity_error_handler
from .logfile import LOG_FORMAT, RequestIdFilter, attach_file_handler, request_id_var
from .print_button import CSP_HASH as PRINT_CSP_HASH
from .db_bootstrap import bootstrap, ensure_new_columns  # noqa: F401 — re-eksport (testy, skrypty)
from .jobs import build_jobs, job_loop, split_jobs
from .leader import leader_loop
from .rate_limit import assert_worker_config
from .routers import (
    admin,
    agency_templates,
    archive_upload,
    intake,
    analytics,
    assistant,
    audit_read,
    auth,
    avatars,
    avizo,
    avizo_forwarder,
    avizo_requests,
    checklist,
    complaints,
    consolidation,
    containers,
    customer_orders,
    customs,
    data_subject,
    dictionaries,
    documents,
    driver,
    forwarding,
    health,
    imports,
    inbox,
    invoice_agency,
    document_tiles,
    invoice_checks,
    invoices,
    knowledge,
    dlt,
    logs,
    materials,
    notifications,
    pallets,
    paz,
    portal,
    purchase_orders,
    purchasing,
    queue_calendar,
    quotes,
    receipts,
    sad_drafts,
    sad_import,
    search,
    supplier_aliases,
    supplier_maps,
    supplier_profiles,
    supplier_samples,
    system,
    tracking,
    warehouse_ops,
    sp_materials,
    watchers,
)
from .security import api_limiter, client_ip

# bez tego root logger nie ma handlera i logi INFO aplikacji (np. ślad audytu
# usunięć) giną na produkcji — uvicorn konfiguruje tylko loggery uvicorn.*
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format=LOG_FORMAT,
)

logger = logging.getLogger(__name__)

from .redaction import (  # noqa: E402,F401 — re-eksport (testy, routery)
    _PUBLIC_TOKEN_PATH_RE, _QUERY_TOKEN_RE, _SENTRY_SENSITIVE, _redact_message_fields,
    _redact_text, _scrub_sensitive, _sentry_before_send, init_sentry, redact_tokens,
)


class AvizoTokenLogFilter(logging.Filter):
    """Maskuje tokeny publicznych linków w komunikacie i argumentach rekordu logu."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_tokens(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(redact_tokens(a) for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: redact_tokens(v) for k, v in record.args.items()}
        try:   # token sklejony z formatu i argumentu ("/avizo/%s", tok)
            msg = record.getMessage()
        except Exception:  # noqa: BLE001 — zły format zgłosi handler, filtr nie może rzucić
            return True
        if redact_tokens(msg) != msg:
            record.msg, record.args = redact_tokens(msg), ()
        return True


_avizo_log_filter = AvizoTokenLogFilter()
for _name in ("uvicorn.access", "uvicorn.error"):
    logging.getLogger(_name).addFilter(_avizo_log_filter)
for _handler in logging.getLogger().handlers:   # logi aplikacji (propagują do roota)
    _handler.addFilter(RequestIdFilter())
    _handler.addFilter(_avizo_log_filter)
if settings.log_file:   # OBS-007: trwały plik (wolumen) — te same filtry co stdout
    try:
        attach_file_handler(settings.log_file, _avizo_log_filter)
    except OSError:   # zły katalog/uprawnienia nie mogą zatrzymać startu — zostaje stdout
        logging.getLogger(__name__).exception("LOG_FILE niedostępny: %s", settings.log_file)

_START_TIME = time.monotonic()  # do /api/health uptime_s — moment importu modułu (start procesu)

# to NIE są sekrety, tylko lista niebezpiecznych wartości domyślnych, którą wykrywamy
INSECURE_DEFAULTS = {"secret_key": "change-me-in-production",  # nosec B105
                     "admin_password": "admin123"}  # nosec B105


def _warn_ollama_url() -> None:
    """AI-006: Ollama bez uwierzytelniania — odrzucony adres = AI wyłączone + ostrzeżenie."""
    from urllib.parse import urlsplit

    from .llm import is_internal_host, url_problem
    url = settings.ollama_url.strip()
    if not url:
        return
    problem = url_problem(url)
    parts = urlsplit(url)
    if problem:
        logger.warning("OLLAMA_URL odrzucony (%s) — funkcje AI wyłączone.", problem)
    elif parts.scheme == "http" and not is_internal_host(parts.hostname or ""):
        logger.warning("OLLAMA_URL po HTTP z OLLAMA_ALLOW_REMOTE=true — skany faktur "
                       "idą bez szyfrowania; użyj https albo sieci Dockera.")


def validate_settings() -> None:
    """Fail fast: produkcja nie może wystartować z domyślnymi sekretami ani bez
    bezpiecznych cookies (uwierzytelnianie po HTTP = przejęcie sesji)."""
    assert_worker_config()   # BUILD-003: >1 worker tylko na PG; każde środowisko
    is_prod = settings.environment.lower() in ("production", "prod")
    insecure = [name for name, default in INSECURE_DEFAULTS.items()
                if getattr(settings, name) == default]
    if is_prod and not settings.secure_cookies:
        if settings.allow_insecure_http:
            logger.warning("ALLOW_INSECURE_HTTP=true — produkcja po HTTP, sesje do przejęcia w sieci; "
                           "włącz HTTPS i SECURE_COOKIES=true.")
        else:
            insecure.append("secure_cookies")
    if is_prod and settings.bcrypt_rounds < 12:
        # niższy koszt = hashe haseł łamalne offline szybciej; 4 jest tylko dla testów
        insecure.append("bcrypt_rounds (min. 12)")
    if is_prod and len(settings.secret_key) < 32:
        # słaby (choć niedomyślny) sekret HS256 jest łamalny offline → wymuszamy min. 32 znaki
        insecure.append("secret_key (min. 32 znaki)")
    if is_prod and not settings.public_base_url:
        # bez tego linki e-mail (reset hasła) budują się z nagłówka Host = host-header injection
        insecure.append("public_base_url")
    if is_prod and settings.automation_api_token and len(settings.automation_api_token) < 32:
        # token serwisowy n8n jest sekretem długoterminowym bez wygaśnięcia — krótki
        # da się zgadnąć, a otwiera API z uprawnieniami konta serwisowego
        insecure.append("automation_api_token (min. 32 znaki)")
    _warn_ollama_url()
    if settings.automation_webhook_url and not settings.automation_webhook_secret:
        logger.warning("AUTOMATION_WEBHOOK_URL bez AUTOMATION_WEBHOOK_SECRET — zdarzenia "
                       "lecą bez podpisu HMAC; zabezpiecz webhook n8n inaczej (header auth).")
    if not insecure:
        return
    message = ("Konfiguracja wymaga zmiany dla produkcji: "
               + ", ".join(f"{n.upper()}" for n in insecure))
    if is_prod:
        raise RuntimeError(message)
    logger.warning("%s (dozwolone tylko poza produkcją, ENVIRONMENT=%s)",
                   message, settings.environment)




@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_settings()
    bootstrap()
    # zrzut dziennika serwera biega na KAŻDEJ instancji (bufor jest per-proces, więc
    # nawet instancja wtórna musi sama zrzucać własny bufor do bazy)
    tasks = [asyncio.create_task(applog_loop())]
    if not settings.run_background_jobs:
        # instancja wtórna (drugi serwer na wspólnej bazie) — serwuje API/panel,
        # ale pętle tła zostawia instancji głównej (bez podwójnych alertów/SMS-ów)
        logger.warning("RUN_BACKGROUND_JOBS=false — pętle tła wyłączone na tej instancji")
        yield
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        return
    with_ais = bool(settings.aisstream_api_key.strip())
    per_process, leader_jobs = split_jobs(build_jobs(with_ais=with_ais))
    tasks += [asyncio.create_task(job_loop(job)) for job in per_process]

    def start_leader_jobs() -> list[asyncio.Task]:
        # BUILD-003: przy WEB_CONCURRENCY>1 tylko proces-lider (leader.py) — jeden na bazę
        started = [asyncio.create_task(job_loop(job)) for job in leader_jobs]
        if with_ais:
            from .tracking.ais import ais_loop
            started.append(asyncio.create_task(ais_loop()))
        return started

    tasks.append(asyncio.create_task(leader_loop(start_leader_jobs)))
    yield
    for task in tasks:
        task.cancel()
    # poczekaj na faktyczne zatrzymanie (domknięcie sesji DB, obsługa CancelledError)
    await asyncio.gather(*tasks, return_exceptions=True)


# inicjalizacja Sentry przed utworzeniem aplikacji — łapie też błędy na starcie,
# nie tylko w trakcie żądań (auto-instrumentacja FastAPI/Starlette włącza się sama)
init_sentry()

# dokumentacja API (/docs, /redoc, /openapi.json) tylko poza produkcją — nie publikujemy
# całej powierzchni API (admin, tokeny) na wewnętrznym narzędziu
_is_prod = settings.environment.lower() in ("production", "prod")
_docs_kw = dict(docs_url=None, redoc_url=None, openapi_url=None) if _is_prod else {}

app = FastAPI(
    title=settings.app_name,
    description="System zarządzania kolejką kontenerów i ich statusami — "
                "spółki, awizacje, odprawy celne, audyt zmian.",
    version="0.1.0",
    lifespan=lifespan,
    **_docs_kw,
)
# DB-007: naruszenie biznesowego klucza unikalnego (ux_*) → 409, reszta IntegrityError jak dotąd
app.add_exception_handler(IntegrityError, integrity_error_handler)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Nagłówki bezpieczeństwa dla API i panelu (CSP, nosniff, anty-clickjacking, SEC-011).
    Te same wartości ma nginx panelu z docker-compose (frontend/nginx.conf, test pilnuje)."""

    CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
           f"script-src 'self' {PRINT_CSP_HASH}; connect-src 'self'; frame-ancestors 'none'; "
           "base-uri 'self'; form-action 'self'")
    HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Content-Security-Policy": CSP,
        # aparat tylko dla własnej domeny (zdjęcia z telefonu, ew. skaner magazynu)
        "Permissions-Policy": "camera=(self), microphone=(), geolocation=()",
        "Cross-Origin-Opener-Policy": "same-origin",
    }

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        for name, value in self.HEADERS.items():
            response.headers.setdefault(name, value)
        path = request.url.path
        if path.startswith(("/avizo/", "/api/avizo/")):
            # link z tokenem nie może wyciec w Referer ani trafić do wyszukiwarek
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
        if settings.secure_cookies:  # aplikacja stoi za HTTPS
            response.headers.setdefault("Strict-Transport-Security",
                                        "max-age=31536000; includeSubDomains")
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Globalny limit żądań API na IP — chroni przed zalewem/pętlą klienta (429)."""

    async def dispatch(self, request, call_next):
        limit = settings.api_rate_limit_per_minute
        path = request.url.path
        # limit odczytujemy w locie (0 = wyłączony); healthcheck i statyki pomijamy
        if limit > 0 and path.startswith("/api") and path != "/api/health":
            retry = api_limiter.hit(client_ip(request), limit)
            if retry is not None:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Za dużo żądań. Spróbuj ponownie za chwilę."},
                    headers={"Retry-After": str(int(retry))})
        return await call_next(request)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Correlation ID żądania — pozwala powiązać logi i zdarzenia Sentry z konkretnym
    żądaniem (nagłówek X-Request-ID w odpowiedzi)."""

    async def dispatch(self, request, call_next):
        request_id = uuid.uuid4().hex[:8]
        request.state.request_id = request_id
        request_id_var.set(request_id)   # rid=… w liniach logów tego żądania
        if settings.sentry_dsn:
            import sentry_sdk
            sentry_sdk.set_tag("request_id", request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


# JSON kolejki ~1 MB → kilkadziesiąt KB (audyt PERF-001); najbardziej wewnętrzny, żeby
# logi i nagłówki widziały już skompresowaną odpowiedź
app.add_middleware(GZipMiddleware, minimum_size=1024)
# CSRF (SEC-004): zapis z ciasteczkiem sesji tylko z naszego frontu — pod RequestLog, żeby
# odrzucenia były w logu żądań
app.add_middleware(CsrfOriginMiddleware)
app.add_middleware(RequestLogMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

# ochrona przed host-header injection (fałszywy Host w linkach e-mail) — filtr nagłówka Host
_hosts = settings.allowed_hosts_list
if _hosts:
    from starlette.middleware.trustedhost import TrustedHostMiddleware
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_hosts)

# CORS tylko dla jawnie wskazanych originów; panel z tego samego adresu go nie potrzebuje
_origins = settings.cors_origins_list
if _origins:
    if "*" in _origins:
        logger.warning("CORS_ORIGINS='*' — ogranicz do zaufanych adresów w produkcji.")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials="*" not in _origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(data_subject.router)   # GDPR-005: eksport danych osoby, anonimizacja kierowcy
app.include_router(dictionaries.router)
app.include_router(containers.router)
app.include_router(queue_calendar.router)
app.include_router(imports.router)
app.include_router(master_quality.router)
app.include_router(avizo.router)
app.include_router(avizo.proposals_router)
app.include_router(avizo_forwarder.router)
app.include_router(avizo_requests.router)
app.include_router(warehouse_ops.router)
app.include_router(complaints.router)
app.include_router(checklist.router)
app.include_router(tracking.router)
app.include_router(forwarding.router)
app.include_router(invoices.router)
app.include_router(agency_templates.router)
app.include_router(archive_upload.router)
app.include_router(intake.router)   # poczekalnia dokumentów (spec 2026-10-06 §2)
app.include_router(invoice_agency.router)
app.include_router(sad_drafts.router)
app.include_router(sad_import.router)
app.include_router(invoice_checks.router)
app.include_router(document_tiles.router)
app.include_router(materials.router)
app.include_router(customs.router)
app.include_router(documents.router)
app.include_router(purchasing.router)
app.include_router(quotes.router)
app.include_router(notifications.router)
app.include_router(knowledge.router)
app.include_router(pallets.router)
app.include_router(pallets.targets_router)
app.include_router(paz.router)
app.include_router(purchase_orders.router)
app.include_router(analytics.router)
app.include_router(driver.router)
app.include_router(dlt.router)
app.include_router(system.router)
app.include_router(portal.router)
app.include_router(customer_orders.router)
app.include_router(consolidation.router)
app.include_router(audit_read.router)
app.include_router(inbox.router)
app.include_router(supplier_maps.router)
app.include_router(supplier_aliases.router)
app.include_router(supplier_profiles.router)
app.include_router(supplier_samples.router)
app.include_router(receipts.router)
app.include_router(search.router)
app.include_router(assistant.router)
app.include_router(sp_materials.router)
app.include_router(watchers.router)
app.include_router(avatars.router)
app.include_router(logs.router)
app.include_router(health.router)   # OBS-009: /api/health/deep
from .sms_settings import router as sms_settings_router  # noqa: E402

app.include_router(sms_settings_router)

from .presence import router as presence_router  # noqa: E402

app.include_router(presence_router)

from .theme_colors import router as theme_colors_router  # noqa: E402

app.include_router(theme_colors_router)


def _best_effort_scalar(db, stmt):
    """Metryka pomocnicza health: błąd zapytania (brak tabeli/wiersza) nie wywala endpointu."""
    try:
        return db.scalar(stmt)
    except Exception:  # noqa: BLE001
        logger.exception("Health check: metryka pomocnicza nie powiodła się")
        return None


@app.get("/api/health")
def health():
    version = settings.app_version if settings.app_version != "dev" \
        else (settings.sentry_release or "dev")
    build = {"version": version, "built_at": settings.build_time,
             "uptime_s": round(time.monotonic() - _START_TIME)}
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
            from .models import Container, TrackedVessel
            last_ais_seen = _best_effort_scalar(db, select(func.max(TrackedVessel.last_seen)))
            last_tracking_sync = _best_effort_scalar(db, select(func.max(Container.tracked_at)))
    except Exception:  # noqa: BLE001
        logger.exception("Health check: baza niedostępna")
        return JSONResponse({"status": "error", "database": "unavailable", **build},
                            status_code=503)
    return {"status": "ok", "database": "ok", **build,
            "last_ais_seen": last_ais_seen.isoformat() if last_ais_seen else None,
            "last_tracking_sync": last_tracking_sync.isoformat() if last_tracking_sync else None}


# Panel webowy z gotowego builda (frontend/dist) — pozwala uruchomić całość
# bez Node.js: API i panel pod jednym adresem. Katalog wskazuje FRONTEND_DIST
# lub domyślnie ../frontend/dist względem backendu.
_dist = pathlib.Path(settings.frontend_dist) if settings.frontend_dist \
    else pathlib.Path(__file__).resolve().parents[2] / "frontend" / "dist"

@app.get("/dzis", include_in_schema=False)
async def dzis_removed(request: Request):
    """Zakładka „Co dziś” usunięta — stare zakładki/linki trafiają na kolejkę (z query)."""
    q = request.url.query
    return RedirectResponse("/kolejka" + (f"?{q}" if q else ""), status_code=301)


def spa_response(dist: pathlib.Path, full_path: str):
    """Plik z builda albo index.html (routing SPA).

    Brakujący /assets/* (stary chunk po wdrożeniu) to 404, nie index.html z 200 — inaczej
    przeglądarka dostaje HTML jako JS i lazy-strona wywala się „Coś poszło nie tak”.
    Pliki z hashem w nazwie (assets/) cache'ujemy na rok, index.html nigdy — po wdrożeniu
    przeglądarka od razu bierze nową listę chunków."""
    # nieistniejące ścieżki API to błąd 404 JSON, nie fallback na index.html (200)
    if full_path.startswith("api/"):
        return JSONResponse({"detail": "Nie znaleziono."}, status_code=404)
    candidate = (dist / full_path).resolve()
    if candidate.is_file() and candidate.is_relative_to(dist.resolve()):
        if full_path.startswith("assets/"):
            return FileResponse(candidate, headers={
                "Cache-Control": "public, max-age=31536000, immutable"})
        if candidate.name != "index.html":
            return FileResponse(candidate)
    elif full_path.startswith("assets/"):
        return JSONResponse({"detail": "Nie znaleziono."}, status_code=404)
    return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})


if (_dist / "index.html").is_file():
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        return spa_response(_dist, full_path)
