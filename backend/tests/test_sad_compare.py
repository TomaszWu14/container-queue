"""Porównanie draftu SAD z paczką faktur (PR 2, spec 2026-09-29-agencja-draft-sad §2):
nasza strona w grupach CN (kartoteka, wagi, j. uzupełniające, koszty dodatkowe) i reguły
porównania — zgodne, rozbieżny CN / wartość / masa, brakujące i nadmiarowe CN, nieodczytane."""
import copy

from sqlalchemy import select

from app.invoices import sad_compare, sad_ours, sad_parse, sad_winsad
from app.models import (Company, InvoiceBatch, InvoiceDocKind, InvoiceItem, InvoiceJob,
                        InvoiceJobStatus, Material, Supplier, SupplierDocProfile)
from tests.test_invoices_api import _container
from tests.test_sad_parse import SAD


def test_batch_side_groups_by_cn(client, admin_headers, db_session):
    company = db_session.scalars(select(Company)).first()
    # nadawca spółki: dostawca z kartoteki (client_company_id NULL) wolno podpiąć tylko
    # w spółkach na materiałach Acme (deps.supplier_clause_for_company)
    sup = Supplier(name="Acme SAD", country="cn", client_company_id=company.id)
    sup.doc_profile = SupplierDocProfile(status="draft", currency="usd",
                                         tol_amount_pct=1.0, tol_qty_pct=2.0)
    db_session.add_all([
        sup,
        Material(ref_code="A1", ref_norm="A1", base_uom="SZT", tariff_cn="4015 19 00",
                 suppl_unit="pary", suppl_factor=0.5),
        Material(ref_code="B2", ref_norm="B2", base_uom="SZT", tariff_cn="40151900",
                 suppl_unit="pary", suppl_factor=1.0),
        Material(ref_code="C3", ref_norm="C3", base_uom="SZT", tariff_cn="")])
    db_session.commit()
    cid = _container(client, admin_headers, company_id=company.id, supplier_id=sup.id)
    batch = InvoiceBatch(container_id=cid, supplier_id=sup.id)
    db_session.add(batch)
    db_session.flush()
    job = InvoiceJob(batch_id=batch.id, filename="ci.pdf", stored_name="ci.pdf",
                     status=InvoiceJobStatus.confirmed, invoice_number="T-1",
                     check_data={"charges": [{"desc": "freight", "amount": "100.00"}]})
    packing = InvoiceJob(batch_id=batch.id, filename="pl.pdf", stored_name="pl.pdf",
                         doc_kind=InvoiceDocKind.packing_list, status=InvoiceJobStatus.packing_list)
    db_session.add_all([job, packing])
    db_session.flush()
    db_session.add_all([
        InvoiceItem(job_id=job.id, line_no=1, raw_ref="A1", master_ref="A1", qty="100",
                    amount="1,000.00", weight_net="12,500"),
        InvoiceItem(job_id=job.id, line_no=2, raw_ref="A1", master_ref="A1", qty="50",
                    amount="500.00"),                         # waga REF tylko na 1. linii (PL)
        InvoiceItem(job_id=job.id, line_no=3, raw_ref="B2", master_ref="B2", qty="10",
                    amount="55.50", weight_net="1"),
        InvoiceItem(job_id=job.id, line_no=4, raw_ref="C3", master_ref="C3", qty="1", amount="5"),
        InvoiceItem(job_id=job.id, line_no=5, raw_ref="X9", qty="1", amount="999", skipped=True)])
    db_session.commit()

    ours = sad_ours.batch_side(db_session, db_session.get(InvoiceBatch, batch.id))
    assert (ours["invoices"], ours["currency"], ours["country"]) == (["T-1"], "USD", "CN")
    assert ours["container"] == "MSDU0806613"
    assert (ours["total"], ours["charges"]) == ("1660.5", "100")     # pozycje + koszty, bez pominiętej
    assert ours["no_cn"] == ["C3"] and (ours["tol_amount_pct"], ours["tol_qty_pct"]) == (1.0, 2.0)
    assert ours["groups"] == {"40151900": {
        "cn": "40151900", "value": "1555.5", "net_mass": "13.5", "suppl_qty": "85",
        "suppl_unit": "pary", "refs": ["A1", "B2"]}}


