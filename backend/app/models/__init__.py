"""Modele ORM — pakiet podzielony wg odpowiedzialności (limit 500 linii/plik).

Re-eksportuje wszystkie dotychczasowe nazwy, więc `from app.models import X` działa jak
przed podziałem. Import pakietu rejestruje wszystkie tabele w `Base.metadata` (alembic
env.py, create_all). Relacje między modułami idą po nazwach klas (rejestr SQLAlchemy).
"""
from .applog import *  # noqa: F401,F403
from .avizo import *  # noqa: F401,F403
from .complaints import *  # noqa: F401,F403
from .container import *  # noqa: F401,F403
from .dictionaries import *  # noqa: F401,F403
from .enums import *  # noqa: F401,F403
from .intake import *  # noqa: F401,F403
from .invoices import *  # noqa: F401,F403
from .knowledge import *  # noqa: F401,F403
from .links import *  # noqa: F401,F403
from .dlt import *  # noqa: F401,F403
from .orders import *  # noqa: F401,F403
from .sad_drafts import *  # noqa: F401,F403
from .sap import *  # noqa: F401,F403
from .supplier_aliases import *  # noqa: F401,F403
from .supplier_catalog import *  # noqa: F401,F403
from .sp_materials import *  # noqa: F401,F403
from .supplier_profiles import *  # noqa: F401,F403
from .system import *  # noqa: F401,F403
from .tracking import *  # noqa: F401,F403
from .transport import *  # noqa: F401,F403
from .typed_text import *  # noqa: F401,F403
