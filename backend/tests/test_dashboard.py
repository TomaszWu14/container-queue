import datetime

from app.models import today_pl


def _company(client, headers, code="BOREALIS"):
    companies = client.get("/api/companies", headers=headers).json()
    return next(c["id"] for c in companies if c["code"] == code)


def test_dashboard_tiles_and_lists(client, admin_headers):
    borealis = _company(client, admin_headers)
    today = today_pl()
    yesterday = today - datetime.timedelta(days=1)

    client.post("/api/containers", headers=admin_headers, json={
        "container_no": "MSDU0806613", "company_id": borealis,
        "notify_date": today.isoformat(), "status": "AWIZOWANY"})
    client.post("/api/containers", headers=admin_headers, json={
        "container_no": "CSQU3054383", "company_id": borealis,
        "eta": yesterday.isoformat(), "status": "W_TRANSPORCIE"})  # opóźniony
    client.post("/api/containers", headers=admin_headers, json={
        "container_no": "TGBU6784203", "company_id": borealis,
        "notify_date": (today + datetime.timedelta(days=1)).isoformat(),
        "status": "W_PORCIE", "customs_status": "ZLECONA"})

    data = client.get("/api/stats/dashboard", headers=admin_headers).json()
    assert data["today"] == 1
    assert data["tomorrow"] == 1
    assert data["delayed"] >= 1
    assert data["at_port"] == 1
    assert data["customs_in_progress"] == 1
    assert any(row["container_no"] == "MSDU0806613" for row in data["today_list"])
    assert any(row["container_no"] == "CSQU3054383" for row in data["delayed_list"])

    # W4: „dziś" wg zegara klienta — jego jutro przesuwa kubełki
    shifted = client.get(f"/api/stats/dashboard?today={(today + datetime.timedelta(days=1)).isoformat()}",
                         headers=admin_headers).json()
    assert shifted["today"] == 1 and shifted["tomorrow"] == 0
    assert any(row["container_no"] == "TGBU6784203" for row in shifted["today_list"])

    # data spoza ±1 dnia = śmieć → fallback na UTC
    junk = client.get(f"/api/stats/dashboard?today={(today + datetime.timedelta(days=5)).isoformat()}",
                      headers=admin_headers).json()
    assert junk["today"] == data["today"] and junk["tomorrow"] == data["tomorrow"]
