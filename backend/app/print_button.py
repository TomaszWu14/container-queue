"""Przycisk „Drukuj” na stronach HTML z backendu (pismo reklamacyjne, CMR) zgodny z CSP.

CSP `script-src 'self'` blokuje inline `onclick` (audyt SEC-011: przycisk nie działał).
Przycisk ma atrybut `data-print`, a obsługę dokłada `PRINT_SCRIPT` — stały skrypt, którego
hash SHA-256 (`CSP_HASH`) jest w CSP, więc przepuszczony zostaje tylko ten jeden skrypt.
Zmiana treści skryptu = nowy hash (liczony tu) — nginx panelu dev ma go wpisanego ręcznie
(frontend/nginx.conf; pilnuje test_security_headers)."""
import base64
import hashlib

_SCRIPT = ("document.querySelectorAll('[data-print]').forEach("
           "b=>b.addEventListener('click',()=>window.print()))")
PRINT_SCRIPT = f"<script>{_SCRIPT}</script>"
CSP_HASH = "'sha256-" + base64.b64encode(hashlib.sha256(_SCRIPT.encode()).digest()).decode() + "'"
