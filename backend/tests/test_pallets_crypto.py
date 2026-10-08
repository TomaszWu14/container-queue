from app import crypto, powerbi


def test_encrypt_roundtrip():
    secret = '{"refresh":"abc123"}'
    enc = crypto.encrypt(secret)
    assert enc != secret and enc.startswith("enc:")
    assert crypto.decrypt(enc) == secret


def test_decrypt_plaintext_passthrough():
    # zgodność wstecz: wartość bez prefiksu zwracana bez zmian
    assert crypto.decrypt("plain-cache") == "plain-cache"
    assert crypto.decrypt("") == ""


def test_apply_column_map(monkeypatch):
    monkeypatch.setattr(powerbi.settings, "powerbi_column_map",
                        '{"ilosc": "menge", "produkt": "material"}')
    rows = [{"material": "X", "menge": 5, "inne": 1}]
    out = powerbi.apply_column_map(rows)
    assert out == [{"produkt": "X", "ilosc": 5, "inne": 1}]


def test_apply_column_map_empty(monkeypatch):
    monkeypatch.setattr(powerbi.settings, "powerbi_column_map", "")
    rows = [{"a": 1}]
    assert powerbi.apply_column_map(rows) == rows
