"""Audyt AI-007: modele ML (joblib = pickle, wykonuje kod przy wczytaniu) poza wolumenem
uploadów i z podpisem HMAC — plik podrzucony/zmieniony na dysku nie jest w ogóle wczytywany."""
import pathlib

import joblib

from app.config import settings
from app.invoices import ml

MARKER = {"path": ""}


def _pwned(path):
    pathlib.Path(path).write_text("wykonano kod z pliku modelu", encoding="utf-8")
    return ml.RefModel()


class Evil:
    """Pickle, który przy wczytaniu wykonuje funkcję (jak spreparowany plik .joblib)."""

    def __reduce__(self):
        return (_pwned, (MARKER["path"],))


def test_default_model_dir_outside_uploads(tmp_path, monkeypatch):
    uploads = tmp_path / "data" / "uploads"
    monkeypatch.setattr(settings, "uploads_dir", str(uploads))
    monkeypatch.setattr(settings, "ml_model_dir", "")
    directory = ml.model_dir().resolve()
    assert not directory.is_relative_to(uploads.resolve())
    assert directory == (tmp_path / "data" / "ml").resolve()


def test_unsigned_model_file_is_not_loaded(tmp_path):
    marker = tmp_path / "pwned.txt"
    MARKER["path"] = str(marker)
    joblib.dump(Evil(), ml.model_dir() / "ref_model.joblib")     # podrzucony, bez podpisu
    ml.invalidate()
    models = ml.get_models()
    assert not marker.exists(), "joblib.load wykonał kod z niepodpisanego pliku"
    assert isinstance(models["ref"], ml.RefModel)


def test_tampered_model_rejected_signed_model_loaded(tmp_path):
    ml._dump_atomic(ml.RefModel(), ml.model_dir() / "ref_model.joblib")
    ml.invalidate()
    assert isinstance(ml.get_models()["ref"], ml.RefModel)       # podpisany — wczytany

    marker = tmp_path / "pwned.txt"
    MARKER["path"] = str(marker)
    joblib.dump(Evil(), ml.model_dir() / "ref_model.joblib")     # podmiana, stary podpis
    ml.invalidate()
    ml.get_models()
    assert not marker.exists(), "podpis nie pasuje — pliku nie wolno wczytać"
