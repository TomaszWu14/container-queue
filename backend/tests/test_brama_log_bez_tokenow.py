"""OBS-005: brama nginx (deploy/gateway/timporye.conf) nie zapisuje tokenów w access logu.

Maskowanie w Pythonie (redaction.redact_tokens) nie obejmuje logów nginx — brama ma własną
mapę `$safe_uri`. Test czyta mapę z pliku i sprawdza ją na tych samych adresach, które maskuje
aplikacja (składnia tych regexów jest wspólna dla PCRE i `re`)."""
import re
from pathlib import Path

CONF = Path(__file__).resolve().parents[2] / "deploy" / "gateway" / "timporye.conf"
TOKEN = "x" * 24   # niska entropia — gitleaks nie bierze za klucz


def _conf() -> str:
    return CONF.read_text(encoding="utf-8")


def _safe_uri(request_uri: str) -> str:
    """Emuluje `map $request_uri $safe_uri` — pierwszy pasujący regex wygrywa."""
    block = re.search(r"map \$request_uri \$safe_uri \{(.*?)\n\}", _conf(), re.S)
    assert block, "brak mapy $safe_uri w timporye.conf"
    for line in block.group(1).splitlines():
        line = line.split("#", 1)[0].strip().rstrip(";")
        if not line.lstrip('"').startswith("~"):
            continue
        pattern, value = line.rsplit(None, 1)
        match = re.search(pattern.strip('"')[1:], request_uri)
        if match:
            return re.sub(r"\$\{?(\w+)\}?", lambda m, hit=match: hit.group(m.group(1)) or "", value.strip('"'))
    return request_uri


def test_tokeny_w_sciezce_i_query_maskowane():
    for uri in (f"/avizo/{TOKEN}", f"/api/avizo/driver/{TOKEN}/confirm", f"/dostawa/{TOKEN}",
                f"/portal/{TOKEN}", f"/api/public/portal/{TOKEN}", f"/dlt/{TOKEN}",
                f"/reset-hasla?token={TOKEN}", f"/api/auth/reset?x=1&token={TOKEN}"):
        assert TOKEN not in _safe_uri(uri), uri
    assert _safe_uri("/api/containers?page=2") == "/api/containers?page=2"   # reszta bez zmian


def test_access_log_uzywa_bezpiecznego_formatu():
    conf = _conf()
    assert re.search(r"log_format\s+bez_tokenow\b[^;]*\$safe_uri", conf, re.S)
    fmt = re.search(r"log_format\s+bez_tokenow\b([^;]*);", conf, re.S).group(1)
    # $request/$request_uri/$http_referer niosą surowy adres (referer strony publicznej = token)
    assert not re.search(r"\$request\b|\$request_uri|\$http_referer", fmt)
    assert re.search(r"access_log\s+\S+\s+bez_tokenow", conf)


def test_maska_zostawia_prefiks():
    assert _safe_uri(f"/avizo/{TOKEN}") == "/avizo/[token]"
    assert _safe_uri(f"/reset-hasla?token={TOKEN}") == "/reset-hasla?[token]"
