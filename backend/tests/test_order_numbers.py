"""Kanon dzielenia Container.order_numbers — jedna funkcja dla wszystkich ścieżek."""
from types import SimpleNamespace

from app.importers.purchasing import _link_container_id
from app.order_numbers import split_order_numbers
from app.routers.containers_contents import container_order_numbers
from app.routers.customer_orders import _container_refs
from app.routers.quotes_core import _has_transit_number


def test_split_order_numbers():
    assert split_order_numbers("4500617421;4700001234") == ["4500617421", "4700001234"]
    assert split_order_numbers("111 222,\n333") == ["111", "222", "333"]
    assert split_order_numbers("4500625519A") == ["4500625519A"]      # sufiks zostaje
    assert split_order_numbers("4500624622 & 4500055555") == ["4500624622", "4500055555"]
    assert split_order_numbers("PO-100, PO-101") == ["PO-100", "PO-101"]
    assert split_order_numbers("-47 / 47, 47") == ["47"]               # brzegowe '-', duplikat
    assert split_order_numbers(None) == [] and split_order_numbers("") == []


def test_callers_share_semantics():
    # średnik: kiedyś quotes (split(',')) nie widział drugiego numeru 47…
    assert _has_transit_number("4500617421;4700001234")
    # …a container_order_numbers (\d{4,}) obcinał sufiks „A"
    c = SimpleNamespace(order_numbers="4500625519A; 12", order=None)
    assert container_order_numbers(c) == ["4500625519", "4500625519A"]
    assert _link_container_id("4500625519A", [(7, "4500625519A")]) == 7
    assert _link_container_id("4500625519", [(7, "4500625519A")]) is None


def test_no_caller_extracts_fewer_numbers_than_before():
    # review #542: stary findall(\d{4,}) wyciągał numer SAP z prefiksu/sufiksu/myślnika
    c = SimpleNamespace(order_numbers="PO4500012345, 4500012346-10; nr4500012347 PO 12",
                        order=None)
    nums = container_order_numbers(c)
    for n in ("4500012345", "4500012346", "4500012347", "4500012346-10"):
        assert n in nums
    assert "PO" not in nums and "12" not in nums   # walidacja linku SENT bez śmieci
    # ETD „4500625519-1" nadal linkuje się do kontenera z „4500625519" (jak przed zmianą)
    assert _link_container_id("4500625519-1", [(7, "4500625519")]) == 7


def test_customer_order_ref_with_slash_still_matches():
    """Review #542: ref specjalnej troski „4500617421/10” musi trafić w cały token
    kontenera (dawny podział po przecinku, średniku i spacji), a pojedyncze numery nadal też."""
    refs = _container_refs("4500617421/10, 4500617422")
    assert {"4500617421/10", "4500617422", "4500617421"} <= refs
