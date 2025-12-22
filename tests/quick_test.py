"""
Quick smoke test for prompt wiring.

Run manually:
    python tests/quick_test.py
"""

import os
import sys
from pathlib import Path
from datetime import datetime
import inspect

# Ensure project root on path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("OPENAI_API_KEY", "dummy-key")
os.environ.setdefault("DATABASE_URL", "sqlite:///weaver.db")

from agent.prompts.prompt_manager import PromptManager, get_prompt_manager  # noqa: E402
import agent.workflows.nodes as nodes  # noqa: E402


def test_basic_functionality() -> None:
    print("Running prompt smoke test")

    mgr = get_prompt_manager()
    print(f"- PromptManager style: {mgr.prompt_style}")

    agent_prompt = mgr.get_agent_prompt(
        context={
            "current_time": datetime.now(),
            "enabled_tools": ["web_search", "execute_python_code", "crawl_url"],
        }
    )
    print(f"- Agent prompt length: {len(agent_prompt)}")

    writer_prompt = mgr.get_writer_prompt()
    print(f"- Writer prompt length: {len(writer_prompt)}")

    # Verify nodes pull system_prompts (no legacy imports)
    agent_src = inspect.getsource(nodes.agent_node)
    writer_src = inspect.getsource(nodes.writer_node)
    uses_system = "system_prompts" in agent_src and "get_agent_prompt" in agent_src
    writer_system = "system_prompts" in writer_src and "get_writer_prompt" in writer_src
    print(f"- agent_node uses system_prompts: {uses_system}")
    print(f"- writer_node uses system_prompts: {writer_system}")


if __name__ == "__main__":
    test_basic_functionality()
    print("Done.")
