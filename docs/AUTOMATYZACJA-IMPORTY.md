# Importy master data przez API automatyzacji

Endpointy importów działają z tokenem serwisowym automatyzacji (n8n) — nagłówek
`X-Automation-Token` zamiast logowania (patrz `docs/N8N.md`). Uprawnienia bierze
ROLA konta serwisowego (`AUTOMATION_ACTOR_LOGIN`, domyślnie `n8n`): importy są
gated `Editors`, więc konto serwisowe musi mieć rolę **logistics** (zalecane,
z `view_all_companies`) albo **admin**.

Wszystkie importy mają `dry_run=true` domyślnie (podgląd liczników bez zapisu) —
do realnego zapisu dodaj `dry_run=false`.

```bash
BASE=https://timporye.example.com
TOKEN='...'   # AUTOMATION_API_TOKEN z Coolify

# MARM — jednostki materiałów (globalne)
curl -H "X-Automation-Token: $TOKEN" -F "file=@marm.xlsx" \
  "$BASE/api/import/material-units?dry_run=false"

# EKKO — nagłówki zamówień SAP (per spółka)
curl -H "X-Automation-Token: $TOKEN" -F "file=@ekko.xlsx" \
  "$BASE/api/import/sap-orders?company_code=ACME&dry_run=false"

# LFA1 — słownik dostawców (do każdej aktywnej spółki w zakresie konta)
curl -H "X-Automation-Token: $TOKEN" -F "file=@lfa1.xlsx" \
  "$BASE/api/import/suppliers-lfa1?dry_run=false"

# Porty kontenerowe (xlsx albo tsv/csv)
curl -H "X-Automation-Token: $TOKEN" -F "file=@porty.tsv" \
  "$BASE/api/import/container-ports?dry_run=false"

# Auto-rozpoznanie typu po nagłówkach (jeden endpoint na wszystkie powyższe;
# company_code potrzebny tylko, gdy plik okaże się eksportem EKKO)
curl -H "X-Automation-Token: $TOKEN" -F "file=@plik.xlsx" \
  "$BASE/api/import/master-data?company_code=ACME&dry_run=false"
```

Odpowiedzi: `{"dry_run": ..., "counts": {...}}` (LFA1: `{"companies": {kod: liczniki}}`;
auto-rozpoznanie dodaje pole `detected`). Niepewne rozpoznanie → `422` z listą typów,
do których plik pasuje częściowo. Każdy realny import zostawia wpis w AuditLog
(`field="import"`), z którego liczona jest świeżość na zakładce „Jakość danych"
i dzienny alert `stale-import` (próg `STALE_IMPORT_DAYS`, domyślnie 14 dni).
