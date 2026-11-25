# Weaver Web 设计规范

更新：2026-11-24。范围：研究聊天、项目工作台、设置及其共享组件。（Agent 推断）

## 方向

- 延续现有企业工作台升级，以完成研究和处理项目资料为主要任务。（用户确认）
- 聊天页采用侧栏、顶部工具栏、消息区和底部输入区；工作台采用项目列表与项目详情。（Agent 推断）
- 同一对象的名称、状态和主要操作放在同一阅读区域，避免靠装饰区块连接信息。（Agent 推断）
- 页面层级依次是当前位置、当前任务、任务内容、辅助说明；不用营销页的大标题组织工作台。（Agent 推断）

## 品牌资产

- 保留 Weaver 名称；`web/public/logo.png` 更新为交织几何带状标志，表达并行研究、工具与证据汇聚成结构化洞察；不使用线框星形。（用户确认）
- 品牌图通过用户指定的 api.site 服务与 gpt-image-2.6-sunburst 生成，保留正方形比例；`web/public/favicon.ico` 使用同一标志。（用户确认）
- 标志直接置于页面表面，在明暗主题中保持可辨认，不再叠加浅色承托框、描边或阴影。（Agent 推断）
- 浏览器标题与图标沿用 `web/app/layout.tsx` 中的产品身份。（Agent 推断）
- 主操作和选中状态沿用现有主色角色；具体取值由主题变量管理。（Agent 推断）
- 字体使用 Inter、Noto Sans SC 与中文系统回退栈；代码使用 JetBrains Mono。具体顺序由 `web/tailwind.config.ts` 管理。（用户确认）

## 语义角色

变量定义在 `web/app/globals.css`，Tailwind 映射在 `web/tailwind.config.ts`；本文不复制色值。（Agent 推断）

- `--background`：页面底面，不承担输入框、菜单或结果卡片的区分。（Agent 推断）
- `--surface-subtle`：侧栏、工具区和次级分区，和正文内容保持可辨认的层级。（Agent 推断）
- `--card` 与 `--card-foreground`：任务内容、表单容器和结果面板。（Agent 推断）
- `--popover` 与 `--popover-foreground`：下拉与菜单；浮层不直接继承页面底色。（Agent 推断）
- `--foreground`：正文、对象名称与关键结果；主要信息不使用弱化文本角色。（Agent 推断）
- `--muted-foreground`：说明、时间、次级标签与辅助图标，不用于唯一的状态反馈。（Agent 推断）
- `--primary` 与 `--primary-foreground`：主要提交、当前选择及用户消息的强调。（Agent 推断）
- `--accent` 与 `--accent-foreground`：悬停及轻量交互反馈，不代替已选状态。（Agent 推断）
- `--border`：区域边界与分隔线；`--input`：输入控件边界。（Agent 推断）
- `--ring`：键盘焦点；焦点可见性不依赖悬停。（Agent 推断）
- `--success`、`--success-surface`、`--success-border`：成功与完成反馈，必须同时显示文字。（Agent 推断）
- `--warning`、`--warning-surface`、`--warning-border`：需关注或待确认状态，不能只用颜色提示。（Agent 推断）
- `--destructive`、`--destructive-surface`、`--destructive-border`：错误和删除；普通取消不使用破坏性色。（Agent 推断）
- `--info`、`--info-surface`、`--info-border`：运行中的信息反馈，和成功、失败分开。（Agent 推断）
- 字体角色由 `web/app/layout.tsx` 注入：`font-sans` 用于导航、标题与正文，`font-mono` 用于代码、JSON 和技术标识。（Agent 推断）
- 标题用字号与字重建立层级，正文不整体加粗；时长、数量与表格数字使用等宽数字。（Agent 推断）
- `--radius`：共享控件形状的依据；输入和按钮用相近圆角，内容容器不改成胶囊形。（Agent 推断）
- 阴影使用现有 surface、elevated 层级；内容靠边框和底面区分，浮层才使用更高阴影。（Agent 推断）
- 动效使用已有短时过渡；减少动态效果时遵循全局 reduced-motion 规则。（Agent 推断）
- 暗色主题保留相同的语义关系，不通过反转图片或固定浅色文本模拟主题。（Agent 推断）

## 可用组件

