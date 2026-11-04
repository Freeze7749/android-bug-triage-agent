"""Check every citation against the real log, so an invented line cannot reach a report."""
from .models import Analysis, Category, Cause, Evidence, LogLine


def _normalize(text: str) -> str:
    return " ".join(text.split())


def is_valid(evidence: Evidence, by_number: dict[int, LogLine]) -> bool:
    line = by_number.get(evidence.line)
    quote = _normalize(evidence.quote)
    return line is not None and bool(quote) and quote in _normalize(line.text)


def verify(analysis: Analysis, lines: list[LogLine]) -> tuple[list[Cause], list[Evidence], int, Category]:
    """Return (kept causes, rejected citations, total citations, predicted category).

    A fault cause left with no valid citation is dropped. A `no_fault` verdict may cite
    nothing, because there is no faulty line to point at.
    """
    by_number = {line.number: line for line in lines}
    kept, rejected, total = [], [], 0
    for cause in analysis.causes:
        valid = []
        for evidence in cause.evidence:
            total += 1
            (valid if is_valid(evidence, by_number) else rejected).append(evidence)
        if valid or cause.category in ("no_fault", "unknown"):
            kept.append(cause.model_copy(update={"evidence": valid}))
    return kept, rejected, total, kept[0].category if kept else "unknown"
