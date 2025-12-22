# 沙盒模式切换（更新）
- 配置：`sandbox_mode` = local | daytona | none
  - local：沿用现有 E2B sandbox_* 工具（browser/files/shell/sheets/presentation/web_dev/vision/image_edit 等）。
  - daytona：跳过本地 sandbox_*，改用 `daytona_create` / `daytona_stop`（返回 VNC/HTTP 链接）。
  - none：不注册 sandbox_* 工具。
- daytona 工具：`daytona_create`/`daytona_stop`（事件化，需配置 daytona_api_key 等）。
- 线程隔离：依旧通过 thread_id 传递（工具包装负责）。
- Teardown：shutdown 时会调用 close_mcp_tools；Daytona stop 可由流程调用 daytona_stop 或后续在 shutdown 扩展。
- 待办：将 daytona session 生命周期与 thread 绑定（当前基于显式工具调用），以及在 shutdown 自动 stop 活动沙盒。
