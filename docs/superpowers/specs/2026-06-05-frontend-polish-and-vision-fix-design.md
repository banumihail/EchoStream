# EchoStream — Front-end polish + vision count fix (design)

**Date:** 2026-06-05
**Status:** Approved pending spec review
**Author:** brainstorming session

## Goal

Improve the existing EchoStream product (the bachelor-thesis pipeline) ahead of a demo video, without a layout teardown. Three independent improvements:

1. Replace the bare full-page login with a **landing page + auth modal** entry experience.
2. A **de-AI-ifying pass**: remove glassmorphism/gradient surfaces and the off-brand purple icons, replacing them with the app's existing flat "forensic console" surfaces and a bespoke icon set.
3. Fix the **vision object over-count** (a 2-person clip reporting "person ×4").

The three workstreams are independent and can be built/shipped in any order. The vision fix (3) is backend-only; (1) and (2) are frontend-only and share the new visual vocabulary.

## Non-goals (YAGNI / scope guardrails)

- No restructuring of the dashboards, interactive transcript, upload flow, or worker pipeline. The user confirmed these have character; this is a surface/entry/icon pass only.
- No change to auth/MFA *logic* — the five MFA methods (TOTP, backup, email OTP, FIDO2, push) keep their exact behavior; only their container and styling change.
- No logged-in landing/home state — after login the user goes straight to the existing app nav (Upload / Analysis / History / Security).
- Vision fix does not add object tracking or re-identification; "distinct count" is approximated by peak-per-frame.

---

## Workstream 1 — Entry experience (landing + modal)

### Current state
[App.jsx](../../../frontend/src/App.jsx) renders `<Login>` as a full-page takeover when `authedUser` is null. [Login.jsx](../../../frontend/src/components/Login.jsx) is a single 464-line component handling login, register, and the MFA challenge step, styled with `glass-panel` + `gradient-text`.

### Target state
Logged-out users see a **landing page**; either "Sign in" or "Get started" opens an **auth modal** layered over it. Login is never a standalone route.

### New unit: `LandingPage.jsx`
- **Purpose:** logged-out marketing/entry screen (Option 2 — capability-grid tone).
- **Props:** `onSignIn()`, `onGetStarted()` — open the modal on the login / register tab respectively.
- **Structure:**
  - Top bar: `EchoStream` wordmark (Fraunces) + ghost `Sign in` + lime `Get started`.
  - Hero: serif headline + one-line subtext.
  - Four capability tiles, each `<Icon>` + title + one line: **Word-level transcript**, **Audio redaction**, **Identity-aware blur**, **PII detection**.
  - Footer credibility line: `WHISPER · BERT · DETR · AST · YuNet+SFace`.
- **Depends on:** `Icon.jsx`, existing CSS tokens (`--ink-*`, `--bone*`, `--acid`, `--rule`, `--serif/--sans/--mono`).
- **Style:** flat surfaces, hairline rules, lime as the single accent. No glass, no gradients.

### New unit: `AuthModal.jsx`
- **Purpose:** overlay that hosts the existing login / register / MFA-challenge states.
- **Props:** `initialMode` (`'login' | 'register'`), `onClose()`, `onLoggedIn(username)`.
- **Behavior:** the existing state machine and network logic from `Login.jsx` move here **unchanged** (the `submit`, `submitMfa`, `startPushApproval`, `verifyWithFido2`, `requestEmailOtp` handlers and their state). Only the wrapping JSX/markup and classes are restyled. Modal concerns: Esc to close, backdrop click to close, ✕ button, focus trap, body scroll lock, `autoFocus` first field.
- **Depends on:** `shared/auth` helpers (`saveSession`, `API_URL`), `@simplewebauthn/browser`, `Icon.jsx`.

### `App.jsx` change
- Logged-out: render `<LandingPage>` + conditionally `<AuthModal>` (state: `authModal = null | 'login' | 'register'`).
- Logged-in: unchanged — existing `<Navbar>` + views.
- The existing `echostream:auth-expired` event handling is preserved.

### `Login.jsx`
- Retired. Its logic relocates into `AuthModal.jsx`. (Kept in git history; deleted from the tree once the modal is verified.)

---

## Workstream 2 — De-AI-ifying pass (look & feel)

