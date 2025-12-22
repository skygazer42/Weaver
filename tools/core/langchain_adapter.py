"""
LangChain Adapter - Bridge between WeaverTool and LangChain

This module provides adapters to make WeaverTool instances compatible
with LangChain's tool ecosystem, allowing seamless integration.

Key features:
- Convert WeaverTool to LangChain BaseTool
- Convert LangChain tool results to ToolResult
- Preserve all metadata and schemas
- Support both sync and async execution
"""

from tools.core.base import WeaverTool, ToolResult, validate_tool_result
from langchain.tools import BaseTool, StructuredTool
from langchain_core.tools import ToolException
from typing import List, Dict, Any, Optional, Callable, Type
from pydantic import BaseModel, Field, create_model
import logging
import json
import inspect

logger = logging.getLogger(__name__)


def create_pydantic_model_from_schema(
    schema: Dict[str, Any],
    model_name: str = "DynamicInput"
) -> Type[BaseModel]:
    """
    Create a Pydantic model from a JSON schema.

    LangChain's StructuredTool requires Pydantic models for input validation.
    This function converts our tool_schema format to Pydantic.

    Args:
        schema: JSON schema dict (parameters section)
        model_name: Name for the generated model

    Returns:
        Pydantic model class
    """
    if not schema or schema.get("type") != "object":
        # Fallback: no parameters
        return create_model(model_name)

    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    # Build field definitions
    fields = {}
    for prop_name, prop_schema in properties.items():
        prop_type = prop_schema.get("type", "string")
        prop_desc = prop_schema.get("description", "")
        prop_default = prop_schema.get("default")

        # Map JSON schema types to Python types
        python_type = {
            "string": str,
            "integer": int,
            "number": float,
            "boolean": bool,
            "array": list,
            "object": dict
        }.get(prop_type, str)

        # Handle optional vs required
        if prop_name in required:
            if prop_default is not None:
                fields[prop_name] = (python_type, Field(default=prop_default, description=prop_desc))
            else:
                fields[prop_name] = (python_type, Field(..., description=prop_desc))
        else:
            if prop_default is not None:
                fields[prop_name] = (python_type, Field(default=prop_default, description=prop_desc))
            else:
                fields[prop_name] = (Optional[python_type], Field(default=None, description=prop_desc))

    return create_model(model_name, **fields)


def weaver_tool_to_langchain(
    weaver_tool: WeaverTool,
    method_name: Optional[str] = None,
    return_direct: bool = False
) -> List[BaseTool]:
    """
    Convert WeaverTool instance to LangChain BaseTool(s).

    Args:
        weaver_tool: WeaverTool instance
        method_name: If specified, only convert this method. Otherwise convert all.
        return_direct: Whether tool output should be returned directly to user

    Returns:
        List of LangChain BaseTool instances
    """
    langchain_tools = []

    # Get all schemas
    schemas = weaver_tool.get_schemas()

    # Filter by method_name if specified
    if method_name:
        if method_name not in schemas:
            logger.warning(f"Method {method_name} not found in {type(weaver_tool).__name__}")
            return []
        schemas = {method_name: schemas[method_name]}

    # Convert each method to a LangChain tool
    for method_key, schema in schemas.items():
        method = weaver_tool.get_method(method_key)
        if not method:
            logger.warning(f"Method {method_key} not found")
            continue

        tool_name = schema.get("name", method_key)
        tool_desc = schema.get("description", f"Executes {method_key}")
        parameters_schema = schema.get("parameters", {})

        # Create wrapper function that handles ToolResult
        def create_wrapper(method_func: Callable) -> Callable:
            def wrapper(**kwargs) -> str:
                """Execute WeaverTool method and convert result."""
                try:
                    result = method_func(**kwargs)

                    # Validate/convert to ToolResult
                    if not isinstance(result, ToolResult):
                        result = validate_tool_result(result)

                    # Return output string (LangChain expects string)
                    return result.output

                except Exception as e:
                    logger.error(f"Tool execution error in {tool_name}: {str(e)}")
                    raise ToolException(f"Tool execution failed: {str(e)}")

            return wrapper

        # Create Pydantic input model
        try:
            InputModel = create_pydantic_model_from_schema(
                parameters_schema,
                model_name=f"{tool_name.replace('-', '_').title()}Input"
            )
        except Exception as e:
            logger.warning(f"Failed to create Pydantic model for {tool_name}: {e}")
            # Fallback: use generic model
            InputModel = create_model(f"{tool_name}Input")

        # Create StructuredTool
        try:
            langchain_tool = StructuredTool(
                name=tool_name,
                description=tool_desc,
                func=create_wrapper(method),
                args_schema=InputModel,
                return_direct=return_direct
            )

            langchain_tools.append(langchain_tool)
            logger.debug(f"Converted {tool_name} to LangChain tool")

        except Exception as e:
            logger.error(f"Failed to create LangChain tool for {tool_name}: {e}")

    return langchain_tools


