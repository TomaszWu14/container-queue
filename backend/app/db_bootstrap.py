"""Start bazy: dev-shim schematu (ensure_new_columns, poza prod), seedy słowników i konto admina.

Wydzielone z app/main.py — main re-eksportuje `bootstrap`/`ensure_new_columns`.
"""
import logging

from sqlalchemy import select, text

from .config import settings
from .database import Base, SessionLocal, engine
from .models import Company, Role, User, today_pl
from .security import hash_password

logger = logging.getLogger(__name__)


DEFAULT_COMPANIES = [("Borealis", "BOREALIS"), ("Cobalt Sport", "COBALT"),
                     ("Iberia", "PT"), ("Acme", "ACME")]

# firmy spedycyjne, dla których zakładamy osobne konta z własnym widokiem
DEFAULT_FORWARDERS = ["SPEDALFA", "Spedgamma", "Spedomega", "Speddelta"]

DEFAULT_PROBLEM_TYPES = [
    "Uszkodzony kontener", "Nieposprzątany kontener", "Spóźniony kontener",
    "Uszkodzony towar", "Braki w dostawie", "Zła plomba / brak plomby",
    "Mokry / zawilgocony towar", "Nieprawidłowe dokumenty", "Uwagi do kierowcy",
]


def seed_problem_types(db) -> None:
    from .models import ProblemType
    if db.scalar(select(ProblemType.id)):
        return
    for i, name in enumerate(DEFAULT_PROBLEM_TYPES):
        db.add(ProblemType(name=name, sort_order=(i + 1) * 10))


# typy kontenerów z wymiarami wewnętrznymi (kubatura liczona z L×W×H) i ładownością
DEFAULT_CONTAINER_TYPES = [
    # name, L, W, H (m, wewn.), payload kg, TEU
    ("20'DV", 5.90, 2.35, 2.39, 28200, 1.0),
    ("40'DV", 12.03, 2.35, 2.39, 26700, 2.0),
    ("40'HC", 12.03, 2.35, 2.70, 26500, 2.0),
    ("45'HC", 13.56, 2.35, 2.70, 27700, 2.25),
    ("20'RF", 5.44, 2.29, 2.27, 27700, 1.0),
    ("40'RF", 11.56, 2.29, 2.25, 27700, 2.0),
]

# porty wypłynięcia (master data): kategoria + transit time morski standard/long (dni do PL)
DEFAULT_PORTS = [
    # name, country, category(True=główny chiński), transit_std, transit_long
    ("Shanghai", "CN", True, 32, 42),
    ("Ningbo", "CN", True, 33, 43),
    ("Shenzhen (Yantian)", "CN", True, 34, 44),
    ("Qingdao", "CN", True, 34, 45),
    ("Guangzhou (Nansha)", "CN", True, 35, 45),
    ("Xiamen", "CN", True, 35, 46),
    ("Tianjin (Xingang)", "CN", True, 36, 47),
    ("Dalian", "CN", True, 36, 47),
    ("Hong Kong", "HK", False, 34, 44),
    ("Kaohsiung", "TW", False, 35, 45),
    ("Fuzhou", "CN", False, 36, 46),
    ("Lianyungang", "CN", False, 36, 47),
]


def seed_container_types(db) -> None:
    from .models import ContainerType
    if db.scalar(select(ContainerType.id)):
        return
    for i, (name, length, width, height, payload, teu) in enumerate(DEFAULT_CONTAINER_TYPES):
        db.add(ContainerType(name=name, inner_length_m=length, inner_width_m=width,
                             inner_height_m=height, max_payload_kg=payload, teu=teu,
                             sort_order=(i + 1) * 10))


def seed_ports(db) -> None:
    from .models import Port, PortCategory
    for name, country, is_main, std, long in DEFAULT_PORTS:
        port = db.scalar(select(Port).where(Port.name == name))
        category = PortCategory.GLOWNY_CN if is_main else PortCategory.OUT
        if port is None:
            db.add(Port(name=name, country=country, category=category,
                        transit_time_days=std, transit_time_long_days=long))
        elif port.transit_time_days is None:
            # uzupełnij metadane portom sprzed wprowadzenia master daty (bez nadpisywania edycji)
            port.country, port.category = country, category
            port.transit_time_days, port.transit_time_long_days = std, long


