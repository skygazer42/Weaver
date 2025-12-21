"""
Prompt Manager for Weaver Agent System.

Provides centralized prompt management with support for:
- Simple vs Enhanced prompt modes
- Custom prompt loading
- Context-aware prompt building
- Easy A/B testing
"""

from typing import Optional, Dict, Any
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class PromptManager:
    """
    Centralized prompt management for Weaver agents.

    Supports multiple prompt styles:
    - "simple": Concise, minimal prompts
    - "enhanced": Detailed prompts with best practices (Manus-inspired)
    - "custom": Load from custom file paths
    """

    def __init__(self, prompt_style: str = "enhanced"):
        """
        Initialize PromptManager.

        Args:
            prompt_style: "simple", "enhanced", or "custom"
        """
        self.prompt_style = prompt_style
        self._custom_prompts: Dict[str, str] = {}

    def set_custom_prompt(self, prompt_type: str, content: str):
        """
        Set a custom prompt for a specific type.

        Args:
            prompt_type: "agent", "writer", "planner", etc.
            content: Prompt content string
        """
        self._custom_prompts[prompt_type] = content
        logger.info(f"Custom {prompt_type} prompt set ({len(content)} chars)")

    def load_custom_prompt(self, prompt_type: str, file_path: str):
        """
        Load a custom prompt from a file.

        Args:
            prompt_type: "agent", "writer", "planner", etc.
            file_path: Path to prompt file
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Prompt file not found: {file_path}")

        content = path.read_text(encoding='utf-8')
        self.set_custom_prompt(prompt_type, content)
        logger.info(f"Loaded custom {prompt_type} prompt from {file_path}")

    def get_agent_prompt(self, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Get the agent system prompt.

        Args:
            context: Optional context dict with:
                - current_time: datetime object
                - enabled_tools: list of tool names

        Returns:
            Agent system prompt string
        """
        # Check for custom prompt first
        if "agent" in self._custom_prompts:
            return self._custom_prompts["agent"]

        # Return based on style
        if self.prompt_style == "simple":
            from agent.agent_prompts import get_default_agent_prompt
            return get_default_agent_prompt()

        elif self.prompt_style == "enhanced":
            from agent.prompts_enhanced import get_agent_prompt
            return get_agent_prompt(mode="agent", context=context)

        # Default to enhanced
        from agent.prompts_enhanced import get_agent_prompt
        return get_agent_prompt(mode="agent", context=context)

    def get_writer_prompt(self) -> str:
        """
        Get the writer system prompt.

        Returns:
            Writer system prompt string
        """
        # Check for custom prompt first
        if "writer" in self._custom_prompts:
            return self._custom_prompts["writer"]

        # Return based on style
        if self.prompt_style == "simple":
            return """You are an expert research analyst. Write a concise, well-structured report with markdown headings, inline source tags like [S1-1], and a Sources section at the end."""

        elif self.prompt_style == "enhanced":
            from agent.prompts_enhanced import get_writer_prompt
            return get_writer_prompt()

        # Default to enhanced
        from agent.prompts_enhanced import get_writer_prompt
        return get_writer_prompt()

    def get_planner_prompt(self) -> str:
        """
        Get the planner guidance prompt.

        Returns:
            Planner guidance string
        """
        # Check for custom prompt first
        if "planner" in self._custom_prompts:
            return self._custom_prompts["planner"]

        # Return based on style
        if self.prompt_style == "simple":
            return "You are a research planner. Generate 3-7 targeted search queries and reasoning."

        elif self.prompt_style == "enhanced":
            return """You are creating a research plan. Follow these principles:

1. **Break Down the Question**
   - Identify key concepts and sub-questions
   - Determine information types needed (facts, statistics, opinions, examples)

2. **Design Search Strategy**
   - Formulate 3-7 specific search queries
   - Each query should target a different aspect
   - Use specific, targeted queries rather than broad ones
   - Examples:
     * Broad: "climate change"
     * Specific: "latest IPCC report 2024 key findings"
     * Specific: "renewable energy adoption statistics 2024"

3. **Consider Multiple Perspectives**
   - Authoritative sources
   - Recent developments
   - Diverse viewpoints

Return JSON with queries and reasoning."""

        # Default to enhanced
        return self.get_planner_prompt()

    def get_deep_research_prompt(self) -> str:
        """
        Get the deep research methodology prompt.

        Returns:
            Deep research prompt string
        """
        # Check for custom prompt first
        if "deep_research" in self._custom_prompts:
            return self._custom_prompts["deep_research"]

        # Only available in enhanced mode
        if self.prompt_style == "enhanced":
            from agent.prompts_enhanced import get_deep_research_prompt
            return get_deep_research_prompt()

        # Fallback to agent prompt
        return self.get_agent_prompt()

    def get_direct_answer_prompt(self) -> str:
        """
        Get the direct answer prompt.

        Returns:
            Direct answer prompt string
        """
        # Check for custom prompt first
        if "direct_answer" in self._custom_prompts:
            return self._custom_prompts["direct_answer"]

        # Simple prompt for quick answers
        return "You are a helpful assistant. Answer succinctly and accurately."


# ============================================================================
# Global PromptManager Instance
# ============================================================================

# Default instance (can be overridden)
_default_prompt_manager: Optional[PromptManager] = None


def get_prompt_manager() -> PromptManager:
    """
    Get the global PromptManager instance.

    Returns:
        PromptManager instance
    """
    global _default_prompt_manager

    if _default_prompt_manager is None:
        # Try to get style from settings
        try:
            from common.config import settings
            style = getattr(settings, 'prompt_style', 'enhanced')
        except:
            style = 'enhanced'

        _default_prompt_manager = PromptManager(prompt_style=style)
        logger.info(f"Initialized PromptManager with style: {style}")

    return _default_prompt_manager


def set_prompt_manager(manager: PromptManager):
    """
    Set the global PromptManager instance.

    Args:
        manager: PromptManager instance to use
    """
    global _default_prompt_manager
    _default_prompt_manager = manager
    logger.info(f"Set global PromptManager to: {manager.prompt_style}")


def reset_prompt_manager():
    """Reset the global PromptManager instance."""
    global _default_prompt_manager
    _default_prompt_manager = None
    logger.info("Reset global PromptManager")


# ============================================================================
# Convenience Functions (for backward compatibility)
# ============================================================================

def get_agent_system_prompt(context: Optional[Dict[str, Any]] = None) -> str:
    """
    Get agent system prompt using global PromptManager.

    Args:
        context: Optional context dict

    Returns:
        Agent system prompt
    """
    return get_prompt_manager().get_agent_prompt(context=context)


def get_writer_system_prompt() -> str:
    """
    Get writer system prompt using global PromptManager.

    Returns:
        Writer system prompt
    """
    return get_prompt_manager().get_writer_prompt()


def get_planner_guidance() -> str:
    """
    Get planner guidance using global PromptManager.

    Returns:
        Planner guidance
    """
    return get_prompt_manager().get_planner_prompt()
