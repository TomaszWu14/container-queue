"""Strażnik śladu audytowego (OBS-003): każda trasa zapisu (POST/PUT/PATCH/DELETE) woła
`record`/`record_changes` z app.audit — w handlerze albo w funkcji aplikacji, którą on
woła (do 3 poziomów, statycznie po AST). Wyjątek = świadomy wpis w NO_AUDIT z powodem.

NO_AUDIT może tylko MALEĆ: dopisując audyt do trasy z listy, usuń jej wpis (test to
wymusza). Nowa trasa zapisu bez audytu = czerwone CI, nie cicha luka w historii zmian."""
import ast
import importlib
import inspect
import textwrap
import types

from .test_routes_require_auth import _api_routes

WRITE = {"POST", "PUT", "PATCH", "DELETE"}

NO_AUDIT: dict[tuple[str, str], str] = {
    # --- logowanie / sesja / ustawienia własnego konta (nie dane biznesowe)
    ("POST", "/api/auth/2fa/setup"): "bez zapisu — zwraca sekret; /2fa/enable ma audyt",
    ("POST", "/api/auth/refresh"): "odnowienie sesji, nie zapis danych",
    ("PUT", "/api/auth/me/prefs"): "preferencje UI własnego konta",
    ("PATCH", "/api/auth/me/settings"): "ustawienia własnego konta",
    ("POST", "/api/me/avatar"): "własny awatar",
    ("DELETE", "/api/me/avatar"): "własny awatar",
    # --- stan osobisty użytkownika (obserwowanie, przeczytane, głosy)
    ("POST", "/api/containers/{container_id}/watch"): "obserwowanie — stan osobisty",
    ("POST", "/api/tracking/vessels/{vessel_id}/watch"): "obserwowanie — stan osobisty",
    ("POST", "/api/notifications/read"): "oznaczenie przeczytanych — stan osobisty",
    ("POST", "/api/notifications/unread"): "oznaczenie jako nieprzeczytane — stan osobisty",
    ("POST", "/api/presence"): "obecność w pasku — ulotny stan w pamięci, bez zapisu w bazie",
    ("POST", "/api/presence/leave"): "obecność w pasku — ulotny stan w pamięci, bez zapisu w bazie",
    ("POST", "/api/knowledge/topics/{topic_id}/vote"): "głos — stan osobisty",
    ("POST", "/api/knowledge/bulletins/{bulletin_id}/ack"): "potwierdzenie przeczytania — sam jest śladem",
    # --- bez zmiany danych / wpis sam jest zapisem zdarzenia
    ("POST", "/api/client-error"): "publiczny raport błędu frontu (log aplikacji)",
    ("POST", "/api/assistant/ask"): "pytanie do asystenta — odczyt",
    ("POST", "/api/admin/system/verify-backup"): "kontrola kopii — bez zmiany danych",
    ("POST", "/api/containers/{container_id}/messages"): "wiadomość = wpis z autorem i czasem",
    ("POST", "/api/knowledge/topics"): "temat = wpis z autorem i czasem",
    ("POST", "/api/knowledge/bulletins"): "komunikat = wpis z autorem i czasem",
    ("POST", "/api/tracking/vessels/{vessel_id}/photo"): "zdjęcie statku — ilustracja",
    ("POST", "/api/tracking/vessels/{vessel_id}/photo/fetch"): "zdjęcie statku — ilustracja",
    ("POST", "/api/containers/{container_id}/unload-photos"): "zdjęcie rozładunku = plik z autorem",
    ("POST", "/api/complaints/{complaint_id}/photos"): "zdjęcie reklamacji = plik z autorem",
}


def _namespace(fn, tree) -> dict:
    """Globalne nazwy modułu + importy wewnątrz funkcji (`from .. import x`)."""
    ns = dict(getattr(fn, "__globals__", {}))
    package = fn.__module__.rpartition(".")[0]
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        module = importlib.import_module("." * node.level + (node.module or ""), package)
        for alias in node.names:
            obj = getattr(module, alias.name, None)
            if obj is None:
                obj = importlib.import_module(f"{module.__name__}.{alias.name}")
            ns[alias.asname or alias.name] = obj
    return ns


def _callees(fn):
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    except (OSError, TypeError):
        return
    ns = _namespace(fn, tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            yield ns.get(func.id)
        elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            base = ns.get(func.value.id)
            if isinstance(base, types.ModuleType):
                yield getattr(base, func.attr, None)


def _audited(fn, depth: int = 3, seen: set | None = None) -> bool:
    seen = set() if seen is None else seen
    fn = inspect.unwrap(fn)
    if fn in seen:
        return False
    seen.add(fn)
    for callee in _callees(fn):
        module = getattr(callee, "__module__", None) or ""
        if module == "app.audit":
            return True
        if (depth and module.startswith("app.") and isinstance(callee, types.FunctionType)
                and _audited(callee, depth - 1, seen)):
            return True
    return False


def _write_routes():
    return {(m, path): r for m, path, r in _api_routes() if m in WRITE}


def test_write_routes_leave_audit_trail():
    missing = sorted(k for k, r in _write_routes().items()
                     if k not in NO_AUDIT and not _audited(r.endpoint))
    assert not missing, ("Trasy zapisu bez audytu (dodaj record()/record_changes() "
                         f"albo świadomy wpis w NO_AUDIT): {missing}")


def test_no_audit_list_only_shrinks():
    routes = _write_routes()
    stale = sorted(k for k in NO_AUDIT if k not in routes or _audited(routes[k].endpoint))
    assert not stale, f"Usuń z NO_AUDIT (trasa nie istnieje albo ma już audyt): {stale}"
