"""Read a log file into LogLine objects, keeping the original line numbers."""
import re
from pathlib import Path

from .models import LogLine
from .redact import redact

# `adb logcat -v threadtime`: date time pid tid level tag: message
_THREADTIME = re.compile(
    r"^(\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\s+(\d+)\s+(\d+)\s+([VDIWEFS])\s+(.+?)\s*:(?:\s(.*))?$"
)


def parse_line(number: int, raw: str) -> LogLine:
    text = redact(raw.rstrip("\r\n"))
    match = _THREADTIME.match(text)
    if not match:
        return LogLine(number=number, text=text, message=text)
    _, _, _, level, tag, message = match.groups()
    return LogLine(number=number, text=text, level=level, tag=tag, message=message or "", parsed=True)


def load_log(path: str | Path) -> list[LogLine]:
    with open(path, encoding="utf-8", errors="replace") as handle:
        return [parse_line(number, raw) for number, raw in enumerate(handle, start=1)]
