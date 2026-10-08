"""Wyceny (RFQ): tworzenie zlecenia, wysyłka, oferty, wybór zwycięzcy, izolacja spedytorów."""
import datetime

from app.database import SessionLocal
from app.models import TransportJob
from tests.conftest import forwarder, login


def _company_id(client, headers, code):
    companies = client.get("/api/companies", headers=headers).json()
    return next(c["id"] for c in companies if c["code"] == code)


def _container(client, headers, no, company_id):
    return client.post("/api/containers", headers=headers, json={
        "container_no": no, "company_id": company_id}).json()["id"]


def _forwarder_account(client, headers, login_name, forwarder_id):
    client.post("/api/users", headers=headers, json={
        "login": login_name, "password": "haslo123", "role": "forwarder",
        "forwarder_id": forwarder_id, "email": f"{login_name}@example.com"})
    return login(client, login_name, "haslo123")


def test_quote_full_flow(client, admin_headers):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    c1 = _container(client, admin_headers, "MSDU0806613", borealis)
    c2 = _container(client, admin_headers, "CSQU3054383", borealis)
    spedalfa = forwarder(client, admin_headers, "SPEDALFA")["id"]
    gamma = forwarder(client, admin_headers, "Spedgamma")["id"]
    dsv_h = _forwarder_account(client, admin_headers, "sped.spedalfa", spedalfa)
    gamma_h = _forwarder_account(client, admin_headers, "sped.gamma", gamma)

    # zlecenie z 2 kontenerów, zaproszone 2 spedycje
    job = client.post("/api/transport-jobs", headers=admin_headers, json={
        "container_ids": [c1, c2], "forwarder_ids": [spedalfa, gamma],
        "pickup_location": "DCT Gdańsk", "delivery_location": "DLT"}).json()
    assert job["status"] == "SZKIC"
    assert job["container_count"] == 2 and len(job["quotes"]) == 2

    # SZKIC — spedytor jeszcze nic nie widzi
    assert client.get("/api/transport-jobs", headers=dsv_h).json() == []

    # wysyłamy do wyceny
    sent = client.post(f"/api/transport-jobs/{job['id']}/send", headers=admin_headers)
    assert sent.status_code == 200 and sent.json()["status"] == "WYSLANE"

    # SPEDALFA widzi zlecenie, ale TYLKO swoją ofertę (nie Omidy)
    dsv_jobs = client.get("/api/transport-jobs", headers=dsv_h).json()
    assert len(dsv_jobs) == 1
    assert len(dsv_jobs[0]["quotes"]) == 1
    assert dsv_jobs[0]["quotes"][0]["forwarder_id"] == spedalfa

    # SPEDALFA i Spedgamma wyceniają
    client.post(f"/api/transport-jobs/{job['id']}/quote", headers=dsv_h,
                json={"amount": "1500.00", "currency": "PLN"})
    client.post(f"/api/transport-jobs/{job['id']}/quote", headers=gamma_h,
                json={"amount": "1800.00", "currency": "PLN"})

    # spedytor NIE widzi ceny konkurencji
    dsv_view = client.get(f"/api/transport-jobs/{job['id']}", headers=dsv_h).json()
    assert len(dsv_view["quotes"]) == 1
    assert dsv_view["my_quote"]["amount"] == "1500.00"

    # admin widzi obie oferty, posortowane rosnąco po cenie
    admin_view = client.get(f"/api/transport-jobs/{job['id']}", headers=admin_headers).json()
    amounts = [q["amount"] for q in admin_view["quotes"]]
    assert amounts == ["1500.00", "1800.00"]

    # wybór taniej oferty (SPEDALFA)
    winner_id = next(q["id"] for q in admin_view["quotes"] if q["forwarder_id"] == spedalfa)
    chosen = client.post(f"/api/transport-jobs/{job['id']}/choose", headers=admin_headers,
                         json={"quote_id": winner_id}).json()
    assert chosen["status"] == "ZLECONE" and chosen["chosen_quote_id"] == winner_id
    statuses = {q["forwarder_id"]: q["status"] for q in chosen["quotes"]}
    assert statuses[spedalfa] == "WYBRANA" and statuses[gamma] == "ODRZUCONA"


