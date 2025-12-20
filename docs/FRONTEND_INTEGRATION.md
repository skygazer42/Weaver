# Agent 可视化前端集成指南

本文档说明如何在前端消费 Weaver Agent 的实时事件，实现类似 ChatGPT 的浏览器操作可视化效果。

## 概述

Weaver 现在支持实时流式推送 Agent 执行过程中的事件，包括：

- **tool_start**: 工具开始执行
- **screenshot**: 浏览器截图
- **tool_result**: 工具执行完成
- **task_update**: 任务进度更新

## SSE 事件格式

所有事件遵循 Vercel AI SDK 格式：

```json
0:{"type":"tool_start","data":{"tool":"sb_browser_navigate","action":"navigate","args":{"url":"https://example.com"}}}

0:{"type":"screenshot","data":{"url":"/api/screenshots/thread_123_navigate_20241220_143022.png","action":"navigate","page_url":"https://example.com"}}

0:{"type":"tool_result","data":{"tool":"sb_browser_navigate","success":true,"duration_ms":1234.56}}
```

## 前端集成示例

### 方式 1: 使用 EventSource (原生)

```javascript
// 创建 SSE 连接
const threadId = 'thread_' + Date.now();
const eventSource = new EventSource(`/api/events/${threadId}`);

// 状态管理
const state = {
  screenshots: [],
  toolExecutions: [],
  currentTool: null,
};

// 处理消息
eventSource.onmessage = (event) => {
  // 解析 Vercel AI SDK 格式: "0:{json}"
  const line = event.data;
  if (!line.startsWith('0:')) return;

  const payload = JSON.parse(line.slice(2));
  const { type, data } = payload;

  switch (type) {
    case 'tool_start':
      handleToolStart(data);
      break;
    case 'screenshot':
      handleScreenshot(data);
      break;
    case 'tool_result':
      handleToolResult(data);
      break;
    case 'task_update':
      handleTaskUpdate(data);
      break;
  }
};

// 工具开始
function handleToolStart(data) {
  state.currentTool = data;

  // 显示正在执行的工具
  const indicator = document.getElementById('tool-indicator');
  indicator.innerHTML = `
    <div class="tool-running">
      <span class="spinner"></span>
      正在执行: ${data.tool}
      ${data.args?.url ? `<br>URL: ${data.args.url}` : ''}
    </div>
  `;
  indicator.classList.add('active');
}

// 处理截图
function handleScreenshot(data) {
  state.screenshots.push(data);

  // 显示截图
  const container = document.getElementById('screenshots');
  const img = document.createElement('img');
  img.src = data.url;
  img.alt = data.action;
  img.className = 'browser-screenshot';
  img.onclick = () => openFullscreen(data.url);

  // 添加标签
  const wrapper = document.createElement('div');
  wrapper.className = 'screenshot-wrapper';
  wrapper.innerHTML = `
    <div class="screenshot-label">${data.action}</div>
  `;
  wrapper.appendChild(img);
  container.appendChild(wrapper);

  // 滚动到最新截图
  wrapper.scrollIntoView({ behavior: 'smooth' });
}

// 工具完成
function handleToolResult(data) {
  state.toolExecutions.push(data);
  state.currentTool = null;

  // 更新指示器
  const indicator = document.getElementById('tool-indicator');
  indicator.classList.remove('active');

  // 显示执行结果
  const resultDiv = document.createElement('div');
  resultDiv.className = `tool-result ${data.success ? 'success' : 'error'}`;
  resultDiv.innerHTML = `
    <span class="tool-name">${data.tool}</span>
    <span class="tool-duration">${data.duration_ms.toFixed(0)}ms</span>
    <span class="tool-status">${data.success ? '✓' : '✗'}</span>
  `;
  document.getElementById('execution-log').appendChild(resultDiv);
}

// 任务更新
function handleTaskUpdate(data) {
  const taskList = document.getElementById('task-list');
  let taskEl = document.getElementById(`task-${data.id}`);

  if (!taskEl) {
    taskEl = document.createElement('div');
    taskEl.id = `task-${data.id}`;
    taskEl.className = 'task-item';
    taskList.appendChild(taskEl);
  }

  taskEl.className = `task-item task-${data.status}`;
  taskEl.innerHTML = `
    <span class="task-status-icon">${getStatusIcon(data.status)}</span>
    <span class="task-title">${data.title || data.id}</span>
    ${data.progress !== undefined ? `<span class="task-progress">${data.progress}%</span>` : ''}
  `;
}

function getStatusIcon(status) {
  switch (status) {
    case 'pending': return '○';
    case 'running': return '◐';
    case 'completed': return '●';
    case 'failed': return '✗';
    default: return '○';
  }
}

// 错误处理
eventSource.onerror = (error) => {
  console.error('SSE Error:', error);
  eventSource.close();
};
```

