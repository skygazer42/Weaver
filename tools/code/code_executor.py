from langchain.tools import tool
from typing import Dict, Any
from common.config import settings
import logging

from common.e2b_env import prepare_e2b_env

logger = logging.getLogger(__name__)


_E2B_PLACEHOLDER_KEYS = {
    "e2b_...",  # common placeholder
    # The repo's .env.example ships with a non-working sample key; treat as placeholder.
    "e2b_39ce8c3d299470afd09b42629c436edec32728d8",
}


@tool
def execute_python_code(code: str) -> Dict[str, Any]:
    """
    Execute Python code in a sandboxed E2B environment.

    Args:
        code: Python code to execute

    Returns:
        Execution results including stdout, stderr, and any generated images
    """
    e2b_key = (settings.e2b_api_key or "").strip()
    if not e2b_key or e2b_key in _E2B_PLACEHOLDER_KEYS:
        return {
            "success": False,
            "stdout": "",
            "stderr": "",
            "error": (
                "E2B_API_KEY is required to execute code with the E2B sandbox. "
                "Get one at https://e2b.dev/docs/api-key"
            ),
            "image": None,
        }

    try:
        from e2b_code_interpreter import Sandbox  # type: ignore
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": "",
            "error": (
                "Missing dependency: e2b-code-interpreter. "
                "Install with `pip install e2b-code-interpreter`."
            ),
            "image": None,
        }

    try:
        prepare_e2b_env()
        with Sandbox(api_key=e2b_key) as sandbox:
            execution = sandbox.run_code(code)

            result = {
                "success": not execution.error,
                "stdout": execution.logs.stdout if execution.logs else "",
                "stderr": execution.logs.stderr if execution.logs else "",
                "error": str(execution.error) if execution.error else None,
                "image": None,
            }

            # Check for matplotlib/image output
            if execution.results:
                for res in execution.results:
                    if hasattr(res, "png") and res.png:
                        result["image"] = res.png  # Base64 encoded
                        break
                    if hasattr(res, "jpeg") and res.jpeg:
                        result["image"] = res.jpeg
                        break

            logger.info(f"Code execution completed. Success: {result['success']}")
            return result
    except Exception as e:
        logger.error(f"Code execution failed: {e}")
        return {
            "success": False,
            "stdout": "",
            "stderr": "",
            "error": str(e),
            "image": None,
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