def test_forwarder_cannot_see_others_job(client, admin_headers):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    c1 = _container(client, admin_headers, "TGBU6784203", borealis)
    spedalfa = forwarder(client, admin_headers, "SPEDALFA")["id"]
    toll = forwarder(client, admin_headers, "Speddelta")["id"]
    toll_h = _forwarder_account(client, admin_headers, "sped.toll", toll)
    # zlecenie tylko dla SPEDALFA, wysłane
    job = client.post("/api/transport-jobs", headers=admin_headers, json={
        "container_ids": [c1], "forwarder_ids": [spedalfa]}).json()
    client.post(f"/api/transport-jobs/{job['id']}/send", headers=admin_headers)
    # Toll (niezaproszony) nie widzi ani na liście, ani po id
    assert client.get("/api/transport-jobs", headers=toll_h).json() == []
    assert client.get(f"/api/transport-jobs/{job['id']}", headers=toll_h).status_code == 404
    # Toll nie może też wycenić
    assert client.post(f"/api/transport-jobs/{job['id']}/quote", headers=toll_h,
                       json={"amount": "1000.00"}).status_code == 404


def test_quote_deadline_kpi_and_carrier(client, admin_headers):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    c1 = _container(client, admin_headers, "MSDU0806613", borealis)
    spedalfa = forwarder(client, admin_headers, "SPEDALFA")["id"]
    gamma = forwarder(client, admin_headers, "Spedgamma")["id"]
    dsv_h = _forwarder_account(client, admin_headers, "sped.spedalfa", spedalfa)
    carrier = client.post("/api/carriers", headers=admin_headers, json={"name": "MSC"}).json()

    job = client.post("/api/transport-jobs", headers=admin_headers, json={
        "container_ids": [c1], "forwarder_ids": [spedalfa, gamma],
        "response_hours": 24, "scfi_index": "1200 USD/FEU"}).json()
    assert job["response_hours"] == 24 and job["scfi_index"] == "1200 USD/FEU"

    sent = client.post(f"/api/transport-jobs/{job['id']}/send", headers=admin_headers).json()
    assert sent["response_deadline"] is not None
    assert sent["kpi"]["invited"] == 2 and sent["kpi"]["responded"] == 0

    # SPEDALFA wycenia z armatorem, ETD/ETA, transit i flagami
    client.post(f"/api/transport-jobs/{job['id']}/quote", headers=dsv_h, json={
        "amount": "1500.00", "currency": "USD", "carrier_id": carrier["id"],
        "etd": "2026-08-01", "eta": "2026-09-02", "transit_time_days": 32,
        "no_equipment": False, "can_roll_booking": True})
    view = client.get(f"/api/transport-jobs/{job['id']}", headers=admin_headers).json()
    q = next(q for q in view["quotes"] if q["forwarder_id"] == spedalfa)
    assert q["carrier_name"] == "MSC" and q["transit_time_days"] == 32
    assert q["can_roll_booking"] is True and q["eta"] == "2026-09-02"
    assert view["kpi"]["responded"] == 1 and view["kpi"]["response_rate"] == 50

    # spedytor NIE widzi SCFI ani statystyk odpowiedzi konkurencji (tylko własny termin)
    dsv_view = client.get(f"/api/transport-jobs/{job['id']}", headers=dsv_h).json()
    assert dsv_view["scfi_index"] == ""
    assert dsv_view["kpi"]["invited"] == 0 and dsv_view["kpi"]["responded"] == 0


def test_quote_after_deadline_still_accepted(client, admin_headers):
    """Q36: oferty przyjmowane także po terminie (do wyboru zwycięzcy); termin
    pozostaje informacyjny w KPI, a oferta bez ceny widnieje jako WYGASLA."""
    borealis = _company_id(client, admin_headers, "BOREALIS")
    c1 = _container(client, admin_headers, "CSQU3054383", borealis)
    spedalfa = forwarder(client, admin_headers, "SPEDALFA")["id"]
    gamma = forwarder(client, admin_headers, "Spedgamma")["id"]
    dsv_h = _forwarder_account(client, admin_headers, "sped.spedalfa", spedalfa)
    job = client.post("/api/transport-jobs", headers=admin_headers, json={
        "container_ids": [c1], "forwarder_ids": [spedalfa, gamma]}).json()
    client.post(f"/api/transport-jobs/{job['id']}/send", headers=admin_headers)
    # cofamy termin w bazie → termin minął, ale wycena wciąż otwarta
    with SessionLocal() as db:
        j = db.get(TransportJob, job["id"])
        j.response_deadline = datetime.datetime.utcnow() - datetime.timedelta(hours=1)
        db.commit()
    resp = client.post(f"/api/transport-jobs/{job['id']}/quote", headers=dsv_h,
                       json={"amount": "1000.00"})
    assert resp.status_code == 200 and resp.json()["my_quote"]["status"] == "WYCENIONA"
    # Spedgamma nie odpowiedziała — po terminie jej oferta widnieje jako WYGASLA
    view = client.get(f"/api/transport-jobs/{job['id']}", headers=admin_headers).json()
    assert view["kpi"]["deadline_passed"] is True
    gamma_q = next(q for q in view["quotes"] if q["forwarder_id"] == gamma)
    assert gamma_q["status"] == "WYGASLA"


