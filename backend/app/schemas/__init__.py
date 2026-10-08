"""Schematy API (pydantic) — pakiet podzielony wg odpowiedzialności (limit 500 linii/plik).

Re-eksportuje wszystkie dotychczasowe nazwy, więc `from app.schemas import X` działa jak
przed podziałem.
"""
from .auth import *  # noqa: F401,F403
from .base import *  # noqa: F401,F403
from .base import _EMAIL_RE, _validate_email  # noqa: F401 — dawne nazwy modułu schemas
from .complaints import *  # noqa: F401,F403
from .containers import *  # noqa: F401,F403
from .dictionaries import *  # noqa: F401,F403
from .invoices import *  # noqa: F401,F403
from .knowledge import *  # noqa: F401,F403
from .dlt import *  # noqa: F401,F403
from .materials_customs import *  # noqa: F401,F403
from .orders import *  # noqa: F401,F403
from .queue import *  # noqa: F401,F403
from .transport import *  # noqa: F401,F403
