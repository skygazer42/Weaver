# Debug: Message Alignment Issue

## 问题描述
在 Deep Research 模式输出后，继续提问时，助手的回答容器异常右对齐（类似用户消息）。

## 已添加调试日志

### 1. 前端组件调试
已在以下文件添加 console.log:

**web/components/chat/MessageItem.tsx** (行 50-57):
- 每次渲染消息时输出: id, role, isUser, content预览
- 检查 `message.role` 是否为正确的 'assistant'
- 检查 `isUser` 计算是否正确

**web/hooks/useChatStream.ts** (行 78-82, 103-107):
- 创建 assistant 消息时输出: id, role, messages数量
- 更新消息内容时输出: id, role, content长度
- 验证 role 始终为 'assistant'

## 测试步骤

### 1. 启动开发服务器
```bash
cd F:\pythonproject\Weaver\web
npm run dev
```

### 2. 打开浏览器控制台
- Chrome/Edge: F12 → Console 标签
- 确保 Console 不被过滤器隐藏日志

### 3. 复现问题
1. 选择 "Deep Research" 模式
2. 提问任意问题（例如："研究 AI 的发展历史"）
3. 等待 Deep Research 完成
4. **关键**: 继续提问第二个问题
5. 观察第二个回答的对齐情况

### 4. 检查控制台输出
查找以下日志模式：

#### 正常情况（期望）:
```
[useChatStream] Creating assistant message: { id: "assistant-1234567890", role: "assistant", ... }
[MessageItem] { id: "assistant-1234567890", role: "assistant", isUser: false, ... }
```

#### 异常情况（如果 role 被错误设置）:
```
[useChatStream] Creating assistant message: { id: "assistant-1234567890", role: "user", ... }  // ❌ WRONG!
[MessageItem] { id: "assistant-1234567890", role: "user", isUser: true, ... }  // ❌ WRONG!
```

## 收集信息

当问题出现时，请记录：

### A. 控制台日志
复制所有 `[useChatStream]` 和 `[MessageItem]` 的日志输出

### B. 问题消息的详细信息
特别关注：
- `role` 字段的值（应该是 'assistant' 但可能是 'user'）
- `isUser` 的值（应该是 false 但可能是 true）
- `id` 字段（检查是否有重复或异常）

### C. 截图
- 对齐异常的页面截图
- 控制台日志截图

### D. 操作序列
记录：
1. 选择的搜索模式
2. 第一个问题内容
3. 第二个问题内容
4. Deep Research 是否完全完成

## 可能的根本原因

### 假设 1: Role 字段被错误设置
**症状**: 控制台显示 `role: "user"` 而不是 `role: "assistant"`
**原因**: useChatStream 中的消息创建逻辑有误
**位置**: web/hooks/useChatStream.ts:71-76

### 假设 2: React 状态更新顺序问题
**症状**: 消息创建时 role 正确，但渲染时 role 错误
**原因**: setMessages 调用的时序或批处理问题
**位置**: web/hooks/useChatStream.ts:84, 108-112

### 假设 3: LocalStorage 数据损坏
**症状**: 刷新页面后加载的历史消息有错误 role
**原因**: 保存/加载时 JSON 序列化问题
**位置**: web/lib/storage-service.ts

### 假设 4: 消息 ID 冲突
**症状**: 相同 ID 的消息被 React 错误复用
**原因**: Date.now() 在极快操作时可能重复
**位置**: web/components/chat/Chat.tsx:154, web/hooks/useChatStream.ts:72

### 假设 5: Deep Research 特殊处理
**症状**: 只在 Deep Research 之后出现
**原因**: Deep Research 的 completion 事件处理有特殊逻辑
**位置**: web/hooks/useChatStream.ts:141-147

## 下一步调试

根据控制台日志结果：

### 如果 role 始终正确但仍右对齐
→ 检查 CSS 样式冲突
→ 检查 Tailwind 配置
→ 检查浏览器缓存

### 如果 role 在某个时刻变成 'user'
→ 定位具体哪个 setMessages 调用导致
→ 检查该调用点的数据来源
→ 修复数据创建逻辑

### 如果控制台没有日志输出
→ 确认是开发模式 (npm run dev)
→ 确认浏览器没有缓存旧代码 (硬刷新 Ctrl+Shift+R)
→ 确认 NODE_ENV === 'development'

## 临时解决方案

如果需要快速修复，可以尝试：

### 方案 1: 强制 role 检查
在 MessageItem.tsx 添加防御性代码：
```typescript
const isUser = message.role === 'user' && message.id.startsWith('user-')
```

### 方案 2: 清除 LocalStorage
```javascript
// 浏览器控制台执行
localStorage.clear()
location.reload()
```

### 方案 3: 使用唯一 ID
修改 ID 生成，避免冲突：
```typescript
// 在 Chat.tsx 和 useChatStream.ts
id: `user-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
id: `assistant-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
```

---

**创建时间**: 2025-12-21
**状态**: 等待测试结果
