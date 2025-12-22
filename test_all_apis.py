#!/usr/bin/env python3
"""
Weaver API 全接口测试脚本
"""
import httpx
import asyncio
import json
import sys
from datetime import datetime

BASE_URL = "http://localhost:8000"
TIMEOUT = 30.0

# 测试结果统计
results = {"passed": 0, "failed": 0, "skipped": 0, "tests": []}


def log_result(name: str, status: str, message: str = "", response: dict = None):
    """记录测试结果"""
    results["tests"].append({
        "name": name,
        "status": status,
        "message": message,
        "response": response
    })
    if status == "PASS":
        results["passed"] += 1
        print(f"  ✓ {name}")
    elif status == "FAIL":
        results["failed"] += 1
        print(f"  ✗ {name}: {message}")
    else:
        results["skipped"] += 1
        print(f"  ⊘ {name}: {message}")


async def test_health_endpoints(client: httpx.AsyncClient):
    """测试健康检查接口"""
    print("\n[1/11] 测试健康检查接口")
    print("-" * 40)

    # GET /
    try:
        r = await client.get("/")
        if r.status_code == 200 and r.json().get("status") == "healthy":
            log_result("GET /", "PASS", response=r.json())
        else:
            log_result("GET /", "FAIL", f"status={r.status_code}")
    except Exception as e:
        log_result("GET /", "FAIL", str(e))

    # GET /health
    try:
        r = await client.get("/health")
        if r.status_code == 200:
            log_result("GET /health", "PASS", response=r.json())
        else:
            log_result("GET /health", "FAIL", f"status={r.status_code}")
    except Exception as e:
        log_result("GET /health", "FAIL", str(e))


async def test_task_endpoints(client: httpx.AsyncClient):
    """测试任务管理接口"""
    print("\n[2/11] 测试任务管理接口")
    print("-" * 40)

    # GET /api/tasks/active
    try:
        r = await client.get("/api/tasks/active")
        if r.status_code == 200:
            log_result("GET /api/tasks/active", "PASS", response=r.json())
        else:
            log_result("GET /api/tasks/active", "FAIL", f"status={r.status_code}")
    except Exception as e:
        log_result("GET /api/tasks/active", "FAIL", str(e))

    # GET /api/runs
    try:
        r = await client.get("/api/runs")
        if r.status_code == 200:
            log_result("GET /api/runs", "PASS", response=r.json())
        else:
            log_result("GET /api/runs", "FAIL", f"status={r.status_code}")
    except Exception as e:
        log_result("GET /api/runs", "FAIL", str(e))

    # GET /api/runs/{thread_id} - should return 404 for non-existent
    try:
        r = await client.get("/api/runs/nonexistent_thread")
        if r.status_code == 404:
            log_result("GET /api/runs/{thread_id} (404)", "PASS")
        else:
            log_result("GET /api/runs/{thread_id} (404)", "FAIL", f"expected 404, got {r.status_code}")
    except Exception as e:
        log_result("GET /api/runs/{thread_id} (404)", "FAIL", str(e))


