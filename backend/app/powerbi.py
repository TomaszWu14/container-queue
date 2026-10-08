"""Integracja z Power BI (kostki SAP BW) przez REST executeQueries (DAX).

Wzorzec produkcyjny: kaskada auth (wklejony token -> service principal ->
delegated device-code z cache MSAL w DB), leniwe importy msal, konfigurowalny TLS,
defensywne parsowanie. Provider-gating (off/mock/real).
"""
from __future__ import annotations

from .config import settings
from .tabular import strip_accents

_API = "https://api.powerbi.com/v1.0/myorg"
_SCOPE = ["https://analysis.windows.net/powerbi/api/.default"]
_PUBLIC_CLIENT = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"  # publiczny klient MS (device-code)


class PowerBINotConfigured(RuntimeError):
    pass


def normalize_header(name: str) -> str:
    """'Tabela'[Krótki opis] -> krotki_opis ; lowercase, bez akcentów, _ zamiast spacji/kropek."""
    if "[" in name and name.endswith("]"):
        name = name[name.index("[") + 1:-1]
    name = strip_accents(name).lower()
    slug = "".join(ch if ch.isalnum() else "_" for ch in name)
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_")


def parse_execute_queries(payload: dict) -> tuple[list[str], list[dict]]:
    """Defensywne parsowanie odpowiedzi executeQueries -> (header, rows). Puste -> ([], [])."""
    results = (payload or {}).get("results") or []
    if not results:
        return [], []
    tables = results[0].get("tables") or []
    if not tables:
        return [], []
    raw_rows = tables[0].get("rows") or []
    if not raw_rows:
        return [], []
    header = [normalize_header(k) for k in raw_rows[0].keys()]
    rows = [{normalize_header(k): v for k, v in r.items()} for r in raw_rows]
    return header, rows


def apply_column_map(rows: list[dict]) -> list[dict]:
    """Remapuje nazwy kolumn wg POWERBI_COLUMN_MAP (JSON {nasza_nazwa: nazwa_w_kostce}).
    Puste = bez zmian. Domyka ryzyko rozjazdu nagłówków realnego DAX vs założeń."""
    import json
    raw = settings.powerbi_column_map.strip()
    if not raw:
        return rows
    try:
        mapping = json.loads(raw)             # {nasza_nazwa: nazwa_w_kostce}
    except (ValueError, TypeError):
        return rows
    inv = {str(cube): str(our) for our, cube in mapping.items()}   # cube -> nasza
    if not inv:
        return rows
    return [{inv.get(k, k): v for k, v in r.items()} for r in rows]


def is_configured() -> bool:
    if settings.powerbi_provider == "mock":
        return True
    return bool(settings.powerbi_provider == "real" and settings.powerbi_workspace_id
                and (settings.powerbi_access_token or settings.powerbi_client_secret
                     or settings.powerbi_tenant_id))


def _dax(table: str) -> str:
    return "EVALUATE '%s'" % table.replace("'", "''")


def _verify():
    if settings.powerbi_ca_bundle:
        return settings.powerbi_ca_bundle
    return settings.powerbi_ssl_verify


def get_access_token(db=None) -> str:
    """Kaskada: wklejony token -> service principal -> delegated device-code (cache w DB)."""
    if settings.powerbi_access_token:
        return settings.powerbi_access_token
    import msal  # leniwy import
    authority = f"https://login.microsoftonline.com/{settings.powerbi_tenant_id}"
    if settings.powerbi_client_secret:
        app = msal.ConfidentialClientApplication(
            settings.powerbi_client_id, authority=authority,
            client_credential=settings.powerbi_client_secret)
        res = app.acquire_token_for_client(scopes=_SCOPE)
        if "access_token" not in res:
            raise PowerBINotConfigured(res.get("error_description", "brak tokenu (SP)"))
        return res["access_token"]
    token = _delegated_token(db)
    if not token:
        raise PowerBINotConfigured("Brak sesji Power BI — połącz ponownie (device-code).")
    return token


