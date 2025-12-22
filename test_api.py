"""
API 接口测试脚本

测试 Weaver 后端所有主要 API 端点
"""

import asyncio
import httpx
import json
import sys
import io
from typing import Dict, Any, Optional

# 修复 Windows 控制台编码问题
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

BASE_URL = "http://localhost:8000"

# 测试结果统计
results = {
    "passed": [],
    "failed": [],
    "skipped": []
}


def print_result(name: str, success: bool, message: str = ""):
    """打印测试结果"""
    status = "✅ PASS" if success else "❌ FAIL"
    print(f"{status} | {name}")
    if message:
        print(f"       {message}")

    if success:
        results["passed"].append(name)
    else:
        results["failed"].append((name, message))


def print_skip(name: str, reason: str = ""):
    """打印跳过的测试"""
    print(f"⏭️ SKIP | {name}")
    if reason:
        print(f"       {reason}")
    results["skipped"].append((name, reason))


async def test_health(client: httpx.AsyncClient):
    """测试健康检查端点"""
    try:
        resp = await client.get("/health")
        print_result("GET /health", resp.status_code == 200, f"status={resp.status_code}")
    except Exception as e:
        print_result("GET /health", False, str(e))


async def test_docs(client: httpx.AsyncClient):
    """测试文档端点"""
    try:
        resp = await client.get("/docs")
        print_result("GET /docs", resp.status_code == 200, f"status={resp.status_code}")
    except Exception as e:
        print_result("GET /docs", False, str(e))


async def test_openapi(client: httpx.AsyncClient):
    """测试 OpenAPI 规范"""
    try:
        resp = await client.get("/openapi.json")
        success = resp.status_code == 200
        if success:
            data = resp.json()
            paths_count = len(data.get("paths", {}))
            print_result("GET /openapi.json", True, f"paths={paths_count}")
        else:
            print_result("GET /openapi.json", False, f"status={resp.status_code}")
    except Exception as e:
        print_result("GET /openapi.json", False, str(e))


async def test_metrics(client: httpx.AsyncClient):
    """测试 Prometheus 指标"""
    try:
        resp = await client.get("/metrics")
        print_result("GET /metrics", resp.status_code == 200, f"status={resp.status_code}")
    except Exception as e:
        print_result("GET /metrics", False, str(e))


# ==================== Agent APIs ====================

async def test_agents_list(client: httpx.AsyncClient):
    """测试获取 Agent 列表"""
    try:
        resp = await client.get("/api/agents")
        success = resp.status_code == 200
        if success:
            data = resp.json()
            count = len(data) if isinstance(data, list) else 0
            print_result("GET /api/agents", True, f"agents={count}")
        else:
            print_result("GET /api/agents", False, f"status={resp.status_code}")
    except Exception as e:
        print_result("GET /api/agents", False, str(e))


async def test_agent_get(client: httpx.AsyncClient):
    """测试获取单个 Agent"""
    try:
        resp = await client.get("/api/agents/default")
        success = resp.status_code in [200, 404]
        print_result("GET /api/agents/default", success, f"status={resp.status_code}")
    except Exception as e:
        print_result("GET /api/agents/default", False, str(e))


# ==================== Chat APIs ====================

async def test_chat_simple(client: httpx.AsyncClient):
    """测试简单聊天（非流式）"""
    try:
        resp = await client.post(
            "/api/chat",
            json={
                "messages": [{"role": "user", "content": "Hello, just say 'Hi' back."}],
                "stream": False,
                "search_mode": ""
            },
            timeout=60.0
        )
        success = resp.status_code == 200
        if success:
            data = resp.json()
            content_len = len(data.get("content", ""))
            print_result("POST /api/chat (non-stream)", True, f"response_len={content_len}")
        else:
            print_result("POST /api/chat (non-stream)", False, f"status={resp.status_code}")
    except httpx.TimeoutException:
        print_result("POST /api/chat (non-stream)", False, "Timeout")
    except Exception as e:
        print_result("POST /api/chat (non-stream)", False, str(e))


async def test_chat_stream(client: httpx.AsyncClient):
    """测试流式聊天"""
    try:
        async with client.stream(
            "POST",
            "/api/chat",
            json={
                "messages": [{"role": "user", "content": "Say 'test' only."}],
                "stream": True,
                "search_mode": ""
            },
            timeout=60.0
        ) as resp:
            if resp.status_code == 200:
                event_count = 0
                async for line in resp.aiter_lines():
                    if line:
                        event_count += 1
                        if event_count >= 3:  # 只读取前几个事件
                            break
                print_result("POST /api/chat (stream)", True, f"events_received={event_count}")
            else:
                print_result("POST /api/chat (stream)", False, f"status={resp.status_code}")
    except httpx.TimeoutException:
        print_result("POST /api/chat (stream)", False, "Timeout")
    except Exception as e:
        print_result("POST /api/chat (stream)", False, str(e))


