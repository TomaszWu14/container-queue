"""Firmy, użytkownicy i słowniki master data (dostawcy, spedycje, agencje, porty, magazyny)."""
import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .checks import in_check
from .enums import PortCategory, Role, utcnow

# active | blocked | inactive_in_sap — importers/lfa1.py; CHECK ck_suppliers_sap_status (DB-007)
SUPPLIER_SAP_STATUSES = ("active", "blocked", "inactive_in_sap")


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # adresy CC maili awizacji tej spółki (CSV) — np. skrzynka zespołu logistyki
    avizo_cc: Mapped[str] = mapped_column(String(500), default="", server_default=text("''"))


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(String(80), unique=True)
    email: Mapped[str] = mapped_column(String(160), default="")
    full_name: Mapped[str] = mapped_column(String(160), default="")
    hashed_password: Mapped[str] = mapped_column(String(200))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.logistics)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    forwarder_id: Mapped[int | None] = mapped_column(ForeignKey("forwarders.id"), nullable=True)
    customs_agency_id: Mapped[int | None] = mapped_column(
        ForeignKey("customs_agencies.id"), nullable=True)
    warehouse_id: Mapped[int | None] = mapped_column(ForeignKey("warehouses.id"), nullable=True)
    view_all_companies: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # wersja sesji: podbicie unieważnia wszystkie wydane access tokeny (wylogowanie)
    session_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # wymuszenie zmiany hasła przy pierwszym logowaniu (konta z zaproszenia)
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"))
    # ostatnia aktywność (aktualizowana z throttlingiem) — status „online" w panelu
    last_seen: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    # gdy True: powiadomienia o kontenerach dostaje tylko dla obserwowanych (gwiazdka)
    watch_only_notifications: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"))
    # profil widoku UI per user (JSON: ukryte kolumny, gęstość wierszy, zapisane
    # widoki kolejki) — podąża za kontem między przeglądarkami/urządzeniami
    ui_prefs: Mapped[str] = mapped_column(Text, default="", server_default=text("''"))
    # 2FA TOTP (RFC 6238): sekret base32; NULL = 2FA wyłączone
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # anty-replay TOTP: ostatni zaakceptowany krok czasowy (30 s); kod z kroku <= nie przejdzie
    totp_last_step: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # kody zapasowe 2FA: JSON-lista hashy SHA-256 (zużyty kod jest usuwany z listy)
    totp_backup_codes: Mapped[str] = mapped_column(Text, default="", server_default=text("''"))
    # W14 #91: zawężenie logistyki do wskazanych magazynów (JSON-lista id);
    # NULL/pusta lista = wszystkie magazyny (dotychczasowe zachowanie)
    allowed_warehouse_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # awatar: nazwa pliku w uploads/avatars/ (pusty = inicjały w UI)
    avatar: Mapped[str] = mapped_column(String(255), default="", server_default="")
    company: Mapped[Company | None] = relationship()

    @property
    def has_avatar(self) -> bool:
        return bool(self.avatar)


