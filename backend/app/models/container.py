"""Kontener — centralny rekord aplikacji — i nasłuch zmiany daty awizacji."""
import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    and_,
    false,
    or_,
    text,
)
from sqlalchemy import event as _sa_event
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.orm.base import NEVER_SET, NO_VALUE

from ..database import Base
from .checks import in_check
from .dictionaries import (
    Carrier,
    Company,
    CustomsAgency,
    CustomsCaseStatus,
    Forwarder,
    Port,
    Supplier,
    Warehouse,
)
from .enums import (
    SPECIAL_REASONS,
    ConsolidationStatus,
    ContainerStatus,
    CustomsStatus,
    DocumentStatus,
    OnCarriage,
    PlanningStatus,
    PurchasingStatus,
    TransportType,
    today_pl,
    utcnow,
)
from .orders import Order

# D9 etapy rampy (drugi wymiar obok ContainerStatus) — też CHECK ck_containers_ramp_stage
RAMP_STAGES = ("PODSTAWIONY", "ROZLADOWANY", "PRZYJETY")


class Container(Base):
    __tablename__ = "containers"
    # Indeks złożony (warehouse_id, notify_date): pokrywa i scope roli magazynu
    # (równość po warehouse_id — kolumna wiodąca), i kalendarz/analizę magazynu
    # (zakres notify_date + sort). Dlatego warehouse_id nie ma osobnego indeksu.
    # *_trgm: GIN pg_trgm pod wyszukiwarkę (migracje trgm002, fkidx001 — pełny OR pola ?q=
    # kolejki musi mieć indeks w każdej gałęzi, inaczej Seq Scan); na SQLite zwykły indeks.
    __table_args__ = (
        Index("ix_containers_wh_notify", "warehouse_id", "notify_date"),
        Index("ix_containers_no_trgm", "container_no", postgresql_using="gin",
              postgresql_ops={"container_no": "gin_trgm_ops"}),
        Index("ix_containers_orders_trgm", "order_numbers", postgresql_using="gin",
              postgresql_ops={"order_numbers": "gin_trgm_ops"}),
        Index("ix_containers_vessel_trgm", "vessel", postgresql_using="gin",
              postgresql_ops={"vessel": "gin_trgm_ops"}),
        Index("ix_containers_notes_trgm", "notes", postgresql_using="gin",
              postgresql_ops={"notes": "gin_trgm_ops"}),
        Index("ix_containers_transport_id_trgm", "transport_id", postgresql_using="gin",
              postgresql_ops={"transport_id": "gin_trgm_ops"}),
        # DB-007: numer kontenera unikalny wśród NIEZREALIZOWANYCH w spółce — tak dopasowują
        # import i sync (N-20); zrealizowany = archiwum, powtórny przyjazd to nowy rekord.
        # Pusty numer (zlecenie przed nadaniem kontenera) poza regułą.
        Index("ux_containers_active_no", "company_id", "container_no", unique=True,
              postgresql_where=text("status <> 'ZREALIZOWANY' AND container_no <> ''"),
              sqlite_where=text("status <> 'ZREALIZOWANY' AND container_no <> ''")),
        # DB-007: słowniki tekstowe i zakresy (migracja chk001; PG: NOT VALID + VALIDATE)
        in_check("containers", "consolidation_status", [s.value for s in ConsolidationStatus]),
        in_check("containers", "ramp_stage", RAMP_STAGES, nullable=True),
        in_check("containers", "special_reason", SPECIAL_REASONS, nullable=True),
        in_check("containers", "on_carriage", [m.value for m in OnCarriage], nullable=True),
        CheckConstraint("capacity_cbm > 0", name="ck_containers_capacity_cbm"),
        CheckConstraint("pallet_count >= 0", name="ck_containers_pallet_count"),
        CheckConstraint("unload_finished_at >= unload_started_at",
                        name="ck_containers_unload_order"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    container_no: Mapped[str] = mapped_column(String(11), index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True, index=True)
    supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("suppliers.id"), nullable=True, index=True)
    # nazwa dostawcy dokładnie jak w pliku kolejki — import nie tworzy już dostawców;
    # supplier_id ustawia dopasowanie nazwy/aliasu (SupplierAlias) albo mapowanie ręczne
    supplier_raw: Mapped[str] = mapped_column(String(160), default="", server_default=text("''"))
    forwarder_id: Mapped[int | None] = mapped_column(
        ForeignKey("forwarders.id"), nullable=True, index=True)
    needs_forwarding: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    warehouse_id: Mapped[int | None] = mapped_column(ForeignKey("warehouses.id"), nullable=True)
    port_id: Mapped[int | None] = mapped_column(ForeignKey("ports.id"), nullable=True)
    carrier_id: Mapped[int | None] = mapped_column(ForeignKey("carriers.id"), nullable=True)
    # tranzyt = kontener obsługiwany poza kolejką do naszego magazynu (nie jedzie do nas).
    # Jedyny wyjątek w logice: nie liczy się do dziennego limitu rozładunków (patrz
    # routers/containers.py, licznik `used`). Reszta — odprawa, demurrage, tracking,
    # powiadomienia — działa jak dla zwykłego kontenera.
    is_transit: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # flaga „specjalny" — ręczne wyróżnienie kontenera do śledzenia (karta statku,
    # kolejka, mapa); ustawiają admin/logistics, widzą wszyscy w zakresie
    is_special: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False)
    # powód śledzenia (dropdown z SPECIAL_REASONS) + komentarz — czemu kontener jest
    # oznaczony; zasila też strukturę „od czego zależy" na dashboardzie (F3)
    special_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    special_note: Mapped[str] = mapped_column(Text, default="", server_default="")

    # T1 — tranzyt celny poza portem (§5.5); równoległy do CustomsStatus, nie sekwencyjny
    customs_t1: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    # klient ze słownika (portal kliencki) — obok tekstowych customer_* z tranzytów
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id"), nullable=True, index=True)

    # tranzyt: dane klienta docelowego (wpisywane ręcznie; maskowane dla warehouse/customs)
    customer_name: Mapped[str] = mapped_column(String, default="")
    customer_address: Mapped[str] = mapped_column(String, default="")
    customer_contact: Mapped[str] = mapped_column(String, default="")

    status: Mapped[ContainerStatus] = mapped_column(
        Enum(ContainerStatus), default=ContainerStatus.ZAPOWIEDZIANY, index=True)
    consolidation_status: Mapped[str] = mapped_column(
        String(20), default=ConsolidationStatus.otwarty.value,
        server_default=ConsolidationStatus.otwarty.value)
    capacity_cbm: Mapped[float] = mapped_column(
        Numeric(10, 3), default=70, server_default="70")
    customs_status: Mapped[CustomsStatus] = mapped_column(
        Enum(CustomsStatus), default=CustomsStatus.BRAK, index=True)
    # status działu zakupów — edytowany wyłącznie przez rolę purchasing / admin / logistics
    purchasing_status: Mapped[PurchasingStatus] = mapped_column(
        Enum(PurchasingStatus), default=PurchasingStatus.BRAK, index=True)
    customs_note: Mapped[str] = mapped_column(Text, default="")
    customs_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    customs_agency: Mapped[str] = mapped_column(String(160), default="")  # nazwa wolnym tekstem (import)
    # strukturalne przypisanie agencji celnej (nowy obieg) + dane agenta wyznaczonego przez agencję
    customs_agency_id: Mapped[int | None] = mapped_column(
        ForeignKey("customs_agencies.id"), nullable=True, index=True)
    customs_agent_name: Mapped[str] = mapped_column(String(160), default="")
    customs_agent_phone: Mapped[str] = mapped_column(String(40), default="")
    customs_agent_email: Mapped[str] = mapped_column(String(160), default="")
    customs_assigned_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    # status sprawy celnej ze słownika admina (CustomsCaseStatus) — ustawiany przez agencję
    customs_case_status_id: Mapped[int | None] = mapped_column(
        ForeignKey("customs_case_statuses.id"), nullable=True, index=True)

    document_status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus), default=DocumentStatus.BRAK,
        server_default="BRAK", nullable=False)

    vessel: Mapped[str] = mapped_column(String(160), default="")
    eta: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    # ETD — data wypłynięcia z portu załadunku; ustawiana automatycznie z trackingu
    # (pierwsze zdarzenie DEPART), podstawa paska postępu rejsu w kolejce
    etd: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    # ATD — rzeczywista data (§10.2); uzupełniana po dostawie, ETA zostaje jako plan
    atd: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    notify_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True, index=True)
    proposed_delivery_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    # --- cykl planowania dostawy (spec 2026-09-02) ---
    # notify_date pozostaje JEDYNYM polem daty i kluczem kolejki; poniższe mówią,
    # ile ta data jest warta i czy wolno ją jeszcze przeliczać z ETA.
    planning_status: Mapped[PlanningStatus] = mapped_column(
        Enum(PlanningStatus), default=PlanningStatus.PROPOZYCJA,
        server_default="PROPOZYCJA", nullable=False, index=True)
    # człowiek wpisał datę ręcznie — ETA z API już jej nie nadpisuje, nawet w PROPOZYCJI
    notify_date_manual: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False)
    planning_sent_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    planning_confirmed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    # NULL gdy potwierdzenie przyszło publicznym linkiem tokenowym (brak zalogowanego usera)
    planning_confirmed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True)
    # zdjęcie ETA w chwili zamrożenia; alert "ETA przesunięta" liczymy w locie z różnicy,
    # zamiast trzymać flagę, która rozjeżdżałaby się przy każdej zmianie ETA
    planning_eta_at_send: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    transport_type: Mapped[TransportType | None] = mapped_column(Enum(TransportType), nullable=True)
    transport_details: Mapped[str] = mapped_column(String(200), default="")
    # dowóz po odprawie; VARCHAR (nie natywny enum) — nowy tryb nie wymaga ALTER TYPE
    on_carriage: Mapped[OnCarriage | None] = mapped_column(
        Enum(OnCarriage, native_enum=False, length=10), nullable=True)
    container_size: Mapped[str] = mapped_column(String(40), default="")
    documents_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    demurrage_free_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    incoming_delivery_no: Mapped[str] = mapped_column(String(80), default="")
    rf_number: Mapped[str] = mapped_column(String(80), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    # identyfikator transportu nadawany automatycznie (np. AT-2026-0001)
    transport_id: Mapped[str | None] = mapped_column(String(20), nullable=True,
                                                     unique=True, index=True)
    order_numbers: Mapped[str] = mapped_column(Text, default="")   # numery zamówień 1:1 z Excela
    delivery_note: Mapped[str] = mapped_column(Text, default="")   # kolumna „Dostawa”
    purchase_note: Mapped[str] = mapped_column(Text, default="")   # kolumna „MAGAZYN - ZAKUPY”
    document_flow: Mapped[str] = mapped_column(Text, default="")   # „PRZEPŁYW DOKUMENTÓW”
    sent_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sent_number: Mapped[str] = mapped_column(Text, default="")
    sent_status: Mapped[str] = mapped_column(String(120), default="")
    driver_name: Mapped[str] = mapped_column(String(160), default="")
    driver_id_no: Mapped[str] = mapped_column(String(60), default="")
    truck_no: Mapped[str] = mapped_column(String(40), default="")
    trailer_no: Mapped[str] = mapped_column(String(40), default="")
    driver_phone: Mapped[str] = mapped_column(String(40), default="")
    # #13 zarezerwowany slot rozładunku (HH:MM z okien magazynu; puste = bez slotu)
    slot_time: Mapped[str] = mapped_column(String(5), default="")
    # D9 etap rampy — drugi wymiar obok zamrożonego ContainerStatus (RAMP_STAGES; None = brak)
    ramp_stage: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # szczegóły dla magazynu przyjmującego (np. zewnętrzny DLT) — widok konta klienta
    materials_list: Mapped[str] = mapped_column(Text, default="")      # lista materiałów
    palletization_note: Mapped[str] = mapped_column(Text, default="")  # instrukcja paletyzacji
    pallet_count: Mapped[int | None] = mapped_column(Integer, nullable=True)  # ilość palet

    # Faza B sync: ostatni uzgodniony stan pól (ser()) — three-way merge Excel<->apka.
    sync_baseline: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)

    # pomiar czasu rozładunku (Start/Stop na karcie rozładunku)
    unload_started_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    unload_finished_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    tracked_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    tracking_error: Mapped[str] = mapped_column(String(300), default="")

    company: Mapped[Company] = relationship()
    order: Mapped[Order | None] = relationship(back_populates="containers")
    supplier: Mapped[Supplier | None] = relationship()
    forwarder: Mapped[Forwarder | None] = relationship()
    customs_agency_rel: Mapped["CustomsAgency | None"] = relationship()
    customs_case_status_rel: Mapped["CustomsCaseStatus | None"] = relationship()
    warehouse: Mapped[Warehouse | None] = relationship()
    port: Mapped[Port | None] = relationship()
    carrier: Mapped[Carrier | None] = relationship()

    ACTIVE_PRE_ARRIVAL = (ContainerStatus.ZAPOWIEDZIANY, ContainerStatus.W_PRODUKCJI,
                          ContainerStatus.TRANSPORT_WSTEPNY, ContainerStatus.W_TRANSPORCIE)
    # BIZ-004 — dwa różne pojęcia „zakończenia” (reguła w docs/REGULY-PROCESU.md):
    # FINISHED = fizycznie zakończony (rozładowany): śledzenie/mapa, demurrage, limity,
    #   SMS, sygnały, opóźnienia — DOSTARCZONY już nie płynie i nie stoi w porcie.
    # open_in_queue() = otwarty w kolejce: wszystko poza ZREALIZOWANY — DOSTARCZONY czeka
    #   w kolejce na rozliczenie (ZREALIZOWANY ustawia logistyka po formalnościach).
    FINISHED = (ContainerStatus.DOSTARCZONY, ContainerStatus.ZREALIZOWANY)
    RAMP_STAGES = RAMP_STAGES

    @property
    def is_delayed(self) -> bool:
        today = today_pl()  # kalendarz polski
        if self.status in self.FINISHED:
            return False
        if self.eta and self.eta < today and self.status in self.ACTIVE_PRE_ARRIVAL:
            return True
        if self.notify_date and self.notify_date < today:
            return True
        return False

    @classmethod
    def open_in_queue(cls):
        """Otwarty w kolejce (lista robocza, wyszukiwarka, skrzynka, liczniki pracy).
        Archiwum = `~Container.open_in_queue()`. Nie mylić z FINISHED (patrz wyżej)."""
        return cls.status != ContainerStatus.ZREALIZOWANY

    @classmethod
    def delayed_clause(cls, today: datetime.date):
        """`is_delayed` jako wyrażenie SQL (filtr listy bez ładowania całej tabeli).
        IS NOT NULL trzyma wynik w TRUE/FALSE — bez tego NOT(...) gubiłby wiersze z NULL."""
        return and_(
            cls.status.not_in(cls.FINISHED),
            or_(and_(cls.eta.is_not(None), cls.eta < today,
                     cls.status.in_(cls.ACTIVE_PRE_ARRIVAL)),
                and_(cls.notify_date.is_not(None), cls.notify_date < today)))

    # ile dni po ETA kontener w porcie przestaje być „świeżo przypłynięty", a zaczyna
    # być „utknięty". Rozładunek i papiery trwają — bez karencji sygnał świeciłby
    # każdemu kontenerowi w dniu przypłynięcia i operator przestałby go widzieć.
    STUCK_AFTER_DAYS = 3

    @property
    def is_stuck(self) -> bool:
        """Kontener stoi w porcie po ETA i nikt go nie awizował.

        Osobny sygnał od `is_delayed` (decyzja 2026-09-16): opóźnienie w transporcie
        i utknięcie w porcie mają różne przyczyny i różne akcje operatora — tu trzeba
        popchnąć awizację/odbiór, nie czekać na statek."""
        if self.status != ContainerStatus.W_PORCIE or self.notify_date:
            return False
        if not self.eta:
            return False
        return self.eta < today_pl() - datetime.timedelta(days=self.STUCK_AFTER_DAYS)