async def test_chat_cancel(client: httpx.AsyncClient):
    """测试取消聊天"""
    try:
        resp = await client.post("/api/chat/cancel/test_thread_123")
        # 即使没有活跃的线程，也应该返回成功
        success = resp.status_code in [200, 404]
        print_result("POST /api/chat/cancel/{thread_id}", success, f"status={resp.status_code}")
    except Exception as e:
        print_result("POST /api/chat/cancel/{thread_id}", False, str(e))


# ==================== Browser APIs ====================

async def test_browser_info(client: httpx.AsyncClient):
    """测试获取浏览器会话信息"""
    try:
        resp = await client.get("/api/browser/test_thread/info")
        success = resp.status_code == 200
        if success:
            data = resp.json()
            active = data.get("active", False)
            print_result("GET /api/browser/{thread_id}/info", True, f"active={active}")
        else:
            print_result("GET /api/browser/{thread_id}/info", False, f"status={resp.status_code}")
    except Exception as e:
        print_result("GET /api/browser/{thread_id}/info", False, str(e))


async def test_browser_screenshot(client: httpx.AsyncClient):
    """测试浏览器截图（无活跃会话时应返回失败）"""
    try:
        resp = await client.post("/api/browser/test_thread/screenshot")
        success = resp.status_code == 200
        if success:
            data = resp.json()
            print_result("POST /api/browser/{thread_id}/screenshot", True, f"success={data.get('success')}")
        else:
            print_result("POST /api/browser/{thread_id}/screenshot", False, f"status={resp.status_code}")
    except Exception as e:
        print_result("POST /api/browser/{thread_id}/screenshot", False, str(e))


# ==================== Screenshot APIs ====================

async def test_screenshots_list(client: httpx.AsyncClient):
    """测试获取截图列表"""
    try:
        resp = await client.get("/api/screenshots")
        success = resp.status_code == 200
        if success:
            data = resp.json()
            count = data.get("count", 0)
            print_result("GET /api/screenshots", True, f"count={count}")
        else:
            print_result("GET /api/screenshots", False, f"status={resp.status_code}")
    except Exception as e:
        print_result("GET /api/screenshots", False, str(e))


async def test_screenshots_cleanup(client: httpx.AsyncClient):
    """测试清理截图"""
    try:
        resp = await client.post("/api/screenshots/cleanup")
        success = resp.status_code == 200
        if success:
            data = resp.json()
            deleted = data.get("deleted_count", 0)
            print_result("POST /api/screenshots/cleanup", True, f"deleted={deleted}")
        else:
            print_result("POST /api/screenshots/cleanup", False, f"status={resp.status_code}")
    except Exception as e:
        print_result("POST /api/screenshots/cleanup", False, str(e))


# ==================== Events API ====================

async def test_events_stream(client: httpx.AsyncClient):
    """测试事件流"""
    try:
        # 使用短超时，只验证连接能建立
        async with client.stream(
            "GET",
            "/api/events/test_thread",
            timeout=5.0
        ) as resp:
            if resp.status_code == 200:
                print_result("GET /api/events/{thread_id}", True, "stream connected")
            else:
                print_result("GET /api/events/{thread_id}", False, f"status={resp.status_code}")
    except httpx.TimeoutException:
        # 超时是正常的，说明流式连接正常工作
        print_result("GET /api/events/{thread_id}", True, "stream timeout (expected)")
    except Exception as e:
        print_result("GET /api/events/{thread_id}", False, str(e))


# ==================== Memory API ====================

async def test_memory_status(client: httpx.AsyncClient):
    """测试内存状态"""
    try:
        resp = await client.get("/api/memory/status")
        success = resp.status_code == 200
        if success:
            data = resp.json()
            enabled = data.get("enabled", False)
            print_result("GET /api/memory/status", True, f"enabled={enabled}")
        else:
            print_result("GET /api/memory/status", False, f"status={resp.status_code}")
    except Exception as e:
        print_result("GET /api/memory/status", False, str(e))


# ==================== MCP API ====================

async def test_mcp_config(client: httpx.AsyncClient):
    """测试 MCP 配置"""
    try:
        resp = await client.get("/api/mcp/config")
        success = resp.status_code == 200
        if success:
            data = resp.json()
            servers = len(data.get("servers", []))
            print_result("GET /api/mcp/config", True, f"servers={servers}")
        else:
            print_result("GET /api/mcp/config", False, f"status={resp.status_code}")
    except Exception as e:
        print_result("GET /api/mcp/config", False, str(e))


# ==================== Runs API ====================

async def test_runs_list(client: httpx.AsyncClient):
    """测试获取运行列表"""
    try:
        resp = await client.get("/api/runs")
        success = resp.status_code == 200
        if success:
            data = resp.json()
            count = len(data) if isinstance(data, list) else data.get("count", 0)
            print_result("GET /api/runs", True, f"count={count}")
        else:
            print_result("GET /api/runs", False, f"status={resp.status_code}")
    except Exception as e:
        print_result("GET /api/runs", False, str(e))