async def test_agent_endpoints(client: httpx.AsyncClient):
    """测试 Agent 管理接口"""
    print("\n[3/11] 测试 Agent 管理接口")
    print("-" * 40)

    # GET /api/agents
    try:
        r = await client.get("/api/agents")
        if r.status_code == 200 and "agents" in r.json():
            log_result("GET /api/agents", "PASS", response=r.json())
        else:
            log_result("GET /api/agents", "FAIL", f"status={r.status_code}")
    except Exception as e:
        log_result("GET /api/agents", "FAIL", str(e))

    # GET /api/agents/default
    try:
        r = await client.get("/api/agents/default")
        if r.status_code == 200:
            log_result("GET /api/agents/default", "PASS", response=r.json())
        else:
            log_result("GET /api/agents/default", "FAIL", f"status={r.status_code}")
    except Exception as e:
        log_result("GET /api/agents/default", "FAIL", str(e))

    # POST /api/agents - 创建测试 agent
    test_agent_id = f"test_agent_{int(datetime.now().timestamp())}"
    try:
        r = await client.post("/api/agents", json={
            "id": test_agent_id,
            "name": "Test Agent",
            "description": "A test agent for API testing",
            "system_prompt": "You are a helpful assistant.",
            "enabled_tools": {"web_search": True}
        })
        if r.status_code == 200:
            log_result("POST /api/agents", "PASS", response=r.json())
        else:
            log_result("POST /api/agents", "FAIL", f"status={r.status_code}, {r.text}")
    except Exception as e:
        log_result("POST /api/agents", "FAIL", str(e))

    # PUT /api/agents/{agent_id}
    try:
        r = await client.put(f"/api/agents/{test_agent_id}", json={
            "name": "Updated Test Agent",
            "description": "Updated description",
            "system_prompt": "Updated prompt",
            "enabled_tools": {"web_search": True, "browser": True}
        })
        if r.status_code == 200:
            log_result(f"PUT /api/agents/{test_agent_id}", "PASS", response=r.json())
        else:
            log_result(f"PUT /api/agents/{test_agent_id}", "FAIL", f"status={r.status_code}")
    except Exception as e:
        log_result(f"PUT /api/agents/{test_agent_id}", "FAIL", str(e))

    # DELETE /api/agents/{agent_id}
    try:
        r = await client.delete(f"/api/agents/{test_agent_id}")
        if r.status_code == 200:
            log_result(f"DELETE /api/agents/{test_agent_id}", "PASS", response=r.json())
        else:
            log_result(f"DELETE /api/agents/{test_agent_id}", "FAIL", f"status={r.status_code}")
    except Exception as e:
        log_result(f"DELETE /api/agents/{test_agent_id}", "FAIL", str(e))

    # DELETE /api/agents/default - should fail (protected)
    try:
        r = await client.delete("/api/agents/default")
        if r.status_code == 400:
            log_result("DELETE /api/agents/default (protected)", "PASS")
        else:
            log_result("DELETE /api/agents/default (protected)", "FAIL", f"expected 400, got {r.status_code}")
    except Exception as e:
        log_result("DELETE /api/agents/default (protected)", "FAIL", str(e))


async def test_mcp_endpoints(client: httpx.AsyncClient):
    """测试 MCP 配置接口"""
    print("\n[4/11] 测试 MCP 配置接口")
    print("-" * 40)

    # GET /api/mcp/config
    try:
        r = await client.get("/api/mcp/config")
        if r.status_code == 200:
            log_result("GET /api/mcp/config", "PASS", response=r.json())
        else:
            log_result("GET /api/mcp/config", "FAIL", f"status={r.status_code}")
    except Exception as e:
        log_result("GET /api/mcp/config", "FAIL", str(e))

    # POST /api/mcp/config - 更新配置
    try:
        r = await client.post("/api/mcp/config", json={
            "enable": False,
            "servers": {}
        })
        if r.status_code == 200:
            log_result("POST /api/mcp/config", "PASS", response=r.json())
        else:
            log_result("POST /api/mcp/config", "FAIL", f"status={r.status_code}")
    except Exception as e:
        log_result("POST /api/mcp/config", "FAIL", str(e))


async def test_memory_endpoints(client: httpx.AsyncClient):
    """测试内存状态接口"""
    print("\n[5/11] 测试内存状态接口")
    print("-" * 40)

    # GET /api/memory/status
    try:
        r = await client.get("/api/memory/status")
        if r.status_code == 200:
            log_result("GET /api/memory/status", "PASS", response=r.json())
        else:
            log_result("GET /api/memory/status", "FAIL", f"status={r.status_code}")
    except Exception as e:
        log_result("GET /api/memory/status", "FAIL", str(e))


async def test_asr_endpoints(client: httpx.AsyncClient):
    """测试 ASR 接口"""
    print("\n[6/11] 测试 ASR 接口")
    print("-" * 40)

    # GET /api/asr/status
    try:
        r = await client.get("/api/asr/status")
        if r.status_code == 200:
            log_result("GET /api/asr/status", "PASS", response=r.json())
        else:
            log_result("GET /api/asr/status", "FAIL", f"status={r.status_code}")
    except Exception as e:
        log_result("GET /api/asr/status", "FAIL", str(e))

    # POST /api/asr/recognize - 需要有效音频数据，跳过实际识别
    try:
        r = await client.post("/api/asr/recognize", json={
            "audio_data": "dGVzdA==",  # "test" in base64
            "format": "wav",
            "sample_rate": 16000
        })
        # 可能返回503(服务未配置)或其他错误，只要不是500就算通过
        if r.status_code in [200, 400, 503]:
            log_result("POST /api/asr/recognize", "PASS", f"status={r.status_code}")
        else:
            log_result("POST /api/asr/recognize", "FAIL", f"status={r.status_code}")
    except Exception as e:
        log_result("POST /api/asr/recognize", "FAIL", str(e))