### 方式 2: 使用 React + Hooks

```typescript
// useAgentEvents.ts
import { useState, useEffect, useCallback } from 'react';

interface ToolStartEvent {
  tool: string;
  action: string;
  args: Record<string, any>;
}

interface ScreenshotEvent {
  url: string;
  filename: string;
  action: string;
  page_url: string;
}

interface ToolResultEvent {
  tool: string;
  success: boolean;
  duration_ms: number;
}

interface AgentState {
  screenshots: ScreenshotEvent[];
  currentTool: ToolStartEvent | null;
  toolResults: ToolResultEvent[];
  isConnected: boolean;
}

export function useAgentEvents(threadId: string) {
  const [state, setState] = useState<AgentState>({
    screenshots: [],
    currentTool: null,
    toolResults: [],
    isConnected: false,
  });

  useEffect(() => {
    if (!threadId) return;

    const eventSource = new EventSource(`/api/events/${threadId}`);

    eventSource.onopen = () => {
      setState(s => ({ ...s, isConnected: true }));
    };

    eventSource.onmessage = (event) => {
      const line = event.data;
      if (!line.startsWith('0:')) return;

      try {
        const payload = JSON.parse(line.slice(2));
        const { type, data } = payload;

        switch (type) {
          case 'tool_start':
            setState(s => ({ ...s, currentTool: data }));
            break;
          case 'screenshot':
            setState(s => ({
              ...s,
              screenshots: [...s.screenshots, data],
            }));
            break;
          case 'tool_result':
            setState(s => ({
              ...s,
              currentTool: null,
              toolResults: [...s.toolResults, data],
            }));
            break;
        }
      } catch (e) {
        console.error('Parse error:', e);
      }
    };

    eventSource.onerror = () => {
      setState(s => ({ ...s, isConnected: false }));
    };

    return () => {
      eventSource.close();
    };
  }, [threadId]);

  return state;
}
```

```tsx
// AgentVisualization.tsx
import React from 'react';
import { useAgentEvents } from './useAgentEvents';

interface Props {
  threadId: string;
}

export function AgentVisualization({ threadId }: Props) {
  const { screenshots, currentTool, toolResults, isConnected } = useAgentEvents(threadId);

  return (
    <div className="agent-visualization">
      {/* 连接状态 */}
      <div className={`connection-status ${isConnected ? 'connected' : 'disconnected'}`}>
        {isConnected ? '● 已连接' : '○ 未连接'}
      </div>

      {/* 当前工具执行状态 */}
      {currentTool && (
        <div className="current-tool">
          <div className="spinner" />
          <span>正在执行: {currentTool.tool}</span>
          {currentTool.args?.url && (
            <span className="tool-url">{currentTool.args.url}</span>
          )}
        </div>
      )}

      {/* 截图列表 */}
      <div className="screenshots-container">
        {screenshots.map((screenshot, index) => (
          <div key={index} className="screenshot-item">
            <img
              src={screenshot.url}
              alt={screenshot.action}
              className="screenshot-image"
            />
            <div className="screenshot-info">
              <span className="action">{screenshot.action}</span>
              <span className="url">{screenshot.page_url}</span>
            </div>
          </div>
        ))}
      </div>

      {/* 执行日志 */}
      <div className="execution-log">
        {toolResults.map((result, index) => (
          <div
            key={index}
            className={`log-item ${result.success ? 'success' : 'error'}`}
          >
            <span className="tool-name">{result.tool}</span>
            <span className="duration">{result.duration_ms.toFixed(0)}ms</span>
            <span className="status">{result.success ? '✓' : '✗'}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

### 方式 3: 使用 Vue 3 Composition API

```typescript
// useAgentEvents.ts
import { ref, onMounted, onUnmounted } from 'vue';

interface ScreenshotEvent {
  url: string;
  action: string;
  page_url: string;
}

