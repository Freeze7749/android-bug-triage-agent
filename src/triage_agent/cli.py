"""Command line: triage collect | templates | analyze | lines"""
import argparse
import json
import sys
from pathlib import Path

from .collect import collect
from .parse import load_log
from .pipeline import triage
from .report import to_jira_fields, to_markdown
from .templates import build_digest, mine_templates


def _cmd_collect(args) -> None:
    print(f"Saved {collect(args.out, args.serial)}")


def _cmd_templates(args) -> None:
    lines = load_log(args.log)
    print(build_digest(lines, mine_templates(lines), max_templates=args.top))


def _cmd_analyze(args) -> None:
    result = triage(args.log, analyzer=args.analyzer, symptom=args.symptom)
    markdown = to_markdown(result)
    print(markdown)
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.md").write_text(markdown, encoding="utf-8")
        (out / "jira_fields.json").write_text(
            json.dumps(to_jira_fields(result, args.project), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (out / "result.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
        print(f"Saved report.md, jira_fields.json and result.json in {out}")


def _cmd_lines(args) -> None:
    for line in load_log(args.log)[max(args.start - 1, 0) : args.end or args.start]:
        print(f"{line.number}: {line.text}")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="triage", description="Android log triage")
    commands = parser.add_subparsers(dest="command", required=True)

    command = commands.add_parser("collect", help="dump logs from a device with adb")
    command.add_argument("--out", default="out/device.log")
    command.add_argument("--serial")
    command.set_defaults(run=_cmd_collect)

    command = commands.add_parser("templates", help="show the template digest")
    command.add_argument("log")
    command.add_argument("--top", type=int, default=30)
    command.set_defaults(run=_cmd_templates)

    command = commands.add_parser("analyze", help="find causes and draft a bug report")
    command.add_argument("log")
    command.add_argument("--analyzer", choices=["auto", "rules", "claude"], default="auto")
    command.add_argument("--symptom", default="", help="what the tester saw")
    command.add_argument("--out", help="folder for report.md, jira_fields.json, result.json")
    command.add_argument("--project", default="PROJ", help="Jira project key")
    command.set_defaults(run=_cmd_analyze)

    command = commands.add_parser("lines", help="print original lines (redacted)")
    command.add_argument("log")
    command.add_argument("start", type=int)
    command.add_argument("end", type=int, nargs="?")
    command.set_defaults(run=_cmd_lines)

    args = parser.parse_args(argv)
    try:
        args.run(args)
    except (RuntimeError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
