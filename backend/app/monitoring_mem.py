"""Szczegóły RAM do monitora serwera: na co idzie pamięć hosta i które procesy ją zjadają.

Rozbicie z /proc/meminfo działa zawsze (meminfo w kontenerze = cały host).
Lista procesów: kontener ma własną przestrzeń PID, więc bez montażu hosta widzi tylko
siebie. Z `/proc:/host/proc:ro` (docker-compose.coolify.yml, jak node-exporter) widać
wszystkie procesy serwera: Coolify, Traefik, bazy, n8n. Czytamy WYŁĄCZNIE `comm`,
`status` i `cgroup` (nazwa, pamięć, id kontenera) — bez cmdline/environ (mogą mieć sekrety).
"""
import pathlib
import re

from .config import settings

TOP_N = 12
_DOCKER_ID = re.compile(r"(?:docker[-/]|containerd[-/]|/)([0-9a-f]{64})")


def breakdown(kb: dict[str, int]) -> dict:
    """Podział zajętej pamięci (MB). „apps” = pamięć procesów (anon), „cache” = do
    odzyskania przez jądro na żądanie, „kernel” = struktury jądra, których nie odzyska."""
    mb = lambda k: kb.get(k, 0) // 1024  # noqa: E731
    return {
        "apps_mb": mb("AnonPages"),
        "shared_mb": mb("Shmem"),        # tmpfs + pamięć współdzielona (np. shared_buffers Postgresa)
        "cache_mb": max(mb("Cached") + mb("Buffers") - mb("Shmem"), 0) + mb("SReclaimable"),
        "kernel_mb": mb("SUnreclaim") + mb("KernelStack") + mb("PageTables"),
        "swap_used_mb": max(mb("SwapTotal") - mb("SwapFree"), 0),
        "swap_total_mb": mb("SwapTotal"),
    }


def _status(pid_dir: pathlib.Path) -> dict[str, int] | None:
    try:
        raw = (pid_dir / "status").read_text()
    except OSError:   # proces zniknął w trakcie odczytu / brak dostępu
        return None
    out = {}
    for ln in raw.splitlines():
        key, _, val = ln.partition(":")
        if key in ("RssAnon", "RssShmem"):
            out[key] = int(val.split()[0])
    return out if out.get("RssAnon") else None   # wątki jądra: brak RSS


def _container(pid_dir: pathlib.Path) -> str:
    try:
        m = _DOCKER_ID.search((pid_dir / "cgroup").read_text())
    except OSError:
        return ""
    return m.group(1)[:12] if m else ""   # 12 znaków = jak w `docker ps`


def top_processes(proc_dir: str | None = None) -> dict:
    """Procesy pogrupowane po (nazwa, kontener). private = suma RssAnon (bez podwójnego
    liczenia), shared = max RssShmem w grupie (współdzielona — wspólna dla wszystkich)."""
    host = pathlib.Path(proc_dir if proc_dir is not None else settings.host_proc_dir or "")
    root = host if str(host) not in ("", ".") and (host / "meminfo").exists() \
        else pathlib.Path("/proc")
    if not (root / "meminfo").exists():   # nie-Linux (dev na Windows)
        return {"scope": None, "items": []}
    groups: dict[tuple[str, str], dict] = {}
    for pid_dir in root.iterdir():
        if not pid_dir.name.isdigit():
            continue
        st = _status(pid_dir)
        if st is None:
            continue
        try:
            name = (pid_dir / "comm").read_text().strip()
        except OSError:
            continue
        cid = _container(pid_dir)
        g = groups.setdefault((name, cid), {"name": name, "container": cid, "count": 0,
                                            "private_kb": 0, "shared_kb": 0})
        g["count"] += 1
        g["private_kb"] += st["RssAnon"]
        g["shared_kb"] = max(g["shared_kb"], st.get("RssShmem", 0))
    top = sorted(groups.values(), key=lambda g: g["private_kb"] + g["shared_kb"], reverse=True)
    return {"scope": "host" if root != pathlib.Path("/proc") else "container",
            "items": [{"name": g["name"], "container": g["container"], "count": g["count"],
                       "private_mb": g["private_kb"] // 1024, "shared_mb": g["shared_kb"] // 1024}
                      for g in top[:TOP_N]]}
