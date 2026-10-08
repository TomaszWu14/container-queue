"""BUILD-008 / INFRA-006: kontenery nie dostają /proc ani /sys hosta ani gniazda Dockera,
a monitor RAM bez montażu hosta działa dalej (procesy samego kontenera, scope=container)."""
import pathlib
from pathlib import Path

import yaml

from app.monitoring_mem import top_processes

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN = ("/proc", "/sys", "/var/run/docker.sock", "/run/docker.sock")


def test_compose_nie_montuje_proc_sys_ani_docker_sock():
    bad = []
    for path in sorted(ROOT.glob("docker-compose*.yml")):
        services = yaml.safe_load(path.read_text(encoding="utf-8"))["services"]
        for name, spec in services.items():
            for vol in spec.get("volumes", []):
                src = vol.get("source", "") if isinstance(vol, dict) else str(vol).split(":", 1)[0]
                if any(src == f or src.startswith(f + "/") for f in FORBIDDEN):
                    bad.append(f"{path.name}:{name}: {vol}")
    assert not bad, f"montaż zasobów hosta w kontenerze: {bad}"


def test_monitor_bez_proc_hosta_pokazuje_sam_kontener(tmp_path):
    res = top_processes(str(tmp_path / "brak-host-proc"))   # jak w kontenerze bez montażu
    if not pathlib.Path("/proc/meminfo").exists():           # dev poza Linuksem
        assert res == {"scope": None, "items": []}
        return
    assert res["scope"] == "container"
    assert isinstance(res["items"], list)


def test_endpoint_monitora_bez_proc_hosta(client, admin_headers):
    body = client.get("/api/admin/monitor", headers=admin_headers).json()
    assert body["processes"]["scope"] in ("container", None)   # /host/proc nie istnieje w testach
