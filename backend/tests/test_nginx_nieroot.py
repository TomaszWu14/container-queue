"""BUILD-006: frontend dev na nginx bez roota (nginx-unprivileged słucha na 8080, nie 80)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_frontend_nginx_nieroot_na_8080():
    dockerfile = (ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")
    runtime = re.findall(r"^FROM\s+(\S+)", dockerfile, flags=re.M)[-1]
    assert re.fullmatch(r"nginxinc/nginx-unprivileged:[\w.-]+@sha256:[0-9a-f]{64}", runtime), runtime
    assert re.search(r"^EXPOSE 8080$", dockerfile, flags=re.M)

    conf = (ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")
    assert re.search(r"^\s*listen 8080;", conf, flags=re.M)
    assert not re.search(r"^\s*listen 80;", conf, flags=re.M)

    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    web = compose.split("\n  web:", 1)[1]
    assert re.search(r'-\s*"(?:[\d.]+:)?8080:8080"', web), "web: port kontenera musi być 8080"


def _location(conf: str, spec: str) -> str:
    m = re.search(r"^\s*location\s+" + re.escape(spec) + r"\s*\{(.*?)^\s*\}", conf, flags=re.M | re.S)
    assert m, f"brak bloku location {spec}"
    return m.group(1)


def test_frontend_nginx_cache_assetow():
    """PERF-005: hashowane assety Vite — rok + immutable; index.html — no-cache."""
    conf = (ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")
    assets = _location(conf, "/assets/")
    assert re.search(r'add_header\s+Cache-Control\s+"public, max-age=31536000, immutable";', assets)
    assert re.search(r"try_files\s+\$uri\s+=404;", assets), "brak assetu nie może dać index.html"
    index = _location(conf, "= /index.html")
    assert re.search(r'add_header\s+Cache-Control\s+"no-cache";', index)
    assert re.search(r"try_files\s+\$uri\s+/index\.html;", _location(conf, "/"))
