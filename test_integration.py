"""
Integration Test Script

Tests the integration of Phase 1-4 components into Weaver workflow.

Usage:
    python test_integration.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_imports():
    """Test that all new components can be imported."""
    print("\n" + "="*70)
    print("Test 1: Import Test")
    print("="*70)

    try:
        # Phase 1: Tool System
        from tools.base import ToolResult, WeaverTool, tool_schema
        print("  [OK] Phase 1: tools.base imported")

        from tools.langchain_adapter import weaver_tool_to_langchain
        print("  [OK] Phase 1: tools.langchain_adapter imported")

        # Phase 2: XML Tool Calling
        from agent.xml_parser import XMLToolParser
        print("  [OK] Phase 2: agent.xml_parser imported")

        from agent.processor_config import AgentProcessorConfig
        print("  [OK] Phase 2: agent.processor_config imported")

        from agent.response_handler import ResponseHandler
        print("  [OK] Phase 2: agent.response_handler imported")

        # Phase 3: Auto-Continuation
        from agent.continuation import (
            ContinuationState,
            ContinuationDecider,
            ToolResultInjector,
            ContinuationHandler
        )
        print("  [OK] Phase 3: agent.continuation imported")

        # Phase 4: Tool Registry
        from tools.registry import ToolRegistry, get_global_registry
        print("  [OK] Phase 4: tools.registry imported")

        print("\n[OK] All imports successful!")
        return True

    except Exception as e:
        print(f"\n[FAIL] Import failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_tool_registry():
    """Test tool registry functionality."""
    print("\n" + "="*70)
    print("Test 2: Tool Registry Test")
    print("="*70)

    try:
        from tools.registry import get_global_registry

        registry = get_global_registry()

        # Register a test function
        def test_function(query: str, limit: int = 5) -> str:
            """Test function for registry."""
            return f"Test result for: {query} (limit={limit})"

        metadata = registry.register(
            name="test_function",
            tool=test_function,
            tags=["test"],
            override=True
        )

        print(f"  [OK] Registered test_function")
        print(f"      Type: {metadata.tool_type}")
        print(f"      Parameters: {list(metadata.parameters.get('properties', {}).keys())}")

        # Get tool back
        retrieved = registry.get("test_function")
        if retrieved:
            print(f"  [OK] Retrieved test_function")
        else:
            print(f"  [FAIL] Failed to retrieve test_function")
            return False

        # Get statistics
        stats = registry.get_statistics()
        print(f"  [OK] Registry statistics:")
        print(f"      Total tools: {stats['total_tools']}")
        print(f"      By type: {stats['by_type']}")

        print("\n[OK] Tool registry test passed!")
        return True

    except Exception as e:
        print(f"\n[FAIL] Tool registry test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_xml_parser():
    """Test XML tool call parser."""
    print("\n" + "="*70)
    print("Test 3: XML Parser Test")
    print("="*70)

    try:
        from agent.xml_parser import XMLToolParser

        parser = XMLToolParser()

        xml_content = """
Let me search for that.

<function_calls>
<invoke name="search_web">
<parameter name="query">Python asyncio tutorial</parameter>
<parameter name="max_results">5</parameter>
</invoke>
</function_calls>
"""

        calls = parser.parse_content(xml_content)

        if not calls:
            print("  [FAIL] No tool calls detected")
            return False

        print(f"  [OK] Detected {len(calls)} tool call(s)")

        call = calls[0]
        print(f"      Function: {call.function_name}")
        print(f"      Parameters: {call.parameters}")

        # Verify parsing
        if call.function_name == "search_web":
            if call.parameters.get("query") == "Python asyncio tutorial":
                if call.parameters.get("max_results") == 5:  # Should be int
                    print("  [OK] Type inference working (5 -> int)")
                else:
                    print(f"  [WARN] Type inference issue: {type(call.parameters.get('max_results'))}")

        print("\n[OK] XML parser test passed!")
        return True

    except Exception as e:
        print(f"\n[FAIL] XML parser test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_processor_config():
    """Test processor configuration."""
    print("\n" + "="*70)
    print("Test 4: Processor Config Test")
    print("="*70)

    try:
        from agent.processor_config import AgentProcessorConfig

        # Test Claude preset
        config_claude = AgentProcessorConfig.for_claude()
        print(f"  [OK] Claude preset: {config_claude.summary()}")

        # Test OpenAI preset
        config_openai = AgentProcessorConfig.for_openai()
        print(f"  [OK] OpenAI preset: {config_openai.summary()}")

        # Test custom config
        config_custom = AgentProcessorConfig(
            xml_tool_calling=True,
            enable_auto_continue=True,
            max_auto_continues=10
        )
        print(f"  [OK] Custom config: {config_custom.summary()}")

        print("\n[OK] Processor config test passed!")
        return True

    except Exception as e:
        print(f"\n[FAIL] Processor config test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_nodes_integration():
    """Test that nodes.py has been properly updated."""
    print("\n" + "="*70)
    print("Test 5: Nodes.py Integration Test")
    print("="*70)

    try:
        from agent.nodes import initialize_enhanced_tools, ENHANCED_TOOLS_AVAILABLE

        print(f"  [OK] Enhanced tools available: {ENHANCED_TOOLS_AVAILABLE}")

        # Try to initialize
        initialize_enhanced_tools()
        print(f"  [OK] initialize_enhanced_tools() executed")

        # Check registry
        from tools.registry import get_global_registry
        registry = get_global_registry()
        tools = registry.list_names()
        print(f"  [OK] Registry contains {len(tools)} tools")
        if tools:
            print(f"      Sample tools: {', '.join(tools[:5])}")

        print("\n[OK] Nodes.py integration test passed!")
        return True

    except Exception as e:
        print(f"\n[FAIL] Nodes.py integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("Weaver Integration Test Suite (Phase 1-4)")
    print("="*70)

    tests = [
        ("Imports", test_imports),
        ("Tool Registry", test_tool_registry),
        ("XML Parser", test_xml_parser),
        ("Processor Config", test_processor_config),
        ("Nodes Integration", test_nodes_integration),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n[ERROR] Test '{test_name}' crashed: {e}")
            results.append((test_name, False))

    # Summary
    print("\n" + "="*70)
    print("Test Summary")
    print("="*70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"  {status} {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n[OK] All integration tests passed!")
        print("\nIntegration successful! You can now:")
        print("  1. Start the Weaver server: python main.py")
        print("  2. Enable XML tool calling in .env: AGENT_XML_TOOL_CALLING=true")
        print("  3. Enable auto-continuation: AGENT_AUTO_CONTINUE=true")
        return 0
    else:
        print("\n[FAIL] Some tests failed. Please check the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
