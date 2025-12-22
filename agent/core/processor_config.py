"""
Agent Processor Configuration - Config-driven behavior control

This module provides configuration classes for controlling agent behavior:
- Tool calling modes (XML vs Native)
- Execution strategies (sequential vs parallel)
- Auto-continuation settings
- Streaming options
- Context management

Design Philosophy:
All agent behavior should be controllable via configuration, allowing
easy switching between different strategies without code changes.

Inspired by Manus AgentPress ProcessorConfig.
"""

from dataclasses import dataclass, field
from typing import Literal, Optional, Dict, Any
import logging

from common.config import settings

logger = logging.getLogger(__name__)


@dataclass
class AgentProcessorConfig:
    """
    Configuration for agent response processing.

    Controls all aspects of how the agent processes LLM responses,
    executes tools, and manages conversation flow.
    """

    # ==================== Tool Calling Modes ====================

    xml_tool_calling: bool = True
    """Enable XML-based tool calling (Claude-friendly format)."""

    native_tool_calling: bool = True
    """Enable native tool calling (OpenAI function calling format)."""

    prefer_xml_over_native: bool = False
    """
    If both XML and native calls detected, which to prefer.
    False = prefer native (default for compatibility)
    True = prefer XML (better for Claude)
    """

    # ==================== Tool Execution ====================

    execute_tools: bool = True
    """Whether to automatically execute tools or just detect them."""

    tool_execution_strategy: Literal["sequential", "parallel"] = "sequential"
    """
    How to execute multiple tools in one turn:
    - sequential: Execute one by one (safer, preserves order)
    - parallel: Execute concurrently (faster, no ordering guarantee)
    """

    max_tool_calls_per_turn: int = 10
    """Maximum number of tool calls allowed in a single turn (0 = unlimited)."""

    tool_execution_timeout: int = 30
    """Timeout for individual tool execution in seconds."""

    # ==================== Auto-Continue Mechanism ====================

    enable_auto_continue: bool = False
    """
    Enable automatic continuation when finish_reason=tool_calls.

    When enabled, the agent will automatically call the LLM again
    with tool results until it produces a final answer (finish_reason=stop).
    """

    max_auto_continues: int = 25
    """Maximum number of auto-continue iterations (prevents infinite loops)."""

    auto_continue_on_xml: bool = True
    """Whether to auto-continue when XML tool calls are detected."""

    auto_continue_on_native: bool = True
    """Whether to auto-continue when native tool calls are detected."""

    # ==================== Streaming Options ====================

    stream_tool_results: bool = True
    """Stream tool execution results in real-time."""

    stream_thinking: bool = True
    """Stream thinking/reasoning before tool calls."""

    execute_on_stream: bool = False
    """
    Execute tools during streaming (as soon as detected) vs after completion.
    False = wait for complete response before executing (safer, default)
    True = execute as soon as tool call detected in stream (faster)
    """

    # ==================== Context Management ====================

    enable_context_compression: bool = True
    """Enable automatic context compression when token limit approached."""

    max_context_tokens: int = 128000
    """Maximum context tokens before compression is triggered."""

    preserve_recent_tool_calls: int = 5
    """Number of recent tool calls to preserve during compression."""

    # ==================== Error Handling ====================

    retry_on_tool_error: bool = True
    """Retry tool execution on error (with exponential backoff)."""

    max_retries: int = 3
    """Maximum number of retries for failed tool calls."""

    retry_backoff_factor: float = 1.5
    """Exponential backoff factor for retries."""

    continue_on_tool_failure: bool = True
    """
    Continue agent execution even if some tools fail.
    False = halt on first tool error
    True = collect errors and continue (default)
    """

    # ==================== Result Injection Strategy ====================

    result_injection_strategy: Literal["user_message", "assistant_message", "tool_message"] = "tool_message"
    """
    How to inject tool results back into conversation:
    - user_message: As a user message (Claude style)
    - assistant_message: Append to assistant message (inline)
    - tool_message: As separate tool message (OpenAI style, default)
    """

    # ==================== Debugging & Logging ====================

    log_tool_calls: bool = True
    """Log all tool calls and results."""

    log_auto_continues: bool = True
    """Log auto-continue iterations."""

    include_raw_xml_in_events: bool = False
    """Include raw XML in events (useful for debugging, increases payload size)."""

    # ==================== Advanced Options ====================

    custom_tool_selector: Optional[callable] = None
    """Custom function to filter/select which tools to execute."""

    tool_call_preprocessor: Optional[callable] = None
    """Custom function to preprocess tool calls before execution."""

    tool_result_postprocessor: Optional[callable] = None
    """Custom function to postprocess tool results before injection."""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Additional custom metadata."""

    def __post_init__(self):
        """Validate configuration after initialization."""
        # Validate execution strategy
        if self.tool_execution_strategy not in ["sequential", "parallel"]:
            raise ValueError(
                f"Invalid tool_execution_strategy: {self.tool_execution_strategy}. "
                "Must be 'sequential' or 'parallel'."
            )

        # Validate result injection strategy
        valid_injection = ["user_message", "assistant_message", "tool_message"]
        if self.result_injection_strategy not in valid_injection:
            raise ValueError(
                f"Invalid result_injection_strategy: {self.result_injection_strategy}. "
                f"Must be one of {valid_injection}."
            )

        # Warn if both tool calling modes are disabled
        if not self.xml_tool_calling and not self.native_tool_calling:
            logger.warning("Both XML and native tool calling are disabled!")

        # Warn if auto-continue is enabled but tool execution is disabled
        if self.enable_auto_continue and not self.execute_tools:
            logger.warning(
                "Auto-continue is enabled but tool execution is disabled. "
                "Auto-continue will have no effect."
            )

        # Validate max values
        if self.max_auto_continues < 1:
            raise ValueError("max_auto_continues must be >= 1")

        if self.max_tool_calls_per_turn < 0:
            raise ValueError("max_tool_calls_per_turn must be >= 0")

        logger.debug(f"AgentProcessorConfig initialized: {self.summary()}")

    def summary(self) -> str:
        """Get a summary string of the configuration."""
        return (
            f"AgentProcessorConfig("
            f"xml={self.xml_tool_calling}, "
            f"native={self.native_tool_calling}, "
            f"execute={self.execute_tools}, "
            f"auto_continue={self.enable_auto_continue}, "
            f"strategy={self.tool_execution_strategy}"
            f")"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            # Tool calling
            "xml_tool_calling": self.xml_tool_calling,
            "native_tool_calling": self.native_tool_calling,
            "prefer_xml_over_native": self.prefer_xml_over_native,

            # Execution
            "execute_tools": self.execute_tools,
            "tool_execution_strategy": self.tool_execution_strategy,
            "max_tool_calls_per_turn": self.max_tool_calls_per_turn,

            # Auto-continue
            "enable_auto_continue": self.enable_auto_continue,
            "max_auto_continues": self.max_auto_continues,

            # Streaming
            "stream_tool_results": self.stream_tool_results,
            "stream_thinking": self.stream_thinking,

            # Context
            "max_context_tokens": self.max_context_tokens,

            # Error handling
            "retry_on_tool_error": self.retry_on_tool_error,
            "max_retries": self.max_retries,

            # Result injection
            "result_injection_strategy": self.result_injection_strategy,

            # Metadata
            "metadata": self.metadata
        }

    @classmethod
    def from_settings(cls) -> "AgentProcessorConfig":
        """
        Create configuration from application settings.

        Reads configuration from common.config.settings.
        """
        return cls(
            # Read from settings if available, otherwise use defaults
            xml_tool_calling=getattr(settings, 'agent_xml_tool_calling', True),
            native_tool_calling=getattr(settings, 'agent_native_tool_calling', True),
            execute_tools=getattr(settings, 'agent_execute_tools', True),
            enable_auto_continue=getattr(settings, 'agent_auto_continue', False),
            max_auto_continues=getattr(settings, 'agent_max_auto_continues', 25),
            tool_execution_strategy=getattr(settings, 'agent_tool_execution_strategy', 'sequential'),
            max_tool_calls_per_turn=getattr(settings, 'tool_call_limit', 10),
            retry_on_tool_error=getattr(settings, 'tool_retry', False),
            max_retries=getattr(settings, 'tool_retry_max_attempts', 3),
        )

    @classmethod
    def for_claude(cls) -> "AgentProcessorConfig":
        """
        Preset configuration optimized for Claude models.

        - Enables XML tool calling
        - Disables native calling
        - Uses sequential execution (Claude works better with clear order)
        """
        return cls(
            xml_tool_calling=True,
            native_tool_calling=False,
            prefer_xml_over_native=True,
            tool_execution_strategy="sequential",
            enable_auto_continue=True,
            stream_thinking=True,
            result_injection_strategy="user_message"
        )

    @classmethod
    def for_openai(cls) -> "AgentProcessorConfig":
        """
        Preset configuration optimized for OpenAI models.

        - Disables XML tool calling
        - Enables native calling (OpenAI function calling)
        - Uses parallel execution for speed
        """
        return cls(
            xml_tool_calling=False,
            native_tool_calling=True,
            tool_execution_strategy="parallel",
            enable_auto_continue=True,
            result_injection_strategy="tool_message"
        )

    @classmethod
    def for_development(cls) -> "AgentProcessorConfig":
        """
        Preset configuration for development/debugging.

        - Enables both XML and native
        - Extensive logging
        - No auto-continue (for easier debugging)
        - Sequential execution (easier to trace)
        """
        return cls(
            xml_tool_calling=True,
            native_tool_calling=True,
            tool_execution_strategy="sequential",
            enable_auto_continue=False,
            log_tool_calls=True,
            log_auto_continues=True,
            include_raw_xml_in_events=True,
            retry_on_tool_error=False  # Fail fast for debugging
        )


# Default configuration instance
default_config = AgentProcessorConfig()


# Example usage
if __name__ == "__main__":
    print("=" * 60)
    print("Agent Processor Configuration Test")
    print("=" * 60)

    # Test 1: Default configuration
    print("\n1. Default Configuration:")
    config1 = AgentProcessorConfig()
    print(f"   {config1.summary()}")
    print(f"   Tool calling: XML={config1.xml_tool_calling}, Native={config1.native_tool_calling}")
    print(f"   Auto-continue: {config1.enable_auto_continue}")

    # Test 2: Claude-optimized configuration
    print("\n2. Claude-Optimized Configuration:")
    config2 = AgentProcessorConfig.for_claude()
    print(f"   {config2.summary()}")
    print(f"   Tool calling: XML={config2.xml_tool_calling}, Native={config2.native_tool_calling}")
    print(f"   Result injection: {config2.result_injection_strategy}")

    # Test 3: OpenAI-optimized configuration
    print("\n3. OpenAI-Optimized Configuration:")
    config3 = AgentProcessorConfig.for_openai()
    print(f"   {config3.summary()}")
    print(f"   Tool calling: XML={config3.xml_tool_calling}, Native={config3.native_tool_calling}")
    print(f"   Execution strategy: {config3.tool_execution_strategy}")

    # Test 4: Development configuration
    print("\n4. Development Configuration:")
    config4 = AgentProcessorConfig.for_development()
    print(f"   {config4.summary()}")
    print(f"   Logging: tool_calls={config4.log_tool_calls}, auto_continues={config4.log_auto_continues}")
    print(f"   Include raw XML: {config4.include_raw_xml_in_events}")

    # Test 5: Custom configuration
    print("\n5. Custom Configuration:")
    config5 = AgentProcessorConfig(
        xml_tool_calling=True,
        native_tool_calling=True,
        enable_auto_continue=True,
        max_auto_continues=10,
        tool_execution_strategy="parallel",
        max_tool_calls_per_turn=5
    )
    print(f"   {config5.summary()}")
    print(f"   Max auto-continues: {config5.max_auto_continues}")
    print(f"   Max tools per turn: {config5.max_tool_calls_per_turn}")

    # Test 6: Dictionary conversion
    print("\n6. Dictionary Conversion:")
    config_dict = config2.to_dict()
    print(f"   Keys: {list(config_dict.keys())[:5]}...")
    print(f"   XML calling: {config_dict['xml_tool_calling']}")

    # Test 7: Validation
    print("\n7. Validation Test:")
    try:
        invalid_config = AgentProcessorConfig(tool_execution_strategy="invalid")
    except ValueError as e:
        print(f"   Caught expected error: {e}")

    print("\n" + "=" * 60)
    print("[OK] All configuration tests passed!")
    print("=" * 60)
