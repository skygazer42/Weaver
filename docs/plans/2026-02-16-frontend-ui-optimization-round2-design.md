# Frontend UI Optimization (Round 2) — Design

**Date:** 2026-02-16

## Context

We already have a distinctive UI direction: glass surfaces, blue/purple gradients, subtle glow, and light motion polish. This round continues that direction with an emphasis on production UI quality: consistency, accessibility, and motion/performance hygiene.

**Priority order (user):** Chat main UI > global components/styles > secondary pages.

## Goals

- Improve Chat experience polish (Message actions, Code blocks, overlays, sidebar/header consistency).
- Reduce visual noise and class sprawl by consolidating repeated patterns into safer defaults (buttons, inputs, cards, globals).
- Tighten motion/performance: avoid `transition-all`, avoid layout/paint-heavy animations, keep interaction feedback <= 200ms.
- Fix small a11y gaps in the interaction surfaces (icon-only buttons, hover-only controls on mobile, focus visibility).
- Keep the existing "glass + gradient + subtle glow" aesthetic (no redesign).

## Non-Goals

- No major information architecture changes (no new views/features).
- No introducing a new component library or re-platforming primitives.
- No large theme overhaul (keep existing tokens and `next-themes` integration).

## Constraints

- Next.js + Tailwind + Radix primitives as currently used.
- TypeScript strictness (including `noUnused*` and `noUncheckedIndexedAccess`).
- Must pass: `pnpm -C web lint`, `pnpm -C web exec tsc --noEmit`, `pnpm -C web build`.

## Design Approach

**Incremental polish (recommended):**

- Chat-first refinements where users spend most time:
  - Make hover-only controls reachable via keyboard and visible on mobile.
  - Normalize spacing, shadows, borders, and transitions.
  - Fix any accidental UI bugs found while polishing (e.g., duplicated state toggles).
- Global component tightening:
  - Replace `transition-all` with targeted transition utilities.
  - Use consistent icon-button sizing (`size-*`) and focus rings.
  - Ensure animation utilities respect reduced-motion and don't leave `will-change` behind.
- Secondary pages:
  - Align a few high-visibility screens/dialogs with the same visual language.

## Motion & Performance Rules (Round 2)

- Interactions: <= 200ms (hover/press/focus).
- Animate compositor props only (`transform`, `opacity`).
- Avoid `backdrop-filter` on large, frequently animated surfaces.
- Remove `transition-all` from common primitives and replace with `transition-colors`, `transition-shadow`, `transition-transform` as appropriate.
- Add `prefers-reduced-motion` fallbacks for decorative entrance/looping animations.

## Accessibility Baselines (Round 2)

- All icon-only buttons must have `aria-label` (and `title` where it helps).
- Hover-only affordances must also appear on keyboard focus (`focus-within`) and on mobile (`max-md:` adjustments).
- Maintain visible focus (`:focus-visible`) and ensure contrast is reasonable in both themes.

## Risks & Mitigations

- **Risk:** Style tweaks change perceived hierarchy or spacing.
  - **Mitigation:** Keep changes small, prefer tokenized values, and limit scope to one surface at a time.
- **Risk:** Motion tweaks introduce regressions.
  - **Mitigation:** Restrict to safe properties and verify with `lint/tsc/build`.

## Acceptance Criteria

- Chat main surface feels consistent across Sidebar/Header/Messages/Input/Overlays.
- Hover-only actions are usable on mobile and via keyboard.
- Reduced `transition-all` usage in Chat + primitives.
- `lint`, `tsc`, and `build` pass.