def backfill_transport_ids(db) -> None:
    """Jednorazowo nadaje ID transportu kontenerom sprzed wprowadzenia pola."""
    from .models import Container
    from .routers.containers import next_transport_id
    missing = db.scalars(select(Container).where(Container.transport_id.is_(None))
                         .order_by(Container.id)).all()
    for container in missing:
        company = db.get(Company, container.company_id)
        year = (container.notify_date or today_pl()).year
        container.transport_id = next_transport_id(db, company, year)
        db.flush()
    if missing:
        logger.info("Nadano ID transportu %s istniejącym kontenerom", len(missing))


def ensure_new_columns() -> None:
    """Dev bez Alembica (SQLite): dokłada nowe kolumny do istniejącej tabeli containers.

    Produkcja (docker/Coolify) migruje przez `alembic upgrade head` — tam bootstrap()
    tej funkcji w ogóle nie woła.
    """
    from sqlalchemy import inspect as sa_inspect
    inspector = sa_inspect(engine)
    if 'containers' not in inspector.get_table_names():
        return
    existing = {column['name'] for column in inspector.get_columns('containers')}
    ddl = {
        'on_carriage': "VARCHAR(10)",
        'driver_name': "VARCHAR(160) DEFAULT ''",
        'driver_id_no': "VARCHAR(60) DEFAULT ''",
        'truck_no': "VARCHAR(40) DEFAULT ''",
        'trailer_no': "VARCHAR(40) DEFAULT ''",
        'driver_phone': "VARCHAR(40) DEFAULT ''",
        'transport_id': "VARCHAR(20)",
        'order_numbers': "TEXT DEFAULT ''",
        'delivery_note': "TEXT DEFAULT ''",
        'purchase_note': "TEXT DEFAULT ''",
        'document_flow': "TEXT DEFAULT ''",
        'sent_required': "BOOLEAN",
        'sent_number': "TEXT DEFAULT ''",
        'sent_status': "VARCHAR(120) DEFAULT ''",
        'materials_list': "TEXT DEFAULT ''",
        'palletization_note': "TEXT DEFAULT ''",
        'pallet_count': "INTEGER",
        'customs_agency_id': "INTEGER",
        'customs_agent_name': "VARCHAR(160) DEFAULT ''",
        'customs_agent_phone': "VARCHAR(40) DEFAULT ''",
        'customs_agent_email': "VARCHAR(160) DEFAULT ''",
        'customs_assigned_at': "TIMESTAMP",
        'customs_case_status_id': "INTEGER",
        'purchasing_status': "VARCHAR(20) DEFAULT 'BRAK' NOT NULL",
        'document_status': "VARCHAR(20) DEFAULT 'BRAK' NOT NULL",
        'atd': "DATE",
        'etd': "DATE",
        'sync_baseline': "JSON",
        'unload_started_at': "DATETIME",
        'unload_finished_at': "DATETIME",
        'is_transit': "BOOLEAN DEFAULT 0 NOT NULL",
        'needs_forwarding': "BOOLEAN DEFAULT 0 NOT NULL",
        'customer_name': "VARCHAR DEFAULT '' NOT NULL",
        'customer_address': "VARCHAR DEFAULT '' NOT NULL",
        'customer_contact': "VARCHAR DEFAULT '' NOT NULL",
        'planning_status': "VARCHAR(20) DEFAULT 'PROPOZYCJA' NOT NULL",
        'notify_date_manual': "BOOLEAN DEFAULT 0 NOT NULL",
        'planning_sent_at': "DATETIME",
        'planning_confirmed_at': "DATETIME",
        'planning_confirmed_by_id': "INTEGER",
        'planning_eta_at_send': "DATE",
        'customer_id': "INTEGER",
        'is_special': "BOOLEAN DEFAULT 0 NOT NULL",
        'special_reason': "VARCHAR(40)",
        'special_note': "TEXT DEFAULT '' NOT NULL",
        'customs_t1': "BOOLEAN DEFAULT 0 NOT NULL",
        'consolidation_status': "VARCHAR(20) DEFAULT 'otwarty' NOT NULL",
        'capacity_cbm': "NUMERIC(10, 3) DEFAULT 70 NOT NULL",
        'slot_time': "VARCHAR(5) DEFAULT '' NOT NULL",   # #13, migracja sl1slot001
        'ramp_stage': "VARCHAR(20)",                     # D9, migracja ramp001
    }
    extra_tables = {
        'refresh_tokens': {'revoked_at': "TIMESTAMP"},
        'purchase_orders': {'crd': "DATE",
                            'crd_target': "DATE",
                            'cart_status': "VARCHAR(20) DEFAULT 'w_koszyku' NOT NULL"},
        # obieg akceptacji faktury transportowej (#42, migracja fi1appr001)
        'freight_invoices': {'status': "VARCHAR(20) DEFAULT 'NOWA' NOT NULL",
                             'approved_by_id': "INTEGER",
                             'approved_at': "TIMESTAMP",
                             'approval_note': "VARCHAR(300) DEFAULT '' NOT NULL"},
        # AIS: geofence portowy (migracja cd34ef56ab78) — tabela powstała wcześniej
        # (ab12cd34ef56), więc create_all jej nie zmieni na starych bazach dev
        'tracked_vessels': {'imo': "INTEGER",
                            'near_port': "VARCHAR(40) DEFAULT ''",
                            'near_port_since': "TIMESTAMP",
                            'length_m': "INTEGER",
                            'beam_m': "INTEGER",
                            'photo': "VARCHAR(255) DEFAULT ''"},
        'users': {'warehouse_id': "INTEGER",
                  'session_version': "INTEGER DEFAULT 0 NOT NULL",
                  'must_change_password': "BOOLEAN DEFAULT 0 NOT NULL",  # nosec B105
                  'last_seen': "TIMESTAMP",
                  'customs_agency_id': "INTEGER",
                  'watch_only_notifications': "BOOLEAN DEFAULT 0 NOT NULL",
                  'ui_prefs': "TEXT DEFAULT '' NOT NULL",
                  # W14: 2FA + uprawnienia per magazyn
                  'totp_secret': "VARCHAR(64)",  # nosec B105 — DDL, nie sekret
                  'totp_backup_codes': "TEXT DEFAULT '' NOT NULL",  # nosec B105
                  'totp_last_step': "INTEGER",
                  'allowed_warehouse_ids': "JSON"},
        'attachments': {'document_type_id': "INTEGER"},
        'forwarders': {'email': "VARCHAR(200) DEFAULT ''",
                       'contact_person': "VARCHAR(160) DEFAULT ''",
                       'contact_phone': "VARCHAR(60) DEFAULT ''",
                       'address': "VARCHAR(300) DEFAULT ''",
                       'note': "TEXT DEFAULT ''",
                       'language': "VARCHAR(2) DEFAULT 'pl' NOT NULL"},
        'customs_agencies': {'contact_person': "VARCHAR(160) DEFAULT ''",
                             'contact_phone': "VARCHAR(60) DEFAULT ''",
                             'address': "VARCHAR(300) DEFAULT ''",
                             'note': "TEXT DEFAULT ''"},
        'suppliers': {'address': "VARCHAR(300) DEFAULT ''",
                      'note': "TEXT DEFAULT ''",
                      'sap_code': "VARCHAR(20) DEFAULT ''",
                      'country': "VARCHAR(2) DEFAULT ''",
                      'column_map': "TEXT DEFAULT ''",
                      # kartoteka dostawców (kartoteka001). Uwaga dev: stara baza SQLite ma
                      # suppliers.company_id NOT NULL — shim go nie zdejmie; usuń timporye.db
                      'client_company_id': "INTEGER",
                      'street': "VARCHAR(160) DEFAULT ''",
                      'city': "VARCHAR(80) DEFAULT ''",
                      'zip': "VARCHAR(20) DEFAULT ''",
                      'vat': "VARCHAR(30) DEFAULT ''",
                      'sap_status': "VARCHAR(20) DEFAULT 'active'",
                      'lat': "FLOAT",
                      'lng': "FLOAT",
                      'geo_source': "VARCHAR(10) DEFAULT 'none'",
                      'shipping_port_id': "INTEGER"},
        'supplier_contacts': {'role': "VARCHAR(20) DEFAULT 'other'",
                              'messenger': "VARCHAR(120) DEFAULT ''",
                              'is_primary': "BOOLEAN DEFAULT 0"},
        'supplier_doc_samples': {'sha256': "VARCHAR(64)",
                                 'doc_type': "VARCHAR(4) DEFAULT ''",
                                 'variant_id': "INTEGER",
                                 'pages': "JSON",
                                 'result': "JSON",
                                 'status': "VARCHAR(12) DEFAULT 'ok'",
                                 'reason': "VARCHAR(300) DEFAULT ''"},
        # draft SAD: odczyt PDF i porównanie (migracja sad002)
        'sad_drafts': {'parsed': "JSON", 'comparison': "JSON"},
        'warehouses': {'email': "VARCHAR(200) DEFAULT ''",
                       'address': "VARCHAR(300) DEFAULT ''",
                       'contact_phone': "VARCHAR(40) DEFAULT ''",
                       'entry_instructions': "TEXT DEFAULT ''",
                       # sloty awizacji (#13, migracja sl1slot001)
                       'slot_windows': "VARCHAR(200) DEFAULT '' NOT NULL",
                       'slot_capacity': "INTEGER DEFAULT 1 NOT NULL"},
        # awizacja dwuetapowa (migracja avz2stg001)
        'avizo_requests': {'expires_at': "TIMESTAMP",
                           'status': "VARCHAR(30) DEFAULT 'SENT_STAGE1' NOT NULL",
                           'language': "VARCHAR(2) DEFAULT 'pl' NOT NULL",
                           'reject_comment': "TEXT DEFAULT '' NOT NULL",
                           'approved_by_id': "INTEGER",
                           'approved_at': "TIMESTAMP",
                           'closed_at': "TIMESTAMP",
                           'driver_data_purged_at': "TIMESTAMP"},
        'companies': {'avizo_cc': "VARCHAR(500) DEFAULT '' NOT NULL"},
        # W11: adresat/terminy/koszty/auto-szkic reklamacji (migracja ab12cd34ef01)
        'complaints': {'recipient_type': "VARCHAR(20) DEFAULT '' NOT NULL",
                       'auto_draft': "BOOLEAN DEFAULT 0 NOT NULL",
                       'claim_amount': "NUMERIC(14, 2)",
                       'recovered_amount': "NUMERIC(14, 2)",
                       'claim_currency': "VARCHAR(3) DEFAULT 'PLN' NOT NULL"},
        # Wywołania-DLT: auta + HU + palety ułamkowe (migracja a1b2c3d4e5f7)
        'pallet_call_lines': {'truck_id': "INTEGER",
                              'hu_numbers': "TEXT DEFAULT ''",
                              'pallets': "NUMERIC(7, 3)"},
        'material_units': {
            'length': "NUMERIC(14, 3)",
            'width': "NUMERIC(14, 3)",
            'height': "NUMERIC(14, 3)",
            'dimension_unit': "VARCHAR(10) DEFAULT '' NOT NULL",
            'sap_status': "VARCHAR(20) DEFAULT 'aktywny' NOT NULL",   # sapstat001
            'ean': "VARCHAR(20) DEFAULT '' NOT NULL",                  # marmean001
        },
        'sap_orders': {'sap_status': "VARCHAR(20) DEFAULT 'aktywny' NOT NULL"},  # sapstat001
        'ports': {
            'country': "VARCHAR(2) DEFAULT 'CN'",
            'category': "VARCHAR(9) DEFAULT 'OUT'",
            'transit_time_days': "INTEGER",
            'transit_time_long_days': "INTEGER",
            'is_active': "BOOLEAN DEFAULT 1",
        },
        'carriers': {'is_active': "BOOLEAN DEFAULT 1 NOT NULL",
                     'demurrage_free_days': "INTEGER"},
        'quotes': {
            'carrier_id': "INTEGER",
            'etd': "DATE",
            'eta': "DATE",
            'transit_time_days': "INTEGER",
            'no_equipment': "BOOLEAN DEFAULT 0 NOT NULL",
            'can_roll_booking': "BOOLEAN DEFAULT 0 NOT NULL",
            'revised_amount': "NUMERIC(12, 2)",
            'revised_note': "TEXT DEFAULT ''",
            'revised_at': "TIMESTAMP",
        },
        'transport_jobs': {
            'response_hours': "INTEGER DEFAULT 24 NOT NULL",
            'response_deadline': "TIMESTAMP",
            'scfi_index': "VARCHAR(60) DEFAULT ''",
            'shipment_number': "VARCHAR(80) DEFAULT ''",
            'agent_name': "VARCHAR(160) DEFAULT ''",
            'agent_phone': "VARCHAR(60) DEFAULT ''",
            'agent_company': "VARCHAR(160) DEFAULT ''",
            'agent_submitted_at': "TIMESTAMP",
            'cancel_reason': "TEXT DEFAULT ''",
            'cancelled_at': "TIMESTAMP",
            'chosen_at': "TIMESTAMP",
        },
        'orders': {
            'supplier_contact_id': "INTEGER",
            'departure_port_id': "INTEGER",
            'container_type_id': "INTEGER",
            'main_mode': "VARCHAR(9)",
            'sea_service': "VARCHAR(9)",
            'container_count': "INTEGER DEFAULT 1 NOT NULL",
            'goods_type': "VARCHAR(200) DEFAULT ''",
            'is_adr': "BOOLEAN DEFAULT 0 NOT NULL",
            'goods_classification': "VARCHAR(200) DEFAULT ''",
            'goods_value': "NUMERIC(14, 2)",
            'goods_currency': "VARCHAR(3) DEFAULT 'USD'",
            'goods_weight': "VARCHAR(60) DEFAULT ''",
            'readiness_date': "DATE",
            'created_by_id': "INTEGER",
            'created_at': "TIMESTAMP",
        },
    }
    with engine.begin() as connection:
        for name, spec in ddl.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE containers ADD COLUMN {name} {spec}"))
        for table, columns in extra_tables.items():
            if table not in inspector.get_table_names():
                continue
            present = {column['name'] for column in inspector.get_columns(table)}
            for name, spec in columns.items():
                if name not in present:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {spec}"))
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_containers_transport_id "
            "ON containers (transport_id)"))


