"""
Deep Search 路由诊断脚本

测试 deep search 模式是否正确路由到 deepsearch_node。

Usage:
    python scripts/deep_search_routing_check.py
"""

import requests
import json
import sys
from datetime import datetime

BASE_URL = "http://localhost:8000"


def run_deep_search_routing_check():
    """测试 deep search 路由"""
    print("=" * 80)
    print("Deep Search 路由诊断测试")
    print("=" * 80)
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"服务器: {BASE_URL}")
    print()

    # 检查服务器是否运行
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        print(f"✅ 服务器运行中 (状态: {response.status_code})")
    except:
        print("❌ 服务器未运行！")
        print("请先启动服务器: python main.py")
        return False

    print("\n" + "-" * 80)
    print("测试 1: 字符串格式 search_mode='deep'")
    print("-" * 80)

    payload1 = {
        "messages": [{"role": "user", "content": "研究人工智能的发展历史和未来趋势"}],
        "stream": False,
        "search_mode": "deep"
    }

    print(f"请求负载: {json.dumps(payload1, ensure_ascii=False, indent=2)}")
    print("\n发送请求...")

    try:
        response = requests.post(
            f"{BASE_URL}/api/chat",
            json=payload1,
            timeout=120
        )

        print(f"响应状态码: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            content = data.get("content", "")
            print(f"✅ 响应成功")
            print(f"响应长度: {len(content)} 字符")
            print(f"内容预览: {content[:200]}...")
        else:
            print(f"⚠️ 响应状态码: {response.status_code}")
            print(f"响应: {response.text[:500]}")

    except requests.exceptions.Timeout:
        print("⚠️ 请求超时（可能正在执行 deep search，这是正常的）")
    except Exception as e:
        print(f"❌ 请求失败: {e}")

    print("\n" + "-" * 80)
    print("测试 2: 对象格式 search_mode={...}")
    print("-" * 80)

    payload2 = {
        "messages": [{"role": "user", "content": "比较不同编程语言的优缺点"}],
        "stream": False,
        "search_mode": {
            "useWebSearch": False,
            "useAgent": True,
            "useDeepSearch": True
        }
    }

    print(f"请求负载: {json.dumps(payload2, ensure_ascii=False, indent=2)}")
    print("\n发送请求...")

    try:
        response = requests.post(
            f"{BASE_URL}/api/chat",
            json=payload2,
            timeout=120
        )

        print(f"响应状态码: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            content = data.get("content", "")
            print(f"✅ 响应成功")
            print(f"响应长度: {len(content)} 字符")
            print(f"内容预览: {content[:200]}...")
        else:
            print(f"⚠️ 响应状态码: {response.status_code}")
            print(f"响应: {response.text[:500]}")

    except requests.exceptions.Timeout:
        print("⚠️ 请求超时（可能正在执行 deep search，这是正常的）")
    except Exception as e:
        print(f"❌ 请求失败: {e}")

    print("\n" + "=" * 80)
    print("诊断说明")
    print("=" * 80)
    print("""
请检查服务器日志中的以下关键信息：

1. 请求接收日志（main.py）:
   Chat request received
     Raw search_mode: deep  # 或 {"useWebSearch": false, ...}
     Normalized mode_info: {'use_web': False, 'use_agent': True, ...}
     Final mode: deep  # ✅ 关键：应该是 'deep'

2. 路由决策日志（nodes.py）:
   [route_node] Routing decision: deep (confidence: 1.0)
   [route_node] search_mode from config: {...}
   [route_node] override_mode: deep
   [route_node] Returning result with route='deep'

3. smart_route 日志（smart_router.py）:
   [smart_route] using override mode: deep

4. 图路由日志（graph.py）:
   [route_decision] state['route'] = 'deep'
   [route_decision] → Routing to 'deepsearch' node  # ✅ 关键

5. deepsearch 执行日志（nodes.py/deepsearch.py）:
   Executing deepsearch node
   [deepsearch] topic='...' epochs=3
   [deepsearch] 开始优化版深度搜索
   [deepsearch] ===== Epoch 1/3 =====
   ...

如果没有看到第4步和第5步的日志，说明路由没有正确到达 deepsearch。

常见问题排查：
- 如果 mode 不是 'deep'，检查 _normalize_search_mode 函数
- 如果 route_decision 没有执行，检查 state 的 route 字段
- 如果路由到了其他节点，检查条件边配置
""")

    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)

    return True


if __name__ == "__main__":
    try:
        success = run_deep_search_routing_check()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