export function useAgentEvents(threadId: string) {
  const screenshots = ref<ScreenshotEvent[]>([]);
  const currentTool = ref<any>(null);
  const isConnected = ref(false);

  let eventSource: EventSource | null = null;

  onMounted(() => {
    eventSource = new EventSource(`/api/events/${threadId}`);

    eventSource.onopen = () => {
      isConnected.value = true;
    };

    eventSource.onmessage = (event) => {
      const line = event.data;
      if (!line.startsWith('0:')) return;

      try {
        const payload = JSON.parse(line.slice(2));
        const { type, data } = payload;

        switch (type) {
          case 'tool_start':
            currentTool.value = data;
            break;
          case 'screenshot':
            screenshots.value.push(data);
            break;
          case 'tool_result':
            currentTool.value = null;
            break;
        }
      } catch (e) {
        console.error('Parse error:', e);
      }
    };

    eventSource.onerror = () => {
      isConnected.value = false;
    };
  });

  onUnmounted(() => {
    eventSource?.close();
  });

  return {
    screenshots,
    currentTool,
    isConnected,
  };
}
```

## CSS 样式示例

```css
/* Agent 可视化样式 */
.agent-visualization {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px;
  background: #1a1a1a;
  border-radius: 8px;
}

.connection-status {
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 4px;
}

.connection-status.connected {
  color: #4caf50;
  background: rgba(76, 175, 80, 0.1);
}

.connection-status.disconnected {
  color: #f44336;
  background: rgba(244, 67, 54, 0.1);
}

.current-tool {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: rgba(33, 150, 243, 0.1);
  border: 1px solid rgba(33, 150, 243, 0.3);
  border-radius: 8px;
  color: #2196f3;
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid transparent;
  border-top-color: currentColor;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.screenshots-container {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}

.screenshot-item {
  border-radius: 8px;
  overflow: hidden;
  background: #2a2a2a;
  transition: transform 0.2s;
}

.screenshot-item:hover {
  transform: scale(1.02);
}

.screenshot-image {
  width: 100%;
  height: auto;
  display: block;
  cursor: pointer;
}

.screenshot-info {
  padding: 8px 12px;
  font-size: 12px;
}

.screenshot-info .action {
  font-weight: 600;
  color: #fff;
  text-transform: capitalize;
}

.screenshot-info .url {
  display: block;
  color: #888;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.execution-log {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 200px;
  overflow-y: auto;
}

.log-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 4px;
  font-size: 12px;
}

.log-item.success {
  background: rgba(76, 175, 80, 0.1);
  color: #4caf50;
}

.log-item.error {
  background: rgba(244, 67, 54, 0.1);
  color: #f44336;
}

.log-item .tool-name {
  flex: 1;
  font-family: monospace;
}

.log-item .duration {
  color: #888;
}
```

## API 端点

### 主聊天端点 (集成事件)

```
POST /api/chat
Content-Type: application/json

{
  "messages": [{"role": "user", "content": "去百度搜索 AI"}],
  "stream": true,
  "agent_profile": {
    "enabled_tools": {
      "sandbox_browser": true
    }
  }
}
```

响应头包含 `X-Thread-ID`，可用于订阅事件。

### 事件订阅端点

```
GET /api/events/{thread_id}
Accept: text/event-stream
```

### 截图端点

```
GET /api/screenshots/{filename}
GET /api/screenshots?thread_id=xxx&limit=50
POST /api/screenshots/cleanup
```

## 完整示例

### HTML 页面

```html
<!DOCTYPE html>
<html lang="zh">
<head>
  <meta charset="UTF-8">
  <title>Weaver Agent 可视化</title>
  <style>
    /* 上面的 CSS 样式 */
  </style>
</head>
<body>
  <div class="agent-visualization">
    <div id="connection-status" class="connection-status disconnected">
      ○ 未连接
    </div>

    <div id="current-tool" class="current-tool" style="display: none;">
      <div class="spinner"></div>
      <span id="tool-name"></span>
    </div>

    <div id="screenshots" class="screenshots-container"></div>

    <div id="execution-log" class="execution-log"></div>
  </div>

  <script>
    // 上面的 JavaScript 代码
  </script>
</body>
</html>
```

## 注意事项

1. **跨域问题**: 确保后端配置了正确的 CORS 设置
2. **连接超时**: EventSource 默认 300 秒超时，需要处理重连
3. **截图大小**: 截图文件可能较大，考虑使用懒加载
4. **内存管理**: 及时清理不需要的截图引用

## 下一步

- 实现截图全屏查看
- 添加操作回放功能
- 支持截图下载
- 实现任务进度条

---

**版本**: v1.0.0
**更新日期**: 2025-12-20
**作者**: Weaver Team