def langchain_result_to_tool_result(result: Any) -> ToolResult:
    """
    Convert LangChain tool result to ToolResult.

    Args:
        result: Result from LangChain tool execution

    Returns:
        ToolResult instance
    """
    return validate_tool_result(result)


def wrap_langchain_tool_with_tool_result(langchain_tool: BaseTool) -> BaseTool:
    """
    Wrap a LangChain tool to return ToolResult instead of raw output.

    This is useful for legacy LangChain tools that you want to upgrade
    to use the unified ToolResult format.

    Args:
        langchain_tool: Original LangChain tool

    Returns:
        Wrapped tool that returns ToolResult
    """
    original_func = langchain_tool.func

    def wrapped_func(*args, **kwargs) -> str:
        """Wrapped function that converts output to ToolResult."""
        try:
            result = original_func(*args, **kwargs)
            tool_result = validate_tool_result(result)
            return tool_result.to_json()
        except Exception as e:
            tool_result = ToolResult(
                success=False,
                output=str(e),
                error=str(e),
                metadata={"error_type": type(e).__name__}
            )
            return tool_result.to_json()

    # Create new tool with wrapped function
    wrapped_tool = type(langchain_tool)(
        name=langchain_tool.name,
        description=langchain_tool.description,
        func=wrapped_func
    )

    return wrapped_tool


def batch_convert_weaver_tools(
    weaver_tools: List[WeaverTool],
    return_direct: bool = False
) -> List[BaseTool]:
    """
    Convert multiple WeaverTool instances to LangChain tools in batch.

    Args:
        weaver_tools: List of WeaverTool instances
        return_direct: Whether tools should return directly

    Returns:
        Flat list of LangChain BaseTool instances
    """
    all_tools = []

    for weaver_tool in weaver_tools:
        tools = weaver_tool_to_langchain(weaver_tool, return_direct=return_direct)
        all_tools.extend(tools)

    logger.info(f"Converted {len(weaver_tools)} WeaverTools into {len(all_tools)} LangChain tools")
    return all_tools


# Example usage
if __name__ == "__main__":
    print("=" * 60)
    print("LangChain Adapter Test")
    print("=" * 60)

    # Import example tool
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from tools.examples.example_enhanced_tool import EnhancedSearchTool, DataAnalysisTool

    # Create WeaverTool instances
    search_tool = EnhancedSearchTool(api_key="test-key")
    data_tool = DataAnalysisTool()

    print("\n1. Converting WeaverTools to LangChain...")

    # Convert to LangChain tools
    langchain_tools = batch_convert_weaver_tools([search_tool, data_tool])

    print(f"   Created {len(langchain_tools)} LangChain tools:")
    for tool in langchain_tools:
        print(f"   - {tool.name}: {tool.description[:60]}...")

    # Test individual tool execution
    print("\n2. Testing tool execution...")

    search_langchain = langchain_tools[0]  # search_web
    try:
        result = search_langchain.invoke({
            "query": "artificial intelligence",
            "max_results": 3,
            "search_type": "general"
        })
        print(f"   Search result (first 200 chars):")
        print(f"   {result[:200]}...")
    except Exception as e:
        print(f"   Error: {e}")

    # Test data analysis tool
    if len(langchain_tools) >= 4:
        analyze_langchain = langchain_tools[3]  # analyze_data
        try:
            result = analyze_langchain.invoke({
                "data": [1, 2, 3, 4, 5],
                "operations": ["mean", "std"]
            })
            print(f"\n   Analysis result:")
            print(f"   {result}")
        except Exception as e:
            print(f"   Error: {e}")

    # Test selective conversion
    print("\n3. Testing selective method conversion...")
    search_only = weaver_tool_to_langchain(search_tool, method_name="search")
    print(f"   Converted only 'search' method: {len(search_only)} tool(s)")

    print("\n" + "=" * 60)
    print("[OK] LangChain adapter test completed!")
    print("=" * 60)
