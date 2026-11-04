"""Uses a fake HTTP opener, so Ollama does not need to be installed for the tests."""
import io
import json
import urllib.error

import pytest

from triage_agent.ollama import DEFAULT_MODEL, analyze_with_ollama

ANSWER = {
    "summary": "SIM lost",
    "causes": [{"category": "sim_failure", "explanation": "x", "confidence": "high", "evidence": [{"line": 1, "quote": "q"}]}],
    "bug_report": {
        "title": "t",
        "severity": "Major",
        "component": "c",
        "steps_to_reproduce": ["s"],
        "actual_result": "a",
        "expected_result": "e",
    },
}


def _opener(reply, captured=None):
    def opener(request, timeout):
        if captured is not None:
            captured.update(json.loads(request.data), url=request.full_url)
        return io.BytesIO(json.dumps(reply).encode())

    return opener


def _reply(content, **extra):
    return {"message": {"content": content}, "prompt_eval_count": 50, "eval_count": 10, **extra}


def test_request_stays_local_and_returns_analysis(monkeypatch):
    monkeypatch.delenv("TRIAGE_OLLAMA_MODEL", raising=False)
    captured = {}
    analysis, tokens_in, tokens_out, model = analyze_with_ollama(
        "DIGEST", "no service", opener=_opener(_reply(json.dumps(ANSWER)), captured)
    )
    assert captured["url"].startswith("http://localhost:")
    assert captured["model"] == DEFAULT_MODEL and captured["options"]["temperature"] == 0
    assert captured["format"]["additionalProperties"] is False
    assert "no service" in captured["messages"][1]["content"] and "DIGEST" in captured["messages"][1]["content"]
    assert (analysis.causes[0].category, tokens_in, tokens_out, model) == ("sim_failure", 50, 10, DEFAULT_MODEL)


def test_model_can_be_chosen_by_environment(monkeypatch):
    monkeypatch.setenv("TRIAGE_OLLAMA_MODEL", "other:1b")
    assert analyze_with_ollama("D", opener=_opener(_reply(json.dumps(ANSWER))))[3] == "other:1b"


def test_large_digest_gets_a_larger_context():
    small, large = {}, {}
    analyze_with_ollama("D", opener=_opener(_reply(json.dumps(ANSWER)), small))
    analyze_with_ollama("D" * 20000, opener=_opener(_reply(json.dumps(ANSWER)), large))
    assert small["options"]["num_ctx"] < large["options"]["num_ctx"]


def test_invalid_answer_raises():
    with pytest.raises(RuntimeError, match="invalid answer"):
        analyze_with_ollama("D", opener=_opener(_reply('{"summary": "only"}')))


def test_truncated_answer_raises():
    with pytest.raises(RuntimeError, match="output space"):
        analyze_with_ollama("D", opener=_opener(_reply("{", done_reason="length")))


def test_server_not_running_gives_clear_error():
    def refused(request, timeout):
        raise urllib.error.URLError("connection refused")

    with pytest.raises(RuntimeError, match="Could not reach Ollama"):
        analyze_with_ollama("D", opener=refused)


def test_missing_model_suggests_pull():
    def missing(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, io.BytesIO(b"model not found"))

    with pytest.raises(RuntimeError, match="ollama pull"):
        analyze_with_ollama("D", opener=missing)
