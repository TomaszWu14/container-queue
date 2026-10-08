"""Moduł ML modułu faktur — w duchu Presebu: scikit-learn, czyste funkcje na listach/
dict-ach, progi w config, logowanie tego, co model „zjadł”. Bez usług zewnętrznych.

Dwa modele, oba trenowane z danych, które już mamy w bazie:

* `RefModel` — sugestia REF master dla pozycji faktury, której reguły (matching.py)
  nie dopasowały. Dwa źródła: (1) HISTORIA — zatwierdzone przez operatora pary
  (dostawca, REF z faktury) → REF master (samouczenie z weryfikacji); (2) PODOBIEŃSTWO —
  TF-IDF na n-gramach znaków (REF + opis z faktury vs REF + nazwy PL/EN z master daty),
  cosinus. Wynik = lista (master_ref, score∈[0,1], source). Powyżej
  `ml_auto_apply_threshold` pipeline sam ustawia dopasowanie (match_source='ml').
* `DocKindModel` — klasyfikator typu strony (faktura / proforma / packing lista / inne)
  TF-IDF + regresja logistyczna, trenowany na tekstach zatwierdzonych dokumentów.
  Uzupełnia reguły markerowe w splitterze, gdy OCR skanu zniekształci nagłówek
  („COMMERC1AL 1NVOICE”). Trenuje się dopiero od `ml_min_examples` i ≥ 2 klas.

Modele leżą na dysku (joblib + podpis HMAC `.sig`) w `ml_model_dir`, poza uploadami (AI-007);
w pamięci singleton z lockiem.
"""
from __future__ import annotations

import datetime
import hashlib
import hmac
import io
import json
import logging
import os
import pathlib
import threading
from collections import Counter, defaultdict
from dataclasses import dataclass

from ..config import settings
from .uom import normalize_ref

logger = logging.getLogger(__name__)

# poniżej tej wartości cosinusa sugestia z podobieństwa jest szumem — nie pokazujemy
SIMILARITY_MIN = 0.35
# ile sugestii zwracamy operatorowi
TOP_K = 3


@dataclass(frozen=True)
class Suggestion:
    master_ref: str
    score: float
    source: str    # history | similarity


def _query_text(raw_ref: str, descr: str) -> str:
    return f"{normalize_ref(raw_ref)} {(descr or '').strip().lower()}".strip()


class RefModel:
    """Sugestie REF master. `fit` przyjmuje czyste dane (bez SQLAlchemy) — łatwo testować."""

    def __init__(self) -> None:
        self.history: dict[tuple[int | None, str], Counter] = {}
        self.refs: list[str] = []
        self.vectorizer = None
        self.matrix = None
        self.trained_at: str = ""
        self.n_examples = 0
        self.n_materials = 0

    def fit(self, materials: list[dict], examples: list[dict]) -> RefModel:
        """materials: [{ref_code, name_pl, name_en}], examples: [{supplier_id, raw_ref, descr,
        master_ref}] (zatwierdzone przez operatora)."""
        history: dict[tuple[int | None, str], Counter] = defaultdict(Counter)
        for ex in examples:
            norm = normalize_ref(ex.get("raw_ref"))
            if not norm or not ex.get("master_ref"):
                continue
            history[(ex.get("supplier_id"), norm)][ex["master_ref"]] += 1
            # klucz globalny (None): decyzje wszystkich dostawców — fallback dla nowego dostawcy
            if ex.get("supplier_id") is not None:
                history[(None, norm)][ex["master_ref"]] += 1
        self.history = dict(history)
        self.n_examples = len(examples)
        self.refs = [m["ref_code"] for m in materials]
        self.n_materials = len(self.refs)
        self.vectorizer = self.matrix = None
        if materials:
            from sklearn.feature_extraction.text import TfidfVectorizer
            docs = [f"{normalize_ref(m['ref_code'])} {(m.get('name_pl') or '').lower()} "
                    f"{(m.get('name_en') or '').lower()}" for m in materials]
            self.vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4),
                                              min_df=1, sublinear_tf=True)
            self.matrix = self.vectorizer.fit_transform(docs)
        self.trained_at = datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")
        logger.info("RefModel: %d materiałów, %d przykładów historii", self.n_materials, self.n_examples)
        return self

    def suggest(self, raw_ref: str, descr: str = "", supplier_id: int | None = None,
                k: int = TOP_K) -> list[Suggestion]:
        out: list[Suggestion] = []
        norm = normalize_ref(raw_ref)
        seen: set[str] = set()
        # 1) historia: najpierw ten dostawca ("history"), potem wszyscy ("history_global" —
        #    wystarczy jako podpowiedź, ale nie rozstrzyga X/X1 innego dostawcy)
        for key, source in (((supplier_id, norm), "history"), ((None, norm), "history_global")):
            counter = self.history.get(key)
            if not counter or not norm:
                continue
            total = sum(counter.values())
            for ref, n in counter.most_common(k):
                if ref in seen:
                    continue
                seen.add(ref)
                # udział głosów; 1/1 daje 1.0 — jedna zgodna decyzja operatora wystarcza,
                # bo dotyczy dokładnie tego REF u tego dostawcy
                out.append(Suggestion(ref, round(n / total, 3), source))
        # 2) podobieństwo do master daty
        if self.vectorizer is not None and (norm or descr):
            from sklearn.metrics.pairwise import cosine_similarity
            sims = cosine_similarity(self.vectorizer.transform([_query_text(raw_ref, descr)]),
                                     self.matrix)[0]
            order = sims.argsort()[::-1][:k * 2]
            for idx in order:
                score = float(sims[idx])
                if score < SIMILARITY_MIN:
                    break
                ref = self.refs[idx]
                if ref in seen:
                    continue
                seen.add(ref)
                out.append(Suggestion(ref, round(score, 3), "similarity"))
        return out[:k]


