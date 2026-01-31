"""
Tool Registry - Dynamic tool registration and management system

This module provides a comprehensive tool registry system for managing,
discovering, validating, and tracking tools in the Weaver agent framework.

Features:
- Dynamic tool registration and unregistration
- Automatic tool discovery from modules
- Tool validation and testing
- Tool metadata management
- Usage statistics tracking
- Version management
- LangChain compatibility (backward compatible)

Design Philosophy:
Centralize all tool management in a single registry that provides discovery,
validation, and lifecycle management, making it easy to add, remove, and
track tools across the agent system.
"""

import importlib
import inspect
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Type

from langchain.tools import BaseTool

from tools.core.base import ToolResult, WeaverTool, tool_schema

logger = logging.getLogger(__name__)


# ==================== Tool Metadata ====================


@dataclass
class ToolMetadata:
    """
    Metadata for a registered tool.

    Tracks information about a tool including its schema,
    usage statistics, and registration details.
    """

    # Basic info
    name: str
    description: str
    tool_type: str  # "weaver" | "langchain" | "function"

    # Schema
    parameters: Dict[str, Any] = field(default_factory=dict)
    return_type: Optional[str] = None

    # Source
    module_name: str = ""
    class_name: str = ""
    function_name: str = ""

    # Registration
    registered_at: str = field(default_factory=lambda: datetime.now().isoformat())
    version: str = "1.0.0"
    tags: List[str] = field(default_factory=list)

    # Usage statistics
    call_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    last_called: Optional[str] = None
    average_duration_ms: float = 0.0

    # Status
    enabled: bool = True
    deprecated: bool = False
    deprecation_message: Optional[str] = None

    def increment_call(self, success: bool, duration_ms: float):
        """Record a tool call."""
        self.call_count += 1
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1

        self.last_called = datetime.now().isoformat()

        # Update average duration (moving average)
        if self.call_count == 1:
            self.average_duration_ms = duration_ms
        else:
            alpha = 0.2  # Weight for new value
            self.average_duration_ms = alpha * duration_ms + (1 - alpha) * self.average_duration_ms

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "tool_type": self.tool_type,
            "parameters": self.parameters,
            "return_type": self.return_type,
            "module_name": self.module_name,
            "class_name": self.class_name,
            "function_name": self.function_name,
            "registered_at": self.registered_at,
            "version": self.version,
            "tags": self.tags,
            "call_count": self.call_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "last_called": self.last_called,
            "average_duration_ms": self.average_duration_ms,
            "enabled": self.enabled,
            "deprecated": self.deprecated,
            "deprecation_message": self.deprecation_message,
        }

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.call_count == 0:
            return 0.0
        return self.success_count / self.call_count


# ==================== Tool Registry ====================