class Supplier(Base):
    """Dostawca. `client_company_id` NULL = globalna kartoteka dostawców Acme (spółki na jego
    materiałach, settings.supplier_company_codes); ustawione = nadawca kontenerów spółki-klienta
    (Borealis, Cobalt…), widoczny tylko dla tej spółki. Spec 2026-09-25-kartoteka-dostawcy."""
    __tablename__ = "suppliers"
    # GIN pg_trgm pod wyszukiwarkę (migracja trgm002); na SQLite zwykły indeks.
    # DB-007: CHECK statusu SAP. Unikalny kod SAP w kartotece dopiero po scaleniu kopii
    # (supplier_consolidation — „kartoteka002”, etap B); dziś kopie z importów są legalne.
    __table_args__ = (Index("ix_suppliers_name_trgm", "name", postgresql_using="gin",
                            postgresql_ops={"name": "gin_trgm_ops"}),
                      in_check("suppliers", "sap_status", SUPPLIER_SAP_STATUSES))
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    client_company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id"), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # sklejka adresu do wyświetlenia (składowe z SAP niżej); kontakty osobowe w SupplierContact
    address: Mapped[str] = mapped_column(String(300), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    # kod dostawcy z SAP (LIFNR) — klucz importu LFA1. "" = brak (nadawca klienta albo rekord
    # „do rozstrzygnięcia"); unikalność w kartotece zakłada migracja kartoteka002 (etap B)
    sap_code: Mapped[str] = mapped_column(String(20), default="", server_default=text("''"),
                                          index=True)
    country: Mapped[str] = mapped_column(String(2), default="", server_default=text("''"))
    street: Mapped[str] = mapped_column(String(160), default="", server_default=text("''"))
    city: Mapped[str] = mapped_column(String(80), default="", server_default=text("''"))
    zip: Mapped[str] = mapped_column(String(20), default="", server_default=text("''"))
    vat: Mapped[str] = mapped_column(String(30), default="", server_default=text("''"))
    # active | blocked | inactive_in_sap (zniknął z pliku SAP — nigdy nie kasujemy)
    sap_status: Mapped[str] = mapped_column(String(20), default="active",
                                            server_default=text("'active'"))
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    geo_source: Mapped[str] = mapped_column(String(10), default="none",
                                            server_default=text("'none'"))  # geocode|manual|none
    shipping_port_id: Mapped[int | None] = mapped_column(ForeignKey("ports.id"), nullable=True)
    # mapa kolumn faktury tego dostawcy dla ekstrakcji PDF → Excel (invoices/extractor):
    # "ref=Item No.; qty=Q'ty; net=Amount". Puste = auto-detekcja nagłówków. Znika w PR5
    # (mapy przechodzą do wariantów układu dokumentów).
    column_map: Mapped[str] = mapped_column(Text, default="", server_default=text("''"))
    # profil dokumentów (CI + PL) — zastępuje column_map (czytane zapasowo do usunięcia)
    # cascade jak przy Port.transit_rows: bez tego ORM przy delete(supplier) próbowałby
    # wyzerować supplier_id (NOT NULL) zamiast skasować profil — wywalało to scalanie
    # dostawców z profilem dokumentów, patrz dictionaries_merge._supplier_premerge.
    doc_profile: Mapped["SupplierDocProfile | None"] = relationship(  # noqa: F821
        back_populates="supplier", uselist=False, cascade="all, delete-orphan")


class SupplierContact(Base):
    """Kontakt u dostawcy: osoba, rola, e-mail, telefon, komunikator."""
    __tablename__ = "supplier_contacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    role: Mapped[str] = mapped_column(String(20), default="other",
                                      server_default=text("'other'"))  # sales|logistics|quality|other
    email: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(60), default="")
    messenger: Mapped[str] = mapped_column(String(120), default="",
                                           server_default=text("''"))  # np. „WeChat: xxx"
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    supplier: Mapped[Supplier] = relationship()


