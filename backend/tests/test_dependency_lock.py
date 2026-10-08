"""Odtwarzalność buildu (audyt DEP-001 / BUILD-001).

- requirements.txt to lock: każda paczka `==` + `--hash=`, wersje spełniają specyfikatory z requirements.in;
- każdy `FROM` w Dockerfile* przypięty digestem, instalacja pip z `--require-hashes`;
- BUILD-005/DEP-003: narzędzia testów i lintu tylko w requirements-dev.txt (lock jak wyżej) —
  obraz instaluje sam runtime, CI oba locki (wspólne paczki w tych samych wersjach i hashach).
"""
import re
from pathlib import Path

import pytest
from packaging.requirements import Requirement

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
DOCKERFILES = [ROOT / "Dockerfile.coolify", BACKEND / "Dockerfile", ROOT / "frontend" / "Dockerfile"]
DEV_ONLY = {"pytest", "ruff", "pluggy", "iniconfig"}


def _name(spec: str) -> str:
    return re.sub(r"[-_.]+", "-", re.split(r"[\[=<>; ]", spec, maxsplit=1)[0]).lower()


def _lock(fname: str = "requirements.txt") -> dict[str, tuple[str, str]]:
    """{nazwa: (wersja, blok tekstu z hashami)} z locka (requirements.txt / requirements-dev.txt)."""
    text = (BACKEND / fname).read_text(encoding="utf-8")
    out = {}
    for block in re.split(r"\n(?=\S)", text):
        if block.startswith("#") or not block.strip():
            continue
        m = re.match(r"([A-Za-z0-9_.\-\[\],]+)==([^\s;\\]+)", block)
        assert m, f"pozycja locka bez ==: {block.splitlines()[0]}"
        out[_name(m.group(1))] = (m.group(2), block)
    return out


def test_lock_ma_hashe_dla_kazdej_paczki():
    for fname, minimum in (("requirements.txt", 20), ("requirements-dev.txt", 2)):
        lock = _lock(fname)
        assert len(lock) >= minimum, fname
        bez_hasha = [n for n, (_, blok) in lock.items() if "--hash=sha256:" not in blok]
        assert not bez_hasha, f"{fname}: paczki bez hasha w locku: {bez_hasha}"


@pytest.mark.parametrize("src,fname", [("requirements.in", "requirements.txt"),
                                       ("requirements-dev.in", "requirements-dev.txt")])
def test_wersje_w_locku_spelniaja_specyfikatory_z_requirements_in(src, fname):
    lock = _lock(fname)
    for line in (BACKEND / src).read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-c "):
            continue
        req = Requirement(line)
        name = _name(req.name)
        assert name in lock, f"{name} z requirements.in brak w locku — odśwież lock"
        assert req.specifier.contains(lock[name][0], prereleases=True), (
            f"{name}=={lock[name][0]} nie spełnia {req.specifier} — odśwież lock"
        )


def test_obrazy_bazowe_przypiete_digestem_i_pip_z_hashami():
    for df in DOCKERFILES:
        text = df.read_text(encoding="utf-8")
        froms = re.findall(r"^FROM\s+(\S+)", text, flags=re.M)
        assert froms, df
        for image in froms:
            assert re.search(r"@sha256:[0-9a-f]{64}$", image), f"{df.name}: {image} bez digestu"
        for pip in re.findall(r"pip install[^\n]*-r requirements\.txt", text):
            assert "--require-hashes" in pip, f"{df.name}: {pip}"


def test_narzedzia_testow_tylko_w_locku_dev():
    runtime, dev = _lock(), _lock("requirements-dev.txt")
    assert not DEV_ONLY & runtime.keys(), f"narzędzia testów w locku runtime: {DEV_ONLY & runtime.keys()}"
    assert {"pytest", "ruff"} <= dev.keys()
    # wspólne paczki (np. packaging): ta sama wersja i hashe — CI instaluje oba locki naraz
    for name in runtime.keys() & dev.keys():
        hashes = [set(re.findall(r"sha256:[0-9a-f]{64}", lock[name][1])) for lock in (runtime, dev)]
        assert runtime[name][0] == dev[name][0] and hashes[0] == hashes[1], \
            f"{name}: rozjazd locków — odśwież requirements-dev.txt (-c requirements.txt)"


def test_obraz_bez_locka_dev_a_ci_z_nim():
    for df in DOCKERFILES:
        assert "requirements-dev" not in df.read_text(encoding="utf-8"), df.name
    ci = (ROOT / ".github" / "workflows" / "ci-backend.yml").read_text(encoding="utf-8")
    assert re.search(r"pip install --require-hashes -r requirements\.txt -r requirements-dev\.txt", ci)