def test_agent_and_shipment_number_flow(client, admin_headers):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    c1 = _container(client, admin_headers, "MSDU0806613", borealis)
    spedalfa = forwarder(client, admin_headers, "SPEDALFA")["id"]
    gamma = forwarder(client, admin_headers, "Spedgamma")["id"]
    dsv_h = _forwarder_account(client, admin_headers, "sped.spedalfa", spedalfa)
    gamma_h = _forwarder_account(client, admin_headers, "sped.gamma", gamma)

    job = client.post("/api/transport-jobs", headers=admin_headers, json={
        "container_ids": [c1], "forwarder_ids": [spedalfa, gamma]}).json()
    client.post(f"/api/transport-jobs/{job['id']}/send", headers=admin_headers)
    client.post(f"/api/transport-jobs/{job['id']}/quote", headers=dsv_h,
                json={"amount": "1500.00"})
    # przed wyborem: spedytor nie może podać agenta
    assert client.post(f"/api/transport-jobs/{job['id']}/agent", headers=dsv_h,
                       json={"agent_name": "X", "agent_phone": "1", "agent_company": "C"}
                       ).status_code == 403

    winner = client.get(f"/api/transport-jobs/{job['id']}", headers=admin_headers).json()
    wid = next(q["id"] for q in winner["quotes"] if q["forwarder_id"] == spedalfa)
    client.post(f"/api/transport-jobs/{job['id']}/choose", headers=admin_headers,
                json={"quote_id": wid})

    # logistyka dostała przypomnienie o numerze przesyłki (brak numeru)
    notes = client.get("/api/notifications", headers=admin_headers).json()
    assert any("numer przesyłki" in n["title"].lower() for n in notes)

    # logistyka uzupełnia numer przesyłki
    upd = client.patch(f"/api/transport-jobs/{job['id']}", headers=admin_headers,
                       json={"shipment_number": "BK-99887766"}).json()
    assert upd["shipment_number"] == "BK-99887766"

    # zwycięska spedycja (SPEDALFA) podaje agenta
    r = client.post(f"/api/transport-jobs/{job['id']}/agent", headers=dsv_h, json={
        "agent_name": "Jan Kowalski", "agent_phone": "+48 600", "agent_company": "AgentCo"})
    assert r.status_code == 200 and r.json()["agent_name"] == "Jan Kowalski"
    # zwycięzca widzi numer przesyłki, przegrany (Spedgamma) NIE
    dsv_view = client.get(f"/api/transport-jobs/{job['id']}", headers=dsv_h).json()
    assert dsv_view["shipment_number"] == "BK-99887766"
    gamma_view = client.get(f"/api/transport-jobs/{job['id']}", headers=gamma_h).json()
    assert gamma_view["shipment_number"] == "" and gamma_view["agent_name"] == ""

    # Spedgamma (przegrana) nie może podać agenta
    assert client.post(f"/api/transport-jobs/{job['id']}/agent", headers=gamma_h,
                       json={"agent_name": "Y", "agent_phone": "1", "agent_company": "C"}
                       ).status_code == 403


