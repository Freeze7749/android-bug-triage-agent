"""Compress log lines into templates with Drain, and render them as a short digest."""
from collections import Counter

from drain3 import TemplateMiner
from drain3.masking import MaskingInstruction
from drain3.template_miner_config import TemplateMinerConfig

from .models import LogLine, Template

_LEVEL_RANK = {"F": 0, "E": 1, "W": 2, "I": 3, "D": 4, "V": 5, "S": 6, "": 3}
_MAX_LINE_CHARS = 300


def _new_miner() -> TemplateMiner:
    config = TemplateMinerConfig()
    config.drain_sim_th = 0.4
    config.drain_depth = 4
    config.profiling_enabled = False
    # Variable values become <NUM>/<HEX>, so they do not create separate templates.
    config.masking_instructions = [
        MaskingInstruction(r"\b0x[0-9a-fA-F]+\b", "HEX"),
        MaskingInstruction(r"(?<![\w.])-?\d+(\.\d+)?(?![\w.])", "NUM"),
    ]
    return TemplateMiner(config=config)


def mine_templates(lines: list[LogLine]) -> list[Template]:
    """Group lines by shape. Logcat buffer headers ("--------- beginning of") are skipped."""
    miner = _new_miner()
    members: dict[int, list[LogLine]] = {}
    for line in lines:
        if line.text.startswith("---------") or not line.text.strip():
            continue
        # The tag is part of the text so equal messages from different tags stay apart.
        result = miner.add_log_message(f"{line.tag or '?'} {line.message}")
        members.setdefault(result["cluster_id"], []).append(line)

    templates = []
    for cluster in miner.drain.clusters:
        group = members[cluster.cluster_id]
        templates.append(
            Template(
                id=cluster.cluster_id,
                pattern=cluster.get_template(),
                line_numbers=[line.number for line in group],
                # Most severe level in the group; most common tag.
                level=min((line.level for line in group), key=lambda lv: _LEVEL_RANK.get(lv, 3)),
                tag=Counter(line.tag for line in group).most_common(1)[0][0],
            )
        )
    return templates


def _priority(template: Template) -> tuple:
    """Severe and rare first: that is where faults hide."""
    return (_LEVEL_RANK.get(template.level, 3), len(template.line_numbers), template.line_numbers[0])


def build_digest(lines: list[LogLine], templates: list[Template], max_templates: int = 150) -> str:
    """Text sent to the LLM: each template with its first and last real line."""
    by_number = {line.number: line for line in lines}
    selected = sorted(templates, key=_priority)[:max_templates]
    rows = [f"Log has {len(lines)} lines and {len(templates)} templates. Showing {len(selected)}."]
    for template in selected:
        numbers = template.line_numbers
        rows.append(f"T{template.id} count={len(numbers)} level={template.level or '?'} tag={template.tag or '?'}")
        for number in sorted({numbers[0], numbers[-1]}):
            rows.append(f"  L{number}: {by_number[number].text[:_MAX_LINE_CHARS]}")
    return "\n".join(rows)
