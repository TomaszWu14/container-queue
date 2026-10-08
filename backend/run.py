"""Uruchomienie serwera deweloperskiego.

Uruchamiaj TEN plik (`python run.py` z katalogu backend/ albo zielona strzałka
w PyCharm), NIE `app/main.py` — main.py używa importów względnych i musi być
ładowany jako pakiet (bezpośrednie uruchomienie daje
`ImportError: attempted relative import with no known parent package`).

Produkcja startuje przez: `uvicorn app.main:app` (patrz docker-compose / Coolify).
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
