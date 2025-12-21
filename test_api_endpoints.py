"""
Comprehensive API Endpoint Testing Script

Tests all API endpoints in the Weaver backend:
- Basic endpoints (health, status)
- Chat endpoints
- Agent management
- MCP configuration
- Memory and storage
- ASR/TTS services
- Screenshot services
- Trigger system
- Metrics and monitoring

Usage:
    python test_api_endpoints.py

Prerequisites:
    - Server running on http://localhost:8000
    - pip install requests
"""

import requests
import json
import time
import base64
from typing import Dict, Any, List, Optional
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:8000"
TIMEOUT = 10

# Test results storage
test_results: List[Dict[str, Any]] = []


def log_test(endpoint: str, method: str, status: str, response_code: Optional[int] = None,
             message: str = "", response_time: Optional[float] = None):
    """Log test result."""
    result = {
        "endpoint": endpoint,
        "method": method,
        "status": status,
        "response_code": response_code,
        "message": message,
        "response_time": response_time,
        "timestamp": datetime.now().isoformat()
    }
    test_results.append(result)

    status_icon = "[OK]" if status == "PASS" else "[FAIL]" if status == "FAIL" else "[SKIP]"
    time_str = f" ({response_time:.3f}s)" if response_time else ""
    code_str = f" [{response_code}]" if response_code else ""
    print(f"{status_icon} {method:6} {endpoint:50}{code_str}{time_str}")
    if message:
        print(f"   └─ {message}")


def test_endpoint(method: str, endpoint: str, expected_codes: List[int] = None,
                 data: Optional[Dict] = None, json_data: Optional[Dict] = None,
                 files: Optional[Dict] = None, description: str = ""):
    """Generic endpoint test."""
    if expected_codes is None:
        expected_codes = [200]

    url = f"{BASE_URL}{endpoint}"

    try:
        start = time.time()

        if method == "GET":
            response = requests.get(url, timeout=TIMEOUT)
        elif method == "POST":
            if files:
                response = requests.post(url, data=data, files=files, timeout=TIMEOUT)
            elif json_data:
                response = requests.post(url, json=json_data, timeout=TIMEOUT)
            else:
                response = requests.post(url, data=data, timeout=TIMEOUT)
        elif method == "PUT":
            response = requests.put(url, json=json_data, timeout=TIMEOUT)
        elif method == "DELETE":
            response = requests.delete(url, timeout=TIMEOUT)
        else:
            log_test(endpoint, method, "SKIP", message=f"Unsupported method: {method}")
            return None

        elapsed = time.time() - start

        if response.status_code in expected_codes:
            log_test(endpoint, method, "PASS", response.status_code, description, elapsed)
            return response
        else:
            log_test(endpoint, method, "FAIL", response.status_code,
                    f"Expected {expected_codes}, got {response.status_code}", elapsed)
            return response

    except requests.exceptions.ConnectionError:
        log_test(endpoint, method, "FAIL", message="Connection refused - Server not running?")
        return None
    except requests.exceptions.Timeout:
        log_test(endpoint, method, "FAIL", message=f"Timeout after {TIMEOUT}s")
        return None
    except Exception as e:
        log_test(endpoint, method, "FAIL", message=str(e))
        return None


def print_section(title: str):
    """Print section header."""
    print(f"\n{'='*80}")
    print(f"{title}")
    print(f"{'='*80}")


def test_basic_endpoints():
    """Test basic health check endpoints."""
    print_section("1. Basic Endpoints")

    test_endpoint("GET", "/", description="Root health check")
    test_endpoint("GET", "/health", description="Detailed health check")


def test_chat_endpoints():
    """Test chat-related endpoints."""
    print_section("2. Chat Endpoints")

    # Test chat endpoint (non-streaming)
    chat_payload = {
        "messages": [{"role": "user", "content": "Hello"}],
        "stream": False,
        "model": "gpt-4o-mini"
    }
    response = test_endpoint("POST", "/api/chat", expected_codes=[200, 500],
                            json_data=chat_payload, description="Non-streaming chat")

    # Test support chat
    support_payload = {
        "message": "Test support message",
        "user_id": "test_user"
    }
    test_endpoint("POST", "/api/support/chat", expected_codes=[200, 500],
                 json_data=support_payload, description="Support chat")


def test_task_management():
    """Test task/cancellation endpoints."""
    print_section("3. Task Management")

    test_endpoint("GET", "/api/tasks/active", description="Get active tasks")

    # Test cancel (will fail if no task, that's ok)
    test_endpoint("POST", "/api/chat/cancel/test_thread_123",
                 expected_codes=[200, 404], description="Cancel specific task")

    test_endpoint("POST", "/api/chat/cancel-all",
                 expected_codes=[200], description="Cancel all tasks")


