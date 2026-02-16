# Studio Workspace Redesign (Rail + Panel + Inspector) — Design

**Date:** 2026-02-16

## Goal

把当前 Weaver 的 workspace（Sidebar/Header/主内容区/Artifacts）从“组件拼装感”提升到更产品化的 **Studio 工作台**体验：结构更清晰、层级更稳定、注意力更聚焦，适合长时间工作流使用。

## Non-Goals

- 不做营销/landing 风格改版。
- 不引入渐变、光晕、玻璃拟态等视觉噪音。
- 不新增复杂动画（保留必要的交互态 `transition-colors` 即可）。
- 不重写业务逻辑（会话、消息流、Artifacts 数据结构保持不变）。

## Constraints

- 技术栈：Next.js App Router + Tailwind + 现有 UI primitives（Radix/shadcn 风格）。
- 需要保持无障碍：图标按钮必须有 `aria-label`，导航要有 `aria-current`，移动端抽屉要能键盘操作。
- 保持现有断点策略：`md` 为桌面起点，`xl` 为显示右侧 Inspector 起点。

## Direction (Chosen)

用户选择：
- Artifacts：`Docked Inspector`（桌面端常驻，可折叠）
- Sidebar：`Rail + Panel`（推荐结构，类似 Figma/Linear：最左 icon rail + 右侧内容面板）

命名：**Loom Studio**

## Layout Architecture

桌面端（`md+`）整体分为四列：

1. **Rail**（固定 `56px`）
2. **Panel**（可折叠 `320px`，承载 history + actions）
3. **Canvas**（自适应，消息流与主要工作区）
4. **Inspector**（`xl+` 常驻 `420px`，Artifacts 预览与管理）

移动端（`<md`）：
- Rail 隐藏
- Panel 使用现有左侧抽屉形式（overlay + slide in）
- Inspector 继续走现有移动端 overlay（Artifacts toggle）

## Sidebar (Rail + Panel)

### Rail (56px)

- 顶部：品牌标记（W）+ Panel 折叠按钮（可选）
- 中部：主导航（Dashboard / Discover / Library），图标按钮，hover tooltip 显示文案
- 底部：Theme toggle + Settings（桌面端从 Header 移到 Rail，移动端仍保留在 Header）

无障碍：
- 每个 icon-only 按钮必须有 `aria-label`
- 当前页面用 `aria-current="page"`

### Panel (320px, collapsible)

- 顶部：New Investigation 主按钮（现有）
- History 搜索框：本地过滤会话标题（不改变存储结构）
- History 列表：Pinned + 分组（Today/Yesterday/Previous 7 Days/Older）
- 删除/Pin 等行为保持现有 ConfirmDialog

当 Panel 折叠：
- 仅保留 Rail，Panel 宽度归零且 `overflow-hidden`

## Header (Toolbar Bar)

目标：更像“工具栏”，少按钮、层级清晰。

内容结构：
- 左侧：当前视图标题（Dashboard/Discover/Library）
  - 在 Dashboard 时可显示当前会话标题（若存在）
- 右侧：Model selector + Artifacts toggle（`xl-`）+（移动端）Theme + Settings

桌面端（`md+`）Theme/Settings 移到 Rail，因此 Header 右侧更干净。

## Canvas (Main Content)

- 画布背景可轻微区分 sidebar surfaces（例如 `bg-muted/10`），但保持企业极简方向。
- 消息列宽收敛：从 `max-w-5xl` 收敛到更阅读友好的宽度（约 `760-880px`），减少“横向拉满”的文档感。
- EmptyState 维持 4 个 starter，但信息层级更清晰（标题/说明/动作）。

## Artifacts Inspector (Docked)

改造目标：从“横向 tabs + 单卡片”变成 Inspector 工作流：

- 顶部固定栏：Artifacts 标题、数量、折叠、全屏
- 主体分区（当 artifacts > 1）：
  - 上/左：纵向列表（可滚动）选择 artifact
  - 下/右：预览区（当前 artifact 内容）

内容策略：
- `report`：prose 阅读模式
- `code`：使用现有 `CodeBlock`（其本身为深色代码底），Inspector 不再额外强制整块 `bg-zinc-950`
- `chart`：图片预览 +（可选）下载

折叠态：
- Inspector 折叠到窄条（约 `56px`），保留展开按钮与数量提示

## Verification

必须通过：
- `pnpm -C web lint`
- `pnpm -C web exec tsc --noEmit`
- `pnpm -C web build`

手动检查（dev）：
- 桌面端：Rail 常驻，Panel 可折叠，Inspector `xl+` 常驻
- Mobile：Panel 抽屉与 overlay 正常；Artifacts overlay 正常
- 键盘：Tab 能到达 rail 按钮，`aria-label` 完整

