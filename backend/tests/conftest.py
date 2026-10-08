import os
import pathlib
import sqlite3
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
# pytest-xdist (-n auto w CI): każdy worker (gw0, gw1…) ma własny plik bazy — wspólny plik
# = testy nadpisują sobie bazę w trakcie (kopia szablonu przed każdym testem)
_WORKER = os.environ.get("PYTEST_XDIST_WORKER", "")
os.environ["DATABASE_URL"] = f"sqlite:///./test_timporye{'_' + _WORKER if _WORKER else ''}.db"
# Pętle tła (demurrage/reklamacje/palety/digesty…) robią pełny przebieg pracy OD RAZU
# na każdym starcie lifespan (sleep na końcu). Bez tego każdy TestClient odpalał 7 pętli
# × setki instancji w suicie → pytest na CI puchł do 30-40 min. Testy tych pętli wołają
# funkcje check_* wprost; tło w TestClient jest zbędne.
os.environ.setdefault("RUN_BACKGROUND_JOBS", "false")
# bcrypt min. koszt: każde logowanie w teście to ~0,3 s przy 12 (produkcja zostaje na 12)
os.environ.setdefault("BCRYPT_ROUNDS", "4")
# globalny limit API wyłączony domyślnie w testach (dedykowany test włącza go punktowo)
os.environ.setdefault("API_RATE_LIMIT_PER_MINUTE", "0")
os.environ.setdefault("ASSISTANT_RATE_LIMIT_PER_MINUTE", "0")
# klucz HS256 min. 32 bajty (RFC 7518) — cichnie InsecureKeyLengthWarning z pyjwt
os.environ.setdefault("SECRET_KEY", "test-secret-key-at-least-32-bytes-long")
# W14 #89: istniejące testy używają 8-znakowych haseł; polityka 12 znaków jest
# testowana punktowo (test_w14_security) przez monkeypatch ustawień
os.environ.setdefault("PASSWORD_MIN_LENGTH", "8")
# SEC-006: obowiązkowe 2FA admina blokowałoby zapisy konta „admin” w setkach testów;
# wymóg jest testowany punktowo (test_2fa_admin_required) przez monkeypatch ustawień
os.environ.setdefault("REQUIRE_2FA_ADMIN", "false")

import pytest
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.main import app, bootstrap


@pytest.fixture(autouse=True)
def _ml_sandbox(tmp_path, monkeypatch):
    """Modele ML i trening: synchronicznie i w katalogu tymczasowym — testy nie zostawiają
    plików joblib w uploads/ i nie ścigają się z wątkiem treningowym."""
    from app.config import settings
    from app.invoices import ml
    monkeypatch.setattr(settings, "ml_model_dir", str(tmp_path / "ml"))
    monkeypatch.setattr(settings, "ml_train_in_background", False)
    ml.invalidate()
    yield
    ml.invalidate()


@pytest.fixture(autouse=True)
def _reset_avizo_public_limit():
    """Limit publicznych endpointów awizacji (30/min na IP) jest w pamięci procesu —
    bez resetu testy z jednej minuty wyczerpałyby go sobie nawzajem (TestClient = jedno IP)."""
    from app.routers import avizo
    avizo._public_limiter._hits.clear()
    # to samo dla publicznego portalu/linku kontenera (klucz „pub:<ip>” w api_limiter)
    from app.security import api_limiter
    api_limiter._hits.clear()
    # limiter logowań trzyma stan w bazie (tabela login_failures, ARCH-003) — fixture `client`
    # odtwarza bazę z szablonu, więc porażki z różnych testów się nie sumują
    yield


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "fresh_db: pełny drop_all + bootstrap() zamiast przywrócenia szablonu")


@pytest.fixture(scope="session")
def _db_template():
    """Schemat + seedy bootstrapu budowane RAZ na sesję, trzymane w pamięci (sqlite3)."""
    Base.metadata.drop_all(bind=engine)
    bootstrap()
    template = sqlite3.connect(":memory:", check_same_thread=False)
    with engine.raw_connection() as raw:
        raw.driver_connection.backup(template)
    yield template
    template.close()


@pytest.fixture()
def client(request, _db_template):
    # Każdy test startuje od bazy świeżo po bootstrapie. Zamiast drop_all + create_all +
    # seedy (~2-3 s/test) nadpisujemy plik bazy kopią szablonu przez backup API SQLite (ms).
    # dispose(): zamyka połączenia z puli, żeby żadne nie trzymało starego schematu/transakcji.
    engine.dispose()
    if request.node.get_closest_marker("fresh_db"):
        Base.metadata.drop_all(bind=engine)
        bootstrap()
    else:
        with engine.raw_connection() as raw:
            _db_template.backup(raw.driver_connection)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db_session(client):
    """Session na tej samej bazie co `client` (tabele już założone przez bootstrap)."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def forwarder(client, headers, name):
    """Get-or-create spedytora po nazwie (część firm jest zasiana przy starcie)."""
    resp = client.post("/api/forwarders", headers=headers, json={"name": name})
    if resp.status_code == 201:
        return resp.json()
    return next(f for f in client.get("/api/forwarders", headers=headers).json()
                if f["name"] == name)


def pdf_bytes(tag: str = "") -> bytes:
    """Prawdziwy 1-stronicowy PDF (bramka wgrania odrzuca atrapy „%PDF-…”); `tag` w metadanych
    daje różną treść — blokada dubli nie zatrzymuje testów wgrywających kilka plików."""
    import io as _io

    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_metadata({"/Title": tag or "test"})
    buf = _io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def login(client, username="admin", password="admin123") -> dict:
    response = client.post("/api/auth/login",
                           data={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture()
def admin_headers(client):
    return login(client)