def test_agent_management():
    """Test agent profile management."""
    print_section("4. Agent Management")

    # List agents
    response = test_endpoint("GET", "/api/agents", description="List all agents")

    # Get default agent
    test_endpoint("GET", "/api/agents/default", description="Get default agent")

    # Get non-existent agent
    test_endpoint("GET", "/api/agents/nonexistent", expected_codes=[404],
                 description="Get non-existent agent")

    # Create test agent
    create_payload = {
        "id": "test_agent_123",
        "name": "Test Agent",
        "description": "Test agent for API testing",
        "system_prompt": "You are a test agent.",
        "enabled_tools": {"web_search": True}
    }
    response = test_endpoint("POST", "/api/agents", json_data=create_payload,
                            description="Create test agent")

    # Update agent (if created successfully)
    if response and response.status_code == 200:
        update_payload = {
            "name": "Updated Test Agent",
            "description": "Updated description",
            "system_prompt": "Updated prompt",
            "enabled_tools": {"web_search": True, "python": True}
        }
        test_endpoint("PUT", "/api/agents/test_agent_123", json_data=update_payload,
                     description="Update test agent")

        # Delete test agent
        test_endpoint("DELETE", "/api/agents/test_agent_123",
                     description="Delete test agent")

    # Try to delete protected agent
    test_endpoint("DELETE", "/api/agents/default", expected_codes=[400],
                 description="Delete protected agent (should fail)")


def test_mcp_config():
    """Test MCP configuration endpoints."""
    print_section("5. MCP Configuration")

    test_endpoint("GET", "/api/mcp/config", description="Get MCP config")

    # Update config (minimal change)
    config_payload = {
        "enable": False
    }
    test_endpoint("POST", "/api/mcp/config", json_data=config_payload,
                 expected_codes=[200, 500], description="Update MCP config")


def test_memory_status():
    """Test memory status endpoint."""
    print_section("6. Memory & Storage")

    test_endpoint("GET", "/api/memory/status", description="Get memory status")


def test_runs_metrics():
    """Test runs and metrics endpoints."""
    print_section("7. Runs & Metrics")

    test_endpoint("GET", "/api/runs", description="List all runs")

    # Test specific run (will fail if not exists)
    test_endpoint("GET", "/api/runs/test_thread_123", expected_codes=[200, 404],
                 description="Get specific run metrics")

    # Test Prometheus metrics (may be disabled)
    test_endpoint("GET", "/metrics", expected_codes=[200, 404],
                 description="Prometheus metrics")


def test_asr_endpoints():
    """Test ASR (speech recognition) endpoints."""
    print_section("8. ASR (Speech Recognition)")

    test_endpoint("GET", "/api/asr/status", description="ASR status")

    # Test ASR recognize with dummy base64 audio
    asr_payload = {
        "audio_data": "dGVzdA==",  # "test" in base64
        "format": "wav",
        "sample_rate": 16000
    }
    test_endpoint("POST", "/api/asr/recognize", expected_codes=[200, 400, 503],
                 json_data=asr_payload, description="ASR recognize (base64)")


def test_tts_endpoints():
    """Test TTS (text-to-speech) endpoints."""
    print_section("9. TTS (Text-to-Speech)")

    test_endpoint("GET", "/api/tts/status", description="TTS status")
    test_endpoint("GET", "/api/tts/voices", description="Get TTS voices")

    # Test TTS synthesis
    tts_payload = {
        "text": "Hello, this is a test.",
        "voice": "longxiaochun"
    }
    test_endpoint("POST", "/api/tts/synthesize", expected_codes=[200, 503],
                 json_data=tts_payload, description="TTS synthesize")


def test_screenshot_endpoints():
    """Test screenshot service endpoints."""
    print_section("10. Screenshot Service")

    test_endpoint("GET", "/api/screenshots", description="List screenshots")

    # Test with thread_id filter
    test_endpoint("GET", "/api/screenshots?thread_id=test&limit=10",
                 description="List screenshots (filtered)")

    # Test get specific screenshot (will fail if not exists)
    test_endpoint("GET", "/api/screenshots/nonexistent.png", expected_codes=[200, 404],
                 description="Get specific screenshot")

    # Test cleanup
    test_endpoint("POST", "/api/screenshots/cleanup",
                 description="Cleanup old screenshots")


