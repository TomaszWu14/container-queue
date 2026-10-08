"""AI-004: każde wywołanie lokalnego LLM zostawia metrykę bez treści (model, czas, wynik,
rozmiar, tokeny) w dzienniku serwera (applog → job_runs, panel Logi → Zadania); ewaluacja
ekstrakcji faktur offline na przypadkach wzorcowych (bez sieci)."""
import json

import httpx
import pytest

from app import applog, llm
from app.config import settings
from scripts import eval_extraction

PROMPT = "Tajna treść pytania o kontener MSKU1234565"
ANSWER = "Kontener jest w porcie."


class _Resp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "http://ollama:11434/api/chat")
            raise httpx.HTTPStatusError("błąd", request=request,
                                        response=httpx.Response(self.status_code, request=request))

    def json(self):
        return self._body


@pytest.fixture()
def ollama(monkeypatch):
    applog.reset_for_tests()
    monkeypatch.setattr(settings, "ollama_url", "http://ollama:11434")
    box = {"resp": _Resp(body={"message": {"content": ANSWER}, "prompt_eval_count": 120,
                                "eval_count": 7})}

    def post(url, json, timeout):
        if isinstance(box["resp"], Exception):
            raise box["resp"]
        return box["resp"]

    monkeypatch.setattr(llm.httpx, "post", post)
    yield box
    applog.reset_for_tests()


def _llm_runs():
    return [j for j in applog._jobs if j["job"] == "llm"]


def test_successful_call_recorded_without_content(ollama):
    assert llm.chat("qwen2.5:1.5b", PROMPT, purpose="assistant") == ANSWER
    [run] = _llm_runs()
    assert run["fn"] == "assistant:qwen2.5:1.5b" and run["ok"] is True
    assert run["duration_ms"] >= 0
    assert "tokeny: we 120, wy 7" in run["detail"]
    assert f"prompt {len(PROMPT)} zn." in run["detail"] and f"odp. {len(ANSWER)} zn." in run["detail"]
    assert "MSKU1234565" not in run["detail"] and "porcie" not in run["detail"]


def test_http_error_recorded_as_failure_and_raised(ollama):
    ollama["resp"] = _Resp(status=500)
    with pytest.raises(httpx.HTTPStatusError):
        llm.chat("qwen2.5vl:3b", PROMPT, images=["b64"], purpose="ocr_vision")
    [run] = _llm_runs()
    assert run["fn"] == "ocr_vision:qwen2.5vl:3b" and run["ok"] is False
    assert "HTTPStatusError" in run["detail"] and "HTTP 500" in run["detail"]
    assert "obrazy 1" in run["detail"] and "MSKU" not in run["detail"]


def test_timeout_recorded_and_slot_released(ollama):
    ollama["resp"] = httpx.ReadTimeout("za długo")
    with pytest.raises(httpx.ReadTimeout):
        llm.chat("qwen2.5:1.5b", PROMPT)
    assert _llm_runs()[0]["ok"] is False and _llm_runs()[0]["fn"] == "chat:qwen2.5:1.5b"
    ollama["resp"] = _Resp(body={"message": {"content": "ok"}})
    assert llm.chat("qwen2.5:1.5b", "x", wait=0) == "ok"     # slot zwolniony mimo wyjątku


def test_busy_rejection_is_not_a_model_call(ollama, monkeypatch):
    monkeypatch.setattr(llm, "_slots", llm.threading.BoundedSemaphore(1))
    llm._slots.acquire()
    try:
        with pytest.raises(llm.LLMBusy):
            llm.chat("qwen2.5:1.5b", PROMPT, wait=0)
    finally:
        llm._slots.release()
    assert _llm_runs() == []


def test_eval_extraction_reference_cases_all_correct():
    report = eval_extraction.evaluate(eval_extraction.DEFAULT_CASES)
    assert report["cases"] >= 5
    assert report["items_expected"] >= 10
    assert report["accuracy_pct"] == 100.0, report["failures"]


def test_eval_extraction_scores_wrong_expectation(tmp_path):
    case = json.loads(next(eval_extraction.DEFAULT_CASES.glob("*.json")).read_text("utf-8"))
    case["expected"]["items"][0]["qty"] = "999999"
    case["expected"]["invoice_number"] = "ZLY-NUMER"
    (tmp_path / "zly.json").write_text(json.dumps(case), encoding="utf-8")
    report = eval_extraction.evaluate(tmp_path)
    assert report["accuracy_pct"] < 100.0 and report["invoice_numbers_ok"] == 0
    assert any("999999" in f for f in report["failures"])
