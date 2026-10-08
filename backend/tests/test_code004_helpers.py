"""CODE-004: funkcje o złożoności > 30 rozbite na pomocniki — testy wydzielonych kawałków
(zachowanie całości pilnują dotychczasowe testy: AIS, pakowanie, kontrole faktur, wyceny,
sygnały, import master daty)."""
import datetime
import json
import types
from decimal import Decimal

import pytest

from app.invoices import checks, master_import
from app.models import ContainerStatus, DocumentStatus
from app.packing import container as packing
from app.routers import quotes_core
from app.tracking import ais

N = types.SimpleNamespace
TODAY = datetime.date(2026, 9, 22)


# --- AIS: dispatch po typie komunikatu ----------------------------------------------------

def test_ais_static_data_sets_dimensions_imo_and_position():
    vessel = N(imo=None, destination="", ais_eta=None, length_m=None, beam_m=None,
               last_seen=None, lat=None, lon=None)
    body = {"ShipStaticData": {"Destination": " PLGDN  ", "ImoNumber": 9876543,
                               "Dimension": {"A": 200, "B": 99, "C": 20, "D": 12}}}
    now = datetime.datetime(2026, 9, 22, 10, 0)
    ais._apply_static(None, vessel, body, {"latitude": 54.4, "longitude": 18.6}, now)
    assert (vessel.destination, vessel.imo, vessel.length_m, vessel.beam_m) == ("PLGDN", 9876543, 299, 32)
    assert (vessel.lat, vessel.lon, vessel.last_seen) == (54.4, 18.6, now)


def test_ais_unknown_message_type_is_ignored_without_commit():
    class Db:
        def commit(self):
            raise AssertionError("brak commitu dla nieobsługiwanego typu")

        def scalar(self, _stmt):
            return None
    vessel = N(mmsi=1, name="MV DEMO ATLAS")
    raw = json.dumps({"MessageType": "UnknownType", "MetaData": {"ShipName": "MV DEMO ATLAS"}})
    assert ais.handle_message(Db(), raw, {"MV DEMO ATLAS": vessel}) is False
    assert set(ais._HANDLERS) == {"PositionReport", "ShipStaticData"}


def test_ais_learn_mmsi_skips_conflict():
    class Db:
        def scalar(self, _stmt):
            return 7   # inny wiersz ma już ten MMSI
    vessel = N(mmsi=None, id=1, name="X")
    ais._learn_mmsi(Db(), vessel, {"MMSI": "123"})
    assert vessel.mmsi is None


# --- pakowanie kontenera: fazy ---------------------------------------------------------------

def test_packing_groups_exclude_bad_qty_and_sort_by_volume():
    rows = {"A": [], "B": []}
    items = [N(quantity="0", material="A", order_number="1", unit="KAR"),
             N(quantity="2", material="MISSING", order_number="2", unit="KAR")]
    excluded: list[dict] = []
    assert packing._sku_groups(items, rows, excluded) == []
    assert [e["reason"] for e in excluded][0] == "nieprawidłowa ilość"
    assert len(excluded) == 2


def test_packing_pool_slices_exclude_when_no_room():
    p = packing._Packing((100.0, 50.0, 50.0))
    p.cursor_x = 95.0
    g = {"sku": "S", "dims": (10.0, 10.0, 10.0), "order_no": "1", "color": "#000",
         "approximated": False}
    packing._place_pool_slices(p, [g])
    assert p.boxes == [] and p.excluded[0]["reason"] == "nie zmieściło się"


# --- kontrole faktury: grupy i wiersze -------------------------------------------------------

def _item(ref, qty, amount, weight="1", raw=None, cn="9018", name="X"):
    return N(master_ref=ref, raw_ref=raw or ref, qty=qty, amount=amount, uom_src="",
             weight_net=weight, tariff_cn=cn, name_pl=name)


def test_checks_group_items_sums_and_flags_missing_weight():
    groups = checks._group_items([_item("A", "2", "10"), _item("A", "3", "5", weight=None)],
                                 {}, [])
    g = groups["A"]
    assert (g["qty"], g["amount"], g["qty_base"]) == (Decimal(5), Decimal(15), Decimal(5))
    assert g["no_weight"] is True and g["no_factor"] is False


def test_checks_group_row_reports_missing_data():
    g = checks._group_items([_item("A", "2", "10", cn="", name="")], {}, [])["A"]
    row = checks._group_row("A", g, None, {}, [], [], 1.0)
    assert row["missing"] == ["cn", "name_pl"] and row["ci_pl"] is None and row["ci_order"] is None
    assert row["price_base"] == checks._s(Decimal("5.0000"))


# --- wyceny: widok spedytora -----------------------------------------------------------------

def test_quotes_forwarder_view_hides_market_data():
    quotes, mine, scfi, kpi = quotes_core._forwarder_view(None, passed=True)
    assert (quotes, mine, scfi) == ([], None, "") and kpi.deadline_passed is True


# --- sygnały: reguły -------------------------------------------------------------------------

def _c(**kw):
    base = dict(id=1, container_no="MEDU1234562", company=None, supplier=None, port=None,
                eta=None, notify_date=None, planning_eta_at_send=None,
                status=ContainerStatus.W_TRANSPORCIE, document_status=DocumentStatus.ZALACZONE,
                is_delayed=False, is_stuck=False)
    base.update(kw)
    return N(**base)


def test_signal_rules_order_and_eta_shift_threshold():
    from app.signals import SIGNAL_WEIGHTS, _RULES, _Ctx, _sig_eta_shift
    assert [r.__name__ for r in _RULES][:3] == ["_sig_demurrage", "_sig_delayed", "_sig_stuck"]
    ctx = _Ctx(TODAY, SIGNAL_WEIGHTS, 0, None, None, None)
    small = _c(eta=TODAY + datetime.timedelta(days=11),
               planning_eta_at_send=TODAY + datetime.timedelta(days=10))
    big = _c(eta=TODAY + datetime.timedelta(days=13),
             planning_eta_at_send=TODAY + datetime.timedelta(days=10))
    assert _sig_eta_shift(small, ctx) is None
    assert _sig_eta_shift(big, ctx)[:2] == ("eta_shift", 3)


# --- import master daty: klasyfikacja nagłówków ----------------------------------------------

@pytest.mark.parametrize(("header", "banner", "expected"), [
    ("Ref", "", ("global", "ref_code")),
    ("Opis PL", "", ("global", "name_pl")),
    ("Kod producenta (Fushide)", "", ("global", "producer_code")),
    ("EAN", "", ("global", "ean")),
    ("EAN", "KAR", ("level", ("karton", "ean"))),
    ("kar_wymiar", "", ("level", ("karton", "wymiar"))),
    ("Ilość podstawowej jednostki miary", "PAZ", ("level", ("paz", "qty_base"))),
    ("przelicznik ppa", "", ("level", ("ppa", "qty_base"))),
    ("wymiary", "", (None, None)),
    ("", "KAR", (None, None)),
])
def test_master_classify(header, banner, expected):
    assert master_import._classify(header, banner) == expected
