"""
Unit tests for tools/base.py - WeaverTool base classes

Tests cover:
- ToolResult creation and serialization
- WeaverTool schema registration
- tool_schema decorator
- Helper methods (success_response, fail_response, partial_response)
- Utility functions (validate_tool_result, merge_tool_results)
"""

import json

import pytest

from tools.core.base import (
    ToolResult,
    WeaverTool,
    merge_tool_results,
    tool_schema,
    validate_tool_result,
)


class TestToolResult:
    """Test ToolResult data class."""

    def test_create_success_result(self):
        """Test creating a successful ToolResult."""
        result = ToolResult(success=True, output="Test output", metadata={"key": "value"})

        assert result.success is True
        assert result.output == "Test output"
        assert result.metadata == {"key": "value"}
        assert result.error is None

    def test_create_failure_result(self):
        """Test creating a failed ToolResult."""
        result = ToolResult(
            success=False,
            output="Error occurred",
            error="Something went wrong",
            metadata={"error_code": 500},
        )

        assert result.success is False
        assert result.error == "Something went wrong"
        assert result.metadata["error_code"] == 500

    def test_to_dict(self):
        """Test ToolResult serialization to dict."""
        result = ToolResult(success=True, output="test", metadata={"a": 1})

        data = result.to_dict()

        assert isinstance(data, dict)
        assert data["success"] is True
        assert data["output"] == "test"
        assert data["metadata"] == {"a": 1}

    def test_to_json(self):
        """Test ToolResult serialization to JSON."""
        result = ToolResult(success=True, output="test", metadata={"count": 5})

        json_str = result.to_json()

        assert isinstance(json_str, str)
        data = json.loads(json_str)
        assert data["success"] is True
        assert data["metadata"]["count"] == 5

    def test_from_dict(self):
        """Test ToolResult deserialization from dict."""
        data = {"success": False, "output": "Failed", "metadata": {}, "error": "Test error"}

        result = ToolResult.from_dict(data)

        assert result.success is False
        assert result.output == "Failed"
        assert result.error == "Test error"

    def test_str_representation(self):
        """Test string representation."""
        result = ToolResult(
            success=True,
            output="x" * 150,  # Long output
        )

        str_repr = str(result)

        assert "[OK]" in str_repr
        assert "..." in str_repr  # Should be truncated


class TestWeaverTool:
    """Test WeaverTool base class."""

    def test_schema_registration(self):
        """Test automatic schema registration."""

        class TestTool(WeaverTool):
            @tool_schema(
                name="test_method",
                description="A test method",
                parameters={"type": "object", "properties": {"arg": {"type": "string"}}},
            )
            def test_method(self, arg: str) -> ToolResult:
                return self.success_response(f"Got: {arg}")

        tool = TestTool()
        schemas = tool.get_schemas()

        assert "test_method" in schemas
        assert schemas["test_method"]["name"] == "test_method"
        assert schemas["test_method"]["description"] == "A test method"

    def test_multiple_methods(self):
        """Test registering multiple methods."""

        class MultiTool(WeaverTool):
            @tool_schema(name="method1", description="Method 1", parameters={})
            def method1(self) -> ToolResult:
                return self.success_response("m1")

            @tool_schema(name="method2", description="Method 2", parameters={})
            def method2(self) -> ToolResult:
                return self.success_response("m2")

            def undecorated_method(self):
                """This should not be registered."""
                pass

        tool = MultiTool()
        schemas = tool.get_schemas()

        assert len(schemas) == 2
        assert "method1" in schemas
        assert "method2" in schemas
        assert "undecorated_method" not in schemas

    def test_get_method(self):
        """Test getting a registered method."""

        class TestTool(WeaverTool):
            @tool_schema(name="my_method", description="Test", parameters={})
            def my_method(self) -> ToolResult:
                return self.success_response("called")

        tool = TestTool()
        method = tool.get_method("my_method")

        assert method is not None
        assert callable(method)

        result = method()
        assert result.success is True
        assert "called" in result.output

    def test_list_methods(self):
        """Test listing all registered methods."""

        class TestTool(WeaverTool):
            @tool_schema(name="a", description="A", parameters={})
            def a(self) -> ToolResult:
                return self.success_response("a")

            @tool_schema(name="b", description="B", parameters={})
            def b(self) -> ToolResult:
                return self.success_response("b")

        tool = TestTool()
        methods = tool.list_methods()

        assert len(methods) == 2
        assert "a" in methods
        assert "b" in methods

    def test_success_response_with_dict(self):
        """Test success_response with dict data."""

        class TestTool(WeaverTool):
            pass

        tool = TestTool()
        result = tool.success_response({"key": "value", "count": 5}, metadata={"source": "test"})

        assert result.success is True
        assert "key" in result.output
        assert "value" in result.output
        assert result.metadata["source"] == "test"

    def test_success_response_with_string(self):
        """Test success_response with string data."""

        class TestTool(WeaverTool):
            pass

        tool = TestTool()
        result = tool.success_response("Simple string output")

        assert result.success is True
        assert result.output == "Simple string output"

    def test_fail_response(self):
        """Test fail_response."""

        class TestTool(WeaverTool):
            pass

        tool = TestTool()
        result = tool.fail_response("Something failed", metadata={"error_code": 404})

        assert result.success is False
        assert result.error == "Something failed"
        assert "Error:" in result.output
        assert result.metadata["error_code"] == 404

    def test_partial_response(self):
        """Test partial_response (partial success with warning)."""

        class TestTool(WeaverTool):
            pass

        tool = TestTool()
        result = tool.partial_response(
            {"data": [1, 2, 3]},
            "Only partial data available",
            metadata={"expected": 10, "found": 3},
        )

        assert result.success is True
        assert result.metadata["warning"] == "Only partial data available"
        assert result.metadata["expected"] == 10


