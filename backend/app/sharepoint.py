"""SharePoint → TIMPORYE: jednokierunkowe pobieranie plików przez Microsoft Graph.

App-only (client credentials) z uprawnieniem Sites.Selected (read) na JEDNĄ witrynę.
Domyślnie wyłączone: bez kompletu SHAREPOINT_* nic się nie dzieje. Instrukcja:
docs/SHAREPOINT-SYNC.md. `fetch_file` jest ogólne — master data doczepi się później.
"""
import datetime
import json
import logging
from urllib.parse import quote

import httpx
from sqlalchemy import select

from . import mailer
from .app_settings import get_setting, set_setting
from .config import settings
from .models import Company, utcnow

logger = logging.getLogger(__name__)

GRAPH = "https://graph.microsoft.com/v1.0"
STATE_KEY = "sharepoint_queue_sync"   # AppSetting: JSON ze stanem ostatniej synchronizacji
TIMEOUT = httpx.Timeout(60.0, connect=15.0)

_app = None        # MSAL ConfidentialClientApplication (cache tokenu)
_site_ids: dict[str, str] = {}


class SharePointError(RuntimeError):
    pass


def is_configured() -> bool:
    s = settings
    return all(v.strip() for v in (s.sharepoint_tenant_id, s.sharepoint_client_id,
                                    s.sharepoint_client_secret, s.sharepoint_site,
                                    s.sharepoint_queue_path, s.sharepoint_queue_company))


def _token() -> str:
    global _app
    if _app is None:
        _app = mailer.graph_app(settings.sharepoint_tenant_id, settings.sharepoint_client_id,
                                settings.sharepoint_client_secret)
    return mailer.graph_token(_app)


def _get(url: str, token: str, headers: dict | None = None) -> httpx.Response:
    try:
        r = httpx.get(url, headers={"Authorization": f"Bearer {token}", **(headers or {})},
                      timeout=TIMEOUT, follow_redirects=True)
    except httpx.HTTPError as exc:
        raise SharePointError(f"Graph: błąd sieci ({type(exc).__name__}: {exc})") from exc
    if r.status_code >= 400:
        raise SharePointError(f"Graph HTTP {r.status_code}: {r.text[:200]}")
    return r


def site_id(token: str) -> str:
    """GET /sites/{hostname}:/{ścieżka} → id witryny (cache na czas procesu)."""
    site = settings.sharepoint_site.strip()
    if site not in _site_ids:
        _site_ids[site] = _get(f"{GRAPH}/sites/{site}", token).json()["id"]
    return _site_ids[site]


def fetch_file(path: str, etag: str | None = None) -> tuple[bytes | None, dict]:
    """Pobiera plik z biblioteki domyślnej witryny. Zwraca (None, meta), gdy eTag się
    nie zmienił (304 albo ten sam eTag) — wtedy treść nie jest ściągana."""
    token = _token()
    item = f"{GRAPH}/sites/{site_id(token)}/drive/root:/{quote(path.strip().strip('/'))}"
    r = _get(item, token, {"If-None-Match": etag} if etag else None)
    if r.status_code == 304:
        return None, {"eTag": etag}
    meta = r.json()
    if etag and meta.get("eTag") == etag:
        return None, meta
    return _get(f"{item}:/content", token).content, meta


def _naive_utc(value: str | None) -> datetime.datetime | None:
    if not value:
        return None
    try:
        dt = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(datetime.UTC).replace(tzinfo=None) if dt.tzinfo else dt


def load_state(db) -> dict:
    try:
        return json.loads(get_setting(db, STATE_KEY) or "{}")
    except ValueError:
        return {}


def sharepoint_queue_sync(db) -> str | None:
    """Job: pobierz kolejkę i przepuść przez ten sam rdzeń co POST /import/queue-sync.
    Błąd nie wychodzi poza funkcję — trafia do stanu (panel integracji)."""
    if not is_configured():
        return None
    from .importers.queue import sync_queue_bytes

    state = load_state(db)
    now = utcnow().isoformat()
    try:
        content, meta = fetch_file(settings.sharepoint_queue_path, state.get("etag"))
        if content is None:
            state.update(status="unchanged", checked_at=now, error="")
        else:
            code = settings.sharepoint_queue_company.strip()
            company = db.scalar(select(Company).where(Company.code == code))
            if company is None:
                raise SharePointError(f"Nieznana spółka SHAREPOINT_QUEUE_COMPANY={code!r}")
            raw_from = get_setting(db, f"queue_sync_date_from:{company.code}")
            date_from = datetime.date.fromisoformat(raw_from) if raw_from else None
            result = sync_queue_bytes(db, company, content, None, date_from=date_from,
                                      file_mtime=_naive_utc(meta.get("lastModifiedDateTime")),
                                      dry_run=False)
            state = {"status": "ok", "checked_at": now, "synced_at": now, "error": "",
                     "etag": meta.get("eTag"),
                     "last_modified": meta.get("lastModifiedDateTime"),
                     "result": {k: result.get(k) for k in
                                ("containers", "changed", "notified", "skipped_old")}}
    except Exception as exc:  # noqa: BLE001 — błąd zapisujemy, pętla tła żyje dalej
        db.rollback()
        logger.warning("SharePoint: sync kolejki nie powiódł się: %s", exc)
        state.update(status="error", checked_at=now, error=str(exc)[:300])
    set_setting(db, STATE_KEY, json.dumps(state))
    db.commit()
    return state["status"]


def status_detail(db) -> tuple[str, datetime.datetime | None]:
    """(opis, czas ostatniej udanej synchronizacji) dla panelu integracji."""
    st = load_state(db)
    if not st:
        return settings.sharepoint_site or "—", None
    r = st.get("result") or {}
    detail = (f"{st.get('status')} (sprawdzono {st.get('checked_at', '')[:16]}); "
              f"ostatni import: {r.get('containers', 0)} wierszy, "
              f"{r.get('changed', 0)} zmienionych/nowych")
    if st.get("error"):
        detail += f"; błąd: {st['error']}"
    return detail, _naive_utc(st.get("synced_at"))
