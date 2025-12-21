"""
Code Executor Tool - Enhanced Version using WeaverTool

This module provides Python code execution in a sandboxed E2B environment.
Enhanced version uses WeaverTool base class for better error handling
and standardized results.

Features:
- Sandboxed Python code execution
- Support for matplotlib/image output
- Structured result format with stdout/stderr separation
- Data visualization helpers
- Backward compatible with LangChain
"""

from tools.base import WeaverTool, ToolResult, tool_schema
from typing import Dict, Any, Optional, List
from common.config import settings
import logging
import json

try:
    from e2b_code_interpreter import Sandbox
    E2B_AVAILABLE = True
except ImportError:
    E2B_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("e2b_code_interpreter not installed. Code execution will be disabled.")

logger = logging.getLogger(__name__)


class CodeExecutorTool(WeaverTool):
    """
    Enhanced Python code executor using E2B sandbox.

    Executes Python code in an isolated environment with support for:
    - Standard output/error capture
    - Image/chart generation (matplotlib)
    - Safe execution (sandboxed)
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize code executor tool.

        Args:
            api_key: E2B API key (defaults to settings.e2b_api_key)
        """
        self.api_key = api_key or settings.e2b_api_key
        if not self.api_key and E2B_AVAILABLE:
            logger.warning("E2B API key not set")
        super().__init__()

    @tool_schema(
        name="execute_python_code",
        description="Execute Python code in a sandboxed E2B environment. Supports data analysis, visualization with matplotlib, and general computation. Returns stdout, stderr, and any generated images.",
        parameters={
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute. Can include imports, data processing, matplotlib plots, etc."
                },
                "timeout": {
                    "type": "integer",
                    "description": "Execution timeout in seconds",
                    "default": 30,
                    "minimum": 1,
                    "maximum": 300
                }
            },
            "required": ["code"]
        }
    )
    def execute(self, code: str, timeout: int = 30) -> ToolResult:
        """
        Execute Python code in a sandboxed environment.

        Args:
            code: Python code to execute
            timeout: Execution timeout in seconds

        Returns:
            ToolResult with execution results including stdout, stderr, and images
        """
        if not E2B_AVAILABLE:
            return self.fail_response(
                "E2B code interpreter not installed. Install with: pip install e2b-code-interpreter",
                metadata={"error_type": "DependencyError"}
            )

        if not self.api_key:
            return self.fail_response(
                "E2B API key not configured",
                metadata={"config_required": "E2B_API_KEY"}
            )

        if not code or not code.strip():
            return self.fail_response(
                "Empty code provided",
                metadata={"error_type": "ValidationError"}
            )

        try:
            with Sandbox(api_key=self.api_key, timeout=timeout) as sandbox:
                execution = sandbox.run_code(code)

                # Extract execution results
                stdout = execution.logs.stdout if execution.logs else ""
                stderr = execution.logs.stderr if execution.logs else ""
                error = str(execution.error) if execution.error else None
                success = not execution.error

                # Check for matplotlib/image output
                images = []
                if execution.results:
                    for res in execution.results:
                        if hasattr(res, 'png') and res.png:
                            images.append({
                                "format": "png",
                                "data": res.png,  # Base64 encoded
                                "type": "image"
                            })
                        elif hasattr(res, 'jpeg') and res.jpeg:
                            images.append({
                                "format": "jpeg",
                                "data": res.jpeg,  # Base64 encoded
                                "type": "image"
                            })

                # Build result data
                result_data = {
                    "success": success,
                    "stdout": stdout,
                    "stderr": stderr,
                    "error": error,
                    "images": images,
                    "has_output": bool(stdout or stderr),
                    "has_images": len(images) > 0
                }

                # Determine output message
                if success:
                    if stdout:
                        output_msg = f"Code executed successfully.\n\nOutput:\n{stdout}"
                    elif images:
                        output_msg = f"Code executed successfully. Generated {len(images)} image(s)."
                    else:
                        output_msg = "Code executed successfully with no output."

                    if images:
                        output_msg += f"\n\nGenerated {len(images)} image(s) (base64 encoded)"

                    return self.success_response(
                        result_data,
                        metadata={
                            "execution_time_ms": getattr(execution, 'execution_time', None),
                            "has_stdout": bool(stdout),
                            "has_stderr": bool(stderr),
                            "image_count": len(images),
                            "sandbox_id": getattr(sandbox, 'id', None)
                        }
                    )
                else:
                    error_msg = f"Code execution failed: {error}"
                    if stderr:
                        error_msg += f"\n\nStderr:\n{stderr}"

                    return self.fail_response(
                        error_msg,
                        metadata={
                            "error_type": "ExecutionError",
                            "stderr": stderr,
                            "has_partial_output": bool(stdout)
                        }
                    )

        except Exception as e:
            logger.error(f"Code execution error: {str(e)}")
            return self.fail_response(
                f"Sandbox error: {str(e)}",
                metadata={
                    "error_type": type(e).__name__,
                    "code_length": len(code)
                }
            )

    @tool_schema(
        name="create_visualization",
        description="Create a data visualization using matplotlib. Automatically generates the matplotlib code and returns the chart as an image.",
        parameters={
            "type": "object",
            "properties": {
                "data": {
                    "type": "object",
                    "description": "Data to visualize (dict or JSON object)"
                },
                "chart_type": {
                    "type": "string",
                    "enum": ["bar", "line", "pie", "scatter", "histogram"],
                    "description": "Type of chart to create",
                    "default": "bar"
                },
                "title": {
                    "type": "string",
                    "description": "Chart title",
                    "default": "Data Visualization"
                },
                "x_label": {
                    "type": "string",
                    "description": "X-axis label",
                    "default": ""
                },
                "y_label": {
                    "type": "string",
                    "description": "Y-axis label",
                    "default": ""
                }
            },
            "required": ["data"]
        }
    )
    def visualize(
        self,
        data: Dict[str, Any],
        chart_type: str = "bar",
        title: str = "Data Visualization",
        x_label: str = "",
        y_label: str = ""
    ) -> ToolResult:
        """
        Create a data visualization.

        Args:
            data: Data to visualize
            chart_type: Type of chart (bar, line, pie, scatter, histogram)
            title: Chart title
            x_label: X-axis label
            y_label: Y-axis label

        Returns:
            ToolResult with generated chart
        """
        # Generate matplotlib code based on chart type
        if chart_type == "bar":
            code = f"""
import matplotlib.pyplot as plt
import json

data = {json.dumps(data)}

# Extract keys and values
if isinstance(data, dict):
    keys = list(data.keys())
    values = list(data.values())
else:
    keys = range(len(data))
    values = data

# Create bar chart
plt.figure(figsize=(10, 6))
plt.bar(keys, values)
plt.title('{title}')
plt.xlabel('{x_label}')
plt.ylabel('{y_label}')
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()
"""
        elif chart_type == "line":
            code = f"""
import matplotlib.pyplot as plt
import json

data = {json.dumps(data)}

if isinstance(data, dict):
    x = list(data.keys())
    y = list(data.values())
else:
    x = range(len(data))
    y = data

plt.figure(figsize=(10, 6))
plt.plot(x, y, marker='o')
plt.title('{title}')
plt.xlabel('{x_label}')
plt.ylabel('{y_label}')
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.show()
"""
        elif chart_type == "pie":
            code = f"""
import matplotlib.pyplot as plt
import json

data = {json.dumps(data)}

if isinstance(data, dict):
    labels = list(data.keys())
    sizes = list(data.values())
else:
    labels = [f'Item {{i+1}}' for i in range(len(data))]
    sizes = data

plt.figure(figsize=(10, 8))
plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=90)
plt.title('{title}')
plt.axis('equal')
plt.tight_layout()
plt.show()
"""
        elif chart_type == "scatter":
            code = f"""
import matplotlib.pyplot as plt
import json

data = {json.dumps(data)}

# Assume data has 'x' and 'y' keys, or is a list of [x,y] pairs
if isinstance(data, dict) and 'x' in data and 'y' in data:
    x = data['x']
    y = data['y']
else:
    # Fallback
    x = range(len(data))
    y = data

plt.figure(figsize=(10, 6))
plt.scatter(x, y, alpha=0.6)
plt.title('{title}')
plt.xlabel('{x_label}')
plt.ylabel('{y_label}')
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.show()
"""
        elif chart_type == "histogram":
            code = f"""
import matplotlib.pyplot as plt
import json

data = {json.dumps(data)}

# Flatten data if needed
if isinstance(data, dict):
    values = list(data.values())
else:
    values = data

plt.figure(figsize=(10, 6))
plt.hist(values, bins=20, alpha=0.7, edgecolor='black')
plt.title('{title}')
plt.xlabel('{x_label}')
plt.ylabel('Frequency')
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.show()
"""
        else:
            return self.fail_response(
                f"Unsupported chart type: {chart_type}",
                metadata={"supported_types": ["bar", "line", "pie", "scatter", "histogram"]}
            )

        # Execute the generated code
        result = self.execute(code)

        if result.success:
            # Add visualization metadata
            result.metadata["chart_type"] = chart_type
            result.metadata["title"] = title
            result.metadata["auto_generated"] = True

        return result


