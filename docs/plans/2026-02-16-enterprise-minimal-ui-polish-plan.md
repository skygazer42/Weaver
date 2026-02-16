# Enterprise Minimal UI Polish (Round 3) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Re-style the Weaver web UI to an enterprise-minimal direction (no gradients/glow/glass), with consistent tokens, cleaner primitives, and improved readability across Chat + secondary pages.

**Architecture:** Token-first styling in `web/app/globals.css` + Tailwind config cleanup, then update UI primitives (`web/components/ui/*`), then update Chat + secondary views and remaining dialogs.

**Tech Stack:** Next.js 16, React 19, Tailwind CSS 4, Radix UI, class-variance-authority.

**Workflow note:** User requested working directly on `main` (no feature branch). Make small commits and push.

---

### Task 1: Simplify Theme Tokens (Remove Gradient/Glass/Glow Vars)

**Files:**
- Modify: `web/app/globals.css`

**Step 1: Update `:root` tokens**
- Remove `--gradient-*`, `--glass-*`, and `--accent-*` (purple/pink/cyan) variables.
- Keep one accent (blue) by setting `--primary` and `--ring` consistently.

**Step 2: Update `.dark` tokens**
- Ensure `--ring` uses the same accent.

**Step 3: Verify build tools**
Run: `pnpm -C web lint`
Expected: PASS

**Step 4: Commit**
Run:
```bash
git add web/app/globals.css
git commit -m "style(web): simplify theme tokens for enterprise minimal"
```

---

### Task 2: Remove Gradient/Glass/Glow Utilities and Add Minimal Surface Utilities

**Files:**
- Modify: `web/app/globals.css`

**Step 1: Delete utility blocks**
- Remove `.gradient-*`, `.glass*`, `.glow*`, and `dark .gradient-bg` utilities.

**Step 2: Add minimal replacements**
- Add utilities like `.surface`, `.surface-muted`, `.hairline`, `.panel` using existing Tailwind tokens (`bg-background`, `bg-card`, `border-border`).

**Step 3: Update component layer classes**
- Rewrite `.sidebar`, `.sidebar-item.active`, `.message-user`, `.message-assistant`, `.message-thinking` to use the new surface utilities (no gradients).

**Step 4: Commit**
```bash
git add web/app/globals.css
git commit -m "style(web): remove gradient/glass/glow utilities; add minimal surfaces"
```

---

### Task 3: Clean Tailwind Config (Remove Gradient Images + Glow Shadows)

**Files:**
- Modify: `web/tailwind.config.js`

**Step 1: Remove non-minimal tokens**
- Remove `accent.purple/pink/cyan` colors.
- Remove `boxShadow.glow*` entries.
- Remove `backgroundImage.gradient-*` entries.

**Step 2: Tighten motion defaults**
- Reduce custom animation durations to <= 200ms where used for UI feedback.

**Step 3: Verify TypeScript + lint**
Run:
- `pnpm -C web exec tsc --noEmit`
- `pnpm -C web lint`
Expected: PASS

**Step 4: Commit**
```bash
git add web/tailwind.config.js
git commit -m "style(web): simplify tailwind config for enterprise minimal"
```

---

### Task 4: Simplify Button Variants (Remove Gradient/Glass/Glow)

**Files:**
- Modify: `web/components/ui/button.tsx`

**Step 1: Remove unused variants**
- Delete `gradient`, `glass`, `glow`, `gradient-outline`, `accent-purple` variants.

**Step 2: Refine base classes**
- Replace `transition duration-200` with `transition-colors` (and `transition-shadow` if needed).
- Prefer `size-*` for icon sizes where possible.

**Step 3: Fix callsites**
- Replace any `variant="gradient"` usage with `default` (primary) or `secondary`.

**Step 4: Verify**
Run: `pnpm -C web lint`
Expected: PASS

**Step 5: Commit**
```bash
git add web/components/ui/button.tsx web/components/**/*.tsx web/app/**/*.tsx
git commit -m "style(web): simplify button variants for minimal system"
```

---

### Task 5: Dialog Primitive (Remove Backdrop Blur + Tracking)

**Files:**
- Modify: `web/components/ui/dialog.tsx`

