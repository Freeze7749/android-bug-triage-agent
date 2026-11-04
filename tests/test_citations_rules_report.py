from triage_agent.citations import verify
from triage_agent.models import Analysis, BugDraft, Cause, Evidence, LogLine
from triage_agent.parse import load_log, parse_line
from triage_agent.pipeline import triage
from triage_agent.report import to_jira_fields, to_markdown
from triage_agent.rules import analyze_with_rules

BUG = BugDraft(title="t", severity="Major", component="c", steps_to_reproduce=["s"], actual_result="a", expected_result="e")
LINES = [LogLine(number=1, text="10-15 10:00:00.000 E Tag: card removed", parsed=True)]


def _analysis(*causes):
    return Analysis(summary="s", causes=list(causes), bug_report=BUG)


def _cause(category, *evidence):
    return Cause(category=category, explanation="x", confidence="high", evidence=list(evidence))


def test_real_citation_is_kept():
    kept, rejected, total, top = verify(_analysis(_cause("sim_failure", Evidence(line=1, quote="card  removed"))), LINES)
    assert (len(kept), rejected, total, top) == (1, [], 1, "sim_failure")


def test_invented_line_number_is_rejected():
    kept, rejected, _, top = verify(_analysis(_cause("sim_failure", Evidence(line=99, quote="card removed"))), LINES)
    assert kept == [] and len(rejected) == 1 and top == "unknown"


def test_quote_not_on_that_line_is_rejected():
    _, rejected, _, _ = verify(_analysis(_cause("sim_failure", Evidence(line=1, quote="modem crashed"))), LINES)
    assert len(rejected) == 1


def test_empty_quote_is_rejected():
    _, rejected, _, _ = verify(_analysis(_cause("sim_failure", Evidence(line=1, quote="  "))), LINES)
    assert len(rejected) == 1


def test_next_supported_cause_becomes_top_when_first_has_no_valid_citation():
    analysis = _analysis(_cause("anr", Evidence(line=50, quote="x")), _cause("sim_failure", Evidence(line=1, quote="card")))
    assert verify(analysis, LINES)[3] == "sim_failure"


def test_no_fault_needs_no_citation():
    assert verify(_analysis(_cause("no_fault")), LINES)[3] == "no_fault"


def test_rules_pick_root_cause_before_consequences():
    lines = [
        parse_line(1, "10-15 10:00:00.000 1 2 D UiccController: handleSimStatus: cardState=ABSENT slot=0"),
        parse_line(2, "10-15 10:00:01.000 1 2 D SST: mVoiceRegState=1(OUT_OF_SERVICE)"),
    ]
    assert [c.category for c in analyze_with_rules(lines).causes] == ["sim_failure", "network_registration_lost"]


def test_rules_report_no_fault_on_clean_log():
    lines = [parse_line(1, "10-15 10:00:00.000 1 2 I Tag: all good")]
    assert analyze_with_rules(lines).causes[0].category == "no_fault"


def test_full_flow_on_sample_without_key(sim_log, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = triage(sim_log)
    assert result.analyzer == "rules" and result.predicted_category == "sim_failure"
    by_number = {line.number: line.text for line in load_log(sim_log)}
    for cause in result.causes:
        assert cause.evidence
        for evidence in cause.evidence:
            assert evidence.quote in by_number[evidence.line]


def test_report_links_each_citation_to_its_line(sim_log):
    result = triage(sim_log, analyzer="rules")
    markdown = to_markdown(result)
    for cause in result.causes:
        for evidence in cause.evidence:
            assert f"#L{evidence.line})" in markdown


def test_jira_fields_have_required_shape(sim_log):
    result = triage(sim_log, analyzer="rules")
    fields = to_jira_fields(result, "QA")
    assert fields["project"] == {"key": "QA"} and fields["issuetype"] == {"name": "Bug"}
    assert fields["priority"] == {"name": "High"}
    assert f"demo_sim_failure.log:{result.causes[0].evidence[0].line}" in fields["description"]