class ToolRegistry:
    """
    Central registry for all tools in the system.

    Provides registration, discovery, validation, and lifecycle
    management for tools.
    """

    def __init__(self):
        """Initialize empty registry."""
        # Main registry: name -> (callable, metadata)
        self._tools: Dict[str, tuple[Callable, ToolMetadata]] = {}

        # Indexes for fast lookup
        self._by_tag: Dict[str, Set[str]] = {}  # tag -> set of tool names
        self._by_module: Dict[str, Set[str]] = {}  # module -> set of tool names
        self._by_type: Dict[str, Set[str]] = {}  # type -> set of tool names

        logger.info("ToolRegistry initialized")

    # ==================== Registration ====================

    def register(
        self,
        name: str,
        tool: Callable,
        description: str = "",
        parameters: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        version: str = "1.0.0",
        override: bool = False,
    ) -> ToolMetadata:
        """
        Register a tool.

        Args:
            name: Unique tool name
            tool: Tool callable (function, WeaverTool method, etc.)
            description: Tool description
            parameters: Parameter schema (auto-detected if not provided)
            tags: Tags for categorization
            version: Tool version
            override: Allow overriding existing tool

        Returns:
            ToolMetadata for the registered tool

        Raises:
            ValueError: If tool already exists and override=False
        """

        # Check for existing
        if name in self._tools and not override:
            raise ValueError(f"Tool '{name}' already registered. Use override=True to replace.")

        # Extract metadata
        tool_type = self._detect_tool_type(tool)
        module_name = tool.__module__ if hasattr(tool, "__module__") else ""
        class_name = (
            tool.__qualname__.split(".")[0]
            if hasattr(tool, "__qualname__") and "." in tool.__qualname__
            else ""
        )
        function_name = tool.__name__ if hasattr(tool, "__name__") else name

        # Auto-detect parameters if not provided
        if parameters is None:
            parameters = self._extract_parameters(tool)

        # Auto-detect description if not provided
        if not description:
            description = self._extract_description(tool)

        # Create metadata
        metadata = ToolMetadata(
            name=name,
            description=description,
            tool_type=tool_type,
            parameters=parameters,
            module_name=module_name,
            class_name=class_name,
            function_name=function_name,
            version=version,
            tags=tags or [],
        )

        # Store in main registry
        self._tools[name] = (tool, metadata)

        # Update indexes
        self._update_indexes(name, metadata)

        logger.info(f"Registered tool: {name} (type={tool_type}, version={version})")

        return metadata

    def register_weaver_tool(
        self,
        tool_instance: Any,  # WeaverTool
        method_name: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> List[ToolMetadata]:
        """
        Register all methods from a WeaverTool instance.

        Args:
            tool_instance: WeaverTool instance
            method_name: Specific method name (None = register all)
            tags: Additional tags for all methods

        Returns:
            List of ToolMetadata for registered methods
        """

        if WeaverTool is None:
            raise ImportError("WeaverTool not available")

        registered = []

        # Get methods to register
        if method_name:
            methods_to_register = {method_name: tool_instance.get_schemas().get(method_name)}
        else:
            methods_to_register = tool_instance.get_schemas()

        # Register each method
        for method_name, schema in methods_to_register.items():
            tool_method = getattr(tool_instance, method_name)

            metadata = self.register(
                name=schema.get("name", method_name),
                tool=tool_method,
                description=schema.get("description", ""),
                parameters=schema.get("parameters", {}),
                tags=(tags or []) + ["weaver_tool"],
                version=getattr(tool_instance, "__version__", "1.0.0"),
            )

            registered.append(metadata)

        logger.info(f"Registered {len(registered)} methods from {tool_instance.__class__.__name__}")

        return registered

    def unregister(self, name: str) -> bool:
        """
        Unregister a tool.

        Args:
            name: Tool name to unregister

        Returns:
            True if unregistered, False if not found
        """

        if name not in self._tools:
            logger.warning(f"Tool '{name}' not found for unregistration")
            return False

        # Get metadata
        _, metadata = self._tools[name]

        # Remove from indexes
        self._remove_from_indexes(name, metadata)

        # Remove from main registry
        del self._tools[name]

        logger.info(f"Unregistered tool: {name}")

        return True

    # ==================== Discovery ====================

    def discover_from_module(
        self, module_name: str, tags: Optional[List[str]] = None, prefix: str = ""
    ) -> List[ToolMetadata]:
        """
        Discover and register tools from a module.

        Automatically finds:
        - WeaverTool subclasses
        - Functions decorated with @tool_schema
        - Async functions with ToolResult return type

        Args:
            module_name: Module to import and scan
            tags: Tags to add to discovered tools
            prefix: Prefix for tool names

        Returns:
            List of registered ToolMetadata
        """

        registered = []

        # Import module
        module = importlib.import_module(module_name)

        # Scan for WeaverTool subclasses
        if WeaverTool is not None:
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, WeaverTool) and obj is not WeaverTool:
                    try:
                        instance = obj()
                        registered.extend(self.register_weaver_tool(instance, tags=tags))
                    except Exception as e:
                        logger.error(f"Failed to instantiate {name}: {e}")

        # Scan for functions with @tool_schema
        for name, obj in inspect.getmembers(module, inspect.isfunction):
            if hasattr(obj, "_tool_schema"):
                schema = obj._tool_schema
                tool_name = prefix + schema.get("name", name)

                try:
                    metadata = self.register(
                        name=tool_name,
                        tool=obj,
                        description=schema.get("description", ""),
                        parameters=schema.get("parameters", {}),
                        tags=(tags or []) + ["auto_discovered"],
                    )
                    registered.append(metadata)
                except ValueError:
                    logger.warning(f"Tool {tool_name} already registered, skipping")

        logger.info(f"Discovered {len(registered)} tools from module '{module_name}'")

        return registered

    def discover_from_directory(
        self,
        directory: str,
        pattern: str = "*.py",
        recursive: bool = True,
        tags: Optional[List[str]] = None,
    ) -> List[ToolMetadata]:
        """
        Discover tools from all Python files in a directory.

        Args:
            directory: Directory path
            pattern: File pattern to match
            recursive: Search subdirectories
            tags: Tags for discovered tools

        Returns:
            List of registered ToolMetadata
        """

        registered = []
        dir_path = Path(directory)

        if not dir_path.exists():
            logger.error(f"Directory not found: {directory}")
            return registered

        # Find Python files
        if recursive:
            files = dir_path.rglob(pattern)
        else:
            files = dir_path.glob(pattern)

        # Discover from each module
        for file_path in files:
            # Skip __init__.py and test files
            if file_path.name.startswith("__") or file_path.name.startswith("test_"):
                continue

            # Convert path to module name
            relative_path = file_path.relative_to(dir_path.parent)
            module_name = str(relative_path.with_suffix("")).replace("/", ".").replace("\\", ".")

            try:
                discovered = self.discover_from_module(module_name, tags=tags)
                registered.extend(discovered)
            except Exception as e:
                logger.error(f"Failed to discover from {module_name}: {e}")

        logger.info(f"Discovered {len(registered)} tools from directory '{directory}'")

        return registered

    # ==================== Retrieval ====================

    def get(self, name: str) -> Optional[Callable]:
        """
        Get a tool by name.

        Args:
            name: Tool name

        Returns:
            Tool callable or None if not found
        """

        entry = self._tools.get(name)
        if entry:
            return entry[0]
        return None

    def get_metadata(self, name: str) -> Optional[ToolMetadata]:
        """
        Get tool metadata.

        Args:
            name: Tool name

        Returns:
            ToolMetadata or None if not found
        """

        entry = self._tools.get(name)
        if entry:
            return entry[1]
        return None

    def get_all(self) -> Dict[str, Callable]:
        """
        Get all registered tools.

        Returns:
            Dictionary of {name: callable}
        """

        return {name: tool for name, (tool, _) in self._tools.items()}

    def get_by_tag(self, tag: str) -> Dict[str, Callable]:
        """Get tools with a specific tag."""
        names = self._by_tag.get(tag, set())
        return {name: self.get(name) for name in names}

    def get_by_type(self, tool_type: str) -> Dict[str, Callable]:
        """Get tools of a specific type."""
        names = self._by_type.get(tool_type, set())
        return {name: self.get(name) for name in names}

    def list_names(self, enabled_only: bool = False) -> List[str]:
        """
        List all tool names.

        Args:
            enabled_only: Only return enabled tools

        Returns:
            List of tool names
        """

        if not enabled_only:
            return list(self._tools.keys())

        return [name for name, (_, metadata) in self._tools.items() if metadata.enabled]

    def list_metadata(self, enabled_only: bool = False) -> List[ToolMetadata]:
        """Get metadata for all tools."""
        return [
            metadata for _, metadata in self._tools.values() if not enabled_only or metadata.enabled
        ]

    # ==================== Statistics ====================

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get registry statistics.

        Returns:
            Dictionary with registry stats
        """

        total = len(self._tools)
        enabled = sum(1 for _, (_, m) in self._tools.items() if m.enabled)
        deprecated = sum(1 for _, (_, m) in self._tools.items() if m.deprecated)

        total_calls = sum(m.call_count for _, (_, m) in self._tools.items())
        total_successes = sum(m.success_count for _, (_, m) in self._tools.items())

        # Most used tools
        most_used = sorted(
            [(name, m.call_count) for name, (_, m) in self._tools.items()],
            key=lambda x: x[1],
            reverse=True,
        )[:10]

        # By type
        by_type = {}
        for tool_type in self._by_type:
            by_type[tool_type] = len(self._by_type[tool_type])

        return {
            "total_tools": total,
            "enabled_tools": enabled,
            "deprecated_tools": deprecated,
            "total_calls": total_calls,
            "total_successes": total_successes,
            "overall_success_rate": total_successes / total_calls if total_calls > 0 else 0.0,
            "most_used": most_used,
            "by_type": by_type,
            "tags": list(self._by_tag.keys()),
        }

    def export_metadata(self, filepath: str):
        """Export all metadata to JSON file."""
        metadata_list = [m.to_dict() for _, (_, m) in self._tools.items()]

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(metadata_list, f, indent=2)

        logger.info(f"Exported metadata for {len(metadata_list)} tools to {filepath}")

    # ==================== Helper Methods ====================

    def _detect_tool_type(self, tool: Callable) -> str:
        """Detect tool type from callable."""
        if WeaverTool and isinstance(tool, WeaverTool):
            return "weaver"
        elif hasattr(tool, "__self__") and WeaverTool and isinstance(tool.__self__, WeaverTool):
            return "weaver"
        elif BaseTool and isinstance(tool, BaseTool):
            return "langchain"
        elif hasattr(tool, "_tool_schema"):
            return "function"
        else:
            return "function"

    def _extract_parameters(self, tool: Callable) -> Dict[str, Any]:
        """Extract parameter schema from callable signature."""
        try:
            sig = inspect.signature(tool)
            parameters = {}

            for name, param in sig.parameters.items():
                if name == "self":
                    continue

                param_info = {"type": "string"}  # Default

                # Extract type annotation
                if param.annotation != inspect.Parameter.empty:
                    annotation = param.annotation
                    if annotation == str:
                        param_info["type"] = "string"
                    elif annotation == int:
                        param_info["type"] = "integer"
                    elif annotation == float:
                        param_info["type"] = "number"
                    elif annotation == bool:
                        param_info["type"] = "boolean"
                    elif hasattr(annotation, "__origin__"):
                        # Handle List, Dict, etc.
                        param_info["type"] = "object"

                # Extract default value
                if param.default != inspect.Parameter.empty:
                    param_info["default"] = param.default

                parameters[name] = param_info

            return {"properties": parameters, "type": "object"}

        except Exception as e:
            logger.warning(f"Failed to extract parameters: {e}")
            return {}

    def _extract_description(self, tool: Callable) -> str:
        """Extract description from docstring."""
        doc = inspect.getdoc(tool)
        if doc:
            # Get first line
            return doc.split("\n")[0].strip()
        return ""

    def _update_indexes(self, name: str, metadata: ToolMetadata):
        """Update lookup indexes."""
        # By tag
        for tag in metadata.tags:
            if tag not in self._by_tag:
                self._by_tag[tag] = set()
            self._by_tag[tag].add(name)

        # By module
        if metadata.module_name:
            if metadata.module_name not in self._by_module:
                self._by_module[metadata.module_name] = set()
            self._by_module[metadata.module_name].add(name)

        # By type
        if metadata.tool_type not in self._by_type:
            self._by_type[metadata.tool_type] = set()
        self._by_type[metadata.tool_type].add(name)

    def _remove_from_indexes(self, name: str, metadata: ToolMetadata):
        """Remove from lookup indexes."""
        # By tag
        for tag in metadata.tags:
            if tag in self._by_tag:
                self._by_tag[tag].discard(name)

        # By module
        if metadata.module_name in self._by_module:
            self._by_module[metadata.module_name].discard(name)

        # By type
        if metadata.tool_type in self._by_type:
            self._by_type[metadata.tool_type].discard(name)


# ==================== Global Registry ====================

# Singleton instance
_global_registry: Optional[ToolRegistry] = None


def get_global_registry() -> ToolRegistry:
    """Get or create the global tool registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
    return _global_registry


