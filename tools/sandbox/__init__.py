"""
Sandbox Tools Package - E2B 沙盒工具集合

包含在 E2B 沙盒环境中运行的所有工具:
- 浏览器操作
- 文件操作
- Shell 命令
- 电子表格生成
- 演示文稿生成
- 图像处理
- Web 搜索
"""

from tools.sandbox.sandbox_browser_session import (
    sandbox_browser_sessions,
    SandboxBrowserSession,
)
from tools.sandbox.sandbox_browser_tools import build_sandbox_browser_tools
from tools.sandbox.sandbox_files_tool import build_sandbox_files_tools
from tools.sandbox.sandbox_shell_tool import build_sandbox_shell_tools
from tools.sandbox.sandbox_sheets_tool import build_sandbox_sheets_tools
from tools.sandbox.sandbox_presentation_tool import build_sandbox_presentation_tools
from tools.sandbox.sandbox_presentation_outline_tool import build_presentation_outline_tools
from tools.sandbox.sandbox_presentation_tool_v2 import build_presentation_v2_tools
from tools.sandbox.sandbox_vision_tool import build_sandbox_vision_tools
from tools.sandbox.sandbox_image_edit_tool import build_image_edit_tools
from tools.sandbox.sandbox_web_search_tool import build_sandbox_web_search_tools
from tools.sandbox.sandbox_web_dev_tool import build_sandbox_web_dev_tools

__all__ = [
    # Session management
    "sandbox_browser_sessions",
    "SandboxBrowserSession",
    # Tool builders
    "build_sandbox_browser_tools",
    "build_sandbox_files_tools",
    "build_sandbox_shell_tools",
    "build_sandbox_sheets_tools",
    "build_sandbox_presentation_tools",
    "build_presentation_outline_tools",
    "build_presentation_v2_tools",
    "build_sandbox_vision_tools",
    "build_image_edit_tools",
    "build_sandbox_web_search_tools",
    "build_sandbox_web_dev_tools",
]
