"""Audyt: handler `async def` z synchroniczną sesją SQLAlchemy blokuje event loop.
Trasy zależne od get_db mają być zwykłym `def` (FastAPI puszcza je w threadpoolu)."""
import importlib
import inspect
import pkgutil

from fastapi import APIRouter
from fastapi.routing import APIRoute

import app.routers as routers_pkg
from app.database import get_db


def _uses_db(dependant) -> bool:
    return any(d.call is get_db or _uses_db(d) for d in dependant.dependencies)


def _routes():
    for info in pkgutil.iter_modules(routers_pkg.__path__):
        module = importlib.import_module(f"app.routers.{info.name}")
        for obj in vars(module).values():
            if isinstance(obj, APIRouter):
                yield from (r for r in obj.routes if isinstance(r, APIRoute))


def test_route_discovery_sees_db_routes():
    assert sum(_uses_db(r.dependant) for r in _routes()) > 50


def test_db_routes_are_not_coroutines():
    offenders = sorted({
        f"{r.endpoint.__module__}.{r.endpoint.__name__}"
        for r in _routes()
        if _uses_db(r.dependant) and inspect.iscoroutinefunction(r.endpoint)})
    assert offenders == []
