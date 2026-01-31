"""
XML Tool Calling Integration Example

This module demonstrates how to integrate XML tool calling support
into Weaver agents using the new Phase 2 components.

Components used:
- XMLToolParser: Parse XML-format tool calls from LLM responses
- AgentProcessorConfig: Configure tool calling behavior
- ResponseHandler: Process responses with tool execution

Usage:
    This can be integrated into agent/nodes.py to add XML tool calling
    support alongside the existing native (OpenAI) format.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import json
from typing import Any, AsyncGenerator, Dict

from agent.core.processor_config import AgentProcessorConfig
from agent.parsers.xml_parser import XMLToolParser
from agent.workflows.response_handler import ResponseHandler
from tools.core.base import ToolResult

# ====================  Mock Tools ====================

async def mock_search_web(query: str, max_results: int = 5) -> ToolResult:
    """Mock web search tool."""
    await asyncio.sleep(0.1)  # Simulate API call

    return ToolResult(
        success=True,
        output=json.dumps({
            "query": query,
            "results": [
                {
                    "title": f"Result {i+1} for '{query}'",
                    "url": f"https://example.com/result/{i+1}",
                    "snippet": f"This is snippet {i+1}..."
                }
                for i in range(min(max_results, 3))
            ],
            "count": min(max_results, 3)
        }),
        metadata={"source": "mock_tavily"}
    )


async def mock_execute_code(code: str) -> ToolResult:
    """Mock Python code executor."""
    await asyncio.sleep(0.2)  # Simulate execution

    try:
        # Simulate execution (don't actually exec in production!)
        return ToolResult(
            success=True,
            output=json.dumps({
                "stdout": f"Simulated execution of code:\n{code[:100]}...",
                "stderr": "",
                "error": None
            }),
            metadata={"sandbox": "mock"}
        )
    except Exception as e:
        return ToolResult(
            success=False,
            output=f"Execution error: {e}",
            error=str(e)
        )


# ==================== Integration Example ====================

async def process_llm_response_with_xml_tools(
    llm_response_text: str,
    tool_registry: Dict[str, Any],
    config: AgentProcessorConfig
) -> Dict[str, Any]:
    """
    Process LLM response that may contain XML tool calls.

    This function demonstrates how to:
    1. Parse XML tool calls from LLM response
    2. Execute tools according to configuration
    3. Collect results for injection back into conversation

    Args:
        llm_response_text: Full text response from LLM
        tool_registry: Available tools {name: callable}
        config: Processor configuration

    Returns:
        Dict with thinking, tool_calls, and results
    """
    parser = XMLToolParser()

    # Extract thinking and tool calls
    thinking, tool_calls = parser.extract_thinking_and_calls(llm_response_text)

    print(f"\n{'='*60}")
    print("Processing LLM Response")
    print(f"{'='*60}")

    if thinking:
        print(f"\nThinking/Reasoning:\n{thinking}\n")

    print(f"Detected {len(tool_calls)} tool call(s)")

    # Execute tools if any
    tool_results = []

    if tool_calls and config.execute_tools:
        print(f"\nExecuting tools ({config.tool_execution_strategy} mode)...")

        handler = ResponseHandler(tool_registry=tool_registry, config=config)

        if config.tool_execution_strategy == "parallel":
            tasks = [
                handler._execute_single_tool(call, "demo-session")
                for call in tool_calls
            ]
            tool_results = await asyncio.gather(*tasks)
        else:
            for i, call in enumerate(tool_calls, 1):
                print(f"\n  [{i}/{len(tool_calls)}] Executing: {call.function_name}")
                result = await handler._execute_single_tool(call, "demo-session")
                tool_results.append(result)

                print(f"      Success: {result.success}")
                if result.success:
                    preview = result.output[:100] + "..." if len(result.output) > 100 else result.output
                    print(f"      Output: {preview}")
                else:
                    print(f"      Error: {result.error}")

    return {
        "thinking": thinking,
        "tool_calls": [call.to_dict() for call in tool_calls],
        "tool_results": [result.to_dict() for result in tool_results],
        "needs_continuation": len(tool_calls) > 0 and config.enable_auto_continue
    }


async def simulate_agent_with_xml_tools():
    """
    Simulate an agent conversation using XML tool calling.

    This demonstrates the full flow:
    1. LLM responds with XML tool calls
    2. Tools are executed
    3. Results would be injected back (simulated here)
    4. LLM continues with the results
    """

    # Setup
    tool_registry = {
        "search_web": mock_search_web,
        "execute_code": mock_execute_code
    }

    # Use Claude-optimized configuration
    config = AgentProcessorConfig.for_claude()
    config.execute_tools = True
    config.enable_auto_continue = True

    print("\n" + "="*70)
    print("XML Tool Calling Integration Demo")
    print("="*70)
    print(f"\nConfiguration:")
    print(f"  {config.summary()}")
    print(f"  Available tools: {list(tool_registry.keys())}")

    # ===== Turn 1: LLM responds with tool call =====

    print("\n" + "="*70)
    print("Turn 1: LLM Response with Tool Call")
    print("="*70)

    llm_response_1 = """
