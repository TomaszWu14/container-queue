"""ARCH-008: jeden mechanizm HTML dla maili i pism — Jinja2 z autoescape.

Szablony w app/templates/ (*.html = autoescape, *.txt bez). Wartość z bazy albo formularza
wstawiona jako {{ wartość }} jest escapowana zawsze, więc bezpieczeństwo nie zależy od
pamiętania o esc() przy każdym nowym polu. Zaufany HTML (stałe stylów firmowych maili,
gotowa tabela) podajemy jawnie jako Markup.
"""
import pathlib

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from .date_pl import date_pl


def nl2br(value) -> Markup:
    """Escapuje, a nowe linie zamienia na <br> (pola wielowierszowe: uwagi, opis, numery)."""
    return Markup("<br>").join(escape(str(value or "")).split("\n"))


env = Environment(loader=FileSystemLoader(pathlib.Path(__file__).parent / "templates"),
                  autoescape=select_autoescape(["html"]), keep_trailing_newline=True)
env.filters["date_pl"] = date_pl
env.filters["nl2br"] = nl2br


def render(name: str, **context) -> str:
    return env.get_template(name).render(**context)
