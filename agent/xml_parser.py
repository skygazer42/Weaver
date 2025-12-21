"""
XML Tool Call Parser - Claude-friendly tool calling format

This module provides parsing for XML-based tool calls, which is the format
preferred by Claude models. The XML format is more natural for Claude and
supports multi-line parameters (like code blocks) better than JSON.

Example XML format:
    <function_calls>
    <invoke name="search_web">
    <parameter name="query">Python async programming</parameter>
    <parameter name="max_results">10</parameter>
    </invoke>
    <invoke name="execute_code">
    <parameter name="language">python</parameter>
    <parameter name="code">
    import asyncio
    print("Hello async")
    </parameter>
    </invoke>
    </function_calls>

Design inspired by Manus AgentPress XMLToolParser.
"""

import re
import json
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class XMLToolCall:
    """
    Represents a parsed XML tool call.

    Attributes:
        function_name: Name of the function to call
        parameters: Dictionary of parameter name -> value
        raw_xml: Original XML content (for debugging)
        call_id: Optional unique identifier for this call
    """
    function_name: str
    parameters: Dict[str, Any]
    raw_xml: str = ""
    call_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "function_name": self.function_name,
            "parameters": self.parameters,
            "raw_xml": self.raw_xml,
            "call_id": self.call_id
        }

    def to_openai_format(self) -> Dict[str, Any]:
        """
        Convert to OpenAI function calling format.

        This allows XML tool calls to be processed by the same
        downstream logic as native OpenAI format calls.
        """
        return {
            "id": self.call_id or f"call_{hash(self.raw_xml)}",
            "type": "function",
            "function": {
                "name": self.function_name,
                "arguments": json.dumps(self.parameters)
            }
        }


