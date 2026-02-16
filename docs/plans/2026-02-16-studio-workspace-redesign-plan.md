# Studio Workspace Redesign (Rail + Panel + Inspector) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the Loom Studio workspace layout: `Rail (56) + Panel (320, collapsible) + Canvas + Inspector (420, docked)` with improved hierarchy across Sidebar/Header/Canvas/Artifacts.

**Architecture:** Refactor `web/components/chat/Sidebar.tsx` into a desktop `Rail+Panel` composition while preserving the existing mobile drawer. Update `Header.tsx` to become a cleaner toolbar that surfaces view + session context, and rework `ArtifactsPanel.tsx` into a docked inspector layout (list + preview).

**Tech Stack:** Next.js 16, React, Tailwind, existing shadcn/Radix primitives, `cn` utility, `react-virtuoso`.

---

### Task 1: Add Workspace Layout Constants (Single Source of Truth)

**Files:**
- Modify: `web/components/chat/Chat.tsx`
- Modify: `web/components/chat/Sidebar.tsx`

**Step 1: Add constants**

Add constants like:
- `RAIL_W = 56`
- `PANEL_W = 320`
- `INSPECTOR_W = 420`
- `INSPECTOR_COLLAPSED_W = 56`

**Step 2: Commit**

Run:
```bash
git add web/components/chat/Chat.tsx web/components/chat/Sidebar.tsx
git commit -m "refactor(web): add workspace layout constants"
```

### Task 2: Split Sidebar Into Desktop Rail + Panel (No Behavioral Change Yet)

**Files:**
- Modify: `web/components/chat/Sidebar.tsx`

**Step 1: Extract components**

Inside `Sidebar.tsx`, extract:
- `WorkspaceRail` (desktop only)
- `WorkspacePanel` (desktop + mobile content reuse)

Keep existing history logic (pinned/grouping/virt list) intact.

**Step 2: Desktop wrapper**

Render a `md:flex` wrapper that contains:
- Rail (always visible)
- Panel (collapsible based on `isOpen`)

Keep the current mobile overlay/drawer path (`md:hidden`) as-is for now.

**Step 3: Commit**
```bash
git add web/components/chat/Sidebar.tsx
git commit -m "refactor(web): sidebar rail+panel scaffolding"
```

### Task 3: Implement Rail Nav (Icon-Only, A11y Correct)

**Files:**
- Modify: `web/components/chat/Sidebar.tsx`
- Modify: `web/components/ui/tooltip.tsx` (only if needed)

**Step 1: Rail nav buttons**

Add icon-only buttons for:
- Dashboard
- Discover
- Library

Requirements:
- `aria-label` on each
- `aria-current="page"` when active
- Tooltip on hover/focus with the label (Radix tooltip)

**Step 2: Commit**
```bash
git add web/components/chat/Sidebar.tsx
git commit -m "feat(web): rail navigation with tooltips"
```

### Task 4: Move Desktop Theme + Settings To Rail Bottom

**Files:**
- Modify: `web/components/chat/Sidebar.tsx`
- Modify: `web/components/chat/Header.tsx`

**Step 1: Add rail bottom actions**

On `md+`:
- Add Theme toggle
- Add Settings button calling `onOpenSettings`

**Step 2: Header mobile-only actions**

In `Header.tsx`:
- Keep Theme + Settings visible on mobile (`md:hidden`)
- Hide Theme + Settings on desktop (`hidden md:flex` in rail)

**Step 3: Commit**
```bash
git add web/components/chat/Sidebar.tsx web/components/chat/Header.tsx
git commit -m "refactor(web): move desktop theme/settings to rail"
```

### Task 5: Make Panel Collapsible On Desktop (Width Collapse, No Layout Animation)

**Files:**
- Modify: `web/components/chat/Sidebar.tsx`

**Step 1: Collapse behavior**

When `isOpen === false` (desktop):
- Panel becomes `w-0` + `overflow-hidden`
- Rail remains visible

Avoid adding new motion/animations beyond `transition-colors`.

**Step 2: Commit**
```bash
git add web/components/chat/Sidebar.tsx
git commit -m "feat(web): collapsible sidebar panel on desktop"
```

### Task 6: Add History Search Field (Local Filter)

**Files:**
- Modify: `web/components/chat/Sidebar.tsx`
- Modify: `web/components/ui/input.tsx` (only if needed)

**Step 1: Add search state**

Add `query` state and filter `history` by `title` (case-insensitive).

Behavior:
- Empty query: keep current pinned + grouped view
- Non-empty: show a single “Results” group (plus pinned if desired)

**Step 2: Commit**
```bash
git add web/components/chat/Sidebar.tsx
git commit -m "feat(web): sidebar history search"
```

### Task 7: Pass View + Session Context Into Header

**Files:**
- Modify: `web/components/chat/Chat.tsx`
- Modify: `web/components/chat/Header.tsx`

**Step 1: Compute header labels**

In `Chat.tsx`, derive:
- `viewTitle` (from `ui.currentView`)
- `sessionTitle` (from `currentSessionId` + `history`, only for dashboard)

**Step 2: Extend Header props**

Add props like:
- `currentView`
- `viewTitle`
- `sessionTitle?`

**Step 3: Commit**
```bash
git add web/components/chat/Chat.tsx web/components/chat/Header.tsx
git commit -m "feat(web): header shows view/session context"
```

### Task 8: Restyle Header As A Studio Toolbar