def reset_global_registry():
    """Reset the global registry (for testing)."""
    global _global_registry
    _global_registry = None


# ==================== Backward Compatibility ====================

# For backward compatibility with existing code
_REGISTERED_TOOLS: List = []


def set_registered_tools(tools: List) -> None:
    """
    Set registered tools (backward compatible).

    Args:
        tools: List of tools (BaseTool or callable)
    """
    global _REGISTERED_TOOLS
    _REGISTERED_TOOLS = tools

    # Also register in new registry if available
    registry = get_global_registry()
    for tool in tools:
        try:
            if BaseTool and isinstance(tool, BaseTool):
                registry.register(
                    name=tool.name, tool=tool._run, description=tool.description, tags=["langchain"]
                )
            else:
                # Assume callable
                name = getattr(tool, "name", tool.__name__)
                registry.register(name=name, tool=tool)
        except Exception as e:
            logger.warning(f"Failed to register tool in new registry: {e}")


def get_registered_tools() -> List:
    """
    Get registered tools (backward compatible).

    Returns:
        List of registered tools
    """
    return list(_REGISTERED_TOOLS)


# ==================== Example Usage ====================

if __name__ == "__main__":
    print("=" * 60)
    print("Tool Registry Test")
    print("=" * 60)

    # Create registry
    registry = ToolRegistry()

    # Test 1: Register a simple function
    print("\n1. Testing simple function registration:")

    def mock_search(query: str, max_results: int = 5) -> str:
        """Search the web for information."""
        return f"Results for: {query}"

    metadata = registry.register(name="search_web", tool=mock_search, tags=["search", "web"])

    print(f"  Registered: {metadata.name}")
    print(f"  Type: {metadata.tool_type}")
    print(f"  Parameters: {list(metadata.parameters.get('properties', {}).keys())}")

    # Test 2: Get tool
    print("\n2. Testing tool retrieval:")
    tool = registry.get("search_web")
    print(f"  Retrieved: {tool.__name__ if tool else 'None'}")

    # Test 3: List tools
    print("\n3. Testing tool listing:")
    print(f"  Total tools: {len(registry.list_names())}")
    print(f"  Tools: {registry.list_names()}")

    # Test 4: Get by tag
    print("\n4. Testing tag-based retrieval:")
    search_tools = registry.get_by_tag("search")
    print(f"  Tools with 'search' tag: {list(search_tools.keys())}")

    # Test 5: Statistics
    print("\n5. Testing statistics:")
    stats = registry.get_statistics()
    print(f"  Total tools: {stats['total_tools']}")
    print(f"  By type: {stats['by_type']}")

    print("\n" + "=" * 60)
    print("[OK] Tool registry test completed!")
    print("=" * 60)
