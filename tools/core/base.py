"""
Weaver Tool Base Classes - Inspired by Manus AgentPress

This module provides the foundational classes for building tools in Weaver:
- ToolResult: Unified result container
- WeaverTool: Abstract base class with decorator-driven schema registration
- tool_schema: Decorator for declaring tool schemas

Design Philosophy:
1. Declarative: Schema and implementation tightly coupled
2. Unified: Consistent result format across all tools
3. Extensible: Easy to add new tools with minimal boilerplate
4. Compatible: Works alongside LangChain tools
"""

from abc import ABC
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional, List, Callable
import json
import inspect
import logging

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """
    Unified container for tool execution results.

    Attributes:
        success: Whether the tool executed successfully
        output: The main output (string, for LLM consumption)
        metadata: Additional structured data (optional)
        error: Error message if execution failed (optional)

    Design rationale:
    - Consistent error handling across all tools
    - Rich metadata for debugging and logging
    - Serializable for storage and transmission
    """
    success: bool
    output: str
    metadata: Optional[Dict[str, Any]] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolResult":
        """Create ToolResult from dictionary."""
        return cls(**data)

    def __str__(self) -> str:
        """Human-readable representation."""
        status = "[OK]" if self.success else "[FAIL]"
        preview = self.output[:100] + "..." if len(self.output) > 100 else self.output
        return f"{status} ToolResult: {preview}"