OURS = {"invoices": ["T-1", "T-2"], "container": "MSDU0806613", "currency": "USD", "total": "1205.5", "charges": "0",
        "country": "CN", "no_cn": [], "tol_amount_pct": 0.5, "tol_qty_pct": 0.0,
        "groups": {"90183900": {"cn": "90183900", "value": "950", "net_mass": "12.5",
                                "suppl_qty": None, "suppl_unit": "", "refs": ["NL753"]},
                   "40151900": {"cn": "40151900", "value": "255.5", "net_mass": "3",
                                "suppl_qty": "775", "suppl_unit": "pary", "refs": ["A1"]}}}


def _statuses(result: dict) -> dict:
    return {g["cn"]: g["status"] for g in result["groups"]}


def test_all_matching():
    result = sad_compare.compare(OURS, sad_parse.parse_text([SAD]))
    assert result["summary"] == {"groups": 2, "ok": 2, "diff": 0, "manual": 0, "all_ok": True}
    assert [h["ok"] for h in result["header"]] == [True, True, True, True, True]


def test_discrepancies_value_missing_extra_invoice():
    ours = copy.deepcopy(OURS)
    ours["invoices"].append("T-3")
    ours["groups"]["90183900"].update(value="900", net_mass="12")    # masa: 0,5 kg = w ±1 kg
    ours["groups"]["84713000"] = {"cn": "84713000", "value": "10", "net_mass": "1",
                                  "suppl_qty": None, "suppl_unit": "", "refs": ["Z9"]}
    del ours["groups"]["40151900"]
    result = sad_compare.compare(ours, sad_parse.parse_text([SAD]))
    assert _statuses(result) == {"40151900": "extra_in_sad", "84713000": "missing_in_sad",
                                 "90183900": "diff"}
    row = next(g for g in result["groups"] if g["cn"] == "90183900")
    assert row["value"]["ok"] is False and row["net_mass"]["ok"] is True
    assert result["header"][0]["ok"] is False and result["header"][0]["detail"] == "T-3"
    assert result["summary"]["all_ok"] is False


def test_mass_beyond_one_kg_and_charges_in_header_total():
    ours = copy.deepcopy(OURS)
    ours["groups"]["90183900"]["net_mass"] = "14"
    assert _statuses(sad_compare.compare(ours, sad_parse.parse_text([SAD])))["90183900"] == "diff"
    ours = copy.deepcopy(OURS)
    ours.update(total="1305.5", charges="100")                      # koszty dodatkowe w sumie
    header = sad_compare.compare(ours, sad_parse.parse_text(
        [SAD.replace("USD 1 205,50", "USD 1 305,50")]))["header"]
    assert header[2]["ok"] is True and header[2]["detail"] == "100"
    assert sad_compare.compare(ours, sad_parse.parse_text([SAD]))["header"][2]["ok"] is False


def test_unread_or_missing_data_means_manual_check():
    ours = copy.deepcopy(OURS)
    ours["groups"]["90183900"]["net_mass"] = None                    # REF bez wagi po naszej stronie
    parsed = sad_parse.parse_text([SAD.replace("41 Jednostki uzupełniające: 775\n", "")])
    result = sad_compare.compare(ours, parsed)
    assert _statuses(result) == {"40151900": "manual", "90183900": "manual"}
    assert result["summary"]["manual"] == 2 and result["summary"]["all_ok"] is False


def test_invoice_numbers_match_as_tokens_not_fragments():
    # „T-1” bez rubryki 44: „T1” siedzi w „DRAFT\n15a”, ale to nie jest numer faktury
    parsed = sad_parse.parse_text([SAD.replace("N380 T-1; N380 T-2", "brak")])
    header = sad_compare.compare(OURS, parsed)["header"][0]
    assert header["ok"] is False and header["detail"] == "T-1, T-2"
    spaced = sad_parse.parse_text([SAD.replace("N380 T-1; N380 T-2", "N380 T 1 / N380 T/2")])
    assert sad_compare.compare(OURS, spaced)["header"][0]["ok"] is True


def test_container_mismatch_and_winsad_draft():
    """Draft dla innego kontenera = rozbieżność w nagłówku; układ WinSAD porównuje się tak samo."""
    from tests.test_sad_parse import WINSAD
    fields, declared = sad_winsad.parse(WINSAD)
    parsed = sad_parse._finish(fields, WINSAD, "winsad", declared)
    result = sad_compare.compare(OURS, parsed)
    assert result["summary"]["all_ok"] is True
    other = sad_compare.compare({**OURS, "container": "TGBU6784203"}, parsed)
    row = next(h for h in other["header"] if h["field"] == "container")
    assert row["ok"] is False and row["sad"] == "MSDU0806613"
    assert other["summary"]["all_ok"] is False