class Forwarder(Base):
    __tablename__ = "forwarders"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    email: Mapped[str] = mapped_column(String(200), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    contact_person: Mapped[str] = mapped_column(String(160), default="")
    contact_phone: Mapped[str] = mapped_column(String(60), default="")
    address: Mapped[str] = mapped_column(String(300), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    # język maili/formularzy awizacji (pl/en)
    language: Mapped[str] = mapped_column(String(2), default="pl", server_default=text("'pl'"))


class CustomsAgency(Base):
    """Agencja celna — partner zewnętrzny obsługujący odprawy. Ma własne konta
    (rola customs), analogicznie do spedycji. Logistyka zleca odprawę agencji,
    agencja wyznacza/zmienia agenta i aktualizuje status — obie strony powiadamiane."""
    __tablename__ = "customs_agencies"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    email: Mapped[str] = mapped_column(String(200), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    contact_person: Mapped[str] = mapped_column(String(160), default="")
    contact_phone: Mapped[str] = mapped_column(String(60), default="")
    address: Mapped[str] = mapped_column(String(300), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    # format pliku do agencji: standard (Excel pozycji) | symbols (Kartoteka symboli)
    export_format: Mapped[str] = mapped_column(String(20), default="standard", server_default=text("'standard'"))
    export_params: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)   # np. {"IDZestawu": 106}


class CustomsCaseStatus(Base):
    """Słownik statusów sprawy celnej — definiowany w panelu admina.

    Niezależny od sztywnego enuma CustomsStatus (obieg odprawy §10.4): agencja
    prowadzi na nim własny, konfigurowalny stan sprawy (np. „Dokumenty otrzymane"
    → „Zgłoszone" → „Odprawione"), a admin może go dopasować bez migracji."""
    __tablename__ = "customs_case_statuses"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class DocumentType(Base):
    """Słownik typów dokumentów kontenera (panel admina) — checklista kompletności.

    `is_required` = typ wymagany do kompletu dokumentów kontenera w obiegu celnym
    (przypisana agencja lub status odprawy ≠ BRAK). Kompletność liczona na żywo,
    bez przechowywanej flagi — zero desynchronizacji."""
    __tablename__ = "document_types"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False)
    # kafelek dokumentów dostawy (spec 2026-10-01-kafelki-dokumentow): stały kod zamiast nazwy —
    # zmiana nazwy typu nie psuje kafelków; jeden typ na kod
    tile_code: Mapped[str | None] = mapped_column(String(12), nullable=True, unique=True)


TILE_CODES = ("PI", "CI", "PL", "BL", "SAD_DRAFT", "SAD_PZ", "SAD_PW")


class Warehouse(Base):
    __tablename__ = "warehouses"
    __table_args__ = (UniqueConstraint("company_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str] = mapped_column(String(200), default="")
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    country: Mapped[str] = mapped_column(String(2), default="PL")  # PL / PT
    default_daily_limit: Mapped[int] = mapped_column(Integer, default=7)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # dane dla kierowcy (strona dostawy z linku SMS)
    address: Mapped[str] = mapped_column(String(300), default="")
    contact_phone: Mapped[str] = mapped_column(String(40), default="")
    entry_instructions: Mapped[str] = mapped_column(Text, default="")
    # #13 sloty awizacji: okna startu rozładunku "07:00,08:00,…" (puste = sloty wyłączone)
    # i ile kontenerów mieści jedno okno
    slot_windows: Mapped[str] = mapped_column(String(200), default="")
    slot_capacity: Mapped[int] = mapped_column(Integer, default=1)


class Port(Base):
    __tablename__ = "ports"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    country: Mapped[str] = mapped_column(String(2), default="CN")
    category: Mapped[PortCategory] = mapped_column(
        # VARCHAR(9) jak w migracji e4f5a6b7c8d9 (nie natywny enum PG — DB-003)
        Enum(PortCategory, native_enum=False, length=9), default=PortCategory.OUT)
    # transit time (w dniach) dla serwisu morskiego: standard i wydłużony (long)
    transit_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transit_time_long_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    transit_rows: Mapped[list["PortTransitTime"]] = relationship(
        back_populates="port", cascade="all, delete-orphan", lazy="selectin")

    @property
    def monthly_transit(self) -> dict[int, int]:
        """Profil sezonowy jako mapa miesiąc→dni (do serializacji w PortOut)."""
        return {row.month: row.days for row in self.transit_rows}


class PortTransitTime(Base):
    """Sezonowy (miesięczny) transit time portu: miesiąc → liczba dni.

    Bez roku świadomie: klient podaje profil sezonowy powtarzalny co rok
    („we wrześniu z Szanghaju płynie się 65 dni”), a nie historię pomiarów.
    Rok dodałby wymiar, którego nikt nie wypełni, i zmusiłby każdego czytelnika
    do wybierania „którego rocznika użyć”. Braki miesięcy są normalne —
    fallbackiem jest `Port.transit_time_days` (patrz `planning.transit_days_for`).
    """
    __tablename__ = "port_transit_times"
    __table_args__ = (UniqueConstraint("port_id", "month"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    port_id: Mapped[int] = mapped_column(ForeignKey("ports.id"), index=True)
    month: Mapped[int] = mapped_column(Integer)   # 1-12
    days: Mapped[int] = mapped_column(Integer)
    port: Mapped[Port] = relationship(back_populates="transit_rows")


class ContainerPort(Base):
    """Słownik WSZYSTKICH portów kontenerowych z importu klienta (kody UN/LOCODE-podobne,
    w tym niestandardowe ZZ***). Osobny od Port (słownik transit-time) — inne źródło,
    inna rola: warstwa mapy trackingu. Współrzędne dopasowywane przy imporcie z zasobu
    UN/LOCODE (app/data/unlocode.csv.gz); brak dopasowania = NULL (mapa go nie pokazuje)."""
    __tablename__ = "container_ports"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    country_code: Mapped[str] = mapped_column(String(2), default="")
    country_name: Mapped[str] = mapped_column(String(80), default="")
    lat: Mapped[float | None] = mapped_column(Numeric(9, 4), nullable=True)
    lon: Mapped[float | None] = mapped_column(Numeric(9, 4), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)


class ContainerType(Base):
    """Słownik typów kontenerów z kubaturą liczoną z wymiarów wewnętrznych."""
    __tablename__ = "container_types"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(40), unique=True)         # np. 40'HC
    inner_length_m: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    inner_width_m: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    inner_height_m: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    max_payload_kg: Mapped[int | None] = mapped_column(Integer, nullable=True)
    teu: Mapped[float | None] = mapped_column(Numeric(3, 1), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    @property
    def volume_m3(self) -> float | None:
        """Kubatura (m³) z wymiarów wewnętrznych; None gdy brak kompletu wymiarów."""
        if self.inner_length_m and self.inner_width_m and self.inner_height_m:
            return round(float(self.inner_length_m) * float(self.inner_width_m)
                         * float(self.inner_height_m), 2)
        return None


class Carrier(Base):
    __tablename__ = "carriers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # dni wolne od demurrage u tego armatora; kontener może nadpisać ręcznie (2026-09-28)
    demurrage_free_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
