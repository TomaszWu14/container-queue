"""DEP-006: tygodniowy job Trivy buduje obraz, zapisuje jego SBOM (CycloneDX) jako artefakt
i skanuje pakiety obrazu. Job działa na runnerze GitHuba (ubuntu-latest),
poza PR-ami i poza REQUIRED, więc nie spowalnia ani nie blokuje merge'y."""
import re
from pathlib import Path

import yaml

WF = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "security.yml"


def _job():
    return yaml.safe_load(WF.read_text(encoding="utf-8"))["jobs"]["trivy"]


def test_sbom_obrazu_jako_artefakt():
    job = _job()
    assert "ubuntu-latest" in job["runs-on"]
    assert "pull_request" in job["if"] and "!=" in job["if"]
    runs = "\n".join(s.get("run", "") for s in job["steps"])
    tag = re.search(r'docker build -f Dockerfile\.coolify -t "([^"]+)"', runs)
    assert tag, "brak buildu obrazu Dockerfile.coolify"
    assert re.search(r"trivy\" image --format cyclonedx --output (\S+)", runs)
    assert re.search(r"trivy\" image --scanners vuln", runs), "brak skanu podatności obrazu"
    upload = [s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/upload-artifact@")]
    assert upload and upload[0]["with"]["path"] in runs
    assert re.fullmatch(r"actions/upload-artifact@[0-9a-f]{40}", upload[0]["uses"])
    cleanup = [s for s in job["steps"] if "docker image rm" in s.get("run", "")]
    assert cleanup and cleanup[0].get("if") == "always()"
