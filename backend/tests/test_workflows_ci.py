"""Strażnik workflowów CI (audyt CICD-002/CICD-003, wersja publiczna repo).

- żaden job nie chodzi na self-hosted runnerze — w publicznym repo PR z forka mógłby
  wykonać dowolny kod na maszynie runnera,
- skany sekretów i zależności nie są wyciszone (`|| true`, `continue-on-error`),
- akcje przypięte do pełnego SHA, bez `curl | sh`.
"""
import pathlib
import re

import yaml

WF = pathlib.Path(__file__).resolve().parents[2] / ".github" / "workflows"


def _workflows():
    return {p.name: yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted(WF.glob("*.yml"))}


def test_no_job_runs_on_self_hosted():
    bad = [f"{f}:{job}" for f, wf in _workflows().items()
           for job, spec in wf["jobs"].items() if "self-hosted" in str(spec.get("runs-on", ""))]
    assert not bad, f"joby na self-hosted runnerze w publicznym repo: {bad}"


def test_security_scans_are_not_silenced():
    for f in ("security.yml", "ci-infra.yml"):
        text = (WF / f).read_text(encoding="utf-8")
        assert "|| true" not in text and "continue-on-error" not in text, f


# CICD-009: akcje przypięte do pełnego SHA z komentarzem `# vX.Y.Z`; tag `@v7` można
# przesunąć na dowolny kod w repo akcji.
USES = re.compile(r"^\s*(?:-\s+)?uses:\s*(\S+)(.*)$", re.M)


def test_actions_pinned_to_full_sha():
    bad = []
    for p in sorted(WF.glob("*.yml")):
        for ref, rest in USES.findall(p.read_text(encoding="utf-8")):
            if ref.startswith(("./", "docker://")):
                continue
            if not (re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", ref)
                    and re.fullmatch(r"\s+# v\d+\.\d+\.\d+", rest)):
                bad.append(f"{p.name}: {ref}{rest}")
    assert not bad, f"akcje bez przypięcia do SHA (# vX.Y.Z): {bad}"


def test_no_remote_script_piped_to_shell():
    pipe = re.compile(r"\b(?:curl|wget)\b[^\n]*\|\s*(?:sudo\s+)?(?:ba)?sh\b")
    bad = [p.name for p in WF.glob("*.yml") if pipe.search(p.read_text(encoding="utf-8"))]
    assert not bad, f"`curl | sh` w workflowach (instaluj przypiętą wersję + sha256): {bad}"