def test_trigger_system():
    """Test trigger system endpoints."""
    print_section("11. Trigger System")

    test_endpoint("GET", "/api/triggers", description="List all triggers")

    # Create scheduled trigger
    scheduled_payload = {
        "name": "Test Scheduled Trigger",
        "description": "Test trigger",
        "schedule": "0 0 * * *",  # Daily at midnight
        "agent_id": "default",
        "task": "test_task",
        "task_params": {}
    }
    response = test_endpoint("POST", "/api/triggers/scheduled",
                            json_data=scheduled_payload,
                            description="Create scheduled trigger")

    trigger_id = None
    if response and response.status_code == 200:
        try:
            data = response.json()
            trigger_id = data.get("trigger_id")
        except:
            pass

    # Create webhook trigger
    webhook_payload = {
        "name": "Test Webhook Trigger",
        "description": "Test webhook",
        "agent_id": "default",
        "task": "test_task",
        "task_params": {},
        "http_methods": ["POST"]
    }
    test_endpoint("POST", "/api/triggers/webhook",
                 json_data=webhook_payload,
                 description="Create webhook trigger")

    # Create event trigger
    event_payload = {
        "name": "Test Event Trigger",
        "description": "Test event",
        "event_type": "test_event",
        "agent_id": "default",
        "task": "test_task",
        "task_params": {}
    }
    test_endpoint("POST", "/api/triggers/event",
                 json_data=event_payload,
                 description="Create event trigger")

    # If we got a trigger_id, test other operations
    if trigger_id:
        test_endpoint("GET", f"/api/triggers/{trigger_id}",
                     description=f"Get trigger {trigger_id}")

        test_endpoint("GET", f"/api/triggers/{trigger_id}/executions",
                     description="Get trigger executions")

        test_endpoint("POST", f"/api/triggers/{trigger_id}/pause",
                     description="Pause trigger")

        test_endpoint("POST", f"/api/triggers/{trigger_id}/resume",
                     description="Resume trigger")

        test_endpoint("DELETE", f"/api/triggers/{trigger_id}",
                     description="Delete trigger")


def test_interrupt_resume():
    """Test interrupt/resume functionality."""
    print_section("12. Interrupt & Resume")

    # This will fail without a valid thread_id and checkpoint
    resume_payload = {
        "thread_id": "test_thread_123",
        "payload": {"test": "data"}
    }
    test_endpoint("POST", "/api/interrupt/resume", expected_codes=[200, 400, 404],
                 json_data=resume_payload, description="Resume interrupted task")


def generate_report():
    """Generate test report."""
    print_section("Test Summary")

    total = len(test_results)
    passed = sum(1 for r in test_results if r["status"] == "PASS")
    failed = sum(1 for r in test_results if r["status"] == "FAIL")
    skipped = sum(1 for r in test_results if r["status"] == "SKIP")

    pass_rate = (passed / total * 100) if total > 0 else 0

    print(f"\nTotal Tests:    {total}")
    print(f"[OK] Passed:    {passed}")
    print(f"[FAIL] Failed:  {failed}")
    print(f"[SKIP] Skipped: {skipped}")
    print(f"Pass Rate:      {pass_rate:.1f}%")

    if failed > 0:
        print("\n[FAIL] Failed Tests:")
        for result in test_results:
            if result["status"] == "FAIL":
                print(f"  - {result['method']} {result['endpoint']}")
                if result["message"]:
                    print(f"    {result['message']}")

    # Calculate average response time for successful requests
    times = [r["response_time"] for r in test_results
             if r["response_time"] is not None and r["status"] == "PASS"]
    if times:
        avg_time = sum(times) / len(times)
        print(f"\nAverage Response Time: {avg_time:.3f}s")

    # Save detailed report
    report_file = "test_api_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump({
            "summary": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "pass_rate": pass_rate,
                "timestamp": datetime.now().isoformat()
            },
            "results": test_results
        }, f, indent=2, ensure_ascii=False)

    print(f"\n[REPORT] Detailed report saved to: {report_file}")


def main():
    """Run all tests."""
    print("="*80)
    print("Weaver API Endpoint Testing")
    print("="*80)
    print(f"Base URL: {BASE_URL}")
    print(f"Timeout: {TIMEOUT}s")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Check if server is running
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        print(f"[OK] Server is running (status: {response.status_code})")
    except:
        print("[FAIL] Server is not running!")
        print("Please start the server with: python main.py")
        return

    # Run all test suites
    test_basic_endpoints()
    test_chat_endpoints()
    test_task_management()
    test_agent_management()
    test_mcp_config()
    test_memory_status()
    test_runs_metrics()
    test_asr_endpoints()
    test_tts_endpoints()
    test_screenshot_endpoints()
    test_trigger_system()
    test_interrupt_resume()

    # Generate report
    generate_report()

    print("\n" + "="*80)
    print("Testing Complete!")
    print("="*80)


if __name__ == "__main__":
    main()
