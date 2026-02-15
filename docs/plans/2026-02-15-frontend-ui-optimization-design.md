# Weaver Frontend UI Optimization Design (2026-02-15)

**Goal:** Improve Weaver's frontend UI quality (consistency, readability, accessibility, and performance) while preserving the existing "glass + blue/purple gradient + subtle glow" aesthetic.

## Context

Weaver's frontend is a `Next.js 14` app (App Router) using `Tailwind CSS` and `Radix UI` primitives.

The current visual language already leans into:
- Glass surfaces (`backdrop-filter`)
- Blue/purple gradients
- Subtle glow accents

However, there are a few foundational inconsistencies that impact polish:
- Theme system is split: custom `ThemeProvider` vs `next-themes` usage in the toast layer
- Safe-area support is referenced (`safe-pb`) but not defined
- A few views still use `h-screen` / `min-h-screen` (better replaced with `*-dvh`)
- Some animations/transitions overuse `transition-all` and/or animate paint/layout-heavy properties
- Z-index usage contains an arbitrary value (`z-[9999]`)

## Chosen Direction (A)

Keep the current aesthetic and refine it:
- Preserve gradients and glass, but reduce unnecessary cost (blur strength, large-surface effects).
- Keep glows as accents, not primary affordances.
- Improve a11y (keyboard, focus visibility) by leaning on Radix primitives where interactions are custom.
- Reduce jank by preferring `transform/opacity` over `width/blur/box-shadow` animation.

## Approach

Hybrid, low-risk iteration:
1. Fix foundation (theme, safe-area, dvh, focus, z-index).
2. Harmonize tokens/utilities (`globals.css`) so components reuse the same visual primitives.
3. Polish the core chat surfaces (Header, Sidebar, MessageItem, ChatInput, overlays).
4. Do targeted motion/perf cleanups (avoid layout/paint-heavy animations).

## Non-Goals

- No major redesign, layout rewrite, or component library migration.
- No sweeping refactors unrelated to UI polish.

## Success Criteria

- Theme toggling and persistence work consistently across the app (including toast theme).
- Safe-area padding works on iOS for fixed/bottom UI.
- No remaining `h-screen` usages in the app UI; use `h-dvh` / `min-h-dvh`.
- Keyboard/focus behavior improved for the model selector (Radix primitive).
- Reduced animation cost: avoid width/blur/box-shadow animations on meaningful surfaces.
- `pnpm -C web lint` and `pnpm -C web build` complete successfully.

