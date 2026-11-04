import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest
from mcp import Client, StdioServerParameters

from triage_agent.cli import main as cli_main
from triage_agent.collect import collect
from triage_agent.mcp_server import server

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "eval"))
from run_eval import score, wilson_interval  # noqa: E402


def _fake_adb(calls):
    def run(command, **_):
        calls.append(command)
        if "get-state" in command:
            return subprocess.CompletedProcess(command, 0, b"device\n", b"")
        return subprocess.CompletedProcess(command, 0, b"LOG\n", b"")

    return run


def test_collect_requests_all_buffers_and_saves_output(tmp_path):
    calls = []
    path = collect(tmp_path / "x" / "d.log", serial="ABC", runner=_fake_adb(calls))
    assert path.read_bytes() == b"LOG\n"
    dump = calls[1]
    assert dump[:3] == ["adb", "-s", "ABC"] and "-d" in dump and "threadtime" in dump
    assert all(name in dump for name in ["main", "system", "crash", "radio"])


def test_collect_never_clears_device_logs(tmp_path):
    calls = []
    collect(tmp_path / "d.log", runner=_fake_adb(calls))
    assert not any("-c" in command for command in calls)


def test_collect_reports_missing_adb(tmp_path):
    def missing(*_, **__):
        raise FileNotFoundError

    with pytest.raises(RuntimeError, match="adb was not found"):
        collect(tmp_path / "d.log", runner=missing)


def test_collect_reports_no_device(tmp_path):
    def none(command, **_):
        return subprocess.CompletedProcess(command, 1, b"", b"no devices/emulators found")

    with pytest.raises(RuntimeError, match="no devices"):
        collect(tmp_path / "d.log", runner=none)


def test_cli_analyze_writes_all_outputs(sim_log, tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert cli_main(["analyze", str(sim_log), "--out", str(tmp_path), "--project", "QA"]) == 0
    assert "sim_failure" in capsys.readouterr().out
    assert json.loads((tmp_path / "jira_fields.json").read_text("utf-8"))["project"]["key"] == "QA"
    assert (tmp_path / "report.md").exists() and (tmp_path / "result.json").exists()


def test_cli_returns_error_code_for_missing_file(capsys):
    assert cli_main(["analyze", "does_not_exist.log", "--analyzer", "rules"]) == 1
    assert "Error" in capsys.readouterr().err


def test_mcp_lists_tools_and_triages_over_protocol(sim_log, monkeypatch):
    monkeypatch.setenv("TRIAGE_ALLOWED_DIR", str(ROOT))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    async def scenario():
        async with Client(server) as client:
            tools = {tool.name for tool in (await client.list_tools()).tools}
            return tools, await client.call_tool("draft_bug_report", {"log_path": str(sim_log)})

    tools, result = asyncio.run(scenario())
    assert tools == {"collect_logs", "summarize_templates", "get_log_lines", "triage_log", "draft_bug_report"}
    assert "sim_failure" in result.content[0].text


def test_mcp_refuses_file_outside_allowed_folder(sim_log, tmp_path, monkeypatch):
    monkeypatch.setenv("TRIAGE_ALLOWED_DIR", str(tmp_path))

    async def scenario():
        async with Client(server) as client:
            return await client.call_tool("get_log_lines", {"log_path": str(sim_log), "start": 1})

    result = asyncio.run(scenario())
    assert result.is_error and "outside the allowed folder" in result.content[0].text


def test_mcp_reports_missing_key_clearly(sim_log, monkeypatch):
    monkeypatch.setenv("TRIAGE_ALLOWED_DIR", str(ROOT))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    async def scenario():
        async with Client(server) as client:
            return await client.call_tool("triage_log", {"log_path": str(sim_log), "analyzer": "claude"})

    result = asyncio.run(scenario())
    assert result.is_error and "ANTHROPIC_API_KEY" in result.content[0].text


def test_mcp_server_works_as_a_real_stdio_process(sim_log):
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "triage_agent.mcp_server"], env={"TRIAGE_ALLOWED_DIR": str(ROOT)}, cwd=str(ROOT)
    )

    async def scenario():
        async with Client(params) as client:
            return await client.call_tool("get_log_lines", {"log_path": str(sim_log), "start": 1, "end": 2})

    result = asyncio.run(scenario())
    assert not result.is_error and result.content[0].text.startswith("1: ")


def _row(expected, predicted, cited=(), keys=(), total=0, rejected=0):
    return dict(
        expected=expected, predicted=predicted, cited_lines=list(cited), key_lines=list(keys),
        citations_total=total, citations_rejected=rejected, lines=10, templates=2, raw_chars=100, digest_chars=25,
    )


def test_score_on_hand_checked_example():
    rows = [
        _row("anr", "anr", cited=[5], keys=[5], total=2, rejected=1),
        _row("anr", "java_crash", cited=[1], keys=[9], total=1),
        _row("java_crash", "java_crash", cited=[3], keys=[4], total=1),
        _row("no_fault", "no_fault"),
    ]
    result = score(rows)
    assert result["accuracy"] == 0.75
    assert result["per_class"]["anr"] == {"precision": 1.0, "recall": 0.5, "f1": 0.667, "support": 2}
    assert result["per_class"]["java_crash"]["precision"] == 0.5
    assert result["citation_validity"] == 0.75
    assert result["correct_fault_cases"] == 2 and result["evidence_hit_rate"] == 0.5
    assert result["char_reduction"] == 0.75
    assert result["confusion"] == {"anr -> java_crash": 1}


def test_wilson_interval_known_value():
    low, high = wilson_interval(8, 10)
    assert round(low, 3) == 0.490 and round(high, 3) == 0.943


def _labels(split):
    return json.loads((ROOT / "eval" / "dataset" / split / "labels.json").read_text("utf-8"))


def test_test_split_only_uses_held_out_scenarios():
    dev, test = _labels("dev"), _labels("test")
    assert len(dev) == 27 and len(test) == 45
    assert not {case["scenario"] for case in dev} & {case["scenario"] for case in test}


def test_only_fault_cases_have_key_lines():
    for case in _labels("test"):
        assert bool(case["key_lines"]) == (case["category"] != "no_fault")