**Files:**
- Modify: `web/components/chat/Header.tsx`

**Step 1: Toolbar visual**

Adjust:
- height (`h-14` preferred)
- left title block (balanced typography)
- reduce border noise (keep subtle `border-b`)

Keep Model selector and (mobile) artifacts toggle.

**Step 2: Commit**
```bash
git add web/components/chat/Header.tsx
git commit -m "style(web): studio toolbar header"
```

### Task 9: Studio Canvas Background + Consistent Page Padding

**Files:**
- Modify: `web/components/chat/Chat.tsx`

**Step 1: Canvas surface**

Introduce a subtle canvas background on the main column (e.g. `bg-muted/10`) while keeping sidebars as `bg-card`.

Ensure no gradients/glows.

**Step 2: Commit**
```bash
git add web/components/chat/Chat.tsx
git commit -m "style(web): studio canvas background"
```

### Task 10: Tighten Message Column Width For Reading

**Files:**
- Modify: `web/components/chat/ChatMessages.tsx`
- Modify: `web/components/chat/MessageItem.tsx` (only if required)

**Step 1: Adjust wrapper width**

Change message container from `max-w-5xl` to a more reading-friendly width (e.g. `max-w-3xl` or `max-w-[820px]`), and normalize padding.

**Step 2: Commit**
```bash
git add web/components/chat/ChatMessages.tsx web/components/chat/MessageItem.tsx
git commit -m "style(web): studio message column width"
```

### Task 11: Align EmptyState With Studio Canvas (Hierarchy + Width)

**Files:**
- Modify: `web/components/chat/EmptyState.tsx`

**Step 1: Adjust layout**

Make EmptyState feel less “landing page”, more “workbench”:
- Keep 4 starters
- Improve hierarchy (title/subtitle/actions)
- Align max-width to canvas width

**Step 2: Commit**
```bash
git add web/components/chat/EmptyState.tsx
git commit -m "style(web): studio empty state"
```

### Task 12: Update Desktop Inspector Wrapper Sizing + Remove Entrance Animation

**Files:**
- Modify: `web/components/chat/Chat.tsx`

**Step 1: Sizing**

Update inspector widths:
- open: `w-[420px]`
- collapsed: `w-[56px]`

Remove `animate-in slide-in-from-right` from the wrapper (baseline-ui: no new animations).

**Step 2: Commit**
```bash
git add web/components/chat/Chat.tsx
git commit -m "style(web): docked inspector sizing (no entrance animation)"
```

### Task 13: Refactor ArtifactsPanel Into Inspector Layout (List + Preview)

**Files:**
- Modify: `web/components/chat/ArtifactsPanel.tsx`

**Step 1: Replace horizontal tabs**

When `artifacts.length > 1`, replace the horizontal tab strip with:
- A vertical selectable list (icon + title + type)
- A preview area for the active artifact

Keep fullscreen mode available.

**Step 2: Commit**
```bash
git add web/components/chat/ArtifactsPanel.tsx
git commit -m "feat(web): artifacts docked inspector (list + preview)"
```

### Task 14: Make Inspector Content Surfaces Consistent (No Extra Dark Blocks)

**Files:**
- Modify: `web/components/chat/ArtifactsPanel.tsx`

**Step 1: Remove forced dark card backgrounds**

Avoid forcing `bg-zinc-950` for non-report artifacts; rely on `CodeBlock` for code darkness and keep card surfaces consistent.

**Step 2: Commit**
```bash
git add web/components/chat/ArtifactsPanel.tsx
git commit -m "style(web): inspector surface consistency"
```

### Task 15: Ensure Mobile Drawer Still Works (Regression Check)

**Files:**
- Modify: `web/components/chat/Sidebar.tsx`

**Step 1: Verify mobile path**

Keep `md:hidden` overlay + drawer behavior working after rail/panel refactor.

**Step 2: Commit (if changes)**
```bash
git add web/components/chat/Sidebar.tsx
git commit -m "fix(web): preserve mobile sidebar drawer after rail refactor"
```

### Task 16: Accessibility Pass For New Icon Buttons

**Files:**
- Modify: `web/components/chat/Sidebar.tsx`
- Modify: `web/components/chat/Header.tsx`
- Modify: `web/components/chat/ArtifactsPanel.tsx`

**Step 1: Audit**

Ensure:
- all icon-only buttons have `aria-label`
- navigation sets `aria-current`
- tooltips don’t break keyboard navigation

**Step 2: Commit**
```bash
git add web/components/chat/Sidebar.tsx web/components/chat/Header.tsx web/components/chat/ArtifactsPanel.tsx
git commit -m "fix(a11y): rail/panel/inspector controls"
```

### Task 17: Run Lint

Run:
```bash
pnpm -C web lint
```

Expected: exit code 0.

### Task 18: Run TypeScript Check

Run:
```bash
pnpm -C web exec tsc --noEmit
```

Expected: exit code 0.

### Task 19: Run Production Build

Run:
```bash
pnpm -C web build
```

Expected: success (Next warnings acceptable, but build must complete).

### Task 20: Final Manual QA + Push

**Manual QA (dev):**
- Desktop `md+`: rail visible, panel collapses, header shows view/session, canvas width feels right
- Desktop `xl+`: inspector docked, collapses to `56px`
- Mobile: sidebar drawer works, artifacts overlay works

**Push:**
```bash
git push origin main
```

