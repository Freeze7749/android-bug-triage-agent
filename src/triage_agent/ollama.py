"""Run the analysis on a local model through Ollama: no API key, no cost, and logs stay on this machine."""
import json
import os
import urllib.error
import urllib.request

import anthropic
from pydantic import ValidationError

from .llm import SYSTEM_PROMPT
from .models import Analysis

DEFAULT_MODEL = "qwen3:8b"
_URL = "http://localhost:11434/api/chat"
# Ollama silently cuts off input beyond its context size. The small size fits an 8 GB GPU; the
# large one is for digests of big logs and may spill onto the much slower CPU.
_SMALL_CONTEXT, _LARGE_CONTEXT, _SMALL_DIGEST_CHARS = 8192, 32768, 12000

# A small model needs the categories spelled out; the schema alone only lists their names.
_CATEGORY_GUIDE = """

Categories:
- java_crash: an app process dies from an uncaught Java or Kotlin exception.
- anr: an app stops responding to input or misses a system deadline.
- native_crash: a process dies from a fatal signal in native code.
- out_of_memory: a process crashes or is killed because memory ran out.
- network_registration_lost: the device loses or is refused registration on the cellular network.
- data_call_failure: mobile data cannot be set up although the device is registered.
- ims_registration_failure: IMS or VoLTE cannot register although the network is available.
- sim_failure: the SIM card is missing, unreadable or unusable.
- no_fault: nothing is wrong. An app crash is a fault even when the rest of the system is healthy.
- unknown: something is clearly wrong but no other category fits.

Only list causes the log supports, and do not list no_fault next to other causes. Routine messages
that repeat through the log are background noise, not causes."""


def analyze_with_ollama(
    digest: str, symptom: str = "", model: str | None = None, opener=urllib.request.urlopen
) -> tuple[Analysis, int, int, str]:
    """Return (analysis, input tokens, output tokens, model that answered)."""
    model = model or os.environ.get("TRIAGE_OLLAMA_MODEL", DEFAULT_MODEL)
    content = f"Reported symptom: {symptom}\n\n{digest}" if symptom else digest
    context_tokens = _SMALL_CONTEXT if len(content) <= _SMALL_DIGEST_CHARS else _LARGE_CONTEXT
    body = {
        "model": model,
        "stream": False,
        "think": False,
        "format": anthropic.transform_schema(Analysis),
        # Temperature 0 and a fixed seed keep repeated evaluation runs as close as possible.
        "options": {"temperature": 0, "seed": 42, "num_ctx": context_tokens},
        "messages": [{"role": "system", "content": SYSTEM_PROMPT + _CATEGORY_GUIDE}, {"role": "user", "content": content}],
    }
    request = urllib.request.Request(
        _URL, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"}
    )
    try:
        with opener(request, timeout=900) as response:
            reply = json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama rejected the request: {detail}. Try: ollama pull {model}") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError(f"Could not reach Ollama at {_URL}. Is it running? ({error})") from error

    if reply.get("done_reason") == "length":
        raise RuntimeError("The local model ran out of output space before finishing.")
    try:
        analysis = Analysis.model_validate_json(reply["message"]["content"])
    except (KeyError, ValidationError) as error:
        raise RuntimeError(f"The local model returned an invalid answer: {error}") from error
    return analysis, reply.get("prompt_eval_count", 0), reply.get("eval_count", 0), model
