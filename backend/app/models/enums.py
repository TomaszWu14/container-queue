"""Enumy domenowe (statusy, tryby, role) i wspólny zegar `utcnow`."""
import datetime
import enum
from zoneinfo import ZoneInfo

PL_TZ = ZoneInfo("Europe/Warsaw")


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


def today_pl() -> datetime.date:
    """„Dziś" wg kalendarza polskiego (w UTC między 00:00 a 02:00 byłoby jeszcze wczoraj)."""
    return datetime.datetime.now(PL_TZ).date()


def pl_midnight_utc(day: datetime.date | None = None) -> datetime.datetime:
    """Polska północ dnia `day` (domyślnie dziś wg PL) jako naiwny UTC — do porównań z kolumnami
    utcnow (created_at). `combine(day, time.min)` bez strefy to północ UTC: między 00:00 a 02:00
    czasu PL gubi zapisy z „dziś” (deduplikacja alertów dublowała powiadomienia)."""
    midnight = datetime.datetime.combine(day or today_pl(), datetime.time.min, PL_TZ)
    return midnight.astimezone(datetime.UTC).replace(tzinfo=None)


def to_pl_date(at: datetime.datetime) -> datetime.date:
    """Data wg kalendarza PL dla znacznika naiwnego UTC (created_at) — `at.date()` to data UTC,
    o dzień wcześniej dla zdarzeń z 00:00–02:00 czasu PL."""
    return at.replace(tzinfo=datetime.UTC).astimezone(PL_TZ).date()


class Role(str, enum.Enum):
    admin = "admin"
    logistics = "logistics"
    warehouse = "warehouse"
    forwarder = "forwarder"
    customs = "customs"        # agencja celna (partner zewnętrzny z własnym loginem)
    purchasing = "purchasing"  # dział zakupów (pracownik wewn. zawężony do spółki)
    sales = "sales"            # sprzedaż: tylko odczyt kolejki/kalendarza/śledzenia/Specjalnej troski, bez kosztów


class TransportOrderStatus(str, enum.Enum):
    WYSTAWIONE = "WYSTAWIONE"
    ZAAKCEPTOWANE = "ZAAKCEPTOWANE"
    ODRZUCONE = "ODRZUCONE"
    W_REALIZACJI = "W_REALIZACJI"
    WYKONANE = "WYKONANE"
    POTWIERDZONE = "POTWIERDZONE"


class TransportJobStatus(str, enum.Enum):
    """Zlecenie transportowe (paczka kontenerów) w obiegu wycen."""
    SZKIC = "SZKIC"            # tworzone u nas, niewidoczne dla spedycji
    WYSLANE = "WYSLANE"        # potwierdzone/wysłane do spedycji — mogą wyceniać
    ZLECONE = "ZLECONE"        # wybrano zwycięzcę wyceny
    ANULOWANE = "ANULOWANE"


class QuoteStatus(str, enum.Enum):
    ZAPYTANIE = "ZAPYTANIE"    # zaproszenie do wyceny (jeszcze bez ceny)
    WYCENIONA = "WYCENIONA"    # spedytor podał cenę
    WYBRANA = "WYBRANA"        # oferta wygrała
    ODRZUCONA = "ODRZUCONA"    # inna oferta wygrała / anulowano
    WYGASLA = "WYGASLA"        # spedytor nie wycenił przed upływem terminu odpowiedzi


class MainMode(str, enum.Enum):
    """Główny środek transportu zlecenia z Chin: morze, samolot albo kolej."""
    SEA = "SEA"       # morski
    AIR = "AIR"       # lotniczy
    RAIL = "RAIL"     # kolejowy


class SeaService(str, enum.Enum):
    """Serwis morski: standardowy albo wydłużony (long)."""
    STANDARD = "STANDARD"
    LONG = "LONG"


class PortCategory(str, enum.Enum):
    """Kategoria portu wypłynięcia."""
    GLOWNY_CN = "GLOWNY_CN"   # główny port chiński (bezpośredni)
    OUT = "OUT"               # port „out" / przeładunkowy / feeder


class ContainerStatus(str, enum.Enum):
    ZAPOWIEDZIANY = "ZAPOWIEDZIANY"
    # etapy 2–3 procesu (2026-09-24); kolejność członów = kolejność procesu (STATUS_FLOW)
    W_PRODUKCJI = "W_PRODUKCJI"
    TRANSPORT_WSTEPNY = "TRANSPORT_WSTEPNY"
    W_TRANSPORCIE = "W_TRANSPORCIE"
    W_PORCIE = "W_PORCIE"
    ODPRAWA = "ODPRAWA"
    AWIZOWANY = "AWIZOWANY"
    W_DOSTAWIE = "W_DOSTAWIE"
    DOSTARCZONY = "DOSTARCZONY"
    ZREALIZOWANY = "ZREALIZOWANY"


class CartStatus(str, enum.Enum):
    w_koszyku = "w_koszyku"
    zwolnione = "zwolnione"
    przypisane = "przypisane"
    zablokowane = "zablokowane"


