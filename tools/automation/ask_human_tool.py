from typing import Optional
from langchain.tools import tool

@tool
def ask_human(prompt: str, note: Optional[str] = None) -> str:
    """
    Request human input. Front-end should intercept this tool call and prompt the user.

    Args:
        prompt: question/content to display to the user
        note: optional additional context
    """
    return f"Human input requested: {prompt}" + (f" ({note})" if note else "")
