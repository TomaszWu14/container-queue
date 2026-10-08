"""Przewalutowanie wartości towaru wg kursów NBP (tabela A).

Kursy pobierane best-effort z api.nbp.pl i cache'owane w pamięci — gdy NBP jest
nieosiągalny (np. brak dostępu wychodzącego), zwracamy dane z flagą available=False,
a operacja zakładania zlecenia nigdy się przez to nie wywraca.
"""
import datetime
import logging

import httpx

logger = logging.getLogger(__name__)

NBP_TABLE_A = "https://api.nbp.pl/api/exchangerates/tables/A?format=json"
# waluty prezentowane po przeliczeniu (PLN zawsze; EUR/USD to najczęstsze waluty zakupu)
DEFAULT_TARGETS = ("PLN", "EUR", "USD")
_CACHE_TTL = datetime.timedelta(hours=6)

# cache: (pobrane_o, {kod_waluty: kurs_w_PLN}, data_notowania)
_cache: tuple[datetime.datetime, dict[str, float], str] | None = None


def _fetch_rates() -> tuple[dict[str, float], str]:
    """Pobiera tabelę A NBP → {KOD: kurs_w_PLN} (PLN=1.0). Rzuca przy błędzie sieci."""
    response = httpx.get(NBP_TABLE_A, timeout=10)
    response.raise_for_status()
    table = response.json()[0]
    rates = {item["code"]: float(item["mid"]) for item in table["rates"]}
    rates["PLN"] = 1.0
    return rates, table["effectiveDate"]


def get_rates(now: datetime.datetime | None = None) -> tuple[dict[str, float], str | None]:
    """Kursy z cache (świeże < TTL) albo z NBP; ({}, None) gdy nieosiągalne."""
    global _cache
    now = now or datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    if _cache and now - _cache[0] < _CACHE_TTL:
        return _cache[1], _cache[2]
    try:
        rates, as_of = _fetch_rates()
        _cache = (now, rates, as_of)
        return rates, as_of
    except Exception:  # noqa: BLE001 — kanał zewnętrzny nie może blokować operacji
        logger.warning("NBP niedostępny — przewalutowanie pominięte", exc_info=True)
        if _cache:  # oddaj ostatnie znane kursy, nawet jeśli przeterminowane
            return _cache[1], _cache[2]
        return {}, None


def convert(amount: float, currency: str,
            targets: tuple[str, ...] = DEFAULT_TARGETS,
            rates: dict[str, float] | None = None,
            as_of: str | None = None) -> dict:
    """Przelicza `amount` w walucie `currency` na waluty docelowe wg kursów NBP.

    `rates`/`as_of` można wstrzyknąć (testy); domyślnie pobierane z NBP (cache).
    """
    currency = currency.upper()
    if rates is None:
        rates, as_of = get_rates()
    available = bool(rates) and currency in rates
    converted: dict[str, float] = {}
    if available:
        amount_pln = amount * rates[currency]
        for target in targets:
            if target in rates and rates[target]:
                converted[target] = round(amount_pln / rates[target], 2)
    shown = {code: rates[code] for code in (*targets, currency) if code in rates}
    return {
        "amount": amount,
        "currency": currency,
        "rates": shown,
        "converted": converted,
        "as_of": as_of,
        "available": available,
    }