class ConsolidationStatus(str, enum.Enum):
    otwarty = "otwarty"
    wypelniony = "wypelniony"
    zamkniety = "zamkniety"


class PlanningStatus(str, enum.Enum):
    """Ile warta jest data w `Container.notify_date`.

    PROPOZYCJA   — nasza zgadywanka (eta + 4 dni); ETA z API może ją jeszcze przesunąć.
    WYSLANE      — poszła do spedycji, czeka na odpowiedź; data zamrożona.
    POTWIERDZONE — spedycja uzgodniła; tylko te liczą się do dziennego limitu.
    """
    PROPOZYCJA = "PROPOZYCJA"
    WYSLANE = "WYSLANE"
    POTWIERDZONE = "POTWIERDZONE"


class CustomsStatus(str, enum.Enum):
    """Status odprawy. DRAFT_* to etap zgłoszenia celnego (§10.4 specyfikacji) —
    wchodzi między zlecenie a odprawę: ZLECONA → DRAFT_WYSLANY → DRAFT_POTWIERDZONY
    → ODPRAWIONY → ZWOLNIONY (SAD-PW: towar zwolniony, można wydać — 2026-10-01).
    Kolejność członków = kolejność w filtrach i listach wyboru."""
    BRAK = "BRAK"
    DOKUMENTY_KOMPLETNE = "DOKUMENTY_KOMPLETNE"
    ZLECONA = "ZLECONA"
    DRAFT_WYSLANY = "DRAFT_WYSLANY"
    DRAFT_POTWIERDZONY = "DRAFT_POTWIERDZONY"
    ODPRAWIONY = "ODPRAWIONY"
    ZWOLNIONY = "ZWOLNIONY"
    ROZLICZONY = "ROZLICZONY"
    REWIZJA = "REWIZJA"


# Grupy statusu odprawy — JEDNO miejsce (pulpit, status kontenera z odprawy, kafelki, reguły cofania).
CUSTOMS_IN_PROGRESS = (CustomsStatus.ZLECONA, CustomsStatus.DRAFT_WYSLANY,
                       CustomsStatus.DRAFT_POTWIERDZONY, CustomsStatus.REWIZJA)
CUSTOMS_CLEARED = (CustomsStatus.ODPRAWIONY, CustomsStatus.ZWOLNIONY, CustomsStatus.ROZLICZONY)
_CUSTOMS_ORDER = list(CustomsStatus)


def customs_rank(status: CustomsStatus) -> int:
    """Pozycja w procesie: REWIZJA stoi w enumie na końcu (kolejność list wyboru), ale to odprawa
    w toku — po zgłoszeniu, przed ODPRAWIONY."""
    if status == CustomsStatus.REWIZJA:
        return _CUSTOMS_ORDER.index(CustomsStatus.DRAFT_POTWIERDZONY)
    return _CUSTOMS_ORDER.index(status)


class DocumentStatus(str, enum.Enum):
    """Obieg dokumentów kontenera (§10.4). Zastępuje docelowo luźne `documents_ok`
    i tekstowy `document_flow` — te zostają na razie dla zgodności z importem Excela."""
    BRAK = "BRAK"
    ZALACZONE = "ZALACZONE"
    WYSLANE = "WYSLANE"


class PurchasingStatus(str, enum.Enum):
    """Status działu zakupów dla kontenera.

    WARTOŚCI STARTOWE — do potwierdzenia z działem zakupów w ramach #12.
    Domyślnie BRAK (jak customs_status), żeby istniejące rekordy nie zyskały
    fałszywego stanu obiegu.
    """
    BRAK = "BRAK"
    DO_ZAMOWIENIA = "DO_ZAMOWIENIA"
    ZAMOWIONE = "ZAMOWIONE"
    POTWIERDZONE = "POTWIERDZONE"
    ZREALIZOWANE = "ZREALIZOWANE"
    WSTRZYMANE = "WSTRZYMANE"


class TransportType(str, enum.Enum):
    """Główny transport kontenera (do hubu/portu); „kola” zostaje dla starych danych."""
    morski = "morski"
    lotniczy = "lotniczy"
    kolej = "kolej"
    kola = "kola"
    inne = "inne"


# powody flagi „specjalny" (dropdown śledzenia) — wspólny kontrakt FE/BE (schemas.containers)
# i CHECK ck_containers_special_reason (DB-007)
SPECIAL_REASONS = ("zlecenie_klienta", "pilne", "kontrola_jakosci",
                   "nowe_produkty", "nowy_producent")


class OnCarriage(str, enum.Enum):
    """Dowóz kontenera po odprawie (hub/port → magazyn)."""
    drogowo = "drogowo"
    intermodal = "intermodal"


class PalletCallStatus(str, enum.Enum):
    draft = "draft"
    sent = "sent"
    confirmed = "confirmed"
    przygotowane = "przygotowane"        # DLT potwierdził przygotowanie (strona tokenowa)
    wyslane_z_dlt = "wyslane_z_dlt"      # DLT potwierdził wysyłkę (dezaktywuje token)
    delivered = "delivered"      # palety przywiezione — przestają być odejmowane z sugestii
    cancelled = "cancelled"
