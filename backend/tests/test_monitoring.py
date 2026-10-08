"""Monitor serwera (2026-09-24): endpoint tylko dla admina, pełny kształt odpowiedzi
także poza Linuksem (dev na Windows → None), historia z próbek zadania tła."""
from app import monitoring
from tests.conftest import login


def test_monitor_admin_only(client, admin_headers):
    client.post("/api/users", headers=admin_headers, json={
        "login": "mon_log", "full_name": "L", "password": "Haslo12345!", "send_invite": False,
        "role": "logistics", "view_all_companies": True, "is_active": True})
    assert client.get("/api/admin/monitor", headers=login(client, "mon_log", "Haslo12345!")).status_code == 403


def test_monitor_shape_and_history(client, admin_headers):
    monitoring.HISTORY.clear()
    monitoring.sample()
    body = client.get("/api/admin/monitor", headers=admin_headers).json()
    for key in ("cpu_percent", "cpu_count", "load_avg", "memory", "container_memory",
                "process_rss_mb", "threads", "disks", "database", "history", "uptime_s"):
        assert key in body
    assert body["database"]["size_mb"] >= 0
    assert body["disks"] and body["disks"][0]["total_gb"] > 0   # shutil działa wszędzie
    assert len(body["history"]) == 1 and "cpu" in body["history"][0]


def test_cpu_percent_from_proc_stat_delta(monkeypatch):
    stats = iter(["cpu 100 0 100 700 100 0 0 0\n", "cpu 150 0 150 750 100 0 0 0\n"])
    monkeypatch.setattr(monitoring, "_read", lambda p: next(stats) if p == "/proc/stat" else None)
    monkeypatch.setattr(monitoring, "_cpu_prev", None)
    assert monitoring.cpu_percent() == 20.0    # busy 200 / total 1000
    assert monitoring.cpu_percent() == 66.7    # delta: busy +100 / total +150


def test_memory_breakdown_from_meminfo():
    from app.monitoring_mem import breakdown
    kb = {"AnonPages": 1_048_576, "Shmem": 102_400, "Cached": 512_000, "Buffers": 10_240,
          "SReclaimable": 51_200, "SUnreclaim": 20_480, "KernelStack": 10_240,
          "PageTables": 10_240, "SwapTotal": 2_097_152, "SwapFree": 1_572_864}
    assert breakdown(kb) == {"apps_mb": 1024, "shared_mb": 100, "cache_mb": 460,
                             "kernel_mb": 40, "swap_used_mb": 512, "swap_total_mb": 2048}


def test_top_processes_groups_by_name_and_container(tmp_path):
    from app.monitoring_mem import top_processes
    (tmp_path / "meminfo").write_text("MemTotal: 1 kB\n")
    cid = "a" * 64
    procs = [(1, "postgres", 200_000, 300_000, cid), (2, "postgres", 100_000, 250_000, cid),
             (3, "php-fpm", 150_000, 0, "b" * 64), (4, "kthreadd", 0, 0, "")]
    for pid, name, anon, shm, c in procs:
        d = tmp_path / str(pid)
        d.mkdir()
        (d / "comm").write_text(name + "\n")
        (d / "status").write_text(f"Name:\t{name}\nRssAnon:\t{anon} kB\nRssShmem:\t{shm} kB\n")
        (d / "cgroup").write_text(f"0::/system.slice/docker-{c}.scope\n" if c else "0::/\n")
    res = top_processes(str(tmp_path))
    assert res["scope"] == "host"
    pg, php = res["items"]    # wątek jądra (RssAnon 0) pominięty
    assert pg == {"name": "postgres", "container": "a" * 12, "count": 2,
                  "private_mb": 292, "shared_mb": 292}
    assert php["name"] == "php-fpm" and php["private_mb"] == 146
