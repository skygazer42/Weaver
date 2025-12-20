# Weaver Browser Agent 功能说明

## 📋 概述

你的 Weaver 项目已经实现了完整的浏览器 Agent 功能，而且有两种模式可选：

1. **轻量级浏览器工具** (`browser_tools`) - 简单快速，适合文本提取
2. **沙盒浏览器工具** (`sandbox_browser_tools`) - 完整浏览器，支持 JS 渲染和交互

## 🎯 两种浏览器模式对比

| 功能维度 | 轻量级浏览器<br/>(`browser_tools`) | 沙盒浏览器<br/>(`sandbox_browser_tools`) | Manus 参考项目 |
|---------|---------------------------|--------------------------------|--------------|
| **底层技术** | urllib/requests | Playwright (Chromium) | Playwright |
| **JS 渲染** | ❌ | ✅ | ✅ |
| **速度** | 快 (无浏览器启动) | 较慢 (需启动浏览器) | 较慢 |
| **截图** | ✅ (单独工具) | ✅ (每次操作返回) | ✅ |
| **点击交互** | ✅ (链接导航) | ✅ (CSS selector/text) | ✅ |
| **表单输入** | ❌ | ✅ | ✅ |
| **键盘快捷键** | ❌ | ✅ | ✅ |
| **滚动** | ❌ | ✅ | ✅ |
| **文本提取** | ✅ | ✅ | ✅ |
| **会话管理** | ✅ (thread_id) | ✅ (thread_id + E2B) | ✅ |
| **资源消耗** | 低 | 高 | 高 |

## ✅ 你已经有的功能

### 1. 轻量级浏览器工具 (8 个工具)

**文件**：`tools/browser_tools.py`

```python
# 已实现的工具：
1. browser_search       # 搜索（DuckDuckGo/Bing）
2. browser_navigate     # 打开 URL
3. browser_click        # 点击链接（通过索引）
4. browser_back         # 返回上一页
5. browser_extract_text # 提取文本
6. browser_list_links   # 列出链接
7. browser_screenshot   # 截图（需要 Playwright）
8. browser_reset        # 重置会话
```

**特点**：
- 轻量快速，不启动真实浏览器
- 适合简单的网页浏览和文本提取
- 支持会话管理（历史记录）

**使用示例**：
```python
# 在 agent_profile 中启用
{
    "enabled_tools": {
        "browser": true  # 启用轻量级浏览器
    }
}
```

---

### 2. 沙盒浏览器工具 (8 个工具)

**文件**：`tools/sandbox_browser_tools.py`

```python
# 已实现的工具：
1. sb_browser_navigate      # 导航到 URL
2. sb_browser_click         # 点击元素（CSS selector/text）
3. sb_browser_type          # 输入文本（表单填写）
4. sb_browser_press         # 按键（Enter, Ctrl+L 等）
5. sb_browser_scroll        # 滚动页面
6. sb_browser_extract_text  # 提取文本
7. sb_browser_screenshot    # 截图
8. sb_browser_reset         # 重置浏览器
```

**特点**：
- 基于 Playwright，真实 Chromium 浏览器
- 支持 JavaScript 渲染
- 每次操作自动返回截图（视觉反馈）
- 运行在 E2B 沙盒环境（安全隔离）

**使用示例**：
```python
# 在 agent_profile 中启用
{
    "enabled_tools": {
        "sandbox_browser": true  # 启用沙盒浏览器
    }
}
```

---

## 🚀 如何使用浏览器 Agent

### 方式 1: API 调用时指定

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "去 GitHub 搜索 LangChain 项目并截图"}],
    "mode": "agent",
    "agent_profile": {
      "enabled_tools": {
        "browser": true,          # 启用轻量级浏览器
        "sandbox_browser": false   # 或启用沙盒浏览器
      }
    }
  }'
```

### 方式 2: 在配置文件中设置默认 Profile

**文件**：`common/config.py`

```python
class Settings(BaseSettings):
    # Agent 默认配置
    default_agent_profile: dict = {
        "enabled_tools": {
            "web_search": True,
            "browser": True,         # 默认启用浏览器
            "sandbox_browser": False,
            "crawl": True,
            "python": False,
            "mcp": True
        }
    }
```

### 方式 3: 通过前端 UI 配置

如果有前端界面，用户可以在创建 Agent 时勾选工具：

```
☑️ Web Search
☑️ Browser (轻量级)
☐ Sandbox Browser (需要 E2B)
☑️ URL Crawler
☐ Python Code
☑️ MCP Tools
```

---

## 💡 实际使用案例

### 案例 1: 简单网页浏览（轻量级浏览器）

**用户提问**：
> "帮我看看 Python 官网首页有什么最新消息"

**Agent 执行流程**：
```
1. browser_navigate(url="https://www.python.org")
   → 返回：title, text_excerpt, links