class TestToolSchemaDecorator:
    """Test @tool_schema decorator."""

    def test_decorator_attaches_schema(self):
        """Test that decorator attaches schema to function."""

        @tool_schema(name="test", description="Test function", parameters={})
        def test_func():
            pass

        assert hasattr(test_func, "_tool_schema")
        assert test_func._tool_schema["name"] == "test"
        assert test_func._tool_schema["description"] == "Test function"

    def test_decorator_with_complex_parameters(self):
        """Test decorator with full parameter schema."""

        @tool_schema(
            name="complex_tool",
            description="A complex tool",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 100},
                },
                "required": ["query"],
            },
        )
        def complex_func():
            pass

        schema = complex_func._tool_schema
        assert schema["name"] == "complex_tool"
        assert "query" in schema["parameters"]["properties"]
        assert schema["parameters"]["properties"]["limit"]["default"] == 10
        assert "query" in schema["parameters"]["required"]


class TestUtilityFunctions:
    """Test utility functions."""

    def test_validate_tool_result_with_tool_result(self):
        """Test validate_tool_result with ToolResult input."""
        original = ToolResult(success=True, output="test")
        validated = validate_tool_result(original)

        assert validated is original

    def test_validate_tool_result_with_dict(self):
        """Test validate_tool_result with dict input."""
        data = {"success": True, "output": "test output", "metadata": {}}
        result = validate_tool_result(data)

        assert isinstance(result, ToolResult)
        assert result.success is True
        assert result.output == "test output"

    def test_validate_tool_result_with_list(self):
        """Test validate_tool_result with list input."""
        data = [1, 2, 3]
        result = validate_tool_result(data)

        assert isinstance(result, ToolResult)
        assert result.success is True
        assert "[1, 2, 3]" in result.output

    def test_validate_tool_result_with_string(self):
        """Test validate_tool_result with string input."""
        result = validate_tool_result("Simple string")

        assert isinstance(result, ToolResult)
        assert result.success is True
        assert result.output == "Simple string"

    def test_merge_tool_results_all_success(self):
        """Test merging all successful results."""
        results = [
            ToolResult(success=True, output="Result 1", metadata={"a": 1}),
            ToolResult(success=True, output="Result 2", metadata={"b": 2}),
            ToolResult(success=True, output="Result 3", metadata={"c": 3}),
        ]

        merged = merge_tool_results(results)

        assert merged.success is True
        assert "Result 1" in merged.output
        assert "Result 2" in merged.output
        assert "Result 3" in merged.output
        assert "result_0" in merged.metadata
        assert "result_1" in merged.metadata
        assert "result_2" in merged.metadata

    def test_merge_tool_results_with_failures(self):
        """Test merging with some failures."""
        results = [
            ToolResult(success=True, output="OK", metadata={}),
            ToolResult(success=False, output="Failed", error="Error 1"),
            ToolResult(success=False, output="Failed", error="Error 2"),
        ]

        merged = merge_tool_results(results)

        assert merged.success is False
        assert "Error 1" in merged.error
        assert "Error 2" in merged.error

    def test_merge_tool_results_empty_list(self):
        """Test merging empty list."""
        merged = merge_tool_results([])

        assert merged.success is False
        assert "No results to merge" in merged.output


class TestIntegration:
    """Integration tests for complete workflows."""

    def test_complete_tool_workflow(self):
        """Test complete tool creation and execution workflow."""

        class CalculatorTool(WeaverTool):
            @tool_schema(
                name="add",
                description="Add two numbers",
                parameters={
                    "type": "object",
                    "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                    "required": ["a", "b"],
                },
            )
            def add(self, a: float, b: float) -> ToolResult:
                try:
                    result = a + b
                    return self.success_response(
                        {"result": result, "operation": "addition"}, metadata={"a": a, "b": b}
                    )
                except Exception as e:
                    return self.fail_response(str(e))

        # Create tool
        tool = CalculatorTool()

        # Verify registration
        assert "add" in tool.list_methods()
        schemas = tool.get_schemas()
        assert schemas["add"]["name"] == "add"

        # Execute method
        result = tool.add(5, 3)

        # Verify result
        assert result.success is True
        data = json.loads(result.output)
        assert data["result"] == 8
        assert data["operation"] == "addition"
        assert result.metadata["a"] == 5
        assert result.metadata["b"] == 3

    def test_error_handling_workflow(self):
        """Test error handling in tool execution."""

        class FaultyTool(WeaverTool):
            @tool_schema(
                name="divide",
                description="Divide two numbers",
                parameters={
                    "type": "object",
                    "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                    "required": ["a", "b"],
                },
            )
            def divide(self, a: float, b: float) -> ToolResult:
                try:
                    result = a / b
                    return self.success_response({"result": result})
                except ZeroDivisionError:
                    return self.fail_response(
                        "Division by zero", metadata={"error_type": "ZeroDivisionError"}
                    )

        tool = FaultyTool()

        # Test successful division
        result1 = tool.divide(10, 2)
        assert result1.success is True

        # Test division by zero
        result2 = tool.divide(10, 0)
        assert result2.success is False
        assert "Division by zero" in result2.error
        assert result2.metadata["error_type"] == "ZeroDivisionError"


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