async def test_tts_endpoints(client: httpx.AsyncClient):
    """测试 TTS 接口"""
    print("\n[7/11] 测试 TTS 接口")
    print("-" * 40)

    # GET /api/tts/status
    try:
        r = await client.get("/api/tts/status")
        if r.status_code == 200:
            log_result("GET /api/tts/status", "PASS", response=r.json())
        else:
            log_result("GET /api/tts/status", "FAIL", f"status={r.status_code}")
    except Exception as e:
        log_result("GET /api/tts/status", "FAIL", str(e))

    # GET /api/tts/voices
    try:
        r = await client.get("/api/tts/voices")
        if r.status_code == 200 and "voices" in r.json():
            log_result("GET /api/tts/voices", "PASS", response=r.json())
        else:
            log_result("GET /api/tts/voices", "FAIL", f"status={r.status_code}")
    except Exception as e:
        log_result("GET /api/tts/voices", "FAIL", str(e))

    # POST /api/tts/synthesize
    try:
        r = await client.post("/api/tts/synthesize", json={
            "text": "Hello",
            "voice": "longxiaochun"
        })
        # 可能返回503(服务未配置)
        if r.status_code in [200, 503]:
            log_result("POST /api/tts/synthesize", "PASS", f"status={r.status_code}")
        else:
            log_result("POST /api/tts/synthesize", "FAIL", f"status={r.status_code}")
    except Exception as e:
        log_result("POST /api/tts/synthesize", "FAIL", str(e))


async def test_screenshot_endpoints(client: httpx.AsyncClient):
    """测试截图接口"""
    print("\n[8/11] 测试截图接口")
    print("-" * 40)

    # GET /api/screenshots
    try:
        r = await client.get("/api/screenshots")
        if r.status_code == 200 and "screenshots" in r.json():
            log_result("GET /api/screenshots", "PASS", response=r.json())
        else:
            log_result("GET /api/screenshots", "FAIL", f"status={r.status_code}")
    except Exception as e:
        log_result("GET /api/screenshots", "FAIL", str(e))

    # GET /api/screenshots/{filename} - should return 404 for non-existent
    try:
        r = await client.get("/api/screenshots/nonexistent.png")
        if r.status_code == 404:
            log_result("GET /api/screenshots/{filename} (404)", "PASS")
        else:
            log_result("GET /api/screenshots/{filename} (404)", "FAIL", f"expected 404, got {r.status_code}")
    except Exception as e:
        log_result("GET /api/screenshots/{filename} (404)", "FAIL", str(e))

    # POST /api/screenshots/cleanup
    try:
        r = await client.post("/api/screenshots/cleanup")
        if r.status_code == 200:
            log_result("POST /api/screenshots/cleanup", "PASS", response=r.json())
        else:
            log_result("POST /api/screenshots/cleanup", "FAIL", f"status={r.status_code}")
    except Exception as e:
        log_result("POST /api/screenshots/cleanup", "FAIL", str(e))