# Backward compatibility: keep original function signature
def execute_python_code(code: str) -> Dict[str, Any]:
    """
    Legacy function for backward compatibility.

    Args:
        code: Python code to execute

    Returns:
        Execution results dict (legacy format)
    """
    tool = CodeExecutorTool()
    result = tool.execute(code)

    if result.success:
        try:
            return json.loads(result.output)
        except json.JSONDecodeError:
            # Fallback to basic format
            return {
                "success": True,
                "stdout": result.output,
                "stderr": "",
                "error": None,
                "image": None
            }
    else:
        return {
            "success": False,
            "stdout": "",
            "stderr": result.error or "",
            "error": result.error,
            "image": None
        }


def create_visualization(data: Dict[str, Any], chart_type: str = "bar") -> Dict[str, Any]:
    """
    Legacy function for backward compatibility.

    Args:
        data: Data to visualize
        chart_type: Type of chart

    Returns:
        Execution result with generated chart
    """
    tool = CodeExecutorTool()
    result = tool.visualize(data, chart_type=chart_type)

    if result.success:
        try:
            return json.loads(result.output)
        except json.JSONDecodeError:
            return {
                "success": True,
                "stdout": "",
                "stderr": "",
                "error": None,
                "image": None
            }
    else:
        return {
            "success": False,
            "stdout": "",
            "stderr": result.error or "",
            "error": result.error,
            "image": None
        }


