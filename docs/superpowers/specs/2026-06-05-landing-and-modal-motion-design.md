# EchoStream — Landing + auth-modal motion (design)

**Date:** 2026-06-05
**Status:** Approved (visual direction validated via live previews)
**Implementation skill:** frontend-design (per user request, in place of writing-plans)

## Goal

Make the logged-out landing page feel alive instead of blank, animate the auth modal, and fix the inconsistent "EchoStream" wordmark — all in the existing forensic / "signal-interception" aesthetic (restrained motion, single lime accent). No new dependencies; pure CSS keyframes + the existing React mount.

## Non-goals

- No change to app logic, auth flow, or the logged-in app.
- No animation library (Framer Motion etc.) — CSS only.
- No restyle of the dashboards; this is motion + the landing hero layout only.

## 1. Wordmark consistency

[LandingPage.jsx](../../../frontend/src/components/LandingPage.jsx) renders a plain `EchoStream` in its nav, while the masthead ([Navbar.jsx](../../../frontend/src/components/Navbar.jsx)) and [AuthModal.jsx](../../../frontend/src/components/AuthModal.jsx) render `Echo<em>Stream</em>` (acid-italic "Stream"). Fix: change the landing nav to `<span className="wordmark">Echo<em>Stream</em></span>` so all three match. (The masthead's `Forensic / v0.1` stamp stays masthead-only — out of scope for the landing nav.)

## 2. Landing animations (all three, layered)

The hero becomes a **two-column** layout (text left, visual right). Three motion layers combine:

### 2a. Decode & reveal (one-time, on mount) — left column
- Eyebrow line with a blinking terminal cursor.
- Eyebrow → headline → subtext rise/fade in on load (opacity + small translateY), lightly staggered. The headline animates as a single block (not split per line) so it stays robust across viewport widths.
- The four capability tiles stagger-rise in (existing `rise`-style entrance, ~80ms apart).
- Runs once on mount (not looping).

### 2b. Live "case" preview (looping) — right column, new `CasePreview.jsx`
- Self-contained sub-component (single responsibility: the demo visual). Props: none (or an optional `entities` array; default uses the real smoke-clip content for authenticity).
- Contents: a faux video frame (diagonal-stripe fill), a face silhouette under a **pulsing dashed lime blur-reticle**, a **lime scan line sweeping** top→bottom, a blinking **"● REC"**, a `FACE BLURRED` tag, and an **entity ticker** cycling `PER [redacted]` / `ORG Microsoft` / `LOC Bucharest` (matches the actual demo clip).
- All motion is CSS keyframes on static markup (no JS timers).

### 2c. Ambient signal (looping) — behind everything
- A `.landing-ambient` layer: a faint **equalizer** of bars along the bottom edge (staggered scaleY), **drifting vertical scan lines** (translateX), and a **breathing lime glow** (radial-gradient opacity). Low contrast so it reads as atmosphere, never competes with the text.

## 3. Auth-modal animations

Added to [AuthModal.jsx](../../../frontend/src/components/AuthModal.jsx) markup + [index.css](../../../frontend/src/index.css):
- **Entrance:** overlay fades (existing); the `.modal-card` scales `0.95→1` and rises ~14px with a soft settle (`cubic-bezier(.22,1,.36,1)`).
- **Scan line:** a single lime sweep down the card on open.
- **Stagger:** title → subtitle → fields → buttons cascade in (~50ms apart) via `animation-delay` on children.
- **Focus:** input border eases to lime with a soft ring (extends existing `.login-input:focus`).
- **Cursor:** blinking lime caret beside the `Echo<em>Stream</em>` title.
- **Error shake:** when `error` becomes set, the error banner does a quick horizontal shake. Implemented with a CSS `shake` keyframe applied via a class; the only JS is React already re-rendering when `error` changes (apply the class whenever the banner renders — it mounts fresh on error, so the animation plays once).

## 4. Accessibility & performance

- **Motion-safety:** all keyframe animations live under `@media (prefers-reduced-motion: no-preference)`, OR are reset in a `@media (prefers-reduced-motion: reduce)` block. With reduced motion, every element renders in its final static state (full opacity, no transform) — nothing is hidden or broken.
- **Performance:** animate only `transform` and `opacity` (compositor-friendly, no layout/paint thrash). The looping layers (case preview, ambient) use modest durations (1–7s) and small element counts.

## Files

- **Modify** `frontend/src/components/LandingPage.jsx` — wordmark fix, two-column hero, decode/reveal entrance classes, mount the ambient layer + `CasePreview`.
- **Create** `frontend/src/components/CasePreview.jsx` — the looping live-case demo visual.
- **Modify** `frontend/src/components/AuthModal.jsx` — title cursor span, stagger classes on content, error-shake class on the banner.
- **Modify** `frontend/src/index.css` — all new `@keyframes` and the landing/modal motion classes, plus the `prefers-reduced-motion` block.

## Verification (visual)

Headless screenshots + Playwright against the running dev server: landing renders with the case preview + ambient + entrance; wordmark reads `Echo`+*Stream*; modal entrance/stagger/scan play on open; an induced error shows the shake; and with `prefers-reduced-motion: reduce` emulated, everything is present and static.
