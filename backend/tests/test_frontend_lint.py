"""CODE-002: ESLint panelu (typescript-eslint + reguły hooków Reacta) działa w CI.

Lint siedzi w osobnym pakiecie frontend/tools/eslint: typescript-eslint wymaga TypeScriptu
< 6.1 (API kompilatora w JS), a panel buduje TypeScript 7 — w jednym package.json to konflikt.
"""
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
FE = ROOT / "frontend"


def test_ci_frontend_odpala_lint_przed_testami():
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "ci-frontend.yml").read_text(encoding="utf-8"))
    runs = [s.get("run", "") for job in wf["jobs"].values() for s in job["steps"]]
    assert "npm run lint:setup" in runs and "npm run lint" in runs
    assert runs.index("npm run lint") < runs.index("npm run test")


def test_skrypty_i_konfiguracja():
    scripts = json.loads((FE / "package.json").read_text(encoding="utf-8"))["scripts"]
    assert "tools/eslint" in scripts["lint:setup"] and "npm ci" in scripts["lint:setup"]
    assert re.search(r"eslint\S* src$", scripts["lint"])
    conf = (FE / "eslint.config.js").read_text(encoding="utf-8")
    for rule in ("react-hooks/rules-of-hooks", "react-hooks/exhaustive-deps"):
        assert f"'{rule}': 'error'" in conf, rule


def test_narzedzia_lintu_przypiete_lockiem():
    pkg = json.loads((FE / "tools" / "eslint" / "package.json").read_text(encoding="utf-8"))
    deps = pkg["devDependencies"]
    assert {"eslint", "typescript-eslint", "eslint-plugin-react-hooks", "typescript"} <= deps.keys()
    assert all(re.fullmatch(r"\d+\.\d+\.\d+", v) for v in deps.values()), deps   # dokładne wersje
    major, minor = map(int, deps["typescript"].split(".")[:2])
    assert (major, minor) < (6, 1), "typescript-eslint 8 obsługuje TypeScript < 6.1"
    lock = json.loads((FE / "tools" / "eslint" / "package-lock.json").read_text(encoding="utf-8"))
    assert lock["packages"]["node_modules/typescript"]["version"] == deps["typescript"]
