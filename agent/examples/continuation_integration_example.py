"""
Auto-Continuation Integration Example

This module demonstrates how to use the auto-continuation mechanism
to build agents that automatically continue execution across multiple
tool calls without user intervention.

Features demonstrated:
- Auto-continuation configuration
- Multi-turn tool calling loops
- Automatic result injection
- Continuation event handling
- Stop conditions and loop control
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import json
from typing import Any, Dict, List

from agent.core.processor_config import AgentProcessorConfig
from agent.workflows.response_handler import ResponseHandler
from tools.core.base import ToolResult

# ==================== Mock Tools ====================


async def mock_search_web(query: str, max_results: int = 5) -> ToolResult:
    """Mock web search tool."""
    await asyncio.sleep(0.1)

    return ToolResult(
        success=True,
        output=json.dumps(
            {
                "query": query,
                "results": [
                    {"title": f"Result {i + 1}", "url": f"https://example.com/{i + 1}"}
                    for i in range(min(max_results, 3))
                ],
            }
        ),
        metadata={"source": "mock_search"},
    )


async def mock_analyze_text(text: str) -> ToolResult:
    """Mock text analysis tool."""
    await asyncio.sleep(0.1)

    return ToolResult(
        success=True,
        output=json.dumps(
            {"word_count": len(text.split()), "char_count": len(text), "sentiment": "positive"}
        ),
        metadata={"analyzer": "mock"},
    )


async def mock_execute_code(code: str) -> ToolResult:
    """Mock code execution tool."""
    await asyncio.sleep(0.2)

    return ToolResult(
        success=True,
        output=json.dumps(
            {"stdout": f"Executed code:\n{code[:50]}...", "stderr": "", "exit_code": 0}
        ),
        metadata={"runtime": "mock"},
    )


# ==================== Mock LLM Responses ====================


class MockLLMResponseGenerator:
    """
    Simulates multi-turn LLM responses with tool calls.

    This simulates what would happen in a real auto-continue scenario:
    1. LLM responds with tool call
    2. Tools execute and results injected
    3. LLM responds again (possibly with more tool calls)
    4. Repeat until LLM responds without tool calls
    """

    def __init__(self):
        self.call_count = 0

    async def __call__(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Simulate LLM call based on conversation state."""
        self.call_count += 1

        # First call: LLM asks to search
        if self.call_count == 1:
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": """I'll search for information about Python async programming.

<function_calls>
<invoke name="search_web">
<parameter name="query">Python asyncio tutorial 2024</parameter>
<parameter name="max_results">3</parameter>
</invoke>
</function_calls>""",
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            }

        # Second call: LLM has search results, asks to analyze
        elif self.call_count == 2:
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": """Great! I found some search results. Let me analyze the first one.

<function_calls>
<invoke name="analyze_text">
<parameter name="text">Python asyncio tutorial - comprehensive guide to async programming</parameter>
</invoke>
</function_calls>""",
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            }

        # Third call: LLM has both results, provides final answer
        else:
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": """Based on the search results and analysis, here's what I found:

1. Python asyncio is a powerful library for asynchronous programming
2. The 2024 tutorials cover modern async/await syntax
3. The sentiment analysis shows positive community reception

