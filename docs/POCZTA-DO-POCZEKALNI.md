# Poczta → poczekalnia dokumentów (n8n)

Spec `docs/superpowers/specs/2026-10-06-dokumenty-dostaw-design.md`, decyzja 27: **wszystkie
dokumenty z poczty trafiają do poczekalni**, kontener dopasowany po treści. Nic nie trafia do
dostawy bez „Potwierdź” człowieka.

Obieg jak w [SAD-Z-POCZTY.md](SAD-Z-POCZTY.md) (Outlook → dysk → n8n na komputerze 24/7, token
`X-Automation-Token` = konto serwisowe z rolą **logistics**), tylko inny adres:

```
curl.exe -X POST http://192.0.2.10:81/api/intake/inbox ^
  -H "X-Automation-Token: <AUTOMATION_API_TOKEN>" ^
  -F "file=@D:\Poczta\przychodzace\wiadomosc.eml" ^
  -F "subject=Dokumenty MSKU1234565" -F "sender=agent@spedytor.pl"
```

- `file` — cały mail (`.eml` / `.msg`, rozpakowywany jak ZIP) albo pojedynczy załącznik.
- `subject`, `sender` (opcjonalne) — zapisane przy wgraniu („nadawca · temat”); numer kontenera
  z tematu przypisuje części bez tekstu (sam mail, Excel).

## Co się dzieje

1. Mail rozpakowany i pocięty jak ręczne wgranie do poczekalni (PDF → części, obrazy → PDF).
2. Każda część PDF: numer kontenera z treści → kontener w zakresie konta automatu; bez numeru —
   numer zamówienia (PO), potem numer faktury.
3. **Jedno wgranie na kontener** (`source = mail`) + jedno zbiorcze powiadomienie logistyki
   spółki: „Poczta: N dokumentów do sprawdzenia w poczekalni MSKU…”.
4. Części bez dopasowania → wgranie **bez kontenera** („poczta bez dopasowania”), widoczne dla
   admina/logistyki spółki konta automatu: `GET /api/intake/unmatched`. Kontener wskazuje się
   per część (`PATCH /api/intake/items/{id}` z `target_container_id`), „Potwierdź” wymaga
   kontenera dla każdej nieodrzuconej części.

## Odpowiedź

```json
{"batches": [{"batch_id": 41, "container_no": "MSKU1234565", "items": 3},
             {"batch_id": 42, "container_no": null, "items": 1}],
 "skipped": ["logo.png (obraz w treści maila)"]}
```

- **201** — utworzono wgrania; **200** — ten sam plik (sha256) przyszedł w ciągu 7 dni: zwrócone
  istniejące wgrania, nic nowego (bezpieczne ponawianie).
- **422** — w pliku nie ma nic do wgrania; **401/403** — zły token / konto bez roli logistics.
