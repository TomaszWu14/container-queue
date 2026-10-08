"""BUILD-007: kontekst builda Dockerfile.coolify (korzeń repo) zawiera tylko to, co obraz
kopiuje, plus drobne pliki z korzenia. Nowy katalog w korzeniu (jak audit/, ~20 MB) musi
trafić do /.dockerignore, zanim spuchnie każdy build na serwerze.

Dopasowanie wzorców odwzorowuje moby/patternmatcher: kotwica w korzeniu kontekstu,
`*` bez `/`, `**` przez katalogi, `!` wyjątek, wygrywa ostatni pasujący wzorzec,
wykluczony katalog wyklucza całą zawartość.
"""
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _compile(pattern: str) -> re.Pattern:
    out, i = "", 0
    while i < len(pattern):
        ch = pattern[i]
        if pattern.startswith("**", i):
            i += 2
            if pattern[i:i + 1] == "/":
                i += 1
            out += ".*" if i >= len(pattern) else "(.*/)?"
            continue
        out += "[^/]*" if ch == "*" else "[^/]" if ch == "?" else re.escape(ch)
        i += 1
    return re.compile(out + r"\Z")


def _patterns():
    rules = []
    for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        negate = line.startswith("!")
        rules.append((negate, _compile(line.lstrip("!").strip("/"))))
    return rules


def _ignored(path: str, rules) -> bool:
    parts = path.split("/")
    candidates = ["/".join(parts[:i]) for i in range(1, len(parts) + 1)]
    ignored = False
    for negate, rx in rules:
        if any(rx.match(c) for c in candidates):
            ignored = not negate
    return ignored


def _copy_sources():
    """Ścieżki z `COPY <src...> <dst>` w Dockerfile.coolify (bez COPY --from=etap)."""
    text = (ROOT / "Dockerfile.coolify").read_text(encoding="utf-8")
    sources = []
    for line in re.findall(r"^COPY\s+(.+)$", text, flags=re.M):
        args = [a for a in line.split() if not a.startswith("--")]
        if "--from=" not in line:
            sources += [a.rstrip("/") for a in args[:-1]]
    return sources


@pytest.fixture(scope="module")
def context_files():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                             check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("brak gita — nie da się wyliczyć plików repo")
    rules = _patterns()
    return [f for f in out.splitlines() if not _ignored(f, rules)]


def test_pattern_semantics():
    rules = [(False, _compile("docs")), (False, _compile("**/.env.*")),
             (True, _compile("**/.env.example"))]
    assert _ignored("docs/a/b.md", rules)
    assert not _ignored("backend/docs/x.py", rules)   # bez `**/` — tylko korzeń
    assert _ignored("backend/.env.local", rules)
    assert not _ignored(".env.example", rules)


def test_context_has_everything_the_image_copies(context_files):
    sources = _copy_sources()
    assert "backend/app" in sources and "frontend" in sources, sources
    for src in sources:
        assert any(f == src or f.startswith(src + "/") for f in context_files), \
            f"{src} wykluczone przez .dockerignore, a Dockerfile.coolify go kopiuje"


def test_context_has_nothing_beyond_copied_paths_and_root_files(context_files):
    """Dozwolone: kopiowane ścieżki + pojedyncze pliki w korzeniu i w katalogach nad nimi
    (np. backend/pyproject.toml). Każdy inny katalog = do .dockerignore."""
    sources = _copy_sources()

    def stray_dir(f):
        if any(f == s or f.startswith(s + "/") for s in sources):
            return None
        parts = f.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            d = "/".join(parts[:i])
            if not any(s == d or s.startswith(d + "/") for s in sources):
                return d
        return None

    extra = sorted({d for f in context_files if (d := stray_dir(f))})
    assert not extra, f"katalogi w kontekście builda, których obraz nie kopiuje: {extra}"


def test_secrets_and_local_artifacts_stay_out():
    rules = _patterns()
    for path in (".git/config", ".env", "backend/.env", "backend/.env.production",
                 "backend/test_timporye.db", "frontend/node_modules/react/index.js",
                 "frontend/dist/index.html", "backend/app/__pycache__/main.cpython-312.pyc",
                 "audit/RAPORT.html", "backend/tests/test_api.py"):
        assert _ignored(path, rules), path
    assert not _ignored(".env.example", rules)
    assert not _ignored("backend/scripts/backup.sh", rules)
