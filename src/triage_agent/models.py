"""Data shapes shared by the whole pipeline."""
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict

Category = Literal[
    "java_crash",
    "anr",
    "native_crash",
    "out_of_memory",
    "network_registration_lost",
    "data_call_failure",
    "ims_registration_failure",
    "sim_failure",
    "no_fault",
    "unknown",
]
Severity = Literal["Blocker", "Critical", "Major", "Minor"]
Confidence = Literal["high", "medium", "low"]


@dataclass
class LogLine:
    """One line of the input file. `text` is already redacted."""

    number: int  # 1-based line number in the original file
    text: str
    level: str = ""
    tag: str = ""
    message: str = ""
    parsed: bool = False


@dataclass
class Template:
    """A group of lines that share the same shape, as found by Drain."""

    id: int
    pattern: str
    line_numbers: list[int]
    level: str
    tag: str


class Evidence(BaseModel):
    """A pointer to one original log line, plus the text claimed to be on it."""

    model_config = ConfigDict(extra="forbid")
    line: int
    quote: str


class Cause(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Category
    explanation: str
    confidence: Confidence
    evidence: list[Evidence]


class BugDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    severity: Severity
    component: str
    steps_to_reproduce: list[str]
    actual_result: str
    expected_result: str


class Analysis(BaseModel):
    """What an analyzer returns. The citations here are not yet trusted."""

    model_config = ConfigDict(extra="forbid")
    summary: str
    causes: list[Cause]
    bug_report: BugDraft


class TriageResult(BaseModel):
    """Final result. Every citation in `causes` has passed the check in citations.py."""

    source: str
    analyzer: str
    predicted_category: Category
    summary: str
    causes: list[Cause]
    rejected_citations: list[Evidence]
    citations_total: int
    bug_report: BugDraft
    total_lines: int
    parsed_lines: int
    template_count: int
    raw_chars: int
    digest_chars: int
    input_tokens: int = 0
    output_tokens: int = 0