def _delegated_token(db) -> str | None:
    import msal

    from .models import PowerBIToken
    if db is None:
        return None
    row = db.query(PowerBIToken).first()
    if not row or not row.cache:
        return None
    from .crypto import decrypt, encrypt
    cache = msal.SerializableTokenCache()
    cache.deserialize(decrypt(row.cache))
    authority = (f"https://login.microsoftonline.com/"
                 f"{settings.powerbi_tenant_id or 'organizations'}")
    app = msal.PublicClientApplication(
        settings.powerbi_client_id or _PUBLIC_CLIENT, authority=authority,
        token_cache=cache)
    accounts = app.get_accounts()
    if not accounts:
        return None
    res = app.acquire_token_silent(_SCOPE, account=accounts[0])
    if cache.has_state_changed:                    # rotacja refresh tokena -> zapis
        row.cache = encrypt(cache.serialize())
        db.commit()
    return (res or {}).get("access_token")


def has_delegated_session(db) -> bool:
    from .models import PowerBIToken
    row = db.query(PowerBIToken).first()
    return bool(row and row.cache)


def begin_device_flow():
    """Inicjuje device-code flow. Zwraca (app, cache, flow) — flow['message'] pokazać
    użytkownikowi. Dokończenie w tle przez complete_device_flow()."""
    import msal
    cache = msal.SerializableTokenCache()
    authority = (f"https://login.microsoftonline.com/"
                 f"{settings.powerbi_tenant_id or 'organizations'}")
    app = msal.PublicClientApplication(
        settings.powerbi_client_id or _PUBLIC_CLIENT, authority=authority,
        token_cache=cache)
    flow = app.initiate_device_flow(scopes=_SCOPE)
    return app, cache, flow


def complete_device_flow(app, cache, flow) -> None:
    """Blokuje do zalogowania (uruchamiać w wątku w tle), potem zapisuje cache MSAL."""
    from .crypto import encrypt
    from .database import SessionLocal
    from .models import PowerBIToken, utcnow
    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        return
    with SessionLocal() as db:
        row = db.query(PowerBIToken).first() or PowerBIToken()
        row.cache = encrypt(cache.serialize())
        row.updated_at = utcnow()
        if row.id is None:
            db.add(row)
        db.commit()


def fetch_table(dataset_id: str, table: str, db=None) -> tuple[list[str], list[dict]]:
    provider = settings.powerbi_provider
    if provider == "off":
        raise PowerBINotConfigured("POWERBI_PROVIDER=off")
    if provider == "mock":
        from tests.fixtures import pallets_mock as m
        t = (table or "").lower()

        def _match(cfg_ds: str, cfg_tbl: str, *keywords: str) -> bool:
            if cfg_ds and dataset_id == cfg_ds:
                return True
            if cfg_tbl and t == cfg_tbl.lower():
                return True
            return any(k in t for k in keywords)

        if _match(settings.powerbi_dataset_vbba, settings.powerbi_table_vbba, "vbba", "zl"):
            return m.VBBA_HEADER, m.VBBA_ROWS
        if _match(settings.powerbi_dataset_orders, settings.powerbi_table_orders,
                  "vbbe", "zlec"):
            return m.ORDERS_HEADER, m.ORDERS_ROWS
        if _match(settings.powerbi_dataset_usage, settings.powerbi_table_usage,
                  "zuzy", "usage"):
            return m.USAGE_HEADER, m.USAGE_ROWS
        return m.STOCK_HEADER, m.STOCK_ROWS
    # real
    import httpx
    token = get_access_token(db)
    if db is not None:   # token odczytany — połączenie z puli wraca przed HTTP (do 120 s)
        db.commit()
    url = f"{_API}/groups/{settings.powerbi_workspace_id}/datasets/{dataset_id}/executeQueries"
    body = {"queries": [{"query": _dax(table)}], "serializerSettings": {"includeNulls": True}}
    resp = httpx.post(url, json=body, headers={"Authorization": f"Bearer {token}"},
                      timeout=120.0, verify=_verify())
    resp.raise_for_status()
    return parse_execute_queries(resp.json())