# ==================== Tasks API ====================

async def test_tasks_active(client: httpx.AsyncClient):
    """测试获取活跃任务"""
    try:
        resp = await client.get("/api/tasks/active")
        success = resp.status_code == 200
        if success:
            data = resp.json()
            count = len(data) if isinstance(data, list) else 0
            print_result("GET /api/tasks/active", True, f"count={count}")
        else:
            print_result("GET /api/tasks/active", False, f"status={resp.status_code}")
    except Exception as e:
        print_result("GET /api/tasks/active", False, str(e))


# ==================== Triggers API ====================

async def test_triggers_list(client: httpx.AsyncClient):
    """测试获取触发器列表"""
    try:
        resp = await client.get("/api/triggers")
        success = resp.status_code == 200
        if success:
            data = resp.json()
            count = len(data) if isinstance(data, list) else 0
            print_result("GET /api/triggers", True, f"count={count}")
        else:
            print_result("GET /api/triggers", False, f"status={resp.status_code}")
    except Exception as e:
        print_result("GET /api/triggers", False, str(e))


# ==================== TTS API ====================

async def test_tts_status(client: httpx.AsyncClient):
    """测试 TTS 状态"""
    try:
        resp = await client.get("/api/tts/status")
        success = resp.status_code == 200
        if success:
            data = resp.json()
            available = data.get("available", False)
            print_result("GET /api/tts/status", True, f"available={available}")
        else:
            print_result("GET /api/tts/status", False, f"status={resp.status_code}")
    except Exception as e:
        print_result("GET /api/tts/status", False, str(e))


async def test_tts_voices(client: httpx.AsyncClient):
    """测试获取 TTS 声音列表"""
    try:
        resp = await client.get("/api/tts/voices")
        success = resp.status_code == 200
        if success:
            data = resp.json()
            count = len(data.get("voices", []))
            print_result("GET /api/tts/voices", True, f"voices={count}")
        else:
            print_result("GET /api/tts/voices", False, f"status={resp.status_code}")
    except Exception as e:
        print_result("GET /api/tts/voices", False, str(e))


# ==================== ASR API ====================

async def test_asr_status(client: httpx.AsyncClient):
    """测试 ASR 状态"""
    try:
        resp = await client.get("/api/asr/status")
        success = resp.status_code == 200
        if success:
            data = resp.json()
            available = data.get("available", False)
            print_result("GET /api/asr/status", True, f"available={available}")
        else:
            print_result("GET /api/asr/status", False, f"status={resp.status_code}")
    except Exception as e:
        print_result("GET /api/asr/status", False, str(e))


async def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("Weaver API 接口测试")
    print("=" * 60)
    print(f"Base URL: {BASE_URL}")
    print()

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # 基础端点
        print("\n--- 基础端点 ---")
        await test_health(client)
        await test_docs(client)
        await test_openapi(client)
        await test_metrics(client)

        # Agent APIs
        print("\n--- Agent APIs ---")
        await test_agents_list(client)
        await test_agent_get(client)

        # Chat APIs
        print("\n--- Chat APIs ---")
        await test_chat_simple(client)
        await test_chat_stream(client)
        await test_chat_cancel(client)

        # Browser APIs
        print("\n--- Browser APIs ---")
        await test_browser_info(client)
        await test_browser_screenshot(client)

        # Screenshot APIs
        print("\n--- Screenshot APIs ---")
        await test_screenshots_list(client)
        await test_screenshots_cleanup(client)

        # Events API
        print("\n--- Events API ---")
        await test_events_stream(client)

        # Memory API
        print("\n--- Memory API ---")
        await test_memory_status(client)

        # MCP API
        print("\n--- MCP API ---")
        await test_mcp_config(client)

        # Runs API
        print("\n--- Runs API ---")
        await test_runs_list(client)

        # Tasks API
        print("\n--- Tasks API ---")
        await test_tasks_active(client)

        # Triggers API
        print("\n--- Triggers API ---")
        await test_triggers_list(client)

        # TTS API
        print("\n--- TTS API ---")
        await test_tts_status(client)
        await test_tts_voices(client)

        # ASR API
        print("\n--- ASR API ---")
        await test_asr_status(client)

    # 打印总结
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    print(f"✅ 通过: {len(results['passed'])}")
    print(f"❌ 失败: {len(results['failed'])}")
    print(f"⏭️ 跳过: {len(results['skipped'])}")

    if results["failed"]:
        print("\n失败的测试:")
        for name, msg in results["failed"]:
            print(f"  - {name}: {msg}")

    total = len(results["passed"]) + len(results["failed"])
    if total > 0:
        success_rate = len(results["passed"]) / total * 100
        print(f"\n成功率: {success_rate:.1f}%")

    return len(results["failed"]) == 0


if __name__ == "__main__":
    print("请确保后端服务器正在运行: uvicorn main:app --reload")
    print()

    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
