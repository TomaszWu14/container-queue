"""Strażnik wyścigu draft→ready (PR #796).

PR otwarty jako draft i po chwili oznaczony „ready for review” daje dwa biegi workflowu.
Gdy bieg z eventu draftu powstał później, `cancel-in-progress` w grupie per-ref anulował
bieg „ready”, a sam się pomijał (`if: !draft`) — wymagany check zostawał tylko
cancelled/skipped i automerge (bierze najnowszy bieg checku po nazwie) blokował PR na zawsze.

Reguła dla każdego joba pomijanego na draftach:
- grupa `concurrency` zawiera stan draftu — bieg draftu nie anuluje biegu „ready”,
- nazwa checku zależy od draftu — pominięty bieg draftu ma inną nazwę niż bieg „ready”,
  więc nie przesłoni jego wyniku (niezależnie od kolejności `started_at`).
"""
import re

from tests.test_workflows_ci import _workflows

DRAFT_IF = "!github.event.pull_request.draft"
DRAFT_NAME = re.compile(
    r"\$\{\{ github\.event\.pull_request\.draft && '([^']+)' \|\| '([^']+)' \}\}")


def _gated():
    for fname, wf in _workflows().items():
        for job, spec in wf["jobs"].items():
            if DRAFT_IF in str(spec.get("if", "")):
                yield fname, wf, job, spec


def test_some_jobs_are_gated_on_draft():
    assert {f for f, *_ in _gated()} >= {"security.yml", "ci-backend.yml", "ci-frontend.yml"}


def test_draft_runs_do_not_cancel_ready_runs():
    bad = sorted({f for f, wf, _, _ in _gated()
                  if (wf.get("concurrency") or {}).get("cancel-in-progress")
                  and "github.event.pull_request.draft" not in wf["concurrency"]["group"]})
    assert not bad, f"grupa concurrency bez stanu draftu (draft anuluje bieg ready): {bad}"


def test_skipped_draft_check_has_its_own_name():
    bad = []
    for fname, _, job, spec in _gated():
        m = DRAFT_NAME.fullmatch(str(spec.get("name", "")))
        if not m or m.group(1) == m.group(2):
            bad.append(f"{fname}:{job}")
    assert not bad, ("job pomijany na draftach musi mieć `name: ${{ github.event.pull_request.draft"
                     f" && '<nazwa> (draft — pominięty)' || '<nazwa>' }}}}`: {bad}")
