"""Aktualności na Pulpicie (spec 2026-10-01-aktualnosci-pulpit): powiadomienia jak news —
kategoria i ważność z rodzaju (`kind`), wątek wg kontenera / statku, numery kontenerów z treści.
Wszystko wyliczane z istniejących kolumn Notification — bez migracji."""
import re

from .invoices.suggestions import found_container_numbers
from .models import Notification

CATEGORIES: dict[str, tuple[str, ...]] = {
    "vessels": ("vessel", "vessel_port", "vessel_stuck", "port_congestion", "dest_port", "eta",
                "eta_drift", "eta_overdue", "tracking", "tracking_error", "carrier"),
    "customs": ("customs", "customs-delay", "docs-missing"),
    "orders": ("order", "freight_approval", "freight_decision", "invoice-mismatch", "supplier",
               "quote", "marm", "forecast-overload", "crd_escalation"),
    "deliveries": ("avizo", "planned", "driver", "gate", "dlt", "pallet_urgent", "status",
                   "demurrage"),
    "messages": ("message", "mention", "file", "complaint", "complaint_deadline",
                 "complaint_draft", "complaint_reminder", "bulletin"),
    # system = reszta (także rodzaje dodane później, bez wpisu wyżej)
    "system": ("system", "system-error", "stale-import", "excel-sync", "daily_digest",
               "weekly_digest", "backup_verify_failed"),
}
_KIND_CATEGORY = {kind: cat for cat, kinds in CATEGORIES.items() for kind in kinds}
KNOWN_NON_SYSTEM = tuple(k for cat, kinds in CATEGORIES.items() if cat != "system" for k in kinds)

URGENT = frozenset({"system-error", "vessel_stuck", "demurrage", "pallet_urgent", "invoice-mismatch",
                    "backup_verify_failed"})
INFO = frozenset({"daily_digest", "weekly_digest", "stale-import", "excel-sync", "marm", "tracking"})

# „Statek MV DEMO HELIOS w porcie docelowym …”, „… w rejonie portu …”, „… stoi przy …”
_VESSEL = re.compile(r"^Statek (.+?) (?:w |stoi )")


def category(kind: str) -> str:
    return _KIND_CATEGORY.get(kind, "system")


def priority(kind: str) -> str:
    return "urgent" if kind in URGENT else "info" if kind in INFO else "normal"


def vessel_name(title: str) -> str | None:
    match = _VESSEL.match(title or "")
    return match.group(1).strip() if match else None


def thread_key(n: Notification) -> str:
    """Wątek: kontener (container_id) > statek z tytułu > sama wiadomość."""
    if n.container_id:
        return f"c:{n.container_id}"
    name = vessel_name(n.title)
    return f"v:{name}" if name else f"n:{n.id}"


def container_numbers(n: Notification) -> list[str]:
    """Numery kontenerów (ISO 6346, z cyfrą kontrolną) z tytułu i treści — w kolejności."""
    return found_container_numbers(f"{n.title}\n{n.body}")
