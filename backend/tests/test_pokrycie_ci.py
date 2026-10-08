"""TEST-005: pokrycie backendu mierzone i pilnowane w CI (pytest-cov z locka dev, próg
w pyproject). Spadek poniżej progu = czerwony „Backend — pytest”."""
import re
import tomllib
from pathlib import Path

import yaml

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent


def test_konfiguracja_pokrycia():
    cov = tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["coverage"]
    assert cov["run"]["source"] == ["app"]
    assert 50 <= float(cov["report"]["fail_under"]) <= 100


def test_ci_mierzy_pokrycie_szybkim_rdzeniem():
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "ci-backend.yml").read_text(encoding="utf-8"))
    env = wf["jobs"]["backend"]["env"]
    assert "--cov" in env["PYTEST_ADDOPTS"].split()
    assert env["COVERAGE_CORE"] == "sysmon"
    assert "--cov-branch" not in env["PYTEST_ADDOPTS"], "gałęzie wyłączają sysmon (wolny tracer)"


def test_pytest_cov_w_locku_dev_nie_w_runtime():
    dev = (BACKEND / "requirements-dev.txt").read_text(encoding="utf-8")
    runtime = (BACKEND / "requirements.txt").read_text(encoding="utf-8")
    assert re.search(r"^pytest-cov==", dev, re.M) and re.search(r"^coverage==", dev, re.M)
    assert not re.search(r"^(pytest-cov|coverage)==", runtime, re.M)