- 基础交互复用 `web/components/ui/button.tsx`，主提交使用默认变体，次要动作用 outline 或 ghost。（Agent 推断）
- 状态标签复用 `web/components/ui/badge.tsx`；标签表达状态，不能伪装成未实现的按钮。（Agent 推断）
- 内容容器复用 `web/components/ui/card.tsx`，不为每行元数据额外包一张卡片。（Agent 推断）
- 对话框复用 `web/components/ui/dialog.tsx`，标题与底部操作固定，长内容在中间滚动。（Agent 推断）
- 删除确认复用 `web/components/ui/confirm-dialog.tsx`；轻量文本编辑复用 `web/components/ui/edit-dialog.tsx`。（Agent 推断）
- 文本、长文本和标签分别复用 `web/components/ui/input.tsx`、`web/components/ui/textarea.tsx`、`web/components/ui/label.tsx`。（Agent 推断）
- 菜单复用 `web/components/ui/popover.tsx`，开关复用 `web/components/ui/switch.tsx`，保留现有键盘行为。（Agent 推断）
- 提示反馈通过 `web/components/ui/sonner.tsx`；保存失败时保留对话框与草稿。（Agent 推断）
- 图标沿用 lucide-react；图标按钮提供可访问名称，装饰图标不重复朗读标签。（Agent 推断）
- 模型选择沿用 Header 和 Settings 的现有列表，数据以公开配置接口返回的允许列表为准。（用户确认）
- 长模型标识在紧凑控件中单行截断，并保留完整名称提示；选中标记不能挤出容器。（Agent 推断）
- 新组件先复用现有主题角色和基础组件，不引入新的组件库或依赖。（用户确认）

## 样板页面

- `web/components/chat/Chat.tsx`：聊天外壳、消息列表与输入区的布局依据。（Agent 推断）
- `web/components/chat/Header.tsx`：当前位置、模型选择和主题/设置操作的排列依据。（Agent 推断）
- `web/components/chat/Sidebar.tsx`：导航、最近会话分组、选中态与收起行为的依据。（Agent 推断）
- `web/components/chat/MessageItem.tsx`：用户消息、研究结果、引用和消息操作的依据。（Agent 推断）
- `web/components/chat/message/ThinkingProcess.tsx`：流式过程、完成摘要和可展开细节的依据。（Agent 推断）
- `web/components/settings/SettingsDialog.tsx`：语言、模型和 MCP 表单分区的依据。（Agent 推断）
- `web/components/settings/McpConfigDialog.tsx`：独立 MCP 编辑和保存反馈的依据。（Agent 推断）
- `web/app/workspace/page.tsx`：项目导航、创建入口与详情工作区的依据。（Agent 推断）
- `web/app/workspace/workspace-panel.tsx`：文件选择、分析提交、历史记录和结果面板的依据。（Agent 推断）
- 样板负责相应区域的取值与交互；新增页面不照抄与自身任务无关的分区。（Agent 推断）

## 用户取舍

- 2026-11-24：品牌标志用指定服务重新生成，呈现 Weaver 的研究编织与多工具协作身份，明暗主题均移除重复承托框。（用户确认）
- 2026-11-24：中文使用 Noto Sans SC 字体栈；起始卡片的模式标签贴近提示文本，图标、文本和箭头对齐，短标题不拉开标签间距。（用户确认）
- 2026-11-24：空状态与输入区同时验证 1440×900、1440×800 和 390×844，底部 AI 说明完整可见。（用户确认）
- 2026-11-24：继续企业 UI 升级，修正剩余问题时保留现有产品行为和水合正确性。（用户确认）
- 2026-11-24：同时验证明暗主题；桌面验收视口为 1440×900，移动聊天为 390×844。（用户确认）
- 2026-11-24：真实后端提供的长模型名称必须能选择，不能造成横向溢出或下拉裁切。（用户确认）
- 2026-11-24：设置、聊天与项目生命周期必须连接真实 FastAPI 数据验证。（用户确认）
- 2026-11-24：设计文档记录可核对的角色和规则，不维护另一份原始色值表。（用户确认）
- 列表密度、边框与阴影的具体使用以上述样板现状为依据，等待独立视觉复核。（Agent 推断）

## 不要做

- 不用装饰性线框星形或网络节点图代替 Weaver 的交织品牌标志。（用户确认）
- 不为单个页面硬编码另一套明暗主题色板。（Agent 推断）
- 不把整个研究工作台改成居中的营销落地页。（Agent 推断）
- 不用大面积渐变、发光或持续动画替代信息层级。（Agent 推断）
- 不隐藏唯一的任务状态、保存结果或错误说明。（Agent 推断）
- 不让长名称撑宽工作台、遮挡选中标记或挤掉主要操作。（用户确认）
- 不让对话框内容把底部取消、保存操作推出视口。（Agent 推断）
- 不只在悬停时暴露触屏或键盘用户必需的操作。（Agent 推断）
- 不把加载失败当成永久的空配置；恢复后允许重新获取真实配置。（用户确认）
- 不把无效 MCP JSON 当作保存成功，也不在保存失败后丢弃用户输入。（Agent 推断）
- 不通过弱化 React Compiler 或 Hooks 规则交付界面改动。（用户确认）
