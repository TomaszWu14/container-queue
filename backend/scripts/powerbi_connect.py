"""Jednorazowe logowanie delegated (device-code) do Power BI.

Uruchomienie:  python -m scripts.powerbi_connect  (z katalogu backend/)
Pokazuje URL + kod; po zalogowaniu zapisuje serializowany cache MSAL do DB.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import PowerBIToken, utcnow  # noqa: E402
from app.powerbi import _PUBLIC_CLIENT, _SCOPE  # noqa: E402


def run_device_flow(db) -> str:
    import msal
    cache = msal.SerializableTokenCache()
    authority = (f"https://login.microsoftonline.com/"
                 f"{settings.powerbi_tenant_id or 'organizations'}")
    app = msal.PublicClientApplication(
        settings.powerbi_client_id or _PUBLIC_CLIENT, authority=authority,
        token_cache=cache)
    flow = app.initiate_device_flow(scopes=_SCOPE)
    if "user_code" not in flow:
        raise RuntimeError(f"Nie udało się rozpocząć device-flow: {flow}")
    print(flow["message"])                 # URL + kod dla użytkownika
    result = app.acquire_token_by_device_flow(flow)   # blokuje do zalogowania
    if "access_token" not in result:
        raise RuntimeError(result.get("error_description", "logowanie nieudane"))
    row = db.query(PowerBIToken).first() or PowerBIToken()
    row.cache = cache.serialize()
    row.updated_at = utcnow()
    if row.id is None:
        db.add(row)
    db.commit()
    return result["access_token"]


if __name__ == "__main__":
    with SessionLocal() as db:
        run_device_flow(db)
        print("Połączono z Power BI (delegated).")