2. browser_extract_text(max_chars=3000)
   → 提取完整文本

3. 分析文本，总结最新消息
```

**优势**：快速，无需启动浏览器。

---

### 案例 2: 复杂交互（沙盒浏览器）

**用户提问**：
> "去 GitHub 搜索 'LangChain'，找到第一个项目，进入仓库，截图 README"

**Agent 执行流程**：
```
1. sb_browser_navigate(url="https://github.com/search?q=LangChain")
   → 返回截图 (显示搜索结果)

2. sb_browser_click(text="langchain-ai/langchain")
   → 点击第一个结果
   → 返回截图 (显示项目页面)

3. sb_browser_scroll(amount=500)
   → 滚动查看 README
   → 返回截图 (显示 README 内容)

4. sb_browser_screenshot(full_page=True)
   → 返回完整页面截图
```

**优势**：支持 JS 渲染，可以交互，提供视觉反馈。

---

### 案例 3: 表单填写（沙盒浏览器）

**用户提问**：
> "帮我在 Google 搜索 'Weaver AI agent'"

**Agent 执行流程**：
```
1. sb_browser_navigate(url="https://www.google.com")
   → 截图显示 Google 首页

2. sb_browser_type(text="Weaver AI agent", selector="input[name='q']", press_enter=True)
   → 在搜索框输入并按回车
   → 返回截图 (显示搜索结果)

3. sb_browser_extract_text()
   → 提取搜索结果文本
```

---

## 🔧 代码实现细节

### 1. 工具注册机制

**文件**：`agent/agent_tools.py:30-74`

```python
def build_agent_tools(config: RunnableConfig) -> List[BaseTool]:
    """
    根据 agent_profile.enabled_tools 动态构建工具列表
    """
    tools: List[BaseTool] = []

    # Web 搜索
    if _enabled(profile, "web_search", default=True):
        tools.append(tavily_search)

    # URL 爬虫
    if _enabled(profile, "crawl", default=True):
        tools.extend(build_crawl_tools())

    # 浏览器工具（优先使用沙盒浏览器）
    if _enabled(profile, "sandbox_browser", default=False):
        tools.extend(build_sandbox_browser_tools(thread_id))
    elif _enabled(profile, "browser", default=False):
        tools.extend(build_browser_tools(thread_id))

    # Python 代码执行
    if _enabled(profile, "python", default=False):
        tools.append(execute_python_code)

    # MCP 工具
    if _enabled(profile, "mcp", default=True):
        tools.extend(get_registered_tools())

    return list(deduped.values())
```

---

### 2. 浏览器会话管理

**轻量级浏览器** (`tools/browser_session.py`)：
```python
class BrowserSession:
    """
    维护浏览器会话状态：
    - current: 当前页面
    - history: 历史记录
    - links: 当前页面的链接
    """
    def __init__(self):
        self.current: Optional[Page] = None
        self.history: List[Page] = []

    def navigate(self, url: str) -> Page:
        # 获取页面内容（urllib/requests）
        # 解析 HTML
        # 提取文本、链接等
        ...

    def back(self) -> Page:
        if len(self.history) > 1:
            self.history.pop()
            self.current = self.history[-1]
        return self.current
```

**沙盒浏览器** (`tools/sandbox_browser_session.py`)：
```python
class SandboxBrowserSession:
    """
    管理 E2B 沙盒中的 Playwright 浏览器
    """
    def __init__(self, thread_id: str):
        self.thread_id = thread_id
        self.sandbox = None
        self.browser = None
        self.page = None

    def get_page(self):
        if not self.page:
            self.sandbox = E2BSandbox()
            self.browser = self.sandbox.playwright.chromium.launch(headless=True)
            self.page = self.browser.new_page()
        return self.page