### 2a. De-glass surfaces
- `glass-panel`, `gradient-text`, and `backdrop-filter` appear only in `Login.jsx` (→ now `AuthModal.jsx`) and [Security.jsx](../../../frontend/src/components/Security.jsx) (17 occurrences across those + their `index.css` definitions).
- Replace with flat editorial surfaces already used by the main app: `--ink-2`/`--ink-3` panel fills, `--rule`/`--rule-bright` hairline borders, solid `--bone`/`--acid` text (no gradient fill on the wordmark).
- Remove the now-unused `glass-panel` / `gradient-text` rules from [index.css](../../../frontend/src/index.css) once no component references them.

### 2b. Bespoke icon set — `Icon.jsx`
- **Purpose:** single source of truth for iconography; `<Icon name="..." />` renders inline SVG with `stroke="currentColor"` so icons inherit bone/acid from context.
- **Style:** 24px grid, 1.5px stroke, **evidence-room / forensic motifs** rather than a generic line set — e.g. transcript as redaction-bars over text lines, audio as a waveform with a mute cut, identity-blur as a face silhouette under a target reticle / halftone dots, PII as a stamped magnifier, alert as a film-frame with a mark.
- **Initial icon list:** `transcript`, `audio`, `identity`, `pii`, `alert`, `search`, `close`, `upload`, `shield` (extendable).
- The bespoke icon shapes will be reviewed visually (rendered SVGs / screenshots) during implementation before they're wired in everywhere.
- Re-stroke the social icons in [icons.svg](../../../frontend/public/icons.svg) from `#aa3bff` (off-brand purple) to bone — keep the icons, fix only the colour.

### 2c. Remove emoji
- Replace the `⚠️` glyph in the auth error banner (currently `Login.jsx`, → `AuthModal.jsx`) with `<Icon name="alert">`. Grep-verify no emoji glyphs remain anywhere in `frontend/src` (the main-app banners already use text tags, not emoji, but confirm).

---

## Workstream 3 — Vision over-count fix

### Root cause
[vision_worker.py:98-104](../../../workers/vision_worker.py) builds `summary` by counting every detection of a label across **all** sampled frames. A 12s clip sampled every 5s ≈ 2 frames; 2 people per frame → "person ×4". The number conflates *detections over time* with *count of objects*.

### Fix (two parts)
1. **Per-frame de-duplication (NMS):** within each frame's results, before appending, merge overlapping same-label boxes using IoU (threshold ≈ 0.6). Removes rare DETR double-detections of one object. Applied to the per-frame `results` loop.
2. **Peak-per-frame summary:** change `summary` to report, per label, the **maximum count seen in any single (de-duplicated) frame** — the intuitive "how many at once". Track per-frame label counts during iteration; `summary[label] = max over frames`.

### Interfaces preserved
- `objects_timeline` stays a flat per-detection list (censor worker / timeline UI unaffected).
- `summary` keeps its `[{label, count}]` shape — only the count *semantics* change. The frontend ([AnalysisDashboard.jsx](../../../frontend/src/components/AnalysisDashboard.jsx)) renders it as-is; no UI change.

---

## Testing / verification

**Vision (3):** re-run the smoke-test scam clip → expect `person ×2` (≤2 people per frame) instead of ×4; confirm censor still blurs persons correctly; spot-check `objects_timeline` length unchanged.

**Frontend (1, 2):**
- Logged-out → landing renders; `Sign in` and `Get started` open the modal on the correct tab.
- Log in with `smoketest` / `smoketest123` (no MFA) → reaches the app.
- Log in with `mihail` → at least one MFA method (e.g. TOTP) completes **inside the modal**, proving the flow survived the move.
- `Esc` / backdrop / ✕ close the modal; focus returns sensibly.
- Grep: no `glass-panel`, `gradient-text`, `backdrop-filter`, `#aa3bff`, or emoji glyphs remain in `frontend/src`.
- Visual smoke: headless Chrome screenshot of landing + open modal (self-signed cert accepted via `--ignore-certificate-errors`).

## Build order (suggested)
1. Vision fix (isolated, fastest, independently verifiable).
2. `Icon.jsx` + de-glass (establishes the visual vocabulary).
3. `LandingPage.jsx` + `AuthModal.jsx` + `App.jsx` rewire (consumes the vocabulary).
