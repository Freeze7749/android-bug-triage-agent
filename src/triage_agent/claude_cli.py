"""Run the same analysis through the Claude Code CLI, using the user's subscription instead of an API key.

The CLI runs in an empty temporary folder with no tools, settings or MCP servers, so it sees only
the digest and cannot read the repository, which holds the evaluation labels.
"""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import anthropic
from pydantic import ValidationError

from .llm import DEFAULT_MODEL, SYSTEM_PROMPT
from .models import Analysis

_API_CREDENTIALS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")


def _executable() -> str:
    path = shutil.which("claude")
    if path is None:
        raise RuntimeError("The claude command was not found. Install Claude Code and log in.")
    # npm's .cmd launcher passes arguments through cmd.exe, which breaks the JSON schema's quotes.
    if path.lower().endswith(".cmd"):
        native = Path(path).parent / "node_modules/@anthropic-ai/claude-code/bin/claude.exe"
        if native.exists():
            return str(native)
    return path


def build_command(executable: str, model: str) -> list[str]:
    return [
        executable,
        "-p",
        "--model", model,
        "--effort", "high",
        "--output-format", "json",
        "--json-schema", json.dumps(anthropic.transform_schema(Analysis)),
        "--system-prompt", SYSTEM_PROMPT,
        "--tools", "",
        "--setting-sources", "",
        "--strict-mcp-config",
        "--disable-slash-commands",
        "--no-session-persistence",
    ]


def analyze_with_claude_cli(
    digest: str, symptom: str = "", runner=subprocess.run, model: str = DEFAULT_MODEL
) -> tuple[Analysis, int, int, str]:
    """Return (analysis, input tokens, output tokens, model that answered)."""
    content = f"Reported symptom: {symptom}\n\n{digest}" if symptom else digest
    # An API key in the environment would take priority over the subscription login.
    env = {name: value for name, value in os.environ.items() if name not in _API_CREDENTIALS}
    with tempfile.TemporaryDirectory() as empty_folder:
        try:
            done = runner(
                build_command(_executable(), model),
                input=content, capture_output=True, text=True, encoding="utf-8",
                timeout=600, env=env, cwd=empty_folder,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("Claude Code did not answer within 10 minutes.") from error

    try:
        output = json.loads(done.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Claude Code failed: {done.stderr.strip() or done.stdout.strip()[:300]}") from error
    if done.returncode != 0 or output.get("is_error"):
        raise RuntimeError(f"Claude Code failed: {str(output.get('result'))[:300]}")
    if "structured_output" not in output:
        raise RuntimeError("Claude Code returned no structured output.")
    try:
        analysis = Analysis.model_validate(output["structured_output"])
    except ValidationError as error:
        raise RuntimeError(f"Claude Code output does not match the schema: {error}") from error

    usage = output.get("usage", {})
    models = ",".join(sorted(output.get("modelUsage", {}))) or model
    # Most input is reported as cache activity, so count all three kinds.
    input_tokens = sum(usage.get(kind, 0) for kind in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    return analysis, input_tokens, usage.get("output_tokens", 0), models
