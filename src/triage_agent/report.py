"""Render a TriageResult as a Markdown report and as Jira issue fields."""
from pathlib import Path

from .models import TriageResult

_JIRA_PRIORITY = {"Blocker": "Highest", "Critical": "High", "Major": "Medium", "Minor": "Low"}


def _link(result: TriageResult, line: int) -> str:
    """A Markdown link to the original line; editors and GitHub understand #L<number>."""
    return f"[{Path(result.source).name}:{line}]({Path(result.source).as_posix()}#L{line})"


def _wrong_citation_warning(result: TriageResult) -> str:
    count = len(result.rejected_citations)
    return f"{count} of {result.citations_total} citations failed verification and were removed." if count else ""


def to_markdown(result: TriageResult) -> str:
    bug = result.bug_report
    rows = [
        f"# {bug.title}",
        "",
        f"**Draft, needs human review.** Analyzer: `{result.analyzer}`. "
        f"Top category: `{result.predicted_category}`. Severity: {bug.severity}. Component: {bug.component}.",
        "",
        f"Source: `{result.source}` ({result.total_lines} lines, {result.template_count} templates)",
        "",
        "## Summary",
        result.summary,
        "",
        "## Steps to reproduce",
        *[f"{index}. {step}" for index, step in enumerate(bug.steps_to_reproduce, start=1)],
        "",
        "## Actual result",
        bug.actual_result,
        "",
        "## Expected result",
        bug.expected_result,
        "",
        "## Possible causes",
    ]
    for index, cause in enumerate(result.causes, start=1):
        rows += ["", f"### {index}. `{cause.category}` ({cause.confidence} confidence)", cause.explanation, ""]
        rows += [f"- {_link(result, ev.line)}: `{ev.quote}`" for ev in cause.evidence]
    warning = _wrong_citation_warning(result)
    if warning:
        rows += ["", f"> Warning: {warning}"]
    return "\n".join(rows) + "\n"


def to_jira_fields(result: TriageResult, project_key: str = "PROJ") -> dict:
    """The `fields` object of Jira's create-issue request, in Jira wiki markup."""
    bug = result.bug_report
    parts = [
        f"h3. Summary\n{result.summary}",
        "h3. Steps to reproduce\n" + "\n".join(f"# {step}" for step in bug.steps_to_reproduce),
        f"h3. Actual result\n{bug.actual_result}",
        f"h3. Expected result\n{bug.expected_result}",
        "h3. Log evidence",
    ]
    for cause in result.causes:
        parts.append(f"*{cause.category}* ({cause.confidence}): {cause.explanation}")
        parts += [f"* {Path(result.source).name}:{ev.line} {{{{{ev.quote}}}}}" for ev in cause.evidence]
    return {
        "project": {"key": project_key},
        "issuetype": {"name": "Bug"},
        "summary": bug.title,
        "priority": {"name": _JIRA_PRIORITY[bug.severity]},
        "components": [{"name": bug.component}],
        "labels": ["auto-triage", result.predicted_category],
        "description": "\n".join(parts),
    }
