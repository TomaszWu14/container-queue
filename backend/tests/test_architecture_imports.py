"""ARCH-001/002: kierunek zależności HTTP → domena. Moduły spoza app/routers nie importują
routerów (także importem w funkcji — takie importy spinały cykl ~85 modułów).

Istniejące wyjątki w ALLOWED mogą tylko znikać (ta sama zasada co BASELINE długości plików):
nowa krawędź domena → router = czerwony test. Wspólna logika idzie do modułu domenowego
(np. app/app_settings.py), a router ją re-eksportuje."""
import ast
import pathlib

APP = pathlib.Path(__file__).resolve().parents[1] / "app"

# stan po wydzieleniu ustawień AppSetting (app_settings.py) — tylko maleje
ALLOWED = {
    ("app.db_bootstrap", "app.routers.containers"),
    ("app.importers.queue", "app.routers.containers"),
    ("app.importers.queue", "app.routers.containers_common"),
    ("app.jobs", "app.routers.complaints"),
    ("app.jobs", "app.routers.driver"),
    ("app.notification_alerts", "app.routers.customs"),
    ("app.notification_digests", "app.routers.customs"),
    ("app.supplier_consolidation", "app.routers.dictionaries_merge"),
}


def _module(path: pathlib.Path) -> str:
    parts = list(path.relative_to(APP.parent).with_suffix("").parts)
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _imported(module: str, is_pkg: bool, node: ast.ImportFrom) -> str:
    if not node.level:
        return node.module or ""
    base = module.split(".") if is_pkg else module.split(".")[:-1]
    base = base[: len(base) - (node.level - 1)] if node.level > 1 else base
    return ".".join(base + ([node.module] if node.module else []))


def domain_to_router_edges() -> set[tuple[str, str]]:
    edges = set()
    for path in APP.rglob("*.py"):
        module = _module(path)
        if module.startswith("app.routers") or module == "app.main":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                target = _imported(module, path.name == "__init__.py", node)
                names = [f"{target}.{a.name}" for a in node.names]
            elif isinstance(node, ast.Import):
                target, names = "", [a.name for a in node.names]
            else:
                continue
            for name in [target, *names]:
                if name.startswith("app.routers."):
                    # moduł routera, nie symbol z niego (app.routers.containers.next_transport_id)
                    parts = name.split(".")
                    router = ".".join(parts[:3])
                    edges.add((module, router))
    return edges


def test_domain_modules_do_not_import_new_routers():
    new = sorted(domain_to_router_edges() - ALLOWED)
    assert not new, ("moduł domenowy importuje router — wydziel wspólną logikę do modułu "
                     f"domenowego (router może ją re-eksportować): {new}")


def test_app_settings_read_without_routers():
    """Wycinek ARCH-001: ustawienia AppSetting czytane z app.app_settings, nie z reklamacji."""
    users = {"app.notification_alerts", "app.notification_digests", "app.sharepoint"}
    edges = {(m, r) for m, r in domain_to_router_edges() if m in users}
    assert not any(r.startswith("app.routers.complaints") for _, r in edges), edges
