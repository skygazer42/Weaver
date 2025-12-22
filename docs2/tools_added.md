# 新增/接入的工具

- HITL: `ask_human`
- 文本编辑: `str_replace`
- 安全 Bash: `safe_bash`（黑名单 rm/shutdown 等，默认超时 20s，可配置 cwd）
- 已接入 Agent 工具选择（agent_profile 可通过 `ask_human`/`str_replace`/`bash` 开关）。
- 事件：上述工具均经 EventedTool 包装，前端可见 start/result/error。

- 规划: plan_steps (reasoning_model)
- 抓取: crawl4ai (可选，未安装时返回提示)
- 可视化: chart_visualize (matplotlib)