**Step 1: Overlay**
- Remove `backdrop-blur-sm`; use a solid overlay like `bg-black/40`.

**Step 2: Content**
- Ensure content uses `bg-card` + `border` + `shadow-lg` without extra effects.

**Step 3: Typography**
- Remove `tracking-tight` per baseline.

**Step 4: Commit**
```bash
git add web/components/ui/dialog.tsx
git commit -m "style(web): dialog overlay/content minimal + no blur"
```

---

### Task 6: Popover + Tooltip Primitives (Align With Minimal Surfaces)

**Files:**
- Modify: `web/components/ui/popover.tsx`
- Modify: `web/components/ui/tooltip.tsx`

**Steps:**
- Ensure panels use `bg-popover`/`bg-card`, `border`, and Tailwind default shadow scale.
- Avoid backdrop blur and glow.

**Verify:** `pnpm -C web lint`

**Commit:**
```bash
git add web/components/ui/popover.tsx web/components/ui/tooltip.tsx
git commit -m "style(web): align popover/tooltip with minimal surfaces"
```

---

### Task 7: Inputs/Textareas (Consistent Borders + Focus)

**Files:**
- Modify: `web/components/ui/input.tsx`
- Modify: `web/components/ui/textarea.tsx`
- Modify: `web/components/ui/search-input.tsx`

**Steps:**
- Use consistent `border-border/60`, `bg-background`, and focus ring via `ring-ring`.
- Remove any scale-on-focus patterns.

**Commit:**
```bash
git add web/components/ui/input.tsx web/components/ui/textarea.tsx web/components/ui/search-input.tsx
git commit -m "style(web): normalize input/textarea styling"
```

---

### Task 8: Badges/Cards/FilterGroup (Remove Tracking, Reduce Visual Noise)

**Files:**
- Modify: `web/components/ui/badge.tsx`
- Modify: `web/components/ui/card.tsx`
- Modify: `web/components/ui/filter-group.tsx`

**Steps:**
- Remove `tracking-*` usage.
- Keep component defaults neutral and predictable.

**Verify:** `pnpm -C web lint`

**Commit:**
```bash
git add web/components/ui/badge.tsx web/components/ui/card.tsx web/components/ui/filter-group.tsx
git commit -m "style(web): refine badge/card/filter styling for enterprise minimal"
```

---

### Task 9: Header (No Blur, Cleaner Controls)

**Files:**
- Modify: `web/components/chat/Header.tsx`

**Steps:**
- Remove `backdrop-blur-md` and translucency.
- Tighten button/icon sizing and spacing.

**Commit:**
```bash
git add web/components/chat/Header.tsx
git commit -m "style(web): header minimal (no blur)"
```

---

### Task 10: Sidebar (Remove Gradients/Glow, Clear Active State)

**Files:**
- Modify: `web/components/chat/Sidebar.tsx`
- Modify: `web/app/globals.css` (if needed for `.sidebar*`)

**Steps:**
- Replace monogram badge + title gradient with a neutral mark.
- Replace `variant="gradient"` new-chat button.
- Remove overlay `backdrop-blur-sm`.
- Remove `tracking-*` usage on group labels.

**Verify:** `pnpm -C web lint`

**Commit:**
```bash
git add web/components/chat/Sidebar.tsx web/app/globals.css
git commit -m "style(web): sidebar enterprise minimal"
```

---

### Task 11: Chat Input Container (Flatter Surface, No Scaling)

**Files:**
- Modify: `web/components/chat/ChatInput.tsx`

**Steps:**
- Replace heavy `shadow-xl`, `scale-*`, and blur overlays with a flat bordered surface.
- Keep drag state clear using border + background only.
- Keep transitions <= 200ms.

**Commit:**
```bash
git add web/components/chat/ChatInput.tsx
git commit -m "style(web): chat input minimal surface + focus"
```

---

### Task 12: Message Surface Styles (User/Assistant/Thinking)

**Files:**
- Modify: `web/app/globals.css`

**Steps:**
- Re-implement `.message-user`, `.message-assistant`, `.message-thinking` without gradients/glass.
- Remove assistant hover glow.

**Commit:**
```bash
git add web/app/globals.css
git commit -m "style(web): message bubble styles enterprise minimal"
```

---

