"""MCP server exposing the pipeline to clients such as Claude Code (stdio transport)."""
import functools
import os
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .collect import collect
from .parse import load_log
from .pipeline import triage
from .report import to_jira_fields, to_markdown
from .templates import build_digest, mine_templates

server = MCPServer("android-bug-triage")


def _allowed_path(path: str) -> Path:
    """Only files under TRIAGE_ALLOWED_DIR (default: current folder) can be read or written."""
    root = Path(os.environ.get("TRIAGE_ALLOWED_DIR", os.getcwd())).resolve()
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(root):
        raise ToolError(f"{path} is outside the allowed folder {root}")
    return resolved


def _clear_errors(tool):
    """Send expected failures (no adb, no key, missing file) to the client as readable messages."""

    @functools.wraps(tool)
    def wrapper(*args, **kwargs):
        try:
            return tool(*args, **kwargs)
        except (RuntimeError, OSError, ValueError) as error:
            raise ToolError(str(error)) from error

    return wrapper


@server.tool()
@_clear_errors
def collect_logs(out_file: str = "out/device.log", serial: str | None = None) -> str:
    """Dump logcat and radio buffers from a connected device into a file and return its path."""
    return str(collect(_allowed_path(out_file), serial))


@server.tool()
@_clear_errors
def summarize_templates(log_path: str, top: int = 30) -> str:
    """Compress a log file into Drain templates, most severe and rarest first."""
    lines = load_log(_allowed_path(log_path))
    return build_digest(lines, mine_templates(lines), max_templates=top)


@server.tool()
@_clear_errors
def get_log_lines(log_path: str, start: int, end: int | None = None) -> str:
    """Return original lines (identifiers masked) by 1-based number, to check a citation."""
    lines = load_log(_allowed_path(log_path))[max(start - 1, 0) : end or start]
    return "\n".join(f"{line.number}: {line.text}" for line in lines)


@server.tool()
@_clear_errors
def triage_log(log_path: str, analyzer: str = "auto", symptom: str = "") -> dict:
    """Find possible causes, each with verified log line citations. Uses rules if no API key is set."""
    return triage(_allowed_path(log_path), analyzer, symptom).model_dump()


@server.tool()
@_clear_errors
def draft_bug_report(log_path: str, analyzer: str = "auto", symptom: str = "", project_key: str = "PROJ") -> dict:
    """Return a Markdown bug report and Jira fields for review. Nothing is sent to Jira."""
    result = triage(_allowed_path(log_path), analyzer, symptom)
    return {"markdown": to_markdown(result), "jira_fields": to_jira_fields(result, project_key)}


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