def check_alembic_head() -> None:
    """Loguje ERROR, gdy baza nie jest na głowie Alembica (nie blokuje startu)."""
    from pathlib import Path

    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory
    try:
        cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        heads = set(ScriptDirectory.from_config(cfg).get_heads())
        with engine.connect() as connection:
            current = set(MigrationContext.configure(connection).get_current_heads())
    except Exception:  # noqa: BLE001 — kontrola diagnostyczna, nie może położyć startu
        logger.exception("Nie udało się sprawdzić wersji schematu Alembica")
        return
    if current != heads:
        logger.error("Schemat bazy (alembic_version=%s) różni się od głowy migracji %s — "
                     "uruchom `alembic upgrade head`", sorted(current), sorted(heads))


def bootstrap() -> None:
    """Seedy (spółki, admin, słowniki); schemat tylko poza produkcją (dev/testy).

    Produkcja migruje wyłącznie `alembic upgrade head` (Dockerfile.coolify CMD) —
    create_all/ensure_new_columns maskowałyby brakującą migrację (BUILD-002, ARCH-005).
    """
    if settings.environment.lower() in ("production", "prod"):
        logger.info("Bootstrap: DDL pominięty na produkcji (schemat z alembica)")
        check_alembic_head()
    else:
        ensure_new_columns()
        Base.metadata.create_all(bind=engine)
    from sqlalchemy.exc import IntegrityError
    with SessionLocal() as db:
        for name, code in DEFAULT_COMPANIES:
            if not db.scalar(select(Company).where(Company.code == code)):
                db.add(Company(name=name, code=code))
        from .models import Forwarder
        for fname in DEFAULT_FORWARDERS:
            if not db.scalar(select(Forwarder).where(Forwarder.name == fname)):
                db.add(Forwarder(name=fname))
        if not db.scalar(select(User).limit(1)):
            db.add(User(
                login=settings.admin_login,
                full_name="Administrator",
                hashed_password=hash_password(settings.admin_password),
                role=Role.admin,
                view_all_companies=True,
            ))
        seed_problem_types(db)
        seed_container_types(db)
        seed_ports(db)
        try:
            db.commit()
        except IntegrityError:
            # równoległy worker zdążył zasiać te same rekordy przy pierwszym starcie
            db.rollback()
            logger.info("Bootstrap: dane zainicjowane równolegle przez inny proces")
        # backfill po commicie seedu, żeby konflikt seedu nie cofał także ID transportu
        backfill_transport_ids(db)
        db.commit()
