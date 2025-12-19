from langchain.tools import tool
from typing import Dict, Any
from common.config import settings
import logging

logger = logging.getLogger(__name__)


@tool
def execute_python_code(code: str) -> Dict[str, Any]:
    """
    Execute Python code in a sandboxed E2B environment.

    Args:
        code: Python code to execute

    Returns:
        Execution results including stdout, stderr, and any generated images
    """
    try:
        from e2b_code_interpreter import Sandbox
        if not settings.e2b_api_key:
            return {
                "success": False,
                "error": "E2B API key not configured",
                "stdout": "",
                "image": None
            }

        with Sandbox(api_key=settings.e2b_api_key) as sandbox:
            execution = sandbox.run_code(code)

            result = {
                "success": not execution.error,
                "stdout": execution.logs.stdout if execution.logs else "",
                "stderr": execution.logs.stderr if execution.logs else "",
                "error": str(execution.error) if execution.error else None,
                "image": None
            }

            # Check for matplotlib/image output
            if execution.results:
                for res in execution.results:
                    if hasattr(res, 'png') and res.png:
                        result["image"] = res.png  # Base64 encoded
                        break
                    elif hasattr(res, 'jpeg') and res.jpeg:
                        result["image"] = res.jpeg
                        break

            logger.info(f"Code execution completed. Success: {result['success']}")
            return result

    except ImportError:
        logger.warning("E2B not installed. Install with: pip install e2b-code-interpreter")
        return {
            "success": False,
            "error": "E2B Code Interpreter not installed",
            "stdout": "",
            "image": None
        }
    except Exception as e:
        logger.error(f"Code execution error: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "stdout": "",
            "image": None
        }


def create_visualization(data: Dict[str, Any], chart_type: str = "bar") -> Dict[str, Any]:
    """
    Helper function to create data visualizations.

    Args:
        data: Data to visualize
        chart_type: Type of chart (bar, line, pie, scatter)

    Returns:
        Execution result with generated chart
    """
    # Generate matplotlib code based on chart type
    code_template = f"""
import matplotlib.pyplot as plt
import numpy as np

# Your data
data = {data}

# Create chart
plt.figure(figsize=(10, 6))
# Add chart code here based on chart_type: {chart_type}
plt.title('Generated Chart')
plt.tight_layout()
plt.show()
"""

    return execute_python_code(code_template)
