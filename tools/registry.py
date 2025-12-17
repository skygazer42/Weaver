from typing import List
from langchain_core.tools import BaseTool

_REGISTERED_TOOLS: List[BaseTool] = []


def set_registered_tools(tools: List[BaseTool]) -> None:
    global _REGISTERED_TOOLS
    _REGISTERED_TOOLS = tools


def get_registered_tools() -> List[BaseTool]:
    return list(_REGISTERED_TOOLS)