# Example usage
if __name__ == "__main__":
    print("=" * 60)
    print("Code Executor Tool - Enhanced Version Test")
    print("=" * 60)

    if not settings.e2b_api_key:
        print("\n[!] E2B_API_KEY not set in environment")
        print("    Code execution requires E2B API key")
        print("    Get one at: https://e2b.dev")
    else:
        tool = CodeExecutorTool()

        print(f"\nRegistered methods: {tool.list_methods()}")

        # Test simple execution
        print("\n" + "=" * 60)
        print("Test 1: Simple Calculation")
        print("=" * 60)

        code1 = """
result = 2 + 2
print(f"2 + 2 = {result}")
"""
        result1 = tool.execute(code1)
        print(f"Success: {result1.success}")
        print(f"Output: {result1.output[:200] if len(result1.output) > 200 else result1.output}")

        # Test visualization
        print("\n" + "=" * 60)
        print("Test 2: Data Visualization")
        print("=" * 60)

        data = {"A": 10, "B": 25, "C": 15, "D": 30}
        result2 = tool.visualize(data, chart_type="bar", title="Sample Bar Chart")
        print(f"Success: {result2.success}")
        if result2.metadata:
            print(f"Generated images: {result2.metadata.get('image_count', 0)}")

    print("\n" + "=" * 60)
    print("[OK] Tests completed!")
    print("=" * 60)