def test_change_alert_price_revision_and_cancel(client, admin_headers):
    borealis = _company_id(client, admin_headers, "BOREALIS")
    c1 = _container(client, admin_headers, "MSDU0806613", borealis)
    spedalfa = forwarder(client, admin_headers, "SPEDALFA")["id"]
    gamma = forwarder(client, admin_headers, "Spedgamma")["id"]
    dsv_h = _forwarder_account(client, admin_headers, "sped.spedalfa", spedalfa)
    gamma_h = _forwarder_account(client, admin_headers, "sped.gamma", gamma)

    job = client.post("/api/transport-jobs", headers=admin_headers, json={
        "container_ids": [c1], "forwarder_ids": [spedalfa, gamma],
        "pickup_location": "DCT Gdańsk"}).json()
    client.post(f"/api/transport-jobs/{job['id']}/send", headers=admin_headers)

    # wiersz 19: zmiana miejsca odbioru wysłanego zlecenia alarmuje zaproszone spedycje
    upd = client.patch(f"/api/transport-jobs/{job['id']}", headers=admin_headers,
                       json={"pickup_location": "DCT Gdynia"}).json()
    assert upd["pickup_location"] == "DCT Gdynia"
    dsv_notes = client.get("/api/notifications", headers=dsv_h).json()
    assert any("zmiana w zleceniu" in n["title"].lower() for n in dsv_notes)

    client.post(f"/api/transport-jobs/{job['id']}/quote", headers=dsv_h,
                json={"amount": "1500.00", "currency": "USD"})
    client.post(f"/api/transport-jobs/{job['id']}/quote", headers=gamma_h,
                json={"amount": "1800.00", "currency": "USD"})
    wid = next(q["id"] for q in
               client.get(f"/api/transport-jobs/{job['id']}", headers=admin_headers).json()["quotes"]
               if q["forwarder_id"] == spedalfa)
    client.post(f"/api/transport-jobs/{job['id']}/choose", headers=admin_headers,
                json={"quote_id": wid})

    # Q55: każda zaproszona spedycja, która złożyła ofertę, może zgłosić zmianę ceny
    # (także przegrana Spedgamma, która wyceniła)
    assert client.post(f"/api/transport-jobs/{job['id']}/price-change", headers=gamma_h,
                       json={"revised_amount": "1"}).status_code == 200
    r = client.post(f"/api/transport-jobs/{job['id']}/price-change", headers=dsv_h,
                    json={"revised_amount": "1900.00", "revised_note": "wzrost frachtu"})
    assert r.status_code == 200
    admin_view = client.get(f"/api/transport-jobs/{job['id']}", headers=admin_headers).json()
    won = next(q for q in admin_view["quotes"] if q["forwarder_id"] == spedalfa)
    # Q56: zmiana czeka na akceptację (revised_amount ustawione, cena oferty bez zmian)
    assert won["revised_amount"] == "1900.00" and won["amount"] == "1500.00"
    assert any("pilna zmiana ceny" in n["title"].lower()
               for n in client.get("/api/notifications", headers=admin_headers).json())
    # logistyka akceptuje → nowa cena zastępuje ofertę, stan „oczekuje" znika
    approved = client.post(
        f"/api/transport-jobs/{job['id']}/quotes/{won['id']}/approve-price",
        headers=admin_headers).json()
    won2 = next(q for q in approved["quotes"] if q["forwarder_id"] == spedalfa)
    assert won2["amount"] == "1900.00" and won2["revised_amount"] is None
    # powtórna akceptacja bez nowej zmiany → 409
    assert client.post(
        f"/api/transport-jobs/{job['id']}/quotes/{won['id']}/approve-price",
        headers=admin_headers).status_code == 409

    # wiersz 20: anulowanie wymaga powodu; działa też na zleceniu przydzielonym
    assert client.post(f"/api/transport-jobs/{job['id']}/cancel", headers=admin_headers,
                       json={}).status_code == 422
    cancelled = client.post(f"/api/transport-jobs/{job['id']}/cancel", headers=admin_headers,
                            json={"reason": "klient wycofał zamówienie"}).json()
    assert cancelled["status"] == "ANULOWANE"
    assert cancelled["cancel_reason"] == "klient wycofał zamówienie"
    assert any("anulowano zlecenie" in n["title"].lower()
               for n in client.get("/api/notifications", headers=dsv_h).json())

    # Q58: wznowienie anulowanego zlecenia → wraca do SZKIC, oferty wyzerowane
    reopened = client.post(f"/api/transport-jobs/{job['id']}/reopen",
                           headers=admin_headers).json()
    assert reopened["status"] == "SZKIC" and reopened["cancel_reason"] == ""
    assert reopened["chosen_quote_id"] is None
    # ponowne wznowienie nie ma sensu (już nie anulowane)
    assert client.post(f"/api/transport-jobs/{job['id']}/reopen",
                       headers=admin_headers).status_code == 409