This comprehensive guide should help you get started with Python async programming!""",
                        },
                        "finish_reason": "stop",
                    }
                ]
            }


# ==================== Example: Basic Auto-Continuation ====================


async def example_basic_auto_continuation():
    """
    Basic example of auto-continuation.

    Shows how the agent automatically continues across multiple
    tool calls without manual intervention.
    """

    print("\n" + "=" * 70)
    print("Example 1: Basic Auto-Continuation")
    print("=" * 70)

    # Setup tools
    tool_registry = {
        "search_web": mock_search_web,
        "analyze_text": mock_analyze_text,
        "execute_code": mock_execute_code,
    }

    # Configure for auto-continuation
    config = AgentProcessorConfig(
        xml_tool_calling=True,
        execute_tools=True,
        enable_auto_continue=True,
        max_auto_continues=5,
        tool_execution_strategy="sequential",
        result_injection_strategy="user_message",
    )

    # Create handler
    handler = ResponseHandler(tool_registry=tool_registry, config=config)

    # Initial messages
    messages = [{"role": "user", "content": "Tell me about Python async programming"}]

    # Mock LLM
    mock_llm = MockLLMResponseGenerator()

    print(f"\nConfiguration: {config.summary()}")
    print(f"\nStarting auto-continuation loop...\n")

    # Process with auto-continuation
    iteration_count = 0
    tool_call_count = 0

    async for event in handler.process_with_auto_continue(
        messages=messages, llm_callable=mock_llm, session_id="example-1"
    ):
        event_type = event.get("type")

        if event_type == "continuation_started":
            print("[START] Auto-continuation loop started")

        elif event_type == "continuation_iteration":
            iteration_count = event["iteration"]
            print(f"\n[ITERATION {iteration_count}] Calling LLM...")

        elif event_type == "llm_response":
            content = event["content"]
            preview = content[:80] + "..." if len(content) > 80 else content
            print(f"  LLM response: {preview}")

        elif event_type == "tool_result":
            tool_call_count += 1
            print(
                f"  [TOOL] {event['function_name']}: {'SUCCESS' if event['success'] else 'FAILED'}"
            )

        elif event_type == "results_injected":
            print(f"  [INJECT] {event['count']} result(s) injected back into conversation")

        elif event_type == "continuation_stopped":
            print(f"\n[STOP] Reason: {event['reason']}")

        elif event_type == "continuation_complete":
            print(f"\n[COMPLETE] Auto-continuation finished:")
            print(f"  Total iterations: {event['total_iterations']}")
            print(f"  Total tool calls: {event['total_tool_calls']}")
            print(f"  Stop reason: {event['stop_reason']}")

    print(f"\nFinal message count: {len(messages)}")
    print(f"Tool calls executed: {tool_call_count}")


# ==================== Example: Max Iterations Limit ====================


async def example_max_iterations():
    """
    Demonstrates max iteration limit.

    Shows how the continuation stops when max iterations reached.
    """

    print("\n" + "=" * 70)
    print("Example 2: Max Iterations Limit")
    print("=" * 70)

    # Create an LLM that always asks for tools
    class AlwaysToolsLLM:
        def __init__(self):
            self.count = 0

        async def __call__(self, messages):
            self.count += 1
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": f"""Iteration {self.count}:
<function_calls>
<invoke name="search_web">
<parameter name="query">test query {self.count}</parameter>
</invoke>
</function_calls>""",
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            }

    tool_registry = {"search_web": mock_search_web}

    # Set low max limit
    config = AgentProcessorConfig(
        xml_tool_calling=True,
        execute_tools=True,
        enable_auto_continue=True,
        max_auto_continues=3,  # Low limit
        tool_execution_strategy="sequential",
    )

    handler = ResponseHandler(tool_registry=tool_registry, config=config)
    messages = [{"role": "user", "content": "Start"}]
    mock_llm = AlwaysToolsLLM()

    print(f"\nMax iterations set to: {config.max_auto_continues}")
    print(f"Starting loop...\n")

    async for event in handler.process_with_auto_continue(
        messages=messages, llm_callable=mock_llm, session_id="example-2"
    ):
        if event.get("type") == "continuation_iteration":
            print(f"  Iteration {event['iteration']}")

        elif event.get("type") == "continuation_complete":
            print(f"\n[COMPLETE] Stopped after {event['total_iterations']} iterations")
            print(f"  Reason: {event['stop_reason']}")


# ==================== Example: Parallel Tool Execution ====================


async def example_parallel_execution():
    """
    Demonstrates parallel tool execution in auto-continuation.

    Shows how multiple tools can be executed concurrently.
    """

    print("\n" + "=" * 70)
    print("Example 3: Parallel Tool Execution")
    print("=" * 70)

    # LLM that calls multiple tools at once
    class MultiToolLLM:
        def __init__(self):
            self.called = False

        async def __call__(self, messages):
            if not self.called:
                self.called = True
                return {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": """I'll do multiple things in parallel:

