"""
Enhanced Response Handler - Process LLM responses with XML tool calling

This module provides enhanced response processing that supports both
XML-based (Claude) and native (OpenAI) tool calling formats.

Features:
- Streaming response processing
- Dual-mode tool call detection (XML + Native)
- Configurable execution strategy (sequential/parallel)
- Tool result injection
- Event streaming for real-time updates

Design Philosophy:
Process LLM responses incrementally, detect tool calls early, execute
tools according to configuration, and inject results back into the
conversation flow.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

from agent.core.processor_config import AgentProcessorConfig
from agent.parsers.xml_parser import XMLToolCall, XMLToolParser
from agent.workflows.continuation import (
    ContinuationDecider,
    ContinuationHandler,
    ContinuationState,
    ToolResultInjector,
)
from tools.core.base import ToolResult, validate_tool_result

CONTINUATION_AVAILABLE = True

logger = logging.getLogger(__name__)


class ResponseHandler:
    """
    Enhanced response handler with XML tool calling support.

    Processes LLM responses, detects tool calls (XML or native),
    executes tools, and manages result injection.
    """

    def __init__(
        self,
        tool_registry: Optional[Dict[str, Callable]] = None,
        config: Optional[AgentProcessorConfig] = None,
    ):
        """
        Initialize response handler.

        Args:
            tool_registry: Dictionary of available tools {name: callable}
            config: Processor configuration
        """
        self.tool_registry = tool_registry or {}
        self.config = config or AgentProcessorConfig()
        self.xml_parser = XMLToolParser()

        # Initialize continuation handler if available and enabled
        self.continuation_handler = None
        if CONTINUATION_AVAILABLE and config and config.enable_auto_continue:
            decider = ContinuationDecider(
                max_iterations=config.max_auto_continues,
                continue_on_tool_calls=True,
                stop_on_tool_failure=not config.continue_on_tool_failure,
            )
            injector = ToolResultInjector(strategy=config.result_injection_strategy)
            self.continuation_handler = ContinuationHandler(decider=decider, injector=injector)
            logger.info("Auto-continuation enabled")

        logger.info(f"ResponseHandler initialized with config: {self.config.summary()}")

    async def process_streaming_response(
        self, response_stream: AsyncGenerator, session_id: str = "default"
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Process streaming LLM response with tool call detection and execution.

        Args:
            response_stream: Async generator yielding response chunks
            session_id: Session identifier for logging

        Yields:
            Event dictionaries with type and data
        """
        accumulated_content = ""
        detected_xml_calls: List[XMLToolCall] = []
        thinking_sent = False

        try:
            async for chunk in response_stream:
                # Extract content from chunk
                content = self._extract_content(chunk)

                if content:
                    accumulated_content += content

                    # Yield text delta for streaming
                    yield {
                        "type": "text_delta",
                        "content": content,
                        "session_id": session_id,
                        "timestamp": datetime.now().isoformat(),
                    }

                    # Check for XML tool calls if enabled
                    if self.config.xml_tool_calling and "<function_calls>" in accumulated_content:
                        # Try to parse XML calls
                        new_calls = self.xml_parser.parse_streaming_content(
                            accumulated_content, detected_xml_calls
                        )

                        for call in new_calls:
                            detected_xml_calls.append(call)

                            # Yield tool call detected event
                            yield {
                                "type": "tool_call_detected",
                                "format": "xml",
                                "function_name": call.function_name,
                                "parameters": call.parameters,
                                "session_id": session_id,
                                "timestamp": datetime.now().isoformat(),
                            }

                            logger.info(
                                f"[{session_id}] Detected XML tool call: "
                                f"{call.function_name} with {len(call.parameters)} params"
                            )

                # Check for native tool calls if enabled
                if self.config.native_tool_calling:
                    native_calls = self._extract_native_tool_calls(chunk)

                    for call in native_calls:
                        yield {
                            "type": "tool_call_detected",
                            "format": "native",
                            "function_name": call.get("function", {}).get("name"),
                            "parameters": call.get("function", {}).get("arguments"),
                            "call_id": call.get("id"),
                            "session_id": session_id,
                            "timestamp": datetime.now().isoformat(),
                        }

            # Response complete - execute tools if any were detected
            if detected_xml_calls and self.config.execute_tools:
                logger.info(f"[{session_id}] Executing {len(detected_xml_calls)} XML tool calls")

                # Execute based on strategy
                if self.config.tool_execution_strategy == "parallel":
                    results = await self._execute_tools_parallel(detected_xml_calls, session_id)
                else:
                    results = await self._execute_tools_sequential(detected_xml_calls, session_id)

                # Yield tool results
                for call, result in zip(detected_xml_calls, results):
                    yield {
                        "type": "tool_result",
                        "function_name": call.function_name,
                        "success": result.success,
                        "output": result.output,
                        "error": result.error,
                        "metadata": result.metadata,
                        "session_id": session_id,
                        "timestamp": datetime.now().isoformat(),
                    }

            # Yield completion event
            yield {
                "type": "response_complete",
                "total_tool_calls": len(detected_xml_calls),
                "session_id": session_id,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"[{session_id}] Error processing response: {e}", exc_info=True)
            yield {
                "type": "error",
                "error": str(e),
                "session_id": session_id,
                "timestamp": datetime.now().isoformat(),
            }

    async def _execute_tools_sequential(
        self, tool_calls: List[XMLToolCall], session_id: str
    ) -> List[ToolResult]:
        """
        Execute tool calls sequentially (one after another).

        Args:
            tool_calls: List of tool calls to execute
            session_id: Session ID for logging

        Returns:
            List of ToolResult objects
        """
        results = []

        for i, call in enumerate(tool_calls, 1):
            logger.info(
                f"[{session_id}] Executing tool {i}/{len(tool_calls)}: {call.function_name}"
            )

            result = await self._execute_single_tool(call, session_id)
            results.append(result)

            # Check if we should continue on failure
            if not result.success and not self.config.continue_on_tool_failure:
                logger.warning(f"[{session_id}] Tool execution failed, halting further executions")
                # Fill remaining with error results
                for remaining_call in tool_calls[i:]:
                    results.append(
                        ToolResult(
                            success=False,
                            output="Skipped due to previous tool failure",
                            error="Previous tool failed",
                        )
                    )
                break

        return results

    async def _execute_tools_parallel(
        self, tool_calls: List[XMLToolCall], session_id: str
    ) -> List[ToolResult]:
        """
        Execute tool calls in parallel (concurrently).

        Args:
            tool_calls: List of tool calls to execute
            session_id: Session ID for logging

        Returns:
            List of ToolResult objects (same order as input)
        """
        logger.info(f"[{session_id}] Executing {len(tool_calls)} tools in parallel")

        tasks = [self._execute_single_tool(call, session_id) for call in tool_calls]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to ToolResult
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"[{session_id}] Tool {i} raised exception: {result}")
                processed_results.append(
                    ToolResult(
                        success=False,
                        output=f"Tool execution error: {str(result)}",
                        error=str(result),
                    )
                )
            else:
                processed_results.append(result)

        return processed_results

    async def _execute_single_tool(self, tool_call: XMLToolCall, session_id: str) -> ToolResult:
        """
        Execute a single tool call.

        Args:
            tool_call: Tool call to execute
            session_id: Session ID for logging

        Returns:
            ToolResult
        """
        function_name = tool_call.function_name
        parameters = tool_call.parameters

        # Check if tool exists
        if function_name not in self.tool_registry:
            error_msg = f"Tool '{function_name}' not found in registry"
            logger.error(f"[{session_id}] {error_msg}")
            return ToolResult(
                success=False,
                output=error_msg,
                error=error_msg,
                metadata={"error_type": "ToolNotFoundError"},
            )

        tool_func = self.tool_registry[function_name]

        # Execute with retry logic if configured
        if self.config.retry_on_tool_error:
            return await self._execute_with_retry(tool_func, parameters, function_name, session_id)
        else:
            return await self._execute_tool_once(tool_func, parameters, function_name, session_id)

    async def _execute_with_retry(
        self, tool_func: Callable, parameters: Dict[str, Any], function_name: str, session_id: str
    ) -> ToolResult:
        """
        Execute tool with retry logic.

        Args:
            tool_func: Tool function to execute
            parameters: Parameters to pass
            function_name: Tool name (for logging)
            session_id: Session ID

        Returns:
            ToolResult
        """
        last_error = None

        for attempt in range(self.config.max_retries):
            try:
                result = await self._execute_tool_once(
                    tool_func, parameters, function_name, session_id
                )

                if result.success:
                    if attempt > 0:
                        logger.info(
                            f"[{session_id}] Tool {function_name} succeeded "
                            f"on attempt {attempt + 1}"
                        )
                    return result

                last_error = result.error

                # Wait before retry (exponential backoff)
                if attempt < self.config.max_retries - 1:
                    wait_time = self.config.retry_backoff_factor**attempt
                    logger.warning(
                        f"[{session_id}] Tool {function_name} failed (attempt {attempt + 1}), "
                        f"retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)

            except Exception as e:
                last_error = str(e)
                logger.error(
                    f"[{session_id}] Tool {function_name} exception (attempt {attempt + 1}): {e}"
                )

                if attempt < self.config.max_retries - 1:
                    wait_time = self.config.retry_backoff_factor**attempt
                    await asyncio.sleep(wait_time)

        # All retries exhausted
        return ToolResult(
            success=False,
            output=f"Tool failed after {self.config.max_retries} attempts: {last_error}",
            error=last_error,
            metadata={"retry_count": self.config.max_retries},
        )

    async def _execute_tool_once(
        self, tool_func: Callable, parameters: Dict[str, Any], function_name: str, session_id: str
    ) -> ToolResult:
        """
        Execute tool function once.

        Args:
            tool_func: Tool function
            parameters: Parameters
            function_name: Tool name
            session_id: Session ID

        Returns:
            ToolResult
        """
        try:
            # Call tool function
            if asyncio.iscoroutinefunction(tool_func):
                result = await tool_func(**parameters)
            else:
                # Run sync function in executor
                result = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: tool_func(**parameters)
                )

            # Ensure result is ToolResult
            if not isinstance(result, ToolResult):
                result = validate_tool_result(result)

            logger.info(f"[{session_id}] Tool {function_name} executed: success={result.success}")

            return result

        except Exception as e:
            logger.error(f"[{session_id}] Tool {function_name} execution error: {e}", exc_info=True)
            return ToolResult(
                success=False,
                output=f"Tool execution error: {str(e)}",
                error=str(e),
                metadata={"error_type": type(e).__name__},
            )

    def _extract_content(self, chunk: Any) -> str:
        """
        Extract text content from response chunk.

        Supports various chunk formats from different LLM APIs.

        Args:
            chunk: Response chunk

        Returns:
            Extracted content string
        """
        # Handle different chunk formats
        if isinstance(chunk, dict):
            # OpenAI-style
            if "choices" in chunk:
                choices = chunk.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    return delta.get("content", "")

            # Direct content
            if "content" in chunk:
                return chunk["content"]

        # Handle object with content attribute
        if hasattr(chunk, "content"):
            return chunk.content

        # Handle string chunks
        if isinstance(chunk, str):
            return chunk

        return ""

    def _extract_native_tool_calls(self, chunk: Any) -> List[Dict[str, Any]]:
        """
        Extract native (OpenAI-format) tool calls from chunk.

        Args:
            chunk: Response chunk

        Returns:
            List of tool call dicts
        """
        tool_calls = []

        # Handle different formats
        if isinstance(chunk, dict):
            if "choices" in chunk:
                choices = chunk.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    if "tool_calls" in delta:
                        tool_calls.extend(delta["tool_calls"])

        if hasattr(chunk, "tool_calls"):
            tool_calls.extend(chunk.tool_calls)

        return tool_calls

    async def process_with_auto_continue(
        self, messages: List[Dict[str, Any]], llm_callable: Callable, session_id: str = "default"
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Process LLM responses with automatic continuation support.

        This method handles the full auto-continue loop:
        1. Call LLM
        2. Detect tool calls
        3. Execute tools
        4. Inject results
        5. Repeat until stop condition

        Args:
            messages: Conversation messages
            llm_callable: Async function to call LLM (takes messages list)
            session_id: Session identifier

        Yields:
            Event dictionaries with auto-continue events
        """

        if not self.continuation_handler:
            logger.warning(
                f"[{session_id}] Auto-continuation not enabled, falling back to single response"
            )
            # Just call LLM once without continuation
            response = await llm_callable(messages)
            yield {
                "type": "response_complete",
                "response": response,
                "session_id": session_id,
                "timestamp": datetime.now().isoformat(),
            }
            return

        # Initialize continuation state
        state = ContinuationState() if CONTINUATION_AVAILABLE else None

        yield {
            "type": "continuation_started",
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
        }

        logger.info(f"[{session_id}] Starting auto-continuation loop")

        iteration = 0
        accumulated_responses = []

        while iteration < self.config.max_auto_continues:
            iteration += 1

            yield {
                "type": "continuation_iteration",
                "iteration": iteration,
                "session_id": session_id,
                "timestamp": datetime.now().isoformat(),
            }

            logger.info(f"[{session_id}] Iteration {iteration}: Calling LLM")

            # Call LLM
            try:
                response = await llm_callable(messages)
                accumulated_responses.append(response)

                # Extract content for parsing
                response_content = self._extract_response_content(response)

                yield {
                    "type": "llm_response",
                    "iteration": iteration,
                    "content": response_content,
                    "session_id": session_id,
                    "timestamp": datetime.now().isoformat(),
                }

            except Exception as e:
                logger.error(f"[{session_id}] LLM call failed: {e}", exc_info=True)
                yield {
                    "type": "error",
                    "error": str(e),
                    "iteration": iteration,
                    "session_id": session_id,
                    "timestamp": datetime.now().isoformat(),
                }
                break

            # Extract finish_reason
            finish_reason = self._extract_finish_reason_from_response(response)

            if state:
                state.add_finish_reason(finish_reason)

            logger.info(f"[{session_id}] Iteration {iteration}: finish_reason={finish_reason}")

            # Parse XML tool calls if enabled
            xml_calls = []
            if self.config.xml_tool_calling and response_content:
                xml_calls = self.xml_parser.parse_content(response_content)

            # Extract native tool calls if enabled
            native_calls = []
            if self.config.native_tool_calling:
                native_calls = self._extract_native_tool_calls_from_response(response)

            all_tool_calls = xml_calls + native_calls

            logger.info(
                f"[{session_id}] Iteration {iteration}: detected {len(all_tool_calls)} tool calls"
            )

            # Check if we should continue
            if state and self.continuation_handler:
                should_continue, stop_reason = self.continuation_handler.decider.should_continue(
                    state=state,
                    finish_reason=finish_reason,
                    has_tool_calls=len(all_tool_calls) > 0,
                    tool_results=None,
                )

                if not should_continue:
                    logger.info(f"[{session_id}] Stopping: {stop_reason}")
                    yield {
                        "type": "continuation_stopped",
                        "reason": stop_reason,
                        "iteration": iteration,
                        "session_id": session_id,
                        "timestamp": datetime.now().isoformat(),
                    }
                    break

            # Execute tools if any
            if all_tool_calls and self.config.execute_tools:
                logger.info(f"[{session_id}] Executing {len(all_tool_calls)} tools")

                # Execute based on strategy
                if self.config.tool_execution_strategy == "parallel":
                    tool_results = await self._execute_tools_parallel(all_tool_calls, session_id)
                else:
                    tool_results = await self._execute_tools_sequential(all_tool_calls, session_id)

                # Record in state
                if state:
                    state.add_tool_calls(all_tool_calls, tool_results)

                # Yield tool results
                for call, result in zip(all_tool_calls, tool_results):
                    function_name = getattr(call, "function_name", "unknown")
                    yield {
                        "type": "tool_result",
                        "iteration": iteration,
                        "function_name": function_name,
                        "success": result.success,
                        "output": result.output,
                        "error": result.error,
                        "session_id": session_id,
                        "timestamp": datetime.now().isoformat(),
                    }

                # Inject results back into conversation
                if self.continuation_handler:
                    messages = self.continuation_handler.injector.inject_results(
                        messages=messages, tool_calls=all_tool_calls, tool_results=tool_results
                    )

                yield {
                    "type": "results_injected",
                    "iteration": iteration,
                    "count": len(tool_results),
                    "session_id": session_id,
                    "timestamp": datetime.now().isoformat(),
                }

            else:
                # No tool calls, stop iteration
                logger.info(f"[{session_id}] No tool calls, stopping")
                break

            # Increment state
            if state:
                state.increment_iteration()

        # Yield completion
        yield {
            "type": "continuation_complete",
            "total_iterations": iteration,
            "total_tool_calls": state.total_tool_calls if state else 0,
            "stop_reason": state.stop_reason if state else "max_iterations",
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "state": state.to_dict() if state else {},
        }

        logger.info(
            f"[{session_id}] Auto-continuation complete: "
            f"{iteration} iterations, "
            f"{state.total_tool_calls if state else 0} tool calls"
        )

    def _extract_response_content(self, response: Any) -> str:
        """Extract text content from LLM response."""
        # OpenAI format
        if hasattr(response, "choices") and response.choices:
            message = response.choices[0].message
            if hasattr(message, "content"):
                return message.content or ""

        # Dict format
        if isinstance(response, dict):
            if "choices" in response and response["choices"]:
                message = response["choices"][0].get("message", {})
                return message.get("content", "")
            if "content" in response:
                return response["content"]

        # Direct content
        if hasattr(response, "content"):
            return response.content

        return ""

    def _extract_finish_reason_from_response(self, response: Any) -> Optional[str]:
        """Extract finish_reason from response."""
        # OpenAI format
        if hasattr(response, "choices") and response.choices:
            return response.choices[0].finish_reason

        # Dict format
        if isinstance(response, dict):
            if "choices" in response and response["choices"]:
                return response["choices"][0].get("finish_reason")

        # Anthropic format
        if hasattr(response, "stop_reason"):
            return response.stop_reason

        return None

    def _extract_native_tool_calls_from_response(self, response: Any) -> List[Any]:
        """Extract native tool calls from full response (not just delta)."""
        tool_calls = []

        # OpenAI format
        if hasattr(response, "choices") and response.choices:
            message = response.choices[0].message
            if hasattr(message, "tool_calls") and message.tool_calls:
                tool_calls.extend(message.tool_calls)

        # Dict format
        if isinstance(response, dict):
            if "choices" in response and response["choices"]:
                message = response["choices"][0].get("message", {})
                if "tool_calls" in message:
                    tool_calls.extend(message["tool_calls"])

        return tool_calls


# Example usage
if __name__ == "__main__":
    print("=" * 60)
    print("Response Handler Test")
    print("=" * 60)

    # Mock tool registry
    async def mock_search(query: str, max_results: int = 5) -> ToolResult:
        """Mock search tool."""
        await asyncio.sleep(0.1)  # Simulate API call
        return ToolResult(
            success=True,
            output=json.dumps(
                {"query": query, "results": [f"Result {i}" for i in range(max_results)]}
            ),
            metadata={"source": "mock"},
        )

    async def mock_calculate(expression: str) -> ToolResult:
        """Mock calculator tool."""
        try:
            result = eval(expression)
            return ToolResult(
                success=True, output=json.dumps({"expression": expression, "result": result})
            )
        except Exception as e:
            return ToolResult(success=False, output=f"Calculation error: {e}", error=str(e))

    tool_registry = {"search_web": mock_search, "calculate": mock_calculate}

    # Create handler
    config = AgentProcessorConfig(
        xml_tool_calling=True, execute_tools=True, tool_execution_strategy="sequential"
    )

    handler = ResponseHandler(tool_registry=tool_registry, config=config)

    # Mock streaming response with XML
    async def mock_stream():
        """Mock streaming response."""
        parts = [
            "Let me search for that.\n\n",
            "<function_calls>\n",
            '<invoke name="search_web">\n',
            '<parameter name="query">Python async</parameter>\n',
            '<parameter name="max_results">3</parameter>\n',
            "</invoke>\n",
            "</function_calls>\n",
        ]

        for part in parts:
            yield {"content": part}
            await asyncio.sleep(0.05)

    # Test
    async def test():
        print("\nTest: Process streaming response with XML tool call\n")

        async for event in handler.process_streaming_response(mock_stream(), "test-session"):
            event_type = event.get("type")

            if event_type == "text_delta":
                print(f"[TEXT] {event['content']}", end="", flush=True)

            elif event_type == "tool_call_detected":
                print(f"\n[TOOL DETECTED] {event['function_name']}")
                print(f"  Parameters: {event['parameters']}")

            elif event_type == "tool_result":
                print(f"\n[TOOL RESULT] {event['function_name']}")
                print(f"  Success: {event['success']}")
                print(f"  Output: {event['output'][:100]}...")

            elif event_type == "response_complete":
                print(f"\n[COMPLETE] Total tool calls: {event['total_tool_calls']}")

    asyncio.run(test())

    print("\n" + "=" * 60)
    print("[OK] Response handler test completed!")
    print("=" * 60)
