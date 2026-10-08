"""HEALTHCHECK obrazu + strażnik zawieszenia (INFRA-008).

Docker sam nie restartuje kontenera „unhealthy” (`restart:` działa tylko po wyjściu procesu),
a zawieszony uvicorn (zablokowana pętla, wyczerpana pula wątków) nie wychodzi. Ten skrypt:

- kod wyjścia jak zwykły healthcheck: 0 = `/api/health` odpowiada 200, 1 = nie,
- liczy KOLEJNE braki odpowiedzi (timeout / odmowa połączenia — proces nie odpowiada);
  po `HEALTH_RESTART_AFTER` (domyślnie 6 × 30 s ≈ 3 min, 0 = wyłączone) kończy procesy
  aplikacji (SIGTERM, dwa sprawdzenia później SIGKILL). Kontener wychodzi, a
  `restart: unless-stopped` stawia go od nowa. Wymaga `init: true` w compose (PID 1 = init,
  aplikacja jest jego dzieckiem — procesu PID 1 nie da się zabić z wnętrza kontenera),
- NIE liczy odpowiedzi 503 (baza niedostępna — restart aplikacji jej nie naprawi) i nic nie
  robi, dopóki aplikacja choć raz nie była zdrowa (start, migracja Alembica — nie przerywamy).

Stan między wywołaniami: mały plik w /tmp, związany z bieżącym startem kontenera (czas startu
PID 1) — po restarcie ten sam kontener liczy od zera. Tylko stdlib — skrypt odpala się co 30 s
i nie może importować aplikacji.
"""
import json
import os
import signal
import sys
import urllib.error
import urllib.request
from pathlib import Path

URL = os.environ.get("HEALTH_URL", "http://127.0.0.1:8000/api/health")
STATE = Path(os.environ.get("HEALTH_STATE_FILE", "/tmp/timporye-health.json"))
# Windows (maszyny deweloperskie) nie ma SIGKILL — prod (Linux) dostaje SIGKILL bez zmian
KILL_SIGNAL = getattr(signal, "SIGKILL", signal.SIGTERM)


def _restart_after() -> int:
    try:
        return max(0, int(os.environ.get("HEALTH_RESTART_AFTER", "6")))
    except ValueError:
        return 6


def probe(url: str = URL, timeout: float = 4) -> str:
    """'ok' (200), 'error' (odpowiedź, ale nie 200 — np. 503 bez bazy), 'down' (brak odpowiedzi)."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return "ok" if resp.status == 200 else "error"
    except urllib.error.HTTPError:
        return "error"
    except (urllib.error.URLError, OSError):
        return "down"


def _boot_id() -> str:
    """Czas startu PID 1 (pole 22 /proc/1/stat) — inny po każdym (re)starcie kontenera."""
    try:
        return Path("/proc/1/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return ""


def _load(boot: str) -> dict:
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"boot": boot}
    return state if isinstance(state, dict) and state.get("boot") == boot else {"boot": boot}


def _save(state: dict) -> None:
    try:
        STATE.write_text(json.dumps(state), encoding="utf-8")
    except OSError:
        pass


def _kill_app(sig: int) -> None:
    """Sygnał do wszystkich procesów tego użytkownika poza sobą i PID 1 (init)."""
    try:
        os.kill(-1, sig)
    except OSError:
        pass


def step(result: str, state: dict, restart_after: int, kill=_kill_app) -> dict:
    """Aktualizuje stan po jednym sprawdzeniu; przy długim braku odpowiedzi ubija aplikację."""
    state = dict(state)
    if result == "ok":
        return {**state, "seen_healthy": True, "down": 0}
    if result == "down" and state.get("seen_healthy") and restart_after:
        state["down"] = state.get("down", 0) + 1
        if state["down"] >= restart_after + 2:
            kill(KILL_SIGNAL)
        elif state["down"] >= restart_after:
            kill(signal.SIGTERM)
    return state


def main() -> int:
    result = probe()
    state = step(result, _load(_boot_id()), _restart_after())
    _save(state)
    if result != "ok":
        print(f"health: {result} (kolejne braki odpowiedzi: {state.get('down', 0)})", file=sys.stderr)
    return 0 if result == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