async def test_trigger_endpoints(client: httpx.AsyncClient):
    """测试触发器接口"""
    print("\n[9/11] 测试触发器接口")
    print("-" * 40)

    # GET /api/triggers
    try:
        r = await client.get("/api/triggers")
        if r.status_code == 200 and "triggers" in r.json():
            log_result("GET /api/triggers", "PASS", response=r.json())
        else:
            log_result("GET /api/triggers", "FAIL", f"status={r.status_code}")
    except Exception as e:
        log_result("GET /api/triggers", "FAIL", str(e))

    # POST /api/triggers/scheduled
    trigger_id = None
    try:
        r = await client.post("/api/triggers/scheduled", json={
            "name": "Test Scheduled Trigger",
            "description": "A test trigger",
            "schedule": "0 * * * *",  # Every hour
            "agent_id": "default",
            "task": "Test task",
            "task_params": {},
            "timezone": "Asia/Shanghai"
        })
        if r.status_code == 200:
            trigger_id = r.json().get("trigger_id")
            log_result("POST /api/triggers/scheduled", "PASS", response=r.json())
        else:
            log_result("POST /api/triggers/scheduled", "FAIL", f"status={r.status_code}, {r.text}")
    except Exception as e:
        log_result("POST /api/triggers/scheduled", "FAIL", str(e))

    # POST /api/triggers/webhook
    webhook_trigger_id = None
    try:
        r = await client.post("/api/triggers/webhook", json={
            "name": "Test Webhook Trigger",
            "description": "A test webhook",
            "agent_id": "default",
            "task": "Handle webhook",
            "task_params": {},
            "http_methods": ["POST"],
            "require_auth": False
        })
        if r.status_code == 200:
            webhook_trigger_id = r.json().get("trigger_id")
            log_result("POST /api/triggers/webhook", "PASS", response=r.json())
        else:
            log_result("POST /api/triggers/webhook", "FAIL", f"status={r.status_code}, {r.text}")
    except Exception as e:
        log_result("POST /api/triggers/webhook", "FAIL", str(e))

    # POST /api/triggers/event
    event_trigger_id = None
    try:
        r = await client.post("/api/triggers/event", json={
            "name": "Test Event Trigger",
            "description": "A test event trigger",
            "event_type": "test_event",
            "agent_id": "default",
            "task": "Handle event",
            "task_params": {}
        })
        if r.status_code == 200:
            event_trigger_id = r.json().get("trigger_id")
            log_result("POST /api/triggers/event", "PASS", response=r.json())
        else:
            log_result("POST /api/triggers/event", "FAIL", f"status={r.status_code}, {r.text}")
    except Exception as e:
        log_result("POST /api/triggers/event", "FAIL", str(e))

    # GET /api/triggers/{trigger_id}
    if trigger_id:
        try:
            r = await client.get(f"/api/triggers/{trigger_id}")
            if r.status_code == 200:
                log_result(f"GET /api/triggers/{trigger_id}", "PASS", response=r.json())
            else:
                log_result(f"GET /api/triggers/{trigger_id}", "FAIL", f"status={r.status_code}")
        except Exception as e:
            log_result(f"GET /api/triggers/{trigger_id}", "FAIL", str(e))

    # POST /api/triggers/{trigger_id}/pause
    if trigger_id:
        try:
            r = await client.post(f"/api/triggers/{trigger_id}/pause")
            if r.status_code == 200:
                log_result(f"POST /api/triggers/{trigger_id}/pause", "PASS", response=r.json())
            else:
                log_result(f"POST /api/triggers/{trigger_id}/pause", "FAIL", f"status={r.status_code}")
        except Exception as e:
            log_result(f"POST /api/triggers/{trigger_id}/pause", "FAIL", str(e))

    # POST /api/triggers/{trigger_id}/resume
    if trigger_id:
        try:
            r = await client.post(f"/api/triggers/{trigger_id}/resume")
            if r.status_code == 200:
                log_result(f"POST /api/triggers/{trigger_id}/resume", "PASS", response=r.json())
            else:
                log_result(f"POST /api/triggers/{trigger_id}/resume", "FAIL", f"status={r.status_code}")
        except Exception as e:
            log_result(f"POST /api/triggers/{trigger_id}/resume", "FAIL", str(e))

    # GET /api/triggers/{trigger_id}/executions
    if trigger_id:
        try:
            r = await client.get(f"/api/triggers/{trigger_id}/executions")
            if r.status_code == 200:
                log_result(f"GET /api/triggers/{trigger_id}/executions", "PASS", response=r.json())
            else:
                log_result(f"GET /api/triggers/{trigger_id}/executions", "FAIL", f"status={r.status_code}")
        except Exception as e:
            log_result(f"GET /api/triggers/{trigger_id}/executions", "FAIL", str(e))

    # DELETE triggers
    for tid in [trigger_id, webhook_trigger_id, event_trigger_id]:
        if tid:
            try:
                r = await client.delete(f"/api/triggers/{tid}")
                if r.status_code == 200:
                    log_result(f"DELETE /api/triggers/{tid}", "PASS")
                else:
                    log_result(f"DELETE /api/triggers/{tid}", "FAIL", f"status={r.status_code}")
            except Exception as e:
                log_result(f"DELETE /api/triggers/{tid}", "FAIL", str(e))


