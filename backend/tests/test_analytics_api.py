import io

CSV = ("data;produkt;ilosc;magazyn\n"
       + "".join(f"2025-{m:02d}-{d:02d};A;{10 if (d%7)<5 else 0};MAG1\n"
                for m in range(1, 6) for d in range(1, 28))).encode()

def _upload(client, headers, commit):
    return client.post(f"/api/analytics/upload?commit={commit}", headers=headers,
                       files={"file": ("h.csv", io.BytesIO(CSV), "text/csv")})

def test_preview_then_commit(client, admin_headers):
    prev = _upload(client, admin_headers, "false").json()
    assert prev["errors"] == [] and prev["rows_count"] > 100 and prev["saved"] == 0
    saved = _upload(client, admin_headers, "true").json()
    assert saved["saved"] > 100
