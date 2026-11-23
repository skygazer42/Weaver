"""Expose bundled workspace skills by metadata, with on-demand file reads."""

from pathlib import Path

import yaml
from langchain_core.tools import tool

_SKILLS_ROOT = Path(__file__).resolve().parents[2] / "workbench" / "skills"


def skill_catalog() -> dict[str, str]:
    catalog = {}
    for path in sorted(_SKILLS_ROOT.glob("*/SKILL.md")):
        with path.open(encoding="utf-8") as source:
            if source.readline().strip() != "---":
                continue
            metadata = []
            for line in source:
                if line.strip() == "---":
                    break
                metadata.append(line)
        record = yaml.safe_load("".join(metadata))
        if (
            isinstance(record, dict)
            and record.get("name") == path.parent.name
            and record.get("description")
        ):
            catalog[path.parent.name] = str(record["description"])
    return catalog


@tool
def read_skill(name: str, resource: str = "SKILL.md") -> str:
    """Read a bundled skill or one of its referenced files. Read the skill before selecting a resource."""
    if name not in skill_catalog():
        return "Skill not found."
    root = (_SKILLS_ROOT / name).resolve()
    target = (root / resource).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        return "Skill resource not found."
    return target.read_text(encoding="utf-8")
