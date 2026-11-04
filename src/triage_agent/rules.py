"""Keyword analyzer: works offline, and is the baseline the LLM is compared against."""
import re

from .models import Analysis, BugDraft, Category, Cause, Evidence, LogLine, Severity

# Checked in this order; the first category with a match becomes the top cause. Device-level
# causes come before their usual consequences (no SIM -> no registration -> no data -> no IMS).
_RULES: list[tuple[Category, re.Pattern]] = [
    ("out_of_memory", re.compile(r"OutOfMemoryError|lowmemorykiller\s*: Kill")),
    ("native_crash", re.compile(r"Fatal signal \d+")),
    ("java_crash", re.compile(r"FATAL EXCEPTION")),
    ("anr", re.compile(r"ANR in ")),
    ("sim_failure", re.compile(r"CARDSTATE_ABSENT|cardState=ABSENT|CARDSTATE_ERROR")),
    ("network_registration_lost", re.compile(r"OUT_OF_SERVICE|rejectCause=[1-9]")),
    ("data_call_failure", re.compile(r"SETUP_DATA_CALL error|onSetupResponse.*cause=(?!NONE)")),
    ("ims_registration_failure", re.compile(r"SIP/2\.0 4\d\d|onImsDisconnected")),
]

_DRAFTS: dict[Category, tuple[str, Severity, str, str]] = {
    "out_of_memory": ("Process killed or crashed from low memory", "Critical", "Memory", "The process keeps running."),
    "native_crash": ("Native crash (fatal signal)", "Critical", "Native", "The process keeps running."),
    "java_crash": ("App crash (uncaught Java exception)", "Critical", "Application", "The app keeps running."),
    "anr": ("Application Not Responding", "Major", "Application", "The app responds to input."),
    "sim_failure": ("SIM card absent or in error state", "Critical", "Telephony/SIM", "The SIM is detected and ready."),
    "network_registration_lost": ("Network registration lost", "Critical", "Telephony/Registration", "The device stays in service."),
    "data_call_failure": ("Mobile data call setup failed", "Major", "Telephony/Data", "The data call is established."),
    "ims_registration_failure": ("IMS registration failed", "Major", "Telephony/IMS", "IMS registers and VoLTE is available."),
}
_MAX_EVIDENCE = 5


def analyze_with_rules(lines: list[LogLine]) -> Analysis:
    causes = []
    for category, pattern in _RULES:
        matched = [line for line in lines if pattern.search(line.text)]
        if matched:
            evidence = [Evidence(line=line.number, quote=line.text) for line in matched[:_MAX_EVIDENCE]]
            causes.append(
                Cause(
                    category=category,
                    explanation=f"{len(matched)} line(s) match the rule for {category}.",
                    confidence="low",
                    evidence=evidence,
                )
            )
    if not causes:
        return Analysis(
            summary="No keyword rule matched.",
            causes=[Cause(category="no_fault", explanation="No rule matched.", confidence="low", evidence=[])],
            bug_report=BugDraft(
                title="No fault found by keyword rules",
                severity="Minor",
                component="Unknown",
                steps_to_reproduce=["Not known: no fault was identified."],
                actual_result="No known fault signature in the log.",
                expected_result="Not applicable.",
            ),
        )
    top = causes[0]
    title, severity, component, expected = _DRAFTS[top.category]
    return Analysis(
        summary=f"Keyword rules matched: {', '.join(cause.category for cause in causes)}.",
        causes=causes,
        bug_report=BugDraft(
            title=title,
            severity=severity,
            component=component,
            steps_to_reproduce=["Not known from the log: add the steps used during the test."],
            actual_result=top.evidence[0].quote,
            expected_result=expected,
        ),
    )
