"""Mask personal identifiers before a log line is stored, shown or sent anywhere."""
import re

# Order matters: more specific patterns run first.
_RULES = [
    (re.compile(r"\bsips?:[^\s;,>]+", re.I), "<SIP_URI>"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "<EMAIL>"),
    (re.compile(r"\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b", re.I), "<MAC>"),
    (re.compile(r"\b(?:[0-9a-f]{1,4}:){4,7}[0-9a-f]{1,4}\b", re.I), "<IPV6>"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "<IPV4>"),
    (re.compile(r"\+\d{8,15}\b"), "<PHONE>"),
    # IMEI and IMSI have 15 digits, ICCID 19-20. Epoch-millisecond times have 13 and survive.
    (re.compile(r"\b\d{14,20}\b"), "<LONG_ID>"),
]


def redact(text: str) -> str:
    for pattern, replacement in _RULES:
        text = pattern.sub(replacement, text)
    return text
