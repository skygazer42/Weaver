# 图表可视化工具
- 新工具：`chart_visualize`（tools/code/chart_viz_tool.py），在 python 工具开关开启时自动加入。
- 支持 line / bar，返回 base64 PNG；经事件包装器输出 start/result/error，前端可展示。
- 依赖 matplotlib；若未安装会按正常依赖报错。
