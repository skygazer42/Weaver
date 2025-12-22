from functools import lru_cache
from pathlib import Path
from typing import Literal

PACKAGE_ROOT = Path(__file__).resolve().parent


@lru_cache(maxsize=8)
def _load(name: str) -> str:
    path = PACKAGE_ROOT / f"{name}.txt"
    return path.read_text(encoding="utf-8").strip()


def get_behavior_prompt(
    variant: Literal["full", "lite"] = "full",
    include_browser: bool = True,
    include_desktop: bool = True,
) -> str:
    if variant == "lite":
        return _load("lite")

    parts = [_load("identity")]
    if include_desktop:
        parts.append(_load("desktop_automation"))
    if include_browser:
        parts.append(_load("browser_strategy"))
    parts.append(_load("completion"))
    return "\n\n".join(parts)
