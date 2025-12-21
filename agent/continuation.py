"""
Auto-Continuation Handler - Automatic continuation mechanism for LLM agents

This module implements the auto-continue mechanism that allows agents to
automatically continue execution when tools are called, similar to how
Manus AgentPress handles multi-turn tool calling conversations.

Core Concepts:
- finish_reason detection: Determine if continuation is needed
- Tool result injection: Insert tool results back into conversation
- Loop control: Prevent infinite loops with max iteration limits
- State management: Track continuation state across turns

Design Philosophy:
Detect when the LLM wants to continue (e.g., finish_reason='tool_calls'),
execute the tools, inject results back into the conversation, and call
the LLM again - all automatically until a natural stop point is reached.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Literal, Callable
from datetime import datetime
import logging
import asyncio

from tools.base import ToolResult
from agent.xml_parser import XMLToolCall

logger = logging.getLogger(__name__)


# ==================== Continuation State ====================

@dataclass
class ContinuationState:
    """
    State tracker for auto-continuation loops.

    Tracks how many times we've continued, why we're continuing,
    and whether we should stop.
    """

    # Counters
    iteration_count: int = 0
    total_tool_calls: int = 0
    successful_tool_calls: int = 0
    failed_tool_calls: int = 0

    # Status
    should_continue: bool = True
    stop_reason: Optional[str] = None

    # History
    finish_reasons: List[str] = field(default_factory=list)
    tool_call_history: List[Dict[str, Any]] = field(default_factory=list)

    # Timestamps
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_iteration_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def increment_iteration(self):
        """Increment iteration counter and update timestamp."""
        self.iteration_count += 1
        self.last_iteration_at = datetime.now().isoformat()

    def add_finish_reason(self, reason: str):
        """Record a finish reason."""
        self.finish_reasons.append(reason)

    def add_tool_calls(self, calls: List[Any], results: List[ToolResult]):
        """Record tool calls and their results."""
        for call, result in zip(calls, results):
            self.total_tool_calls += 1

            if result.success:
                self.successful_tool_calls += 1
            else:
                self.failed_tool_calls += 1

            # Extract function name from different formats
            if hasattr(call, 'function_name'):
                function_name = call.function_name
            elif isinstance(call, dict):
                function_name = call.get('name', call.get('function', {}).get('name', 'unknown'))
            else:
                function_name = 'unknown'

            # Record in history
            call_record = {
                "iteration": self.iteration_count,
                "function_name": function_name,
                "success": result.success,
                "timestamp": datetime.now().isoformat()
            }
            self.tool_call_history.append(call_record)

    def stop(self, reason: str):
        """Mark continuation as stopped with a reason."""
        self.should_continue = False
        self.stop_reason = reason

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "iteration_count": self.iteration_count,
            "total_tool_calls": self.total_tool_calls,
            "successful_tool_calls": self.successful_tool_calls,
            "failed_tool_calls": self.failed_tool_calls,
            "should_continue": self.should_continue,
            "stop_reason": self.stop_reason,
            "finish_reasons": self.finish_reasons,
            "tool_call_history": self.tool_call_history,
            "started_at": self.started_at,
            "last_iteration_at": self.last_iteration_at
        }

    def summary(self) -> str:
        """Get human-readable summary."""
        return (
            f"Iterations: {self.iteration_count}, "
            f"Tools: {self.total_tool_calls} "
            f"({self.successful_tool_calls} success, {self.failed_tool_calls} failed), "
            f"Status: {'Continue' if self.should_continue else f'Stopped ({self.stop_reason})'}"
        )


# ==================== Continuation Decision ====================

class ContinuationDecider:
    """
    Decides whether to continue based on finish_reason and configuration.

    This is the core decision-making component that determines if the
    agent should automatically continue after a response.
    """

    # Finish reasons that typically indicate continuation needed
    CONTINUE_REASONS = {"tool_calls", "function_call"}

    # Finish reasons that indicate natural stop
    STOP_REASONS = {"stop", "end_turn"}

    # Finish reasons that indicate special handling needed
    LENGTH_REASONS = {"length", "max_tokens"}

    def __init__(
        self,
        max_iterations: int = 25,
        continue_on_tool_calls: bool = True,
        continue_on_length: bool = False,
        stop_on_tool_failure: bool = False
    ):
        """
        Initialize continuation decider.

        Args:
            max_iterations: Maximum continuation loops allowed
            continue_on_tool_calls: Continue when finish_reason is 'tool_calls'
            continue_on_length: Continue when finish_reason is 'length'
            stop_on_tool_failure: Stop if any tool fails
        """
        self.max_iterations = max_iterations
        self.continue_on_tool_calls = continue_on_tool_calls
        self.continue_on_length = continue_on_length
        self.stop_on_tool_failure = stop_on_tool_failure

    def should_continue(
        self,
        state: ContinuationState,
        finish_reason: Optional[str],
        has_tool_calls: bool,
        tool_results: Optional[List[ToolResult]] = None
    ) -> tuple[bool, Optional[str]]:
        """
        Determine if continuation should happen.

        Args:
            state: Current continuation state
            finish_reason: LLM response finish_reason
            has_tool_calls: Whether response contains tool calls
            tool_results: Results from tool execution (if any)

        Returns:
            Tuple of (should_continue, stop_reason)
        """

        # Check max iterations
        if state.iteration_count >= self.max_iterations:
            return False, f"max_iterations_reached ({self.max_iterations})"

        # Check if already stopped
        if not state.should_continue:
            return False, state.stop_reason

        # Check tool failure stop condition
        if self.stop_on_tool_failure and tool_results:
            if any(not result.success for result in tool_results):
                return False, "tool_execution_failed"

        # Decide based on finish_reason
        if finish_reason in self.CONTINUE_REASONS:
            if self.continue_on_tool_calls and has_tool_calls:
                return True, None
            else:
                return False, "tool_calls_disabled"

        elif finish_reason in self.STOP_REASONS:
            return False, f"natural_stop ({finish_reason})"

        elif finish_reason in self.LENGTH_REASONS:
            if self.continue_on_length:
                return True, None
            else:
                return False, f"length_limit ({finish_reason})"

        # Unknown finish_reason - default to stop
        return False, f"unknown_finish_reason ({finish_reason})"


# ==================== Result Injector ====================

class ToolResultInjector:
    """
    Injects tool results back into the conversation.

    Different injection strategies for different model types:
    - user_message: Inject as user message (for Claude)
    - assistant_message: Inject as assistant message
    - tool_message: Inject as tool message (for OpenAI)
    """

    def __init__(
        self,
        strategy: Literal["user_message", "assistant_message", "tool_message"] = "user_message"
    ):
        """
        Initialize result injector.

        Args:
            strategy: How to inject results into conversation
        """
        self.strategy = strategy

    def inject_results(
        self,
        messages: List[Dict[str, Any]],
        tool_calls: List[Any],
        tool_results: List[ToolResult],
        format_type: Literal["xml", "native"] = "xml"
    ) -> List[Dict[str, Any]]:
        """
        Inject tool results into message list.

        Args:
            messages: Current message list
            tool_calls: Tool calls that were executed
            tool_results: Results from tool execution
            format_type: Tool call format (xml or native)

        Returns:
            Updated message list with results injected
        """

        if self.strategy == "user_message":
            return self._inject_as_user_message(messages, tool_calls, tool_results)

        elif self.strategy == "assistant_message":
            return self._inject_as_assistant_message(messages, tool_calls, tool_results)

        elif self.strategy == "tool_message":
            return self._inject_as_tool_message(messages, tool_calls, tool_results)

        else:
            raise ValueError(f"Unknown injection strategy: {self.strategy}")

    def _inject_as_user_message(
        self,
        messages: List[Dict[str, Any]],
        tool_calls: List[Any],
        tool_results: List[ToolResult]
    ) -> List[Dict[str, Any]]:
        """
        Inject results as user messages.

        Good for Claude models - they expect tool results as user input.
        """

        # Build result message content
        result_parts = []
        for call, result in zip(tool_calls, tool_results):
            # Extract function name from different formats
            if hasattr(call, 'function_name'):
                function_name = call.function_name
            elif isinstance(call, dict):
                function_name = call.get('name', call.get('function', {}).get('name', 'unknown'))
            else:
                function_name = 'unknown'

            result_parts.append(f"<tool_result name='{function_name}'>")

            if result.success:
                result_parts.append(f"<output>\n{result.output}\n</output>")
            else:
                result_parts.append(f"<error>\n{result.error}\n</error>")

            if result.metadata:
                result_parts.append(f"<metadata>{result.metadata}</metadata>")

            result_parts.append("</tool_result>")

        result_content = "\n".join(result_parts)

        # Inject as user message
        messages.append({
            "role": "user",
            "content": result_content
        })

        return messages

    def _inject_as_assistant_message(
        self,
        messages: List[Dict[str, Any]],
        tool_calls: List[Any],
        tool_results: List[ToolResult]
    ) -> List[Dict[str, Any]]:
        """
        Inject results as assistant messages.

        Alternative approach - assistant acknowledges tool results.
        """

        result_parts = []
        for call, result in zip(tool_calls, tool_results):
            # Extract function name from different formats
            if hasattr(call, 'function_name'):
                function_name = call.function_name
            elif isinstance(call, dict):
                function_name = call.get('name', call.get('function', {}).get('name', 'unknown'))
            else:
                function_name = 'unknown'

            if result.success:
                result_parts.append(f"Tool '{function_name}' completed successfully.")
            else:
                result_parts.append(f"Tool '{function_name}' failed: {result.error}")

        messages.append({
            "role": "assistant",
            "content": "\n".join(result_parts)
        })

        return messages

    def _inject_as_tool_message(
        self,
        messages: List[Dict[str, Any]],
        tool_calls: List[Any],
        tool_results: List[ToolResult]
    ) -> List[Dict[str, Any]]:
        """
        Inject results as tool messages.

        OpenAI-compatible format with tool_call_id.
        """

        for call, result in zip(tool_calls, tool_results):
            # Extract function name and ID from different formats
            if hasattr(call, 'function_name'):
                function_name = call.function_name
                call_id = getattr(call, 'id', f"call_{function_name}")
            elif isinstance(call, dict):
                function_name = call.get('name', call.get('function', {}).get('name', 'unknown'))
                call_id = call.get('id', f"call_{function_name}")
            else:
                function_name = 'unknown'
                call_id = 'call_unknown'

            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "name": function_name,
                "content": result.output if result.success else f"Error: {result.error}"
            })

        return messages


# ==================== Continuation Handler ====================

class ContinuationHandler:
    """
    Main handler for auto-continuation loops.

    Orchestrates the entire continuation process:
    1. Check if continuation is needed
    2. Inject tool results
    3. Call LLM again
    4. Repeat until stop condition
    """

    def __init__(
        self,
        decider: Optional[ContinuationDecider] = None,
        injector: Optional[ToolResultInjector] = None
    ):
        """
        Initialize continuation handler.

        Args:
            decider: Continuation decision logic
            injector: Tool result injection logic
        """
        self.decider = decider or ContinuationDecider()
        self.injector = injector or ToolResultInjector()

    async def handle_continuation(
        self,
        messages: List[Dict[str, Any]],
        llm_callable: Callable,
        tool_executor: Callable,
        initial_response: Any,
        session_id: str = "default"
    ) -> Dict[str, Any]:
        """
        Handle auto-continuation loop.

        Args:
            messages: Current message list
            llm_callable: Async function to call LLM
            tool_executor: Async function to execute tools
            initial_response: Initial LLM response
            session_id: Session identifier

        Returns:
            Dict with final response and continuation state
        """

        state = ContinuationState()
        current_response = initial_response
        accumulated_responses = [initial_response]

        logger.info(f"[{session_id}] Starting auto-continuation loop")

        while state.should_continue:
            # Extract finish_reason and tool calls
            finish_reason = self._extract_finish_reason(current_response)
            tool_calls = self._extract_tool_calls(current_response)

            state.add_finish_reason(finish_reason)

            logger.info(
                f"[{session_id}] Iteration {state.iteration_count + 1}: "
                f"finish_reason={finish_reason}, tools={len(tool_calls)}"
            )

            # Check if we should continue
            should_continue, stop_reason = self.decider.should_continue(
                state=state,
                finish_reason=finish_reason,
                has_tool_calls=len(tool_calls) > 0,
                tool_results=None
            )

            if not should_continue:
                state.stop(stop_reason)
                logger.info(f"[{session_id}] Stopping continuation: {stop_reason}")
                break

            # Execute tools if any
            if tool_calls:
                tool_results = await tool_executor(tool_calls)
                state.add_tool_calls(tool_calls, tool_results)

                # Check if we should stop due to tool failure
                if self.decider.stop_on_tool_failure:
                    if any(not r.success for r in tool_results):
                        state.stop("tool_execution_failed")
                        logger.warning(f"[{session_id}] Tool execution failed, stopping")
                        break

                # Inject results back into conversation
                messages = self.injector.inject_results(
                    messages=messages,
                    tool_calls=tool_calls,
                    tool_results=tool_results
                )

            # Increment iteration
            state.increment_iteration()

            # Call LLM again
            try:
                logger.info(f"[{session_id}] Calling LLM (iteration {state.iteration_count})")
                current_response = await llm_callable(messages)
                accumulated_responses.append(current_response)

            except Exception as e:
                logger.error(f"[{session_id}] LLM call failed: {e}", exc_info=True)
                state.stop(f"llm_error: {str(e)}")
                break

        # Return final result
        logger.info(f"[{session_id}] Continuation complete: {state.summary()}")

        return {
            "final_response": current_response,
            "all_responses": accumulated_responses,
            "continuation_state": state.to_dict(),
            "total_iterations": state.iteration_count,
            "stop_reason": state.stop_reason,
            "messages": messages
        }

    def _extract_finish_reason(self, response: Any) -> Optional[str]:
        """
        Extract finish_reason from LLM response.

        Supports various response formats.
        """

        # OpenAI format
        if hasattr(response, 'choices') and response.choices:
            return response.choices[0].finish_reason

        # Dict format
        if isinstance(response, dict):
            if 'choices' in response and response['choices']:
                return response['choices'][0].get('finish_reason')
            if 'finish_reason' in response:
                return response['finish_reason']

        # Anthropic format
        if hasattr(response, 'stop_reason'):
            return response.stop_reason

        return None

    def _extract_tool_calls(self, response: Any) -> List[Any]:
        """
        Extract tool calls from LLM response.

        Supports both native and XML formats.
        """

        tool_calls = []

        # Native format (OpenAI)
        if hasattr(response, 'tool_calls') and response.tool_calls:
            tool_calls.extend(response.tool_calls)

        # Dict format
        if isinstance(response, dict):
            if 'tool_calls' in response:
                tool_calls.extend(response['tool_calls'])

            # Check in choices
            if 'choices' in response and response['choices']:
                message = response['choices'][0].get('message', {})
                if 'tool_calls' in message:
                    tool_calls.extend(message['tool_calls'])

        # XML format - would need XMLToolParser
        # This is handled separately in the response handler

        return tool_calls


# ==================== Example Usage ====================

if __name__ == "__main__":
    print("=" * 60)
    print("Continuation Handler Test")
    print("=" * 60)

    # Test ContinuationState
    print("\n1. Testing ContinuationState:")
    state = ContinuationState()
    state.increment_iteration()
    state.add_finish_reason("tool_calls")

    from tools.base import ToolResult
    mock_call = type('MockCall', (), {'function_name': 'test_tool'})()
    mock_result = ToolResult(success=True, output="Test output")
    state.add_tool_calls([mock_call], [mock_result])

    print(f"  {state.summary()}")
    print(f"  State dict: {state.to_dict()}")

    # Test ContinuationDecider
    print("\n2. Testing ContinuationDecider:")
    decider = ContinuationDecider(max_iterations=5)

    test_cases = [
        ("tool_calls", True, "Should continue for tool_calls"),
        ("stop", False, "Should stop for stop"),
        ("length", False, "Should stop for length (default)"),
    ]

    for finish_reason, has_tools, description in test_cases:
        state = ContinuationState()
        should_continue, stop_reason = decider.should_continue(
            state, finish_reason, has_tools
        )
        status = "[CONTINUE]" if should_continue else f"[STOP: {stop_reason}]"
        print(f"  {status} {description}")

    # Test ToolResultInjector
    print("\n3. Testing ToolResultInjector:")
    injector = ToolResultInjector(strategy="user_message")

    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Let me search for that."}
    ]

    mock_call = type('MockCall', (), {'function_name': 'search_web'})()
    mock_result = ToolResult(
        success=True,
        output="Search results here",
        metadata={"source": "test"}
    )

    updated_messages = injector.inject_results(
        messages, [mock_call], [mock_result]
    )

    print(f"  Injected {len(updated_messages) - len(messages)} message(s)")
    print(f"  Last message role: {updated_messages[-1]['role']}")
    print(f"  Content preview: {updated_messages[-1]['content'][:50]}...")

    print("\n" + "=" * 60)
    print("[OK] Continuation handler test completed!")
    print("=" * 60)
