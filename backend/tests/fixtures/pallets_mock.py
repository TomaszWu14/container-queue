"""Realistyczny podzbiór kolumn 4 źródeł (SAP BW) do trybu mock i testów.

Lokalizacje: '0099ZONE' = magazyn ACME, '3DLT' = DLT (mapowanie w testach).
"""
STOCK_HEADER = ["miejsce_skladowania", "produkt", "krotki_opis_produktu", "ilosc",
                "podst_jedn_miary", "rodzaj_zapasow", "partia", "glowna_hu"]
STOCK_ROWS = [
    {"miejsce_skladowania": "0099ZONE", "produkt": "DEMO-SKU-020",
     "krotki_opis_produktu": "Strzykawka demo 20ml", "ilosc": 1000,
     "podst_jedn_miary": "OP", "rodzaj_zapasow": "F2", "partia": "1000000101",
     "glowna_hu": "10000601"},
    {"miejsce_skladowania": "3DLT", "produkt": "DEMO-SKU-020",
     "krotki_opis_produktu": "Strzykawka demo 20ml", "ilosc": 2000,
     "podst_jedn_miary": "OP", "rodzaj_zapasow": "F2", "partia": "1000000101",
     "glowna_hu": "10000777"},
    {"miejsce_skladowania": "0099ZONE", "produkt": "DEMO-SKU-079",
     "krotki_opis_produktu": "Urządzenie demo", "ilosc": 79,
     "podst_jedn_miary": "OP", "rodzaj_zapasow": "F2", "partia": "1000000102",
     "glowna_hu": "10007965"},
]
VBBA_HEADER = ["dokument", "produkt", "ilosc", "status_pobrania"]
VBBA_ROWS = [
    {"dokument": "80000659", "produkt": "DEMO-SKU-020", "ilosc": 400,
     "status_pobrania": "Nie rozpoczęte"},
    {"dokument": "80000700", "produkt": "DEMO-SKU-020", "ilosc": 300,
     "status_pobrania": "Zakończone"},   # pominięte (zamknięte)
]
ORDERS_HEADER = ["produkt", "otw", "potw", "niestandardowe"]
ORDERS_ROWS = [
    # kolumny jak w arkuszu vbbe+likp: Otw / Potw / Niestandardowe (niepotwierdzone)
    {"produkt": "DEMO-SKU-020", "otw": 300, "potw": 100, "niestandardowe": 200},
]
USAGE_HEADER = ["produkt", "zuzycie_dzienne"]
USAGE_ROWS = [
    {"produkt": "DEMO-SKU-020", "zuzycie_dzienne": 100},
]