class XMLToolParser:
    """
    Parser for XML-based tool calls (Claude format).

    Uses a three-layer regex-based parsing approach:
    1. Extract <function_calls> blocks
    2. Extract <invoke> blocks within function_calls
    3. Extract <parameter> blocks within invoke

    This approach is more forgiving than strict XML parsing and handles
    malformed LLM output better.
    """

    # Layer 1: Extract <function_calls> blocks
    FUNCTION_CALLS_PATTERN = re.compile(
        r'<function_calls>(.*?)</function_calls>',
        re.DOTALL | re.IGNORECASE
    )

    # Layer 2: Extract <invoke> blocks
    INVOKE_PATTERN = re.compile(
        r'<invoke\s+name=["\']([^"\']+)["\']>(.*?)</invoke>',
        re.DOTALL | re.IGNORECASE
    )

    # Alternative invoke pattern (name as attribute or child element)
    INVOKE_ALT_PATTERN = re.compile(
        r'<invoke[^>]*>(.*?)</invoke>',
        re.DOTALL | re.IGNORECASE
    )

    # Layer 3: Extract <parameter> blocks
    PARAMETER_PATTERN = re.compile(
        r'<parameter\s+name=["\']([^"\']+)["\']>(.*?)</parameter>',
        re.DOTALL | re.IGNORECASE
    )

    # Extract name from invoke content if not in attribute
    NAME_PATTERN = re.compile(
        r'<name>(.*?)</name>',
        re.IGNORECASE
    )

    def __init__(self):
        """Initialize the XML parser."""
        self.parsed_calls = 0
        self.parse_errors = 0

    def parse_content(self, content: str) -> List[XMLToolCall]:
        """
        Parse XML tool calls from content.

        Args:
            content: String content that may contain XML tool calls

        Returns:
            List of XMLToolCall objects
        """
        tool_calls = []

        try:
            # Layer 1: Find all <function_calls> blocks
            function_calls_matches = self.FUNCTION_CALLS_PATTERN.findall(content)

            if not function_calls_matches:
                logger.debug("No <function_calls> blocks found in content")
                return tool_calls

            for fc_content in function_calls_matches:
                # Layer 2: Find all <invoke> blocks
                invoke_matches = self.INVOKE_PATTERN.findall(fc_content)

                for function_name, invoke_content in invoke_matches:
                    parameters = {}

                    # Layer 3: Extract parameters
                    param_matches = self.PARAMETER_PATTERN.findall(invoke_content)

                    for param_name, param_value in param_matches:
                        # Parse parameter value with type inference
                        parsed_value = self._parse_parameter_value(param_value.strip())
                        parameters[param_name] = parsed_value

                    # Create tool call
                    tool_call = XMLToolCall(
                        function_name=function_name.strip(),
                        parameters=parameters,
                        raw_xml=f'<invoke name="{function_name}">{invoke_content}</invoke>'
                    )

                    tool_calls.append(tool_call)
                    self.parsed_calls += 1

                    logger.debug(
                        f"Parsed XML tool call: {function_name} "
                        f"with {len(parameters)} parameters"
                    )

        except Exception as e:
            logger.error(f"Error parsing XML tool calls: {e}", exc_info=True)
            self.parse_errors += 1

        return tool_calls

    def _parse_parameter_value(self, value: str) -> Any:
        """
        Parse parameter value with intelligent type inference.

        Attempts to infer the correct type from the string value:
        1. JSON objects/arrays
        2. Boolean values (true/false)
        3. Numbers (integers/floats)
        4. Strings (fallback)

        Args:
            value: String value to parse

        Returns:
            Parsed value with appropriate type
        """
        value = value.strip()

        if not value:
            return ""

        # 1. Try parsing as JSON (objects/arrays)
        if value.startswith(('{', '[')):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                logger.debug(f"Failed to parse as JSON: {value[:50]}...")
                pass

        # 2. Boolean values
        if value.lower() in ('true', 'false'):
            return value.lower() == 'true'

        # 3. Null/None values
        if value.lower() in ('null', 'none'):
            return None

        # 4. Try parsing as number
        try:
            # Check for float
            if '.' in value or 'e' in value.lower():
                return float(value)
            # Integer
            return int(value)
        except ValueError:
            pass

        # 5. String (default fallback)
        return value

    def parse_streaming_content(
        self,
        accumulated_content: str,
        previous_calls: List[XMLToolCall]
    ) -> List[XMLToolCall]:
        """
        Parse tool calls from streaming content.

        This method is optimized for streaming scenarios where content
        is received incrementally. It only returns new tool calls that
        weren't in the previous parse.

        Args:
            accumulated_content: Accumulated content so far
            previous_calls: Tool calls from previous parse

        Returns:
            List of NEW tool calls (not in previous_calls)
        """
        all_calls = self.parse_content(accumulated_content)

        # Filter out calls that were already parsed
        previous_call_count = len(previous_calls)
        new_calls = all_calls[previous_call_count:]

        return new_calls

    def has_complete_function_calls(self, content: str) -> bool:
        """
        Check if content has complete <function_calls> blocks.

        Args:
            content: Content to check

        Returns:
            True if there's at least one complete function_calls block
        """
        return bool(self.FUNCTION_CALLS_PATTERN.search(content))

    def extract_thinking_and_calls(
        self,
        content: str
    ) -> tuple[Optional[str], List[XMLToolCall]]:
        """
        Extract both thinking/reasoning text and tool calls.

        Args:
            content: Full content that may contain both thinking and tool calls

        Returns:
            Tuple of (thinking_text, tool_calls)
        """
        # Extract tool calls
        tool_calls = self.parse_content(content)

        # Extract thinking (everything before first <function_calls>)
        thinking = None
        match = self.FUNCTION_CALLS_PATTERN.search(content)
        if match:
            thinking = content[:match.start()].strip()

        return thinking, tool_calls

    def validate_tool_call(self, tool_call: XMLToolCall) -> tuple[bool, Optional[str]]:
        """
        Validate a parsed tool call.

        Args:
            tool_call: Tool call to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check function name
        if not tool_call.function_name:
            return False, "Missing function name"

        # Check for empty parameters (might be OK)
        if not tool_call.parameters:
            logger.warning(f"Tool call {tool_call.function_name} has no parameters")

        # Check for valid parameter names
        for param_name in tool_call.parameters.keys():
            if not param_name or not param_name.strip():
                return False, f"Invalid parameter name: '{param_name}'"

        return True, None

    def get_statistics(self) -> Dict[str, int]:
        """
        Get parsing statistics.

        Returns:
            Dictionary with parsing stats
        """
        return {
            "parsed_calls": self.parsed_calls,
            "parse_errors": self.parse_errors
        }


# Utility functions

def convert_xml_to_openai_format(xml_calls: List[XMLToolCall]) -> List[Dict[str, Any]]:
    """
    Convert XML tool calls to OpenAI function calling format.

    This enables unified processing of both XML and native tool calls.

    Args:
        xml_calls: List of XMLToolCall objects

    Returns:
        List of OpenAI-format tool call dicts
    """
    return [call.to_openai_format() for call in xml_calls]


def extract_tool_calls_from_response(
    response_content: str,
    format_type: str = "auto"
) -> tuple[Optional[str], List[XMLToolCall]]:
    """
    Extract tool calls from LLM response content.

    Args:
        response_content: Response content from LLM
        format_type: "xml", "native", or "auto" (detect automatically)

    Returns:
        Tuple of (thinking_text, tool_calls)
    """
    if format_type == "xml" or (format_type == "auto" and "<function_calls>" in response_content):
        parser = XMLToolParser()
        return parser.extract_thinking_and_calls(response_content)

    # Native format is handled by LLM API directly
    return response_content, []


# Example usage and tests
if __name__ == "__main__":
    print("=" * 60)
    print("XML Tool Parser Test")
    print("=" * 60)

    # Test case 1: Simple tool call
    xml_content_1 = """
