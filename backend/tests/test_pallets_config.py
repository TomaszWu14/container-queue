from app.config import settings


def test_powerbi_defaults():
    assert settings.powerbi_provider == "off"
    assert settings.powerbi_merge_key == "produkt"
    assert settings.powerbi_cache_ttl_min == 15
    assert settings.powerbi_ssl_verify is True
    assert settings.pallet_target_days == 14


def test_open_statuses_set():
    assert settings.vbba_open_statuses_set == {"Nie rozpoczęte", "Częściowo zakończone"}
