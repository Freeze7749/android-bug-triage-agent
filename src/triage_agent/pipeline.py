"""The whole flow in one place: load -> templates -> analyze -> verify citations."""
import os
from pathlib import Path

from .citations import verify
from .llm import analyze_with_claude
from .models import TriageResult
from .parse import load_log
from .rules import analyze_with_rules
from .templates import build_digest, mine_templates


def choose_analyzer(requested: str = "auto") -> str:
    if requested == "auto":
        return "claude" if os.environ.get("ANTHROPIC_API_KEY") else "rules"
    if requested not in ("rules", "claude"):
        raise ValueError(f"Unknown analyzer: {requested}")
    return requested


def triage(path: str | Path, analyzer: str = "auto", symptom: str = "", client=None) -> TriageResult:
    lines = load_log(path)
    templates = mine_templates(lines)
    digest = build_digest(lines, templates)

    name = choose_analyzer(analyzer)
    input_tokens = output_tokens = 0
    if name == "claude":
        analysis, input_tokens, output_tokens = analyze_with_claude(digest, symptom, client)
    else:
        analysis = analyze_with_rules(lines)

    causes, rejected, total, predicted = verify(analysis, lines)
    return TriageResult(
        source=str(path),
        analyzer=name,
        predicted_category=predicted,
        summary=analysis.summary,
        causes=causes,
        rejected_citations=rejected,
        citations_total=total,
        bug_report=analysis.bug_report,
        total_lines=len(lines),
        parsed_lines=sum(line.parsed for line in lines),
        template_count=len(templates),
        raw_chars=sum(len(line.text) for line in lines),
        digest_chars=len(digest),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