class TransportIdCounter(Base):
    """DB-011: ostatni nadany numer transport_id per prefiks („AT-2026-”) — sekwencja w bazie.

    Nadawanie (routers/containers_common.reserve_transport_seqs) to upsert z blokadą wiersza:
    równoległe transakcje dostają kolejne numery zamiast tego samego max+1 z Pythona."""
    __tablename__ = "transport_id_counters"
    prefix: Mapped[str] = mapped_column(String(20), primary_key=True)
    last_seq: Mapped[int] = mapped_column(Integer)


# #13 — slot rozładunku należy do KONKRETNEGO dnia: każda zmiana daty awizacji (kolejka,
# PATCH, plan, portal) zwalnia slot, żeby nie przeniósł się na nowy dzień ponad pojemność.
# Portal ustawia nowy slot PO zmianie daty, więc świeży wybór nie jest kasowany.
#
# Slot jest liczony per (magazyn, dzień, okno) — ta sama reguła dla zmiany magazynu (PATCH,
# sync z Excela przez FK, endpoint nazwy magazynu przez relację), inaczej nowy magazyn
# dostaje nadrezerwację okna. active_history=True: stara wartość jest znana także po
# expire (po commicie); NO_VALUE/NEVER_SET = pierwsze ustawienie (konstruktor) — nie zmiana.
def _release_slot(target, old, new) -> None:
    if old in (NO_VALUE, NEVER_SET) or old is new or old == new:
        return
    if target.slot_time:
        target.slot_time = ""


@_sa_event.listens_for(Container.notify_date, "set", active_history=True)
def _clear_slot_on_date_change(target, value, oldvalue, _initiator):
    _release_slot(target, oldvalue, value)


@_sa_event.listens_for(Container.warehouse_id, "set", active_history=True)
def _clear_slot_on_warehouse_change(target, value, oldvalue, _initiator):
    _release_slot(target, oldvalue, value)


@_sa_event.listens_for(Container.warehouse, "set", active_history=True)
def _clear_slot_on_warehouse_rel_change(target, value, oldvalue, _initiator):
    # porównanie po id: nowy (jeszcze niezflushowany) magazyn ma id None ≠ stary FK
    if oldvalue in (NO_VALUE, NEVER_SET):
        return
    _release_slot(target, getattr(oldvalue, "id", None), getattr(value, "id", None))