class DocKindModel:
    """Typ strony z tekstu. `predict` zwraca (etykieta, prawdopodobieństwo) albo None,
    gdy model nie jest wytrenowany."""

    def __init__(self) -> None:
        self.pipeline = None
        self.classes: list[str] = []
        self.n_examples = 0
        self.trained_at: str = ""

    def fit(self, texts: list[str], labels: list[str], min_examples: int | None = None) -> DocKindModel:
        min_examples = settings.ml_min_examples if min_examples is None else min_examples
        pairs = [(t, lab) for t, lab in zip(texts, labels, strict=True) if (t or "").strip() and lab]
        self.n_examples = len(pairs)
        self.pipeline = None
        self.classes = sorted({lab for _, lab in pairs})
        if len(pairs) < min_examples or len(self.classes) < 2:
            logger.info("DocKindModel: za mało danych (%d przykładów, %d klas) — bez treningu",
                        len(pairs), len(self.classes))
            return self
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        self.pipeline = make_pipeline(
            TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1, sublinear_tf=True,
                            lowercase=True, max_features=50000),
            LogisticRegression(max_iter=1000, C=5.0, class_weight="balanced"))
        self.pipeline.fit([t[:4000] for t, _ in pairs], [lab for _, lab in pairs])
        self.trained_at = datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")
        logger.info("DocKindModel: wytrenowany na %d przykładach, klasy %s", len(pairs), self.classes)
        return self

    def predict(self, text: str) -> tuple[str, float] | None:
        if self.pipeline is None or not (text or "").strip():
            return None
        probs = self.pipeline.predict_proba([text[:4000]])[0]
        best = int(probs.argmax())
        return str(self.pipeline.classes_[best]), float(probs[best])


# --- magazyn modeli (dysk + pamięć) --------------------------------------------------

_lock = threading.Lock()
_models: dict = {}   # {"ref": RefModel, "dockind": DocKindModel} — ładowane leniwie


