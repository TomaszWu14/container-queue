"""Limitery żądań (logowanie, API per IP) i ustalanie IP klienta za proxy.

Wydzielone z security.py (limit 500 linii); security re-eksportuje te nazwy."""
import datetime
import hashlib
import ipaddress
import logging
import math
import threading
import time

from fastapi import HTTPException, Request, status
from sqlalchemy import delete, func, insert, select

from .config import settings
from .models.enums import utcnow

logger = logging.getLogger(__name__)


def _too_many(retry_after: int | None = None) -> HTTPException:
    headers = {"Retry-After": str(retry_after)} if retry_after else None
    return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                         "Zbyt wiele nieudanych prób logowania. Spróbuj ponownie później.",
                         headers=headers)


class LoginRateLimiter:
    """Limiter nieudanych logowań (okno przesuwne) ze stanem w BAZIE (ARCH-003, SEC-012).

    Wiersz `login_failures` = jedna porażka dla klucza (ip:…, para ip+login, acct:…, 2fa:…,
    forgot:…, reset:…). Restart (każdy deploy) nie zeruje liczników, a kilka workerów /
    instancji na wspólnej bazie liczy razem — słownik w pamięci procesu dawał limit ×N.
    Klucze trzymamy jako SHA-256: IP i wpisany login (bywa pomyłkowo hasłem) nie leżą w
    bazie jawnie. Każda operacja to krótka własna transakcja na osobnym połączeniu, więc
    porażka zostaje zapisana także wtedy, gdy transakcja żądania zostanie wycofana."""

    SWEEP_EVERY = 200   # co tyle porażek (w procesie) kasujemy wiersze starsze niż okno

    def __init__(self, bind=None) -> None:
        self._bind = bind
        self._lock = threading.Lock()
        self._sweeps = 0

    def _engine(self):
        if self._bind is not None:
            return self._bind
        from .database import engine   # leniwie — ten sam silnik co sesje aplikacji
        return engine

    @staticmethod
    def digest(key: str) -> str:
        return hashlib.sha256(key.encode()).hexdigest()

    @staticmethod
    def _window() -> datetime.timedelta:
        return datetime.timedelta(minutes=settings.login_window_minutes)

    def stats(self, *keys: str) -> dict[str, tuple[int, datetime.datetime]]:
        """{klucz: (porażek w oknie, ostatnia porażka)} — klucze bez porażek pominięte."""
        from .models import LoginFailure
        by_digest = {self.digest(k): k for k in keys}
        cutoff = utcnow() - self._window()
        with self._engine().connect() as conn:
            rows = conn.execute(
                select(LoginFailure.key, func.count(), func.max(LoginFailure.created_at))
                .where(LoginFailure.key.in_(list(by_digest)), LoginFailure.created_at > cutoff)
                .group_by(LoginFailure.key)).all()
        return {by_digest[d]: (n, last) for d, n, last in rows}

    def failures(self, key: str) -> int:
        return self.stats(key).get(key, (0, None))[0]

    def check(self, *keys: str, limit: int | None = None) -> None:
        cap = limit or settings.login_max_attempts
        if any(n >= cap for n, _ in self.stats(*keys).values()):
            raise _too_many()

    @staticmethod
    def account_delay(failures: int) -> datetime.timedelta | None:
        """SEC-012: od `login_account_lock_after` porażek konta (ze wszystkich IP) każda
        kolejna podwaja przerwę: base, 2×base, 4×base… maks. okno logowań."""
        over = failures - settings.login_account_lock_after
        if over < 0:
            return None
        seconds = settings.login_account_lock_seconds * 2 ** min(over, 20)
        return datetime.timedelta(seconds=min(seconds, settings.login_window_minutes * 60))

    def check_account(self, key: str) -> None:
        """429 z Retry-After, gdy konto (klucz acct:<login>) jest w progresywnej przerwie.
        Klucz liczony także dla nieistniejących loginów — blokada nie zdradza, czy konto jest."""
        failures, last = self.stats(key).get(key, (0, None))
        delay = self.account_delay(failures)
        if delay is None:
            return
        remaining = (last + delay - utcnow()).total_seconds()
        if remaining > 0:
            raise _too_many(math.ceil(remaining))

    def register_failure(self, *keys: str) -> None:
        from .models import LoginFailure
        now = utcnow()
        with self._lock:
            self._sweeps += 1
            sweep = self._sweeps >= self.SWEEP_EVERY
            if sweep:
                self._sweeps = 0
        with self._engine().begin() as conn:
            conn.execute(insert(LoginFailure),
                         [{"key": self.digest(k), "created_at": now} for k in keys])
            if sweep:
                conn.execute(delete(LoginFailure).where(
                    LoginFailure.created_at <= now - self._window()))

    def reset(self, *keys: str) -> None:
        from .models import LoginFailure
        with self._engine().begin() as conn:
            conn.execute(delete(LoginFailure).where(
                LoginFailure.key.in_([self.digest(k) for k in keys])))


