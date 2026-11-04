"""Score an analyzer on a labelled split and save the numbers.

    python eval/run_eval.py --analyzer rules --split test
    python eval/run_eval.py --analyzer claude --split test
    python eval/run_eval.py --analyzer claude-cli --split test
    python eval/run_eval.py --analyzer ollama --split test
"""
import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from triage_agent.llm import DEFAULT_MODEL
from triage_agent.pipeline import triage

HERE = Path(__file__).parent
MAX_FAILURES_IN_A_ROW = 3
PRICE_PER_MILLION = {"claude-opus-5-5": (4.0, 20.0)}  # input, output in USD


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """95% confidence interval for a proportion. Small test sets deserve wide error bars."""
    if total == 0:
        return (0.0, 0.0)
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def score(rows: list[dict]) -> dict:
    """Compute metrics from per-case rows, keeping the calculation easy to check by hand."""
    total = len(rows)
    correct = sum(row["predicted"] == row["expected"] for row in rows)

    per_class = {}
    for category in sorted({row["expected"] for row in rows}):
        tp = sum(row["expected"] == category and row["predicted"] == category for row in rows)
        fp = sum(row["expected"] != category and row["predicted"] == category for row in rows)
        fn = sum(row["expected"] == category and row["predicted"] != category for row in rows)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[category] = {"precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3), "support": tp + fn}

    # Of fault cases predicted correctly, how many cite at least one line that is truly the fault?
    correct_faults = [row for row in rows if row["predicted"] == row["expected"] != "no_fault"]
    evidence_hits = sum(bool(set(row["cited_lines"]) & set(row["key_lines"])) for row in correct_faults)
    citations = sum(row["citations_total"] for row in rows)
    rejected = sum(row["citations_rejected"] for row in rows)
    lines = sum(row["lines"] for row in rows)
    templates = sum(row["templates"] for row in rows)
    raw_chars = sum(row["raw_chars"] for row in rows)
    digest_chars = sum(row["digest_chars"] for row in rows)
    low, high = wilson_interval(correct, total)

    return {
        "cases": total,
        "correct": correct,
        "accuracy": round(correct / total, 3) if total else 0.0,
        "accuracy_95ci": [round(low, 3), round(high, 3)],
        "macro_f1": round(sum(c["f1"] for c in per_class.values()) / len(per_class), 3) if per_class else 0.0,
        "per_class": per_class,
        "confusion": dict(Counter(f"{row['expected']} -> {row['predicted']}" for row in rows if row["expected"] != row["predicted"])),
        "citations_total": citations,
        "citations_rejected": rejected,
        "citation_validity": round((citations - rejected) / citations, 3) if citations else None,
        "correct_fault_cases": len(correct_faults),
        "evidence_hit_rate": round(evidence_hits / len(correct_faults), 3) if correct_faults else None,
        "avg_lines_per_log": round(lines / total, 1) if total else 0,
        "avg_templates_per_log": round(templates / total, 1) if total else 0,
        "char_reduction": round(1 - digest_chars / raw_chars, 3) if raw_chars else 0.0,
        "errors": sum(row["predicted"] == "error" for row in rows),
    }


def run(analyzer: str, split: str, limit: int | None = None) -> dict:
    folder = HERE / "dataset" / split
    labels = json.loads((folder / "labels.json").read_text(encoding="utf-8"))
    if limit:
        labels = labels[:limit]

    # Finished cases are saved as we go, so a usage limit or crash does not lose or repeat paid work.
    checkpoint = HERE / "results" / f"{analyzer}_{split}.partial.jsonl"
    checkpoint.parent.mkdir(exist_ok=True)
    done = {}
    if checkpoint.exists() and not limit:
        rows_saved = [json.loads(line) for line in checkpoint.read_text(encoding="utf-8").splitlines()]
        done = {row["file"]: row for row in rows_saved}

    rows, failures_in_a_row = [], 0
    for label in labels:
        if label["file"] in done:
            rows.append(done[label["file"]])
            continue
        row = {"file": label["file"], "expected": label["category"], "key_lines": label["key_lines"]}
        try:
            result = triage(folder / label["file"], analyzer=analyzer)
            row.update(
                predicted=result.predicted_category,
                cited_lines=[ev.line for cause in result.causes for ev in cause.evidence],
                citations_total=result.citations_total,
                citations_rejected=len(result.rejected_citations),
                lines=result.total_lines,
                templates=result.template_count,
                raw_chars=result.raw_chars,
                digest_chars=result.digest_chars,
                model=result.model,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
            )
            failures_in_a_row = 0
            if not limit:
                with checkpoint.open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(json.dumps(row) + "\n")
        except Exception as error:  # One failed API call must not lose the whole paid run.
            print(f"{label['file']}: {error}", file=sys.stderr)
            failures_in_a_row += 1
            row.update(predicted="error", cited_lines=[], citations_total=0, citations_rejected=0,
                       lines=0, templates=0, raw_chars=0, digest_chars=0, error=str(error))
        print(f"{row['file']}: expected={row['expected']} predicted={row['predicted']}")
        rows.append(row)
        if failures_in_a_row >= MAX_FAILURES_IN_A_ROW:
            sys.exit(f"Stopped after {failures_in_a_row} failures in a row. Rerun the same command later to continue.")

    summary = score(rows)
    input_tokens = sum(row.get("input_tokens", 0) for row in rows)
    output_tokens = sum(row.get("output_tokens", 0) for row in rows)
    summary.update(
        analyzer=analyzer,
        models_seen=sorted({row["model"] for row in rows if row.get("model")}),
        split=split,
        date=datetime.now(timezone.utc).date().isoformat(),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    if not limit and summary["errors"] == 0:
        checkpoint.unlink(missing_ok=True)
    if analyzer == "claude":
        price_in, price_out = PRICE_PER_MILLION[DEFAULT_MODEL]
        summary["estimated_cost_usd"] = round((input_tokens * price_in + output_tokens * price_out) / 1_000_000, 4)
    return {"summary": summary, "cases": rows}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analyzer", choices=["rules", "claude", "claude-cli", "ollama"], required=True)
    parser.add_argument("--split", choices=["dev", "test"], required=True)
    parser.add_argument("--limit", type=int, help="score only the first N cases (results are not saved)")
    args = parser.parse_args()

    output = run(args.analyzer, args.split, args.limit)
    print(json.dumps({k: v for k, v in output["summary"].items() if k != "per_class"}, indent=2))
    if not args.limit:
        out = HERE / "results" / f"{args.analyzer}_{args.split}.json"
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(output, indent=1), encoding="utf-8", newline="\n")
        print(f"Saved {out}")


if __name__ == "__main__":
    main()
