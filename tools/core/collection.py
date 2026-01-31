"""
Lightweight ToolCollection for Weaver.

Purpose: provide a simple, runtime-mutable aggregation of tools (functions or
LangChain BaseTool instances) with name-based lookup and optional whitelist /
blacklist filtering. This mirrors OpenManus's ToolCollection but is adapted to
Weaver's tool registry and LangGraph agents.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class ToolCollection:
    tools: List[Any] = field(default_factory=list)
    tool_map: Dict[str, Any] = field(default_factory=dict)

    def __iter__(self):
        return iter(self.tools)

    def add_tool(self, tool: Any) -> "ToolCollection":
        name = getattr(tool, "name", None) or getattr(tool, "__name__", None)
        if not name:
            return self
        if name in self.tool_map:
            # Skip duplicates; keeps first registered
            return self
        self.tools.append(tool)
        self.tool_map[name] = tool
        return self

    def add_tools(self, tools: Iterable[Any]) -> "ToolCollection":
        for t in tools:
            self.add_tool(t)
        return self

    def get(self, name: str) -> Optional[Any]:
        return self.tool_map.get(name)

    def to_list(self) -> List[Any]:
        return list(self.tools)

    def filter(
        self,
        whitelist: Optional[Iterable[str]] = None,
        blacklist: Optional[Iterable[str]] = None,
    ) -> "ToolCollection":
        whitelist_set = set(whitelist or [])
        blacklist_set = set(blacklist or [])

        filtered = ToolCollection()
        for tool in self.tools:
            name = getattr(tool, "name", None) or getattr(tool, "__name__", None)
            if not name:
                continue
            if whitelist_set and name not in whitelist_set:
                continue
            if name in blacklist_set:
                continue
            filtered.add_tool(tool)
        return filtered