login_limiter = LoginRateLimiter()


def assert_worker_config() -> None:
    """BUILD-003: kilka workerów uvicorna (WEB_CONCURRENCY — uvicorn czyta ją sam, workery
    dziedziczą env) tylko na PostgreSQL. Tam limiter logowań jest w bazie (loginlim001), a
    pętle tła prowadzi jeden proces-lider (leader.py, advisory lock). SQLite (dev/testy) nie
    ma advisory locków i ma jednego zapisującego — tam start z >1 workerem jest odrzucany.
    Budżet połączeń trafia do logu (do porównania z max_connections Postgresa)."""
    workers = settings.web_concurrency
    if workers <= 1:
        return
    if settings.database_url.startswith("sqlite"):
        raise RuntimeError(
            f"WEB_CONCURRENCY={workers}: kilka workerów uvicorna wymaga PostgreSQL (lider "
            "pętli tła na advisory locku, wspólny limiter logowań) — na SQLite ustaw "
            "WEB_CONCURRENCY=1. Patrz docs/JEDNA-INSTANCJA.md.")
    per_worker = settings.db_pool_size + settings.db_max_overflow + 2   # + lider i job_lock
    logger.info("WEB_CONCURRENCY=%d: do %d połączeń z bazą (%d na worker) — sprawdź "
                "max_connections Postgresa", workers, workers * per_worker, per_worker)


def _trusted_networks() -> list:
    """Sieci z TRUSTED_PROXY_CIDRS; błędny wpis (np. „1”) pomijany z ostrzeżeniem,
    zamiast wywracać każde żądanie wyjątkiem ValueError."""
    nets = []
    for cidr in settings.trusted_proxy_cidrs.split(","):
        cidr = cidr.strip()
        if not cidr:
            continue
        try:
            nets.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            logger.warning("TRUSTED_PROXY_CIDRS: pomijam niepoprawny wpis %r (oczekiwano np. 172.16.0.0/12)", cidr)
    return nets


def _is_trusted_proxy(host: str) -> bool:
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(addr in net for net in _trusted_networks())


def client_ip(request: Request) -> str:
    """Prawdziwe IP klienta, odporne na podszywanie się X-Forwarded-For.

    Za `trusted_proxy_count` zaufanymi proxy realne IP to N-ta pozycja od PRAWEJ
    w X-Forwarded-For (dopisuje ją nasze proxy), nie skrajnie lewa (od klienta).
    Wspólne dla limitera logowań i globalnego limitera API. XFF liczy się tylko,
    gdy bezpośredni peer jest zaufanym proxy (`trusted_proxy_cidrs`).
    """
    n = settings.trusted_proxy_count
    if n > 0 and _is_trusted_proxy(request.client.host if request.client else ""):
        xff = request.headers.get("x-forwarded-for", "")
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if len(parts) >= n:
            return parts[-n]
    return request.client.host if request.client else "unknown"


class ApiRateLimiter:
    """Globalny limiter żądań API na IP (okno minutowe, w pamięci procesu).

    Chroni pojedynczą instancję przed zalewem/pętlą klienta. Przy wielu instancjach
    za load balancerem limit działa per instancja — dla tej skali wystarczające
    (docelowo współdzielony licznik w Redis)."""

    WINDOW = 60.0

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()
        self._sweeps = 0

    def hit(self, key: str, limit: int) -> float | None:
        """Rejestruje żądanie; zwraca zalecany Retry-After (s), gdy limit przekroczony."""
        now = time.monotonic()
        with self._lock:
            entries = [t for t in self._hits.get(key, []) if now - t < self.WINDOW]
            if len(entries) >= limit:
                self._hits[key] = entries
                return self.WINDOW - (now - entries[0]) + 1
            entries.append(now)
            self._hits[key] = entries
            # okresowe czyszczenie martwych kluczy (IP, które przestały pukać)
            self._sweeps += 1
            if self._sweeps >= 1000:
                self._sweeps = 0
                self._hits = {k: v for k, v in self._hits.items()
                              if any(now - t < self.WINDOW for t in v)}
            return None


api_limiter = ApiRateLimiter()
