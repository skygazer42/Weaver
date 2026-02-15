# Weaver Frontend UI Optimization Implementation Plan (20 Tasks)

> **For Codex:** Execute task-by-task; verify with `pnpm -C web lint` and `pnpm -C web build` before calling the work complete.

**Goal:** Preserve Weaver's existing "glass + gradient + glow" aesthetic while improving consistency, readability, accessibility, and motion performance across the core chat UI.

**Architecture:** Incremental changes in `web/app/globals.css` plus small, localized component updates (Header, Sidebar, ChatInput, MessageItem, overlays). No library migrations.

**Tech Stack:** Next.js 14, React 18, Tailwind CSS 3.4, Radix UI, next-themes, sonner.

---

### Task 1: Unify Theme Provider (Single Source of Truth)

**Files:**
- Modify: `web/components/theme-provider.tsx`
- Verify: `web/components/ui/sonner.tsx` usage remains aligned

**Steps:**
1. Wrap and re-export `next-themes` `ThemeProvider`/`useTheme`.
2. Ensure `attribute="class"` so `.dark` styles apply.

---

### Task 2: Ensure Theme Persistence Works Everywhere

**Files:**
- Modify: `web/app/layout.tsx`
- Modify: `web/components/chat/Header.tsx`

**Steps:**
1. Ensure `storageKey="weaver-theme"` is respected by the actual provider.
2. Toggle theme via `next-themes` hook.

---

### Task 3: Add Safe-Area Utility Classes

**Files:**
- Modify: `web/app/globals.css`

**Steps:**
1. Add `.safe-pb` (and minimal related utilities) using `env(safe-area-inset-*)`.

---

### Task 4: Apply Safe-Area to Bottom Input and Fixed UI

**Files:**
- Modify: `web/components/chat/ChatInput.tsx`
- Modify: `web/components/chat/ChatOverlays.tsx` (if needed)

**Steps:**
1. Use `.safe-pb` and remove conflicting padding utilities where required.

---

### Task 5: Replace `h-screen`/`min-h-screen` With `*-dvh`

**Files:**
- Modify: `web/app/layout.tsx`
- Modify: `web/app/error.tsx`
- Modify: `web/app/not-found.tsx`
- Modify: `web/components/chat/ChatSkeleton.tsx`

---

### Task 6: Fix Global `focus-visible` Styling

**Files:**
- Modify: `web/app/globals.css`

**Steps:**
1. Replace invalid ring styling with Tailwind ring utilities (ring color must actually apply).

---

### Task 7: Remove Arbitrary Z-Index in Skip Link

**Files:**
- Modify: `web/app/globals.css`

---

### Task 8: Make Glass Effects Cheaper + Add Fallback

**Files:**
- Modify: `web/app/globals.css`

**Steps:**
1. Reduce default blur.
2. Add `@supports (backdrop-filter: blur(1px))` to avoid expensive unsupported paths.

---

### Task 9: Make Glow Utilities Valid With CSS Variables

**Files:**
- Modify: `web/app/globals.css`
- Modify: `web/tailwind.config.ts`

**Steps:**
1. Replace `hsla(var(--... ), a)` with `hsl(var(--...) / a)` so shadows work reliably.

---

### Task 10: Change Pulse Glow Animation to Compositor Props

**Files:**
- Modify: `web/app/globals.css`

**Steps:**
1. Update `@keyframes pulseGlow` to animate `opacity/transform`, not `box-shadow`.

---

### Task 11: Unify Gradient Button Variant With App Tokens

**Files:**
- Modify: `web/components/ui/button.tsx`

---

### Task 12: Add/Use `text-pretty` and Apply to Key Body Copy

**Files:**
- Modify: `web/app/globals.css`
- Modify: `web/components/chat/EmptyState.tsx`

---

### Task 13: Replace Custom Model Dropdown With Radix Select

**Files:**
- Modify: `web/components/chat/Header.tsx`

**Steps:**
1. Use `web/components/ui/select.tsx` for keyboard and SR support.

---

### Task 14: Reduce `transition-all` in Core Chat Surfaces

**Files:**
- Modify: `web/components/chat/Header.tsx`
- Modify: `web/components/chat/Sidebar.tsx`
- Modify: `web/components/chat/ChatInput.tsx`
- Modify: `web/components/chat/MessageItem.tsx`
- Modify: `web/components/chat/ChatOverlays.tsx`

---

### Task 15: Convert Thinking Stepper Progress to `scaleX` (No Width Animation)

**Files:**
- Modify: `web/components/chat/message/ThinkingProcess.tsx`

---

### Task 16: Tokenize Sidebar Active State (Avoid Hard-Coded Blues)

**Files:**
- Modify: `web/app/globals.css`

---

### Task 17: Optimize EmptyState Glow/Blur (No Blur Transition)

**Files:**
- Modify: `web/components/chat/EmptyState.tsx`

---

### Task 18: Unify Overlay Blur Strengths (Artifacts + Modals)

**Files:**
- Modify: `web/components/chat/ArtifactsPanel.tsx`
- Modify: `web/components/ui/dialog.tsx`

---

### Task 19: Improve Cross-Browser Scrollbars (Firefox + Utility Consistency)

**Files:**
- Modify: `web/app/globals.css`

---

### Task 20: Verify and Fix Lint/Build Regressions

**Steps:**
1. Run: `pnpm -C web lint`
2. Run: `pnpm -C web build`
3. Fix any warnings/errors introduced by the refactor.