class WeaverTool(ABC):
    """
    Abstract base class for Weaver tools.

    Features:
    1. Decorator-driven schema registration
    2. Automatic schema discovery
    3. Unified result format (ToolResult)
    4. Built-in error handling helpers

    Usage:
        class MyTool(WeaverTool):
            def __init__(self, api_key: str):
                self.api_key = api_key
                super().__init__()

            @tool_schema(
                name="my_function",
                description="Does something useful",
                parameters={...}
            )
            def my_function(self, arg: str) -> ToolResult:
                try:
                    result = do_something(arg)
                    return self.success_response(result)
                except Exception as e:
                    return self.fail_response(str(e))
    """

    def __init__(self):
        """Initialize tool and register schemas."""
        self._schemas: Dict[str, Dict[str, Any]] = {}
        self._methods: Dict[str, Callable] = {}
        self._register_schemas()

    def _register_schemas(self):
        """
        Automatically scan and register all methods decorated with @tool_schema.

        This is called during __init__ to populate self._schemas and self._methods.
        """
        for name, method in inspect.getmembers(self, predicate=inspect.ismethod):
            # Skip private and magic methods
            if name.startswith('_'):
                continue

            # Check if method has tool_schema attribute
            if hasattr(method, '_tool_schema'):
                schema = method._tool_schema
                self._schemas[name] = schema
                self._methods[name] = method
                logger.debug(f"Registered tool method: {name} with schema: {schema.get('name')}")

    def get_schemas(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all registered tool schemas.

        Returns:
            Dictionary mapping method names to their schemas
        """
        return self._schemas.copy()

    def get_method(self, name: str) -> Optional[Callable]:
        """
        Get a registered method by name.

        Args:
            name: Method name

        Returns:
            The method callable, or None if not found
        """
        return self._methods.get(name)

    def list_methods(self) -> List[str]:
        """List all registered method names."""
        return list(self._methods.keys())

    # Helper methods for creating responses

    def success_response(
        self,
        data: Any,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        """
        Create a success ToolResult.

        Args:
            data: The result data (will be JSON serialized if not a string)
            metadata: Additional metadata

        Returns:
            ToolResult with success=True
        """
        if isinstance(data, str):
            output = data
        elif isinstance(data, (dict, list)):
            output = json.dumps(data, ensure_ascii=False, indent=2)
        else:
            output = str(data)

        return ToolResult(
            success=True,
            output=output,
            metadata=metadata or {},
            error=None
        )

    def fail_response(
        self,
        error_msg: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        """
        Create a failure ToolResult.

        Args:
            error_msg: Error message
            metadata: Additional metadata (e.g., error type, stack trace)

        Returns:
            ToolResult with success=False
        """
        return ToolResult(
            success=False,
            output=f"Error: {error_msg}",
            metadata=metadata or {},
            error=error_msg
        )

    def partial_response(
        self,
        data: Any,
        warning: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        """
        Create a partial success ToolResult (succeeded but with warnings).

        Args:
            data: The partial result data
            warning: Warning message
            metadata: Additional metadata

        Returns:
            ToolResult with success=True but warning in metadata
        """
        if isinstance(data, str):
            output = data
        else:
            output = json.dumps(data, ensure_ascii=False, indent=2)

        merged_metadata = metadata or {}
        merged_metadata['warning'] = warning

        return ToolResult(
            success=True,
            output=output,
            metadata=merged_metadata,
            error=None
        )


def tool_schema(**schema: Any) -> Callable:
    """
    Decorator for declaring tool schemas.

    Usage:
        @tool_schema(
            name="search_web",
            description="Search the web for information",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum results",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        )
        def search_web(self, query: str, max_results: int = 5) -> ToolResult:
            # Implementation
            pass

    Args:
        **schema: Schema definition (name, description, parameters)

    Returns:
        Decorated function with _tool_schema attribute
    """
    def decorator(func: Callable) -> Callable:
        # Attach schema to function
        func._tool_schema = schema  # type: ignore
        return func

    return decorator


# Utility functions

def validate_tool_result(result: Any) -> ToolResult:
    """
    Validate and convert any result to ToolResult.

    This is useful for adapting legacy tools that don't return ToolResult.

    Args:
        result: Any result value

    Returns:
        ToolResult instance
    """
    if isinstance(result, ToolResult):
        return result

    # Convert common formats
    if isinstance(result, dict):
        if "success" in result and "output" in result:
            return ToolResult(**result)
        else:
            # Treat as successful data
            return ToolResult(
                success=True,
                output=json.dumps(result, ensure_ascii=False),
                metadata={}
            )

    if isinstance(result, list):
        return ToolResult(
            success=True,
            output=json.dumps(result, ensure_ascii=False),
            metadata={}
        )

    if isinstance(result, str):
        return ToolResult(
            success=True,
            output=result,
            metadata={}
        )

    # Fallback
    return ToolResult(
        success=True,
        output=str(result),
        metadata={}
    )


def merge_tool_results(results: List[ToolResult]) -> ToolResult:
    """
    Merge multiple ToolResults into one.

    Useful for aggregating results from multiple tool calls.

    Args:
        results: List of ToolResult instances

    Returns:
        Merged ToolResult (success if all succeeded)
    """
    if not results:
        return ToolResult(
            success=False,
            output="No results to merge",
            error="Empty results list"
        )

    all_success = all(r.success for r in results)
    outputs = [r.output for r in results if r.output]
    errors = [r.error for r in results if r.error]

    merged_metadata = {}
    for i, result in enumerate(results):
        if result.metadata:
            merged_metadata[f"result_{i}"] = result.metadata

    return ToolResult(
        success=all_success,
        output="\n\n---\n\n".join(outputs),
        metadata=merged_metadata,
        error="; ".join(errors) if errors else None
    )


# Example usage and tests

if __name__ == "__main__":
    # Example tool implementation
    class ExampleTool(WeaverTool):
        """Example tool to demonstrate usage."""

        def __init__(self, api_key: str):
            self.api_key = api_key
            super().__init__()

        @tool_schema(
            name="greet",
            description="Greet a user by name",
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "User's name"
                    },
                    "language": {
                        "type": "string",
                        "enum": ["en", "zh", "es"],
                        "default": "en",
                        "description": "Language for greeting"
                    }
                },
                "required": ["name"]
            }
        )
        def greet(self, name: str, language: str = "en") -> ToolResult:
            """Greet the user."""
            greetings = {
                "en": f"Hello, {name}!",
                "zh": f"你好, {name}!",
                "es": f"¡Hola, {name}!"
            }

            greeting = greetings.get(language, greetings["en"])

            return self.success_response(
                {"greeting": greeting, "name": name},
                metadata={"language": language}
            )

        @tool_schema(
            name="calculate",
            description="Perform a calculation",
            parameters={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Mathematical expression"
                    }
                },
                "required": ["expression"]
            }
        )
        def calculate(self, expression: str) -> ToolResult:
            """Calculate a mathematical expression."""
            try:
                result = eval(expression)  # In production, use a safer evaluator
                return self.success_response(
                    {"expression": expression, "result": result}
                )
            except Exception as e:
                return self.fail_response(
                    f"Calculation failed: {str(e)}",
                    metadata={"expression": expression, "error_type": type(e).__name__}
                )

    # Test the example tool
    print("=" * 60)
    print("Testing WeaverTool Base Classes")
    print("=" * 60)

    tool = ExampleTool(api_key="test-key")

    print(f"\nRegistered methods: {tool.list_methods()}")
    print(f"\nSchemas: {json.dumps(tool.get_schemas(), indent=2)}")

    # Test successful call
    result1 = tool.greet("Alice", language="zh")
    print(f"\nTest 1 - Greet: {result1}")
    print(f"JSON: {result1.to_json()}")

    # Test calculation
    result2 = tool.calculate("2 + 2 * 10")
    print(f"\nTest 2 - Calculate: {result2}")

    # Test error handling
    result3 = tool.calculate("1 / 0")
    print(f"\nTest 3 - Error: {result3}")

    # Test result merging
    merged = merge_tool_results([result1, result2, result3])
    print(f"\nMerged results:\n{merged.to_json()}")

    print("\n" + "=" * 60)
    print("✓ All tests completed!")
    print("=" * 60)
