"""Maskowanie tokenów linków publicznych i danych osobowych w logach i zdarzeniach Sentry.

Wydzielone z app/main.py (limit 500 linii); main re-eksportuje te nazwy."""
import logging
import re

from .config import settings

logger = logging.getLogger("app.main")


# Tokeny publicznych linków (bearer w ŚCIEŻCE: awizacja, portal kliencki, udostępnione
# kontenery, łącznik kierowcy, DLT, SPA /dostawa/ i /portal/; w QUERY: reset hasła
# ?token=) — bez maskowania lądują w logach dostępu uvicorn, logach aplikacji i Sentry
# (= działający link w logach).
_PUBLIC_TOKEN_PATH_RE = re.compile(
    r"(/(?:api/)?(?:avizo/(?:driver/)?|public/portal/|public/containers/|driver/|dlt/"
    r"|dostawa/|portal/))[A-Za-z0-9_-]{16,}")
_QUERY_TOKEN_RE = re.compile(r"([?&]token=)[^&\s\"'#]+")


def redact_tokens(value):
    if not isinstance(value, str):
        return value
    return _QUERY_TOKEN_RE.sub(r"\1[token]", _PUBLIC_TOKEN_PATH_RE.sub(r"\1[token]", value))


# pola maskowane w zdarzeniach Sentry: PII kierowców + sekrety/tokeny (RODO)
_SENTRY_SENSITIVE = {
    "password", "hashed_password", "token", "access_token", "refresh_token",
    "authorization", "cookie", "set-cookie", "secret", "secret_key",
    "smtp_password", "driver_id_no", "driver_phone", "driver_name",
    "truck_no", "trailer_no", "ms_client_secret",
    "x-automation-token", "x-api-key", "totp_secret", "pending_token",
}


def _scrub_sensitive(data):
    """Rekurencyjnie maskuje wrażliwe klucze (dane osobowe kierowców, hasła, tokeny)."""
    if isinstance(data, dict):
        return {k: ("[Filtered]" if str(k).lower() in _SENTRY_SENSITIVE else _scrub_sensitive(v))
                for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [_scrub_sensitive(v) for v in data]
    return data


# B4/RODO: PII wchodzi do Sentry także w WOLNYM TEKŚCIE (komunikat wyjątku,
# logi, breadcrumbs) — tam scrubbing po kluczach nie sięga. Maskujemy e-maile
# i dłuższe ciągi cyfr (telefony/nr dokumentów) w treści komunikatów.
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_LONG_DIGITS_RE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{6,}\d(?!\w)")


def _redact_text(value):
    if not isinstance(value, str):
        return value
    value = redact_tokens(value)
    return _LONG_DIGITS_RE.sub("[number]", _EMAIL_RE.sub("[email]", value))


def _redact_message_fields(event) -> None:
    """Maskuje PII w polach tekstowych zdarzenia; zmienne lokalne ramek stosu usuwa
    (GDPR-003: repr modeli z telefonem/e-mailem — regexem nie do wyczyszczenia)."""
    exception = event.get("exception")
    if isinstance(exception, dict):
        for value in exception.get("values", []):
            if not isinstance(value, dict):
                continue
            if isinstance(value.get("value"), str):
                value["value"] = _redact_text(value["value"])
            for frame in (value.get("stacktrace") or {}).get("frames", []):
                if isinstance(frame, dict):
                    frame.pop("vars", None)
    logentry = event.get("logentry")
    if isinstance(logentry, dict):
        for key in ("message", "formatted"):
            if isinstance(logentry.get(key), str):
                logentry[key] = _redact_text(logentry[key])
        logentry.pop("params", None)   # treść jest już w (zredagowanym) „formatted”
    if isinstance(event.get("message"), str):
        event["message"] = _redact_text(event["message"])
    breadcrumbs = event.get("breadcrumbs")
    crumbs = breadcrumbs.get("values", []) if isinstance(breadcrumbs, dict) else breadcrumbs
    if isinstance(crumbs, list):
        for crumb in crumbs:
            if not isinstance(crumb, dict):
                continue
            if isinstance(crumb.get("message"), str):
                crumb["message"] = _redact_text(crumb["message"])
            if isinstance(crumb.get("data"), dict):   # breadcrumb http: data.url niesie token
                crumb["data"] = {k: _redact_text(v) for k, v in
                                 _scrub_sensitive(crumb["data"]).items()}


def _sentry_before_send(event, _hint):
    """Usuwa dane wrażliwe z żądania i kontekstu przed wysłaniem do Sentry."""
    request = event.get("request")
    if isinstance(request, dict):
        for key in ("data", "headers"):
            if key in request:
                request[key] = _scrub_sensitive(request[key])
        if "cookies" in request:
            request["cookies"] = "[Filtered]"   # cookies niosą tokeny sesji — maskujemy w całości
        request.pop("query_string", None)       # parametry URL mogą nieść tokeny/PII
        if "url" in request:
            request["url"] = redact_tokens(request["url"])
    if "transaction" in event:
        event["transaction"] = redact_tokens(event["transaction"])
    if "extra" in event:
        event["extra"] = _scrub_sensitive(event["extra"])
    _redact_message_fields(event)   # B4: PII w wolnym tekście (wyjątek/log/breadcrumbs)
    return event


def sentry_release() -> str | None:
    """Wersja dla Sentry: SENTRY_RELEASE, a bez niego SHA z obrazu (APP_VERSION, OBS-006)."""
    if settings.sentry_release:
        return settings.sentry_release
    return settings.app_version if settings.app_version != "dev" else None


def init_sentry() -> None:
    """Monitoring błędów — aktywny tylko przy ustawionym SENTRY_DSN."""
    if not settings.sentry_dsn:
        return
    import sentry_sdk
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        release=sentry_release(),  # brak = Sentry grupuje bez wersji
        traces_sample_rate=settings.sentry_traces_rate,   # OBS-010: z konfiguracji, domyślnie 5%
        include_local_variables=False,   # GDPR-003: bez zmiennych lokalnych (PII)
        send_default_pii=False,          # nie dołączaj domyślnie danych użytkownika/ciała
        before_send=_sentry_before_send,  # dodatkowo maskuj PII kierowców i sekrety
        before_send_transaction=_sentry_before_send,  # tokeny awizacji w URL transakcji
    )
    logger.info("Sentry włączony (environment=%s)", settings.environment)


def capture_client_error(name: str, message: str, stack: str, url: str, user_agent: str) -> None:
    """OBS-010: błąd JS z beaconu panelu jako osobne zdarzenie Sentry — bez SDK we froncie
    i bez DSN w przeglądarce. Grupowanie po nazwie i komunikacie (inaczej wszystkie błędy JS
    byłyby jednym „issue”), tag source=frontend. Tokeny linków i e-maile/telefony maskowane
    tu, reszta jak dla backendu (before_send). Bez SENTRY_DSN — nic nie wychodzi."""
    if not settings.sentry_dsn:
        return
    import sentry_sdk
    message = _redact_text(redact_tokens(message))[:300]
    sentry_sdk.capture_message(
        f"[frontend] {name}: {message}", level="error",
        tags={"source": "frontend"}, fingerprint=["frontend", name, message[:120]],
        extras={"url": _redact_text(redact_tokens(url)), "user_agent": user_agent,
                "stack": _redact_text(redact_tokens(stack))[-4000:]})