<function_calls>
<invoke name="search_web">
<parameter name="query">Python asyncio</parameter>
<parameter name="max_results">2</parameter>
</invoke>
<invoke name="analyze_text">
<parameter name="text">Async programming is powerful</parameter>
</invoke>
<invoke name="execute_code">
<parameter name="code">import asyncio\nprint('Hello')</parameter>
</invoke>
</function_calls>""",
                            },
                            "finish_reason": "tool_calls",
                        }
                    ]
                }
            else:
                return {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "All tools completed successfully!",
                            },
                            "finish_reason": "stop",
                        }
                    ]
                }

    tool_registry = {
        "search_web": mock_search_web,
        "analyze_text": mock_analyze_text,
        "execute_code": mock_execute_code,
    }

    # Configure for parallel execution
    config = AgentProcessorConfig(
        xml_tool_calling=True,
        execute_tools=True,
        enable_auto_continue=True,
        max_auto_continues=5,
        tool_execution_strategy="parallel",  # Parallel!
    )

    handler = ResponseHandler(tool_registry=tool_registry, config=config)
    messages = [{"role": "user", "content": "Do multiple things"}]
    mock_llm = MultiToolLLM()

    print(f"\nExecution strategy: {config.tool_execution_strategy}")
    print(f"Starting...\n")

    import time

    start_time = time.time()

    async for event in handler.process_with_auto_continue(
        messages=messages, llm_callable=mock_llm, session_id="example-3"
    ):
        if event.get("type") == "tool_result":
            elapsed = time.time() - start_time
            print(f"  [TOOL] {event['function_name']} completed at {elapsed:.2f}s")

        elif event.get("type") == "continuation_complete":
            elapsed = time.time() - start_time
            print(f"\n[COMPLETE] Total time: {elapsed:.2f}s")
            print(f"  (Parallel execution is faster than sequential)")


# ==================== Integration Summary ====================


async def show_integration_summary():
    """Display integration summary and usage tips."""

    print("\n" + "=" * 70)
    print("Auto-Continuation Integration Summary")
    print("=" * 70)

    print("""
[OK] Auto-Continuation Components:

1. ContinuationState
   - Tracks iteration count, tool calls, finish reasons
   - Provides summary and serialization

2. ContinuationDecider
   - Decides when to continue vs stop
   - Configurable stop conditions
   - Max iteration limits

3. ToolResultInjector
   - Injects tool results back into conversation
   - Supports different injection strategies:
     * user_message (for Claude)
     * assistant_message
     * tool_message (for OpenAI)

4. ContinuationHandler
   - Orchestrates the full continuation loop
   - Integrates decider and injector
   - Returns final state

5. ResponseHandler.process_with_auto_continue()
   - High-level API for auto-continuation
   - Yields real-time events
   - Automatically handles tool execution

[OK] Configuration Options:

- enable_auto_continue: Enable/disable auto-continuation
- max_auto_continues: Maximum iteration limit (default: 25)
- result_injection_strategy: How to inject results
- tool_execution_strategy: sequential | parallel
- continue_on_tool_failure: Continue even if tools fail

[OK] Event Types:

- continuation_started: Loop started
- continuation_iteration: New iteration beginning
- llm_response: LLM responded
- tool_result: Tool execution result
- results_injected: Results injected into conversation
- continuation_stopped: Loop stopped (with reason)
- continuation_complete: Loop finished (with stats)

[OK] Usage Pattern:

```python
# 1. Configure
config = AgentProcessorConfig(
    xml_tool_calling=True,
    enable_auto_continue=True,
    max_auto_continues=10
)

# 2. Create handler
handler = ResponseHandler(tool_registry, config)

# 3. Process with auto-continue
async for event in handler.process_with_auto_continue(
    messages=messages,
    llm_callable=my_llm_function,
    session_id="my-session"
):
    # Handle events
    if event["type"] == "continuation_complete":
        print(f"Done! {event['total_iterations']} iterations")
```

[OK] Benefits:

- Automatic multi-turn tool calling
- No manual result injection needed
- Configurable stop conditions
- Real-time event streaming
- Detailed state tracking
- Prevents infinite loops

[OK] Use Cases:

1. Research agents: Search → Analyze → Synthesize
2. Code assistants: Plan → Code → Test → Fix
3. Data pipelines: Fetch → Transform → Store
4. Multi-step tasks: Any workflow with dependencies

""")


# ==================== Main ====================


async def main():
    """Run all examples."""

    print("\n" + "=" * 70)
    print("Auto-Continuation Mechanism Examples")
    print("=" * 70)

    # Run examples
    await example_basic_auto_continuation()
    await example_max_iterations()
    await example_parallel_execution()
    await show_integration_summary()

    print("\n" + "=" * 70)
    print("[OK] All examples completed!")
    print("=" * 70)
    print("\nNext Steps:")
    print("1. Review the event handling patterns")
    print("2. Adapt the configuration to your use case")
    print("3. Implement your own LLM callable")
    print("4. Add your custom tools to the registry")
    print("5. Monitor continuation_state for debugging")
    print("\nFor more details, see: docs/PHASE3_COMPLETION_SUMMARY.md")


if __name__ == "__main__":
    asyncio.run(main())
