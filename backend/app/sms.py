"""Wysyłka SMS do kierowców — abstrakcja providera (wzorzec jak tracking).

SMS_PROVIDER: 'smsapi' (SMSAPI.pl, wymaga SMSAPI_TOKEN), 'mock' (dev/testy —
rejestr w pamięci), 'off' (funkcja wyłączona, czytelny błąd konfiguracyjny).
Rekord SmsMessage zapisuje wywołujący — tu tylko transport.
"""
import logging

import httpx

from .config import settings

logger = logging.getLogger(__name__)


class SmsError(Exception):
    pass


# rejestr wysyłek providera mock (dev/testy)
mock_outbox: list[dict] = []


def sms_configured() -> bool:
    if settings.sms_provider == "mock":
        return True
    return settings.sms_provider == "smsapi" and bool(settings.smsapi_token.strip())


def send_sms(phone: str, body: str) -> None:
    """Wysyła SMS. Podnosi SmsError przy braku konfiguracji lub błędzie providera."""
    provider = settings.sms_provider
    if provider == "off" or not sms_configured():
        raise SmsError("SMS nie jest skonfigurowany (SMS_PROVIDER / SMSAPI_TOKEN). "
                       "Skontaktuj się z administratorem.")
    phone = phone.strip().replace(" ", "")
    if not phone:
        raise SmsError("Brak numeru telefonu kierowcy.")
    if provider == "mock":
        mock_outbox.append({"phone": phone, "body": body})
        logger.info("SMS mock → •••%s: %s", phone[-3:], body)  # numer maskowany (PII)
        return
    # SMSAPI.pl: POST sms.do, autoryzacja Bearer OAuth tokenem
    try:
        response = httpx.post(
            settings.smsapi_url,
            headers={"Authorization": f"Bearer {settings.smsapi_token}"},
            data={"to": phone, "message": body, "format": "json", "encoding": "utf-8"},
            timeout=15.0)
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as exc:
        raise SmsError(f"Błąd bramki SMS: {exc}") from exc
    except ValueError as exc:   # nie-JSON (np. strona błędu proxy) — też błąd bramki
        raise SmsError(f"Błąd bramki SMS: nieczytelna odpowiedź ({exc})") from exc
    if not isinstance(payload, dict):
        raise SmsError("Błąd bramki SMS: nieoczekiwana odpowiedź.")
    if payload.get("error"):
        raise SmsError(f"SMSAPI: {payload.get('message', payload['error'])}")