def model_dir() -> pathlib.Path:
    """Domyślnie OBOK uploadów (np. /data/ml), nie w nich — joblib = pickle, a wolumen
    uploadów zapisują pliki od użytkowników i partnerów (audyt AI-007)."""
    path = pathlib.Path(settings.ml_model_dir
                        or (pathlib.Path(settings.uploads_dir).parent / "ml"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _signature(data: bytes) -> str:
    """HMAC-SHA256 pliku modelu kluczem z SECRET_KEY (etykieta kontekstu): podrzucony lub
    podmieniony plik nie ma poprawnego podpisu, więc nie trafi do joblib.load (AI-007).
    Zmiana SECRET_KEY = modele bez ważnego podpisu → puste do najbliższego treningu."""
    key = hashlib.sha256(b"timporye-ml-model:" + settings.secret_key.encode()).digest()
    return hmac.new(key, data, hashlib.sha256).hexdigest()


def _read_verified(file: pathlib.Path) -> bytes | None:
    sig_file = file.with_name(file.name + ".sig")
    data = file.read_bytes()
    expected = sig_file.read_text(encoding="ascii").strip() if sig_file.exists() else ""
    if not hmac.compare_digest(expected, _signature(data)):
        logger.warning("ML: %s bez ważnego podpisu — pomijam (trening zapisze nowy)", file.name)
        return None
    return data


def _load_from_disk() -> dict:
    import joblib
    out = {}
    for name, cls in (("ref", RefModel), ("dockind", DocKindModel)):
        file = model_dir() / f"{name}_model.joblib"
        if file.exists():
            try:
                data = _read_verified(file)
                # wczytujemy dokładnie te bajty, które sprawdził podpis (bez TOCTOU)
                loaded = joblib.load(io.BytesIO(data)) if data is not None else None
                out[name] = loaded if isinstance(loaded, cls) else cls()
            except Exception as exc:  # noqa: BLE001 — uszkodzony plik = jak brak modelu
                logger.warning("ML: nie wczytano %s: %s", file.name, exc)
                out[name] = cls()
        else:
            out[name] = cls()
    return out


def get_models() -> dict:
    with _lock:
        if not _models:
            _models.update(_load_from_disk())
        return dict(_models)


def invalidate() -> None:
    with _lock:
        _models.clear()


def training_data(db) -> tuple[list[dict], list[dict], list[str], list[str]]:
    """Czyste dane treningowe z bazy: materiały, zatwierdzone pary REF, teksty dokumentów."""
    from sqlalchemy import select

    from ..models import (
        INVOICE_LIKE_KINDS,
        InvoiceBatch,
        InvoiceItem,
        InvoiceJob,
        InvoiceJobStatus,
        InvoiceMatchStatus,
        Material,
    )
    # same kolumny: pełne ORM-y ciągnęłyby selectin-em wszystkie nadpisania per spółka
    materials = [{"ref_code": ref, "name_pl": pl, "name_en": en}
                 for ref, pl, en in db.execute(
                     select(Material.ref_code, Material.name_pl, Material.name_en)
                     .where(Material.is_active))]
    rows = db.execute(
        select(InvoiceBatch.supplier_id, InvoiceItem.raw_ref, InvoiceItem.descr, InvoiceItem.master_ref)
        .join(InvoiceJob, InvoiceItem.job_id == InvoiceJob.id)
        .join(InvoiceBatch, InvoiceJob.batch_id == InvoiceBatch.id)
        .where(InvoiceJob.status == InvoiceJobStatus.confirmed,
               InvoiceItem.match_status == InvoiceMatchStatus.matched,
               # decyzje operatora i reguł; dopasowania samego ML NIE wracają do historii —
               # inaczej jedna błędna auto-sugestia (≥ próg) utrwalałaby się z każdym
               # zatwierdzeniem jako „historia operatora” (pętla sprzężenia zwrotnego)
               InvoiceItem.match_source.in_(("user", "rules")),
               InvoiceItem.skipped.is_(False), InvoiceItem.master_ref != "")).all()
    examples = [{"supplier_id": r[0], "raw_ref": r[1], "descr": r[2], "master_ref": r[3]} for r in rows]
    texts, labels = [], []
    done = (InvoiceJobStatus.confirmed, InvoiceJobStatus.packing_list, InvoiceJobStatus.ignored)
    for job in db.scalars(select(InvoiceJob).where(InvoiceJob.status.in_(done),
                                                   InvoiceJob.text_excerpt != "")):
        if job.doc_kind in INVOICE_LIKE_KINDS and job.status != InvoiceJobStatus.confirmed:
            continue
        texts.append(job.text_excerpt)
        labels.append(job.doc_kind.value)
    return materials, examples, texts, labels


def _dump_atomic(obj, target: pathlib.Path) -> None:
    """Zapis przez plik tymczasowy + os.replace: równoległy odczyt nigdy nie trafi na
    w połowie zapisany plik (joblib.load rzuciłby i model „zniknąłby” do restartu)."""
    import joblib
    tmp = target.with_name(target.name + ".tmp")
    joblib.dump(obj, tmp)
    sig_tmp = target.with_name(target.name + ".sig.tmp")
    sig_tmp.write_text(_signature(tmp.read_bytes()), encoding="ascii")
    os.replace(tmp, target)
    os.replace(sig_tmp, target.with_name(target.name + ".sig"))


def train(db) -> dict:
    """Trenuje oba modele z bazy, zapisuje na dysk, odświeża pamięć. Zwraca statystyki."""
    materials, examples, texts, labels = training_data(db)
    ref_model = RefModel().fit(materials, examples)
    kind_model = DocKindModel().fit(texts, labels)
    directory = model_dir()
    _dump_atomic(ref_model, directory / "ref_model.joblib")
    _dump_atomic(kind_model, directory / "dockind_model.joblib")
    stats = _stats(ref_model, kind_model)
    (directory / "ml_meta.json").write_text(json.dumps(stats, ensure_ascii=False), encoding="utf-8")
    with _lock:
        _models.clear()
        _models.update({"ref": ref_model, "dockind": kind_model})
    return stats


# --- dotrenowanie w tle -----------------------------------------------------------------
# Zatwierdzenie faktury nie może czekać na TF-IDF po 10k materiałów + zapis na dysk.
# Jeden wątek treningowy naraz; kolejne żądania w trakcie treningu składają się w JEDNO
# ponowne uruchomienie po jego zakończeniu (coalescing), więc N zatwierdzeń = ≤ 2 treningi.

_train_state_lock = threading.Lock()
_train_running = False
_train_pending = False


def _train_worker() -> None:
    global _train_running, _train_pending
    from ..database import SessionLocal
    while True:
        db = SessionLocal()
        try:
            train(db)
        except Exception as exc:  # noqa: BLE001 — trening w tle nie może wywrócić wątku
            logger.warning("ML: trening w tle nie powiódł się: %s", exc)
        finally:
            db.close()
        with _train_state_lock:
            if not _train_pending:
                _train_running = False
                return
            _train_pending = False


def schedule_training() -> None:
    """Dotrenuj modele po zmianie danych (zatwierdzenie, import master daty).
    `ml_train_in_background=False` (testy) trenuje synchronicznie w bieżącym wątku."""
    global _train_running, _train_pending
    if not settings.ml_auto_train:
        return
    if not settings.ml_train_in_background:
        from ..database import SessionLocal
        db = SessionLocal()
        try:
            train(db)
        finally:
            db.close()
        return
    with _train_state_lock:
        if _train_running:
            _train_pending = True
            return
        _train_running = True
    threading.Thread(target=_train_worker, name="ml-train", daemon=True).start()


def _stats(ref_model: RefModel, kind_model: DocKindModel) -> dict:
    return {
        "ref_materials": ref_model.n_materials,
        "ref_examples": ref_model.n_examples,
        "ref_trained_at": ref_model.trained_at or None,
        "dockind_examples": kind_model.n_examples,
        "dockind_classes": kind_model.classes,
        "dockind_trained": kind_model.pipeline is not None,
        "dockind_trained_at": kind_model.trained_at or None,
        "auto_apply_threshold": settings.ml_auto_apply_threshold,
        "min_examples": settings.ml_min_examples,
    }


def stats() -> dict:
    models = get_models()
    return _stats(models["ref"], models["dockind"])


def suggest_ref(raw_ref: str, descr: str = "", supplier_id: int | None = None) -> list[Suggestion]:
    """Sugestie dla pipeline'u — bezpieczne: model niewytrenowany/uszkodzony = brak sugestii."""
    try:
        return get_models()["ref"].suggest(raw_ref, descr, supplier_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ML suggest_ref: %s", exc)
        return []


def predict_doc_kind(text: str) -> tuple[str, float] | None:
    try:
        return get_models()["dockind"].predict(text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ML predict_doc_kind: %s", exc)
        return None