def test_weighted_ranking_and_choice_reason(client, admin_headers):
    """Q39: ranking ważony (rekomendacja); Q40: wybór spoza rekomendacji wymaga powodu."""
    borealis = _company_id(client, admin_headers, "BOREALIS")
    c1 = _container(client, admin_headers, "MSDU0806613", borealis)
    spedalfa = forwarder(client, admin_headers, "SPEDALFA")["id"]
    gamma = forwarder(client, admin_headers, "Spedgamma")["id"]
    dsv_h = _forwarder_account(client, admin_headers, "sped.spedalfa", spedalfa)
    gamma_h = _forwarder_account(client, admin_headers, "sped.gamma", gamma)
    job = client.post("/api/transport-jobs", headers=admin_headers, json={
        "container_ids": [c1], "forwarder_ids": [spedalfa, gamma]}).json()
    client.post(f"/api/transport-jobs/{job['id']}/send", headers=admin_headers)
    # SPEDALFA tańszy → rekomendowany; Spedgamma droższa
    client.post(f"/api/transport-jobs/{job['id']}/quote", headers=dsv_h, json={"amount": "1500.00"})
    client.post(f"/api/transport-jobs/{job['id']}/quote", headers=gamma_h, json={"amount": "2200.00"})

    view = client.get(f"/api/transport-jobs/{job['id']}", headers=admin_headers).json()
    rec = next(q for q in view["quotes"] if q["recommended"])
    assert rec["forwarder_id"] == spedalfa and rec["score"] > 0
    gamma_q = next(q for q in view["quotes"] if q["forwarder_id"] == gamma)
    assert gamma_q["recommended"] is False and gamma_q["score"] < rec["score"]
    # spedytor nie widzi score konkurencji (ani własnego rankingu)
    assert client.get(f"/api/transport-jobs/{job['id']}", headers=dsv_h).json()["my_quote"]["score"] is None

    # wybór droższej Omidy bez powodu → 422; z powodem → 200
    oid = gamma_q["id"]
    assert client.post(f"/api/transport-jobs/{job['id']}/choose", headers=admin_headers,
                       json={"quote_id": oid}).status_code == 422
    ok = client.post(f"/api/transport-jobs/{job['id']}/choose", headers=admin_headers,
                     json={"quote_id": oid, "reason": "lepszy termin dostawy"})
    assert ok.status_code == 200 and ok.json()["chosen_quote_id"] == oid


def test_equal_score_needs_no_reason(client, admin_headers):
    """Ranking: dwie równorzędne oferty — wybór dowolnej nie wymaga powodu (współrekomendacja)."""
    borealis = _company_id(client, admin_headers, "BOREALIS")
    c1 = _container(client, admin_headers, "MSDU0806613", borealis)
    spedalfa = forwarder(client, admin_headers, "SPEDALFA")["id"]
    gamma = forwarder(client, admin_headers, "Spedgamma")["id"]
    dsv_h = _forwarder_account(client, admin_headers, "sped.spedalfa", spedalfa)
    gamma_h = _forwarder_account(client, admin_headers, "sped.gamma", gamma)
    job = client.post("/api/transport-jobs", headers=admin_headers, json={
        "container_ids": [c1], "forwarder_ids": [spedalfa, gamma]}).json()
    client.post(f"/api/transport-jobs/{job['id']}/send", headers=admin_headers)
    # identyczne oferty → identyczny score
    client.post(f"/api/transport-jobs/{job['id']}/quote", headers=dsv_h, json={"amount": "1500.00"})
    client.post(f"/api/transport-jobs/{job['id']}/quote", headers=gamma_h, json={"amount": "1500.00"})
    view = client.get(f"/api/transport-jobs/{job['id']}", headers=admin_headers).json()
    quoted = [q for q in view["quotes"] if q["score"] is not None]
    # równorzędny score → obie oferty współrekomendowane
    assert len(quoted) == 2
    assert all(q["recommended"] for q in quoted)
    assert quoted[0]["score"] == quoted[1]["score"]
    # wybór dowolnej z równorzędnych ofert bez powodu → 200
    r = client.post(f"/api/transport-jobs/{job['id']}/choose", headers=admin_headers,
                    json={"quote_id": quoted[1]["id"]})
    assert r.status_code == 200


