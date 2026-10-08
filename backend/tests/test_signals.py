"""Silnik sygnałów: wykrywanie typów, punktacja i sort dla listy 'Co dziś'.
Czysta funkcja — bez DB, na lekkich atrapach kontenera."""
import datetime
import types

from app.signals import compute_signals
from app.models import ContainerStatus, DocumentStatus

TODAY = datetime.date(2026, 9, 22)


def _c(**kw):
    """Atrapa kontenera: tylko pola/właściwości, których dotyka compute_signals."""
    defaults = dict(
        id=1, container_no="MEDU1234562",
        company=types.SimpleNamespace(name="ACME"),
        supplier=types.SimpleNamespace(name="Fushide"),
        port=types.SimpleNamespace(name="Gdańsk"),
        eta=None, notify_date=None, planning_eta_at_send=None,
        status=ContainerStatus.W_TRANSPORCIE,
        document_status=DocumentStatus.ZALACZONE,
        is_delayed=False, is_stuck=False,
    )
    defaults.update(kw)
    return types.SimpleNamespace(**defaults)


def test_detects_delayed():
    c = _c(is_delayed=True, eta=datetime.date(2026, 9, 15),
           status=ContainerStatus.W_PORCIE)
    feed = compute_signals([c], {c.id: None}, TODAY)
    types_ = {s["type"] for s in feed}
    assert "delayed" in types_


def test_demurrage_has_cost_and_outranks_missing_docs():
    demur = _c(id=1, container_no="MEDU1234562",
               eta=datetime.date(2026, 9, 20), status=ContainerStatus.W_PORCIE)
    docs = _c(id=2, container_no="CAIU7654324",
              document_status=DocumentStatus.BRAK)
    deadlines = {1: datetime.date(2026, 9, 24), 2: None}
    feed = compute_signals([demur, docs], deadlines, TODAY)
    demur_sig = next(s for s in feed if s["type"] == "demurrage")
    docs_sig = next(s for s in feed if s["type"] == "missing_docs")
    assert demur_sig["cost_eur"] and demur_sig["cost_eur"] > 0
    assert demur_sig["summary_key"] == "sigSum_demurrage"
    assert demur_sig["summary_params"]["cost"] > 0
    # demurrage z kosztem musi być wyżej na liście niż drobny brak dokumentu
    assert feed.index(demur_sig) < feed.index(docs_sig)


def test_missing_avizo_and_eta_and_action_kinds():
    avizo = _c(id=1, eta=datetime.date(2026, 9, 23), notify_date=None,
               status=ContainerStatus.W_TRANSPORCIE)
    no_eta = _c(id=2, container_no="CAIU7654324",
                eta=None, status=ContainerStatus.W_PORCIE)
    feed = compute_signals([avizo, no_eta], {1: None, 2: None}, TODAY)
    by_type = {s["type"]: s for s in feed}
    assert by_type["missing_avizo"]["action_kind"] == "avizo-form"
    assert "missing_eta" in by_type


def test_one_container_can_emit_multiple_signals():
    c = _c(is_delayed=True, eta=datetime.date(2026, 9, 10),
           status=ContainerStatus.W_PORCIE, document_status=DocumentStatus.BRAK)
    feed = compute_signals([c], {c.id: None}, TODAY)
    assert len({s["type"] for s in feed}) >= 2


def test_eta_shift_signal():
    # ETA przesunęła się o 5 dni względem zdjęcia z chwili awizacji (#25)
    c = _c(eta=datetime.date(2026, 9, 30), planning_eta_at_send=datetime.date(2026, 9, 25),
           status=ContainerStatus.W_TRANSPORCIE)
    by = {s["type"]: s for s in compute_signals([c], {c.id: None}, TODAY)}
    assert "eta_shift" in by and by["eta_shift"]["summary_params"]["days"] == 5


def test_po_unconfirmed_from_orders_map():
    # #9 — dane potwierdzenia zamówienia przychodzą mapą orders (spoza silnika)
    c = _c(eta=datetime.date(2026, 10, 10), notify_date=datetime.date(2026, 10, 5))
    feed = compute_signals([c], {c.id: None}, TODAY, orders={c.id: {"unconfirmed": True, "days": 7}})
    by = {s["type"]: s for s in feed}
    assert by["po_unconfirmed"]["summary_params"]["days"] == 7
    assert by["po_unconfirmed"]["action_kind"] == "container"


def test_docs_pre_eta_vs_plain_missing_docs():
    # brak dokumentów: w oknie przed ETA → docs_pre_eta; daleko → zwykły missing_docs (#30)
    near = _c(id=1, eta=datetime.date(2026, 9, 25), status=ContainerStatus.W_PORCIE,
              document_status=DocumentStatus.BRAK)
    far = _c(id=2, container_no="CAIU7654324", eta=datetime.date(2026, 11, 30),
             status=ContainerStatus.W_TRANSPORCIE, document_status=DocumentStatus.BRAK)
    feed = compute_signals([near, far], {1: None, 2: None}, TODAY)
    by = {s["type"]: s for s in feed}
    assert by["docs_pre_eta"]["summary_params"]["days"] == 3 and "missing_docs" in by
    near_docs = [s for s in feed if s["container_id"] == 1
                 and s["type"] in ("docs_pre_eta", "missing_docs")]
    assert len(near_docs) == 1   # jeden sygnał dokumentowy na kontener


def test_empty_when_all_clear():
    c = _c(eta=datetime.date(2026, 10, 30), notify_date=datetime.date(2026, 10, 25),
           status=ContainerStatus.W_TRANSPORCIE, document_status=DocumentStatus.ZALACZONE)
    feed = compute_signals([c], {c.id: None}, TODAY)
    assert feed == []


def test_finished_container_has_no_signals():
    """DOSTARCZONY z przeterminowanym demurrage i brakiem dokumentów nie trafia do 'Co dziś'."""
    c = _c(status=ContainerStatus.DOSTARCZONY, eta=datetime.date(2026, 9, 2),
           document_status=DocumentStatus.BRAK)
    assert compute_signals([c], {c.id: datetime.date(2026, 9, 6)}, TODAY) == []


def test_special_care_signal_from_care_map():
    # D13: ryzyko T1/T2 specjalnej troski trafia do 'Co dziś' jako osobny typ
    c = _c()
    feed = compute_signals([c], {c.id: None}, TODAY,
                           care={c.id: {"name": "Zam. X", "t1": True, "days": 4}})
    by = {s["type"]: s for s in feed}
    assert by["special_care"]["summary_key"] == "sigSum_special_care_etd"
    assert by["special_care"]["summary_params"] == {"name": "Zam. X", "days": 4}
    feed = compute_signals([c], {c.id: None}, TODAY,
                           care={c.id: {"name": "Zam. X", "t1": False, "days": 2}})
    assert feed[0]["summary_key"] == "sigSum_special_care_late"
