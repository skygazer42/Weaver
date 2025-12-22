# Stuck 检测（草案）
- 新增 `agent/workflows/stuck_middleware.py`：
  - `detect_stuck(messages, threshold=2)`: 检测最后一条 AIMessage 是否重复超过阈值。
  - `inject_stuck_hint(messages)`: 在消息末尾追加提示，鼓励换策略/用其他工具。
- 接入点（待做）：在 evaluator 或 agent_node 后处理阶段调用 detect_stuck，若 True 则注入 hint 或触发 AskHuman/重新规划。