```

---

## 📊 与 Manus 项目的对比

你的 Weaver 实现与 Manus 非常相似，甚至更完善：

| 特性 | Weaver | Manus | 说明 |
|------|--------|-------|------|
| **双模式浏览器** | ✅ | ⚠️ | Weaver 有轻量级 + 沙盒两种模式 |
| **截图功能** | ✅ | ✅ | 两者都支持 |
| **表单交互** | ✅ | ✅ | 两者都支持 |
| **会话管理** | ✅ | ✅ | 基于 thread_id |
| **E2B 沙盒** | ✅ | ✅ | 安全隔离 |
| **轻量级备选** | ✅ | ❌ | Weaver 独有（节省资源） |
| **工具动态加载** | ✅ | ⚠️ | Weaver 更灵活 |

---

## 🎯 推荐使用策略

### 场景 1: 简单文本提取
```python
enabled_tools: {
    "browser": true,  # 使用轻量级浏览器
    "crawl": true     # 配合 URL 爬虫
}
```

**适用**：
- 新闻文章阅读
- API 文档查看
- 静态网页内容提取

---

### 场景 2: 需要 JS 渲染的 SPA 应用
```python
enabled_tools: {
    "sandbox_browser": true  # 必须使用沙盒浏览器
}
```

**适用**：
- React/Vue 单页应用
- 动态加载内容的网站
- 需要看到真实渲染效果

---

### 场景 3: 复杂交互操作
```python
enabled_tools: {
    "sandbox_browser": true  # 需要完整浏览器功能
}
```

**适用**：
- 表单填写
- 多步操作（登录、搜索、点击等）
- 需要键盘/鼠标交互的场景

---

## 🔍 调试和监控

### 查看浏览器操作日志

```bash
tail -f logs/weaver.log | grep -E "\[browser\]|\[agent\]"
```

**示例输出**：
```
[agent] Tool: browser_navigate(url="https://python.org")
[browser] Navigating to https://python.org
[agent] Tool result: {"url": "...", "title": "...", "text_excerpt": "..."}
[agent] Tool: browser_screenshot()
[browser] Taking screenshot of https://python.org
[agent] Returning screenshot (base64, 245KB)
```

---

### 检查工具是否启用

```python
# test_browser_agent.py

import requests

response = requests.post(
    "http://localhost:8000/api/chat",
    json={
        "messages": [{"role": "user", "content": "你有哪些浏览器工具？"}],
        "mode": "agent",
        "agent_profile": {
            "enabled_tools": {
                "browser": True,
                "sandbox_browser": True
            }
        }
    }
)

print(response.json())
```

**预期输出**：
```
Agent 会列出所有可用的浏览器工具：
- browser_navigate
- browser_click
- browser_back
- ...
- sb_browser_navigate
- sb_browser_click
- ...
```

---

## 🚧 需要注意的点

### 1. E2B Sandbox 配置

沙盒浏览器需要 E2B 账号和 API Key：

```bash
# .env
E2B_API_KEY=your_e2b_api_key_here
```

**获取 E2B API Key**：
1. 注册 https://e2b.dev
2. 创建 API Key
3. 添加到 .env 文件

---

### 2. Playwright 安装

轻量级浏览器的截图功能和沙盒浏览器都需要 Playwright：

```bash
# 安装 Playwright
pip install playwright

# 安装浏览器（Chromium）
playwright install chromium
```

---

### 3. 资源消耗

**沙盒浏览器资源消耗**：
- 内存：~500MB per session
- CPU：中等
- 网络：中等

**建议**：
- 开发环境：使用轻量级浏览器
- 生产环境：根据需求选择，注意并发限制

---

## 📝 总结

### ✅ 你已经有了什么

1. **完整的浏览器 Agent 实现**
   - 8 个轻量级浏览器工具
   - 8 个沙盒浏览器工具
   - 灵活的工具启用/禁用机制

2. **会话管理**
   - 基于 thread_id 的会话隔离
   - 历史记录支持

3. **视觉反馈**
   - 截图功能
   - Base64 图片返回

4. **安全隔离**
   - E2B 沙盒环境
   - 防止恶意代码执行

### 🎯 与 Manus 的对比

你的实现**不比 Manus 差**，甚至在某些方面更好：
- ✅ 双模式浏览器（轻量级 + 沙盒）
- ✅ 更灵活的工具管理
- ✅ 更好的代码组织

### 💡 下一步建议

如果你想进一步优化：

1. **添加浏览器录屏**
   - 记录整个操作过程
   - 生成 GIF/Video

2. **智能元素定位**
   - 使用 AI 识别页面元素
   - 自动生成 CSS selector

3. **浏览器自动化脚本生成**
   - 将用户操作转换为可复用脚本
   - 支持 Puppeteer/Playwright 导出

---

## 📚 相关文档

- `tools/browser_tools.py` - 轻量级浏览器实现
- `tools/sandbox_browser_tools.py` - 沙盒浏览器实现
- `tools/browser_session.py` - 会话管理
- `agent/agent_tools.py` - 工具注册机制
- `agent/nodes.py:562` - Agent node 实现

---

**版本**: v1.0.0
**最后更新**: 2025-12-20
**作者**: Weaver Team