def test_cost_report_and_export(client, admin_headers):
    """Q98/Q86: raport kosztów z wygranych ofert, eksport CSV."""
    borealis = _company_id(client, admin_headers, "BOREALIS")
    c1 = _container(client, admin_headers, "MSDU0806613", borealis)
    spedalfa = forwarder(client, admin_headers, "SPEDALFA")["id"]
    dsv_h = _forwarder_account(client, admin_headers, "sped.spedalfa", spedalfa)
    job = client.post("/api/transport-jobs", headers=admin_headers, json={
        "container_ids": [c1], "forwarder_ids": [spedalfa]}).json()
    client.post(f"/api/transport-jobs/{job['id']}/send", headers=admin_headers)
    client.post(f"/api/transport-jobs/{job['id']}/quote", headers=dsv_h,
                json={"amount": "1500.00", "currency": "USD"})
    qid = client.get(f"/api/transport-jobs/{job['id']}", headers=admin_headers).json()["quotes"][0]["id"]
    client.post(f"/api/transport-jobs/{job['id']}/choose", headers=admin_headers,
                json={"quote_id": qid})
    # raport kosztów: wygrana oferta 1500 USD
    report = client.get("/api/stats/cost-report", headers=admin_headers).json()
    assert any(r["currency"] == "USD" and r["total"] == 1500.0 for r in report)
    # eksport CSV zawiera numer zlecenia
    csv = client.get("/api/stats/transport-jobs.csv", headers=admin_headers)
    assert csv.status_code == 200 and job["number"] in csv.text
    # spedytor nie ma dostępu do statystyk/eksportu
    assert client.get("/api/stats/cost-report", headers=dsv_h).status_code == 403
    # raport wydajności spedytorów: SPEDALFA — 1 zaproszenie, 1 odpowiedź, 1 wygrana
    perf = client.get("/api/stats/forwarders", headers=admin_headers).json()
    dsv_row = next(r for r in perf if r["forwarder_id"] == spedalfa)
    assert dsv_row["invited"] == 1 and dsv_row["responded"] == 1 and dsv_row["won"] == 1
    assert dsv_row["response_rate"] == 100 and dsv_row["win_rate"] == 100
    assert client.get("/api/stats/forwarders", headers=dsv_h).status_code == 403


def test_quote_history(client, admin_headers):
    """Q47: historia wersji oferty — wycena, korekta, zgłoszenie zmiany, akceptacja."""
    borealis = _company_id(client, admin_headers, "BOREALIS")
    c1 = _container(client, admin_headers, "MSDU0806613", borealis)
    spedalfa = forwarder(client, admin_headers, "SPEDALFA")["id"]
    dsv_h = _forwarder_account(client, admin_headers, "sped.spedalfa", spedalfa)
    job = client.post("/api/transport-jobs", headers=admin_headers, json={
        "container_ids": [c1], "forwarder_ids": [spedalfa]}).json()
    client.post(f"/api/transport-jobs/{job['id']}/send", headers=admin_headers)
    # wycena + korekta
    client.post(f"/api/transport-jobs/{job['id']}/quote", headers=dsv_h, json={"amount": "1500.00"})
    client.post(f"/api/transport-jobs/{job['id']}/quote", headers=dsv_h, json={"amount": "1400.00"})
    qid = client.get(f"/api/transport-jobs/{job['id']}", headers=admin_headers).json()["quotes"][0]["id"]
    client.post(f"/api/transport-jobs/{job['id']}/choose", headers=admin_headers, json={"quote_id": qid})
    # zgłoszenie zmiany + akceptacja
    client.post(f"/api/transport-jobs/{job['id']}/price-change", headers=dsv_h,
                json={"revised_amount": "1600.00"})
    client.post(f"/api/transport-jobs/{job['id']}/quotes/{qid}/approve-price", headers=admin_headers)

    hist = client.get(f"/api/transport-jobs/{job['id']}/quotes/{qid}/history",
                      headers=admin_headers).json()
    kinds = [h["kind"] for h in hist]
    assert kinds == ["wycena", "korekta", "zgłoszenie zmiany", "akceptacja"]
    assert hist[0]["amount"] == "1500.00" and hist[-1]["amount"] == "1600.00"
    # spedytor widzi historię własnej oferty
    assert len(client.get(f"/api/transport-jobs/{job['id']}/quotes/{qid}/history",
                          headers=dsv_h).json()) == 4