Let me search for that information.

<function_calls>
<invoke name="search_web">
<parameter name="query">Python async programming</parameter>
<parameter name="max_results">5</parameter>
</invoke>
</function_calls>
"""

    parser = XMLToolParser()
    calls = parser.parse_content(xml_content_1)

    print(f"\nTest 1: Simple tool call")
    print(f"Found {len(calls)} tool call(s)")
    for call in calls:
        print(f"  Function: {call.function_name}")
        print(f"  Parameters: {call.parameters}")

    # Test case 2: Multiple tool calls
    xml_content_2 = """
<function_calls>
<invoke name="search_web">
<parameter name="query">LangChain tutorial</parameter>
<parameter name="max_results">10</parameter>
</invoke>
<invoke name="execute_code">
<parameter name="language">python</parameter>
<parameter name="code">
import asyncio

async def main():
    print("Hello async!")

asyncio.run(main())
</parameter>
</invoke>
</function_calls>
"""

    calls2 = parser.parse_content(xml_content_2)

    print(f"\nTest 2: Multiple tool calls")
    print(f"Found {len(calls2)} tool call(s)")
    for i, call in enumerate(calls2, 1):
        print(f"\n  Call {i}:")
        print(f"    Function: {call.function_name}")
        print(f"    Parameters: {list(call.parameters.keys())}")

    # Test case 3: Type inference
    xml_content_3 = """
<function_calls>
<invoke name="test_types">
<parameter name="string_param">hello world</parameter>
<parameter name="int_param">42</parameter>
<parameter name="float_param">3.14</parameter>
<parameter name="bool_param">true</parameter>
<parameter name="json_param">{"key": "value", "number": 123}</parameter>
<parameter name="array_param">[1, 2, 3, 4, 5]</parameter>
</invoke>
</function_calls>
"""

    calls3 = parser.parse_content(xml_content_3)

    print(f"\nTest 3: Type inference")
    if calls3:
        call = calls3[0]
        print(f"  Parameters and types:")
        for name, value in call.parameters.items():
            print(f"    {name}: {type(value).__name__} = {repr(value)}")

    # Test case 4: Thinking + tool calls
    xml_content_4 = """
I need to analyze this data. Let me first search for relevant information,
then execute some code to process it.

<function_calls>
<invoke name="search_web">
<parameter name="query">data analysis best practices</parameter>
</invoke>
</function_calls>
"""

    thinking, calls4 = parser.extract_thinking_and_calls(xml_content_4)

    print(f"\nTest 4: Thinking + tool calls")
    print(f"  Thinking: {thinking[:100] if thinking else 'None'}...")
    print(f"  Tool calls: {len(calls4)}")

    # Statistics
    print(f"\nParser statistics:")
    stats = parser.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    # Test validation
    print(f"\nTest 5: Validation")
    if calls:
        is_valid, error = parser.validate_tool_call(calls[0])
        print(f"  Valid: {is_valid}")
        if error:
            print(f"  Error: {error}")

    # Test OpenAI format conversion
    print(f"\nTest 6: OpenAI format conversion")
    openai_format = convert_xml_to_openai_format(calls[:1])
    print(f"  OpenAI format:")
    print(f"  {json.dumps(openai_format, indent=2)}")

    print("\n" + "=" * 60)
    print("[OK] All tests completed!")
    print("=" * 60)
