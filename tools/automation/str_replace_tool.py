from typing import Optional
from langchain.tools import tool
from pathlib import Path

@tool
def str_replace(path: str, search: str, replace: str, encoding: str = "utf-8") -> str:
    """
    Replace all occurrences of `search` with `replace` in a text file.
    """
    p = Path(path)
    if not p.exists():
        return f"File not found: {path}"
    text = p.read_text(encoding=encoding)
    new_text = text.replace(search, replace)
    p.write_text(new_text, encoding=encoding)
    return f"Replaced occurrences in {path}"
