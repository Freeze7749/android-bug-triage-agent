"""Runs the real Anthropic SDK against a fake network, so no key and no cost are involved."""
import json

import anthropic
import httpx2 as httpx
import pytest

from triage_agent.llm import DEFAULT_MODEL, analyze_with_claude
from triage_agent.parse import load_log
from triage_agent.pipeline import triage


def _client(answer: dict, stop_reason="end_turn", captured=None):
    def respond(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured["headers"] = request.headers
            captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": DEFAULT_MODEL,
                "content": [{"type": "text", "text": json.dumps(answer)}],
                "stop_reason": stop_reason,
                "stop_sequence": None,
                "usage": {"input_tokens": 100, "output_tokens": 20},
            },
        )

    return anthropic.Anthropic(api_key="test", http_client=httpx.Client(transport=httpx.MockTransport(respond)))


def _answer(line, quote):
    return {
        "summary": "SIM lost",
        "causes": [
            {"category": "sim_failure", "explanation": "x", "confidence": "high", "evidence": [{"line": line, "quote": quote}]}
        ],
        "bug_report": {
            "title": "SIM lost",
            "severity": "Critical",
            "component": "SIM",
            "steps_to_reproduce": ["Not shown in log"],
            "actual_result": "a",
            "expected_result": "e",
        },
    }


def test_request_uses_expected_model_schema_and_fallback():
    captured = {}
    analysis, tokens_in, tokens_out = analyze_with_claude("DIGEST", "no service", _client(_answer(1, "q"), captured=captured))
    body = captured["body"]
    assert body["model"] == "claude-opus-5-5" and body["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in captured["headers"]["anthropic-beta"]
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["output_config"]["format"]["schema"]["additionalProperties"] is False
    assert "no service" in body["messages"][0]["content"] and "DIGEST" in body["messages"][0]["content"]
    assert (analysis.causes[0].category, tokens_in, tokens_out) == ("sim_failure", 100, 20)


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_incomplete_answer_raises(stop_reason):
    with pytest.raises(RuntimeError, match=stop_reason):
        analyze_with_claude("D", client=_client(_answer(1, "q"), stop_reason=stop_reason))


def test_api_error_becomes_clear_runtime_error():
    def respond(request):
        return httpx.Response(401, json={"type": "error", "error": {"type": "authentication_error", "message": "bad key"}})

    client = anthropic.Anthropic(api_key="test", http_client=httpx.Client(transport=httpx.MockTransport(respond)))
    with pytest.raises(RuntimeError, match="Claude API call failed"):
        analyze_with_claude("D", client=client)


def test_answer_outside_schema_raises():
    with pytest.raises(RuntimeError, match="schema"):
        analyze_with_claude("D", client=_client({"summary": "only this"}))


def test_missing_key_gives_clear_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        analyze_with_claude("D")


def test_invented_citation_does_not_reach_the_result(sim_log):
    result = triage(sim_log, analyzer="claude", client=_client(_answer(999999, "made up")))
    assert result.causes == [] and result.predicted_category == "unknown"
    assert result.citations_total == 1 and len(result.rejected_citations) == 1


def test_real_citation_survives_end_to_end(sim_log):
    line = next(l for l in load_log(sim_log) if "cardState=ABSENT" in l.text)
    result = triage(sim_log, analyzer="claude", client=_client(_answer(line.number, "cardState=ABSENT")))
    assert result.predicted_category == "sim_failure" and result.rejected_citations == []
    assert (result.input_tokens, result.output_tokens) == (100, 20)