### Task 13: Message Item Component (Spacing + Action Bar Hygiene)

**Files:**
- Modify: `web/components/chat/MessageItem.tsx`

**Steps:**
- Remove `animate-fade-in-up` dependency.
- Ensure action affordances are usable via `group-focus-within` and on mobile.

**Verify:** `pnpm -C web lint`

**Commit:**
```bash
git add web/components/chat/MessageItem.tsx
git commit -m "style(web): message item layout polish"
```

---

### Task 14: Code Blocks (Remove Glassy Blur Header)

**Files:**
- Modify: `web/components/chat/message/CodeBlock.tsx`

**Steps:**
- Remove `backdrop-blur-sm` from header.
- Simplify header visuals (language label + actions only).

**Commit:**
```bash
git add web/components/chat/message/CodeBlock.tsx
git commit -m "style(web): code block header minimal"
```

---

### Task 15: Empty State (No Glow/Gradients)

**Files:**
- Modify: `web/components/chat/EmptyState.tsx`

**Steps:**
- Remove blurred glow halo and gradient heading.
- Remove `tracking-*` usage.
- Keep layout quiet and centered with clear starters.

**Commit:**
```bash
git add web/components/chat/EmptyState.tsx
git commit -m "style(web): empty state enterprise minimal"
```

---

### Task 16: Discover View (Single Accent, Neutral Cards)

**Files:**
- Modify: `web/components/views/Discover.tsx`

**Steps:**
- Remove purple accent usage.
- Ensure cards rely on border + subtle hover (no heavy shadow).

**Verify:** `pnpm -C web lint`

**Commit:**
```bash
git add web/components/views/Discover.tsx
git commit -m "style(web): discover view minimal polish"
```

---

### Task 17: Library View (Refine Layout + Empty State)

**Files:**
- Modify: `web/components/views/Library.tsx`

**Steps:**
- Align typography/spacing with Chat.
- Make empty state and controls consistent with the minimal surface system.

**Commit:**
```bash
git add web/components/views/Library.tsx
git commit -m "style(web): library view enterprise minimal"
```

---

### Task 18: Session/Artifact Items (Fix Pinned Border Bug + Remove Tracking)

**Files:**
- Modify: `web/components/library/SessionItem.tsx`
- Modify: `web/components/library/ArtifactItem.tsx`

**Steps:**
- Replace inline `borderLeftColor: 'var(--primary)'` with `border-l-primary` (valid color).
- Remove `tracking-wider` on artifact type badge.

**Verify:** `pnpm -C web lint`

**Commit:**
```bash
git add web/components/library/SessionItem.tsx web/components/library/ArtifactItem.tsx
git commit -m "fix(web): library items pinned border + minimal typography"
```

---

### Task 19: Collaboration/Export/Version UI (Remove Glass/Gradient)

**Files:**
- Modify: `web/components/collaboration/ShareDialog.tsx`
- Modify: `web/components/export/ExportDialog.tsx`
- Modify: `web/components/collaboration/VersionHistory.tsx`

**Steps:**
- Remove `glass-strong`, `gradient-accent`, `variant="gradient"` usage.
- Use `bg-card`, `border`, and `Button` default/secondary variants.
- Remove overlay backdrop blur.

**Commit:**
```bash
git add web/components/collaboration/ShareDialog.tsx web/components/export/ExportDialog.tsx web/components/collaboration/VersionHistory.tsx
git commit -m "style(web): dialogs minimal (no glass/gradients)"
```

---

### Task 20: Comments Panel + Final Sweep + Full Verification

**Files:**
- Modify: `web/components/collaboration/CommentsPanel.tsx`
- Modify: any remaining files from sweep

**Step 1: Comments panel**
- Remove glass/gradient usage.

**Step 2: Sweep**
Run:
- `rg -n "gradient-|glow|glass|backdrop-blur|shadow-glow|accent-purple" web`
Replace remaining usages with minimal equivalents.

**Step 3: Full verification**
Run:
- `pnpm -C web lint`
- `pnpm -C web exec tsc --noEmit`
- `pnpm -C web build`
Expected: PASS

**Step 4: Commit + Push**
```bash
git add -A
git commit -m "style(web): enterprise minimal sweep + verify"

git push origin main
```