async def test_cancel_endpoints(client: httpx.AsyncClient):
    """测试取消任务接口"""
    print("\n[10/11] 测试取消任务接口")
    print("-" * 40)

    # POST /api/chat/cancel/{thread_id}
    try:
        r = await client.post("/api/chat/cancel/test_thread_123", json={
            "reason": "Test cancellation"
        })
        if r.status_code == 200:
            log_result("POST /api/chat/cancel/{thread_id}", "PASS", response=r.json())
        else:
            log_result("POST /api/chat/cancel/{thread_id}", "FAIL", f"status={r.status_code}")
    except Exception as e:
        log_result("POST /api/chat/cancel/{thread_id}", "FAIL", str(e))

    # POST /api/chat/cancel-all
    try:
        r = await client.post("/api/chat/cancel-all")
        if r.status_code == 200:
            log_result("POST /api/chat/cancel-all", "PASS", response=r.json())
        else:
            log_result("POST /api/chat/cancel-all", "FAIL", f"status={r.status_code}")
    except Exception as e:
        log_result("POST /api/chat/cancel-all", "FAIL", str(e))


async def test_chat_endpoint(client: httpx.AsyncClient):
    """测试聊天接口"""
    print("\n[11/11] 测试聊天接口")
    print("-" * 40)

    # POST /api/chat (non-streaming)
    try:
        r = await client.post("/api/chat", json={
            "messages": [{"role": "user", "content": "Hello, respond with just 'Hi'"}],
            "stream": False,
            "search_mode": "direct"
        }, timeout=60.0)
        if r.status_code == 200:
            log_result("POST /api/chat (non-streaming)", "PASS", response=r.json())
        else:
            log_result("POST /api/chat (non-streaming)", "FAIL", f"status={r.status_code}, {r.text[:200]}")
    except Exception as e:
        log_result("POST /api/chat (non-streaming)", "FAIL", str(e))

    # POST /api/chat (streaming) - 简单测试流式响应
    try:
        async with client.stream("POST", "/api/chat", json={
            "messages": [{"role": "user", "content": "Say 'OK'"}],
            "stream": True,
            "search_mode": "direct"
        }, timeout=60.0) as response:
            if response.status_code == 200:
                # 读取一些数据验证流式响应
                chunks = []
                async for chunk in response.aiter_text():
                    chunks.append(chunk)
                    if len(chunks) >= 3:  # 只读几个 chunk
                        break
                log_result("POST /api/chat (streaming)", "PASS", f"received {len(chunks)} chunks")
            else:
                log_result("POST /api/chat (streaming)", "FAIL", f"status={response.status_code}")
    except Exception as e:
        log_result("POST /api/chat (streaming)", "FAIL", str(e))

    # POST /api/support/chat
    try:
        r = await client.post("/api/support/chat", json={
            "message": "Hello support",
            "user_id": "test_user"
        }, timeout=60.0)
        if r.status_code == 200:
            log_result("POST /api/support/chat", "PASS", response=r.json())
        else:
            log_result("POST /api/support/chat", "FAIL", f"status={r.status_code}, {r.text[:200]}")
    except Exception as e:
        log_result("POST /api/support/chat", "FAIL", str(e))


async def main():
    """运行所有测试"""
    print("=" * 60)
    print("Weaver API 全接口测试")
    print("=" * 60)
    print(f"目标: {BASE_URL}")
    print(f"时间: {datetime.now().isoformat()}")

    # 禁用代理（忽略环境变量中的代理设置）
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT, trust_env=False) as client:
        # 按顺序运行测试
        await test_health_endpoints(client)
        await test_task_endpoints(client)
        await test_agent_endpoints(client)
        await test_mcp_endpoints(client)
        await test_memory_endpoints(client)
        await test_asr_endpoints(client)
        await test_tts_endpoints(client)
        await test_screenshot_endpoints(client)
        await test_trigger_endpoints(client)
        await test_cancel_endpoints(client)
        await test_chat_endpoint(client)

    # 输出总结
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    total = results["passed"] + results["failed"] + results["skipped"]
    print(f"  通过: {results['passed']}/{total}")
    print(f"  失败: {results['failed']}/{total}")
    print(f"  跳过: {results['skipped']}/{total}")

    if results["failed"] > 0:
        print("\n失败的测试:")
        for test in results["tests"]:
            if test["status"] == "FAIL":
                print(f"  - {test['name']}: {test['message']}")

    print("=" * 60)

    return results["failed"] == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