I'll search for information about Python async programming.

<function_calls>
<invoke name="search_web">
<parameter name="query">Python asyncio tutorial 2024</parameter>
<parameter name="max_results">5</parameter>
</invoke>
</function_calls>
"""

    result_1 = await process_llm_response_with_xml_tools(
        llm_response_1,
        tool_registry,
        config
    )

    # ===== Turn 2: LLM analyzes results =====

    if result_1["needs_continuation"]:
        print("\n" + "="*70)
        print("Turn 2: Would inject tool results and call LLM again")
        print("="*70)
        print("\n(In a real agent, tool results would be injected as a user message)")
        print("(LLM would then generate a final response using the tool results)")

    # ===== Example with multiple tools =====

    print("\n\n" + "="*70)
    print("Turn 3: LLM Response with Multiple Tools")
    print("="*70)

    llm_response_2 = """
Let me search and then execute some analysis code.

<function_calls>
<invoke name="search_web">
<parameter name="query">asyncio best practices</parameter>
<parameter name="max_results">3</parameter>
</invoke>
<invoke name="execute_code">
<parameter name="code">
import asyncio

async def demo():
    print("Async demo")
    await asyncio.sleep(1)
    return "Done"

asyncio.run(demo())
</parameter>
</invoke>
</function_calls>
"""

    # Test parallel execution
    config.tool_execution_strategy = "parallel"
    print(f"\nSwitched to parallel execution mode")

    result_2 = await process_llm_response_with_xml_tools(
        llm_response_2,
        tool_registry,
        config
    )

    # ===== Summary =====

    print("\n\n" + "="*70)
    print("Integration Summary")
    print("="*70)

    print(f"""
✅ XML Tool Calling Components:
   - XMLToolParser: Parses XML <function_calls> format
   - AgentProcessorConfig: Configures behavior (Claude vs OpenAI modes)
   - ResponseHandler: Executes tools and manages results

✅ Features Demonstrated:
   - XML tool call parsing with type inference
   - Sequential vs parallel tool execution
   - Auto-continue detection
   - Thinking/reasoning extraction
   - Tool result collection

✅ Integration Points for agent/nodes.py:
   1. In agent_node: Check if response contains XML tool calls
   2. If yes: Use ResponseHandler to execute tools
   3. Inject results back into conversation (as user message for Claude)
   4. If auto_continue enabled: Call LLM again with results
   5. Otherwise: Return accumulated output

✅ Configuration:
   - Set AGENT_XML_TOOL_CALLING=true in .env for XML mode
   - Set AGENT_TOOL_EXECUTION_STRATEGY=sequential|parallel
   - Set AGENT_AUTO_CONTINUE=true for automatic continuation
""")


# ==================== Main ====================

if __name__ == "__main__":
    print("\n" + "="*70)
    print("Running XML Tool Calling Integration Examples")
    print("="*70)

    asyncio.run(simulate_agent_with_xml_tools())

    print("\n" + "="*70)
    print("[OK] Integration examples completed!")
    print("="*70)
    print("""
Next Steps:
1. Review the integration points above
2. Integrate into agent/nodes.py when ready
3. Test with real Claude model
4. Monitor performance and adjust configuration

For full integration, see: docs/XML_INTEGRATION_GUIDE.md
""")