def test_winner_forwarder_sets_shipment_number(client, admin_headers):
    """Q49: numer przesyłki podaje zwycięska spedycja (przez formularz agenta)."""
    borealis = _company_id(client, admin_headers, "BOREALIS")
    c1 = _container(client, admin_headers, "MSDU0806613", borealis)
    spedalfa = forwarder(client, admin_headers, "SPEDALFA")["id"]
    dsv_h = _forwarder_account(client, admin_headers, "sped.spedalfa", spedalfa)
    job = client.post("/api/transport-jobs", headers=admin_headers, json={
        "container_ids": [c1], "forwarder_ids": [spedalfa]}).json()
    client.post(f"/api/transport-jobs/{job['id']}/send", headers=admin_headers)
    client.post(f"/api/transport-jobs/{job['id']}/quote", headers=dsv_h,
                json={"amount": "1500.00"})
    wid = next(q["id"] for q in
               client.get(f"/api/transport-jobs/{job['id']}", headers=admin_headers).json()["quotes"]
               if q["forwarder_id"] == spedalfa)
    client.post(f"/api/transport-jobs/{job['id']}/choose", headers=admin_headers,
                json={"quote_id": wid})
    # zwycięzca podaje agenta razem z numerem przesyłki
    r = client.post(f"/api/transport-jobs/{job['id']}/agent", headers=dsv_h, json={
        "agent_name": "Jan Kowalski", "agent_phone": "+48 600", "agent_company": "AgentCo",
        "shipment_number": "BK-55443322"})
    assert r.status_code == 200 and r.json()["shipment_number"] == "BK-55443322"
    # logistyka widzi numer podany przez spedycję
    admin_view = client.get(f"/api/transport-jobs/{job['id']}", headers=admin_headers).json()
    assert admin_view["shipment_number"] == "BK-55443322"

    # reopen po anulowaniu czyści dane rozstrzygnięcia (agent, numer przesyłki)
    client.post(f"/api/transport-jobs/{job['id']}/cancel", headers=admin_headers,
                json={"reason": "zmiana planu"})
    reopened = client.post(f"/api/transport-jobs/{job['id']}/reopen",
                           headers=admin_headers).json()
    assert reopened["shipment_number"] == "" and reopened["agent_name"] == ""


def test_company_scoped_logistics_cannot_see_other_company_jobs(client, admin_headers):
    """#2 audytu: logistyk przypisany do jednej spółki (view_all=False) nie może
    widzieć zleceń wyceny innych firm — ani na liście, ani po id."""
    borealis = _company_id(client, admin_headers, "BOREALIS")
    acme = _company_id(client, admin_headers, "ACME")
    ct = _container(client, admin_headers, "MSDU0806613", borealis)
    cz = _container(client, admin_headers, "CSQU3054383", acme)
    spedalfa = forwarder(client, admin_headers, "SPEDALFA")["id"]
    job_t = client.post("/api/transport-jobs", headers=admin_headers, json={
        "container_ids": [ct], "forwarder_ids": [spedalfa],
        "pickup_location": "A", "delivery_location": "B"}).json()
    job_z = client.post("/api/transport-jobs", headers=admin_headers, json={
        "container_ids": [cz], "forwarder_ids": [spedalfa],
        "pickup_location": "A", "delivery_location": "B"}).json()

    client.post("/api/users", headers=admin_headers, json={
        "login": "log.borealis", "password": "haslo123", "role": "logistics",
        "company_id": borealis, "view_all_companies": False,
        "email": "log.borealis@example.com"})
    log_h = login(client, "log.borealis", "haslo123")

    ids = [j["id"] for j in client.get("/api/transport-jobs", headers=log_h).json()]
    assert job_t["id"] in ids
    assert job_z["id"] not in ids
    assert client.get(f"/api/transport-jobs/{job_z['id']}", headers=log_h).status_code == 404
    assert client.get(f"/api/transport-jobs/{job_t['id']}", headers=log_h).status_code == 200
