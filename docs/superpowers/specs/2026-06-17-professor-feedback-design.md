# EchoStream — Professor feedback changes (design)

**Date:** 2026-06-17
**Status:** Approved (verbal)
**Origin:** Two suggestions from the thesis review: (1) keep a single MFA method, (2) let the blur strength be controlled from the app.

These are two **independent** changes (authentication vs. censorship). They share nothing and should be implemented as **two separate plans**, in any order.

---

## Change A — TOTP-only authentication

### Goal
Reduce the multi-factor system to a single method — **Google Authenticator (TOTP)** — removing backup codes, email OTP, FIDO2/WebAuthn, and Telegram push entirely, leaving a clean single-method auth project.

### Backend ([api/main.py](../../../api/main.py))
- Delete the endpoint groups for the four removed methods: `/auth/mfa/backup/*`, `/auth/mfa/email/*`, `/auth/mfa/fido2/*`, `/auth/mfa/push/*`.
- Keep the TOTP endpoints: `/auth/mfa/totp/setup`, `/confirm`, `/verify`, `/disable`.
- In `/auth/login`, filter the offered methods to the supported set: `methods = [m for m in (user.mfa_methods or []) if m == 'totp']`. This means existing accounts enrolled in all five (e.g. `mihail`) are only ever challenged for TOTP — **no data migration**; the stale `mfa_methods` / `backup_codes_hashed` / `fido2_*` fields on user docs are simply left unused.
- `/auth/me` keeps returning `mfa_methods` (now effectively just `['totp']` in practice); drop the `backup_codes_remaining` field it currently exposes.

### Shared + workers
- [shared/auth.py](../../../shared/auth.py): remove the backup-code helpers (`generate_backup_codes`, `hash_backup_code`, `consume_backup_code`) and any email/FIDO2/push helpers. Keep the TOTP helpers (`pyotp`-based).
- Delete `shared/telegram_push.py` (push transport) and any WebAuthn server helpers.
- Delete the `workers/telegram_poller.py` worker (only the push flow used it); remove it from the boot/run scripts.

### Frontend
- [AuthModal.jsx](../../../frontend/src/components/AuthModal.jsx): the `step === 'mfa'` branch becomes **TOTP-only** — drop the method `<select>` and the `push` / `fido2` / `email` / `backup` conditional blocks; render only the 6-digit code input + Verify. All non-TOTP handlers (`startPushApproval`, `verifyWithFido2`, `requestEmailOtp`, email/push state) are removed.
- [Security.jsx](../../../frontend/src/components/Security.jsx): keep only the TOTP enrollment card (QR + confirm + disable); remove the backup/email/FIDO2/push cards and their handlers.
- `frontend/package.json`: remove the `@simplewebauthn/browser` dependency (FIDO2 only).

### Verification (manual/visual — no FE test framework)
- A TOTP-enrolled user logs in: password → 6-digit code → app. (`mihail`, enrolled in all 5, is offered only TOTP.)
- The removed endpoints return 404; the login modal and Security tab show only TOTP.
- `grep` confirms no references to the removed methods remain in `frontend/src` or the backend; frontend build passes.

---

## Change B — Blur-strength slider

### Goal
Let the user control how strong the censorship blur is, from the redaction panel, end-to-end.

### UI ([AnalysisDashboard.jsx](../../../frontend/src/components/AnalysisDashboard.jsx))
- Add a **"Blur strength"** range slider to the Visual-redaction card, shown only when `videoMode` is `blur` or `pixelate`.
- Scale presented to the user as **Light → Strong** (no raw sigma numbers). Internally a small integer, e.g. `1–10`, state `blurStrength` (default `5`).
- The default position reproduces today's output, so existing behaviour is unchanged unless the user moves the slider.

### Data flow
- The censor request (`handleCensor`) appends `blur_strength` to the existing `FormData`.
- `/tasks/{task_id}/censor` ([api/main.py](../../../api/main.py)) gains `blur_strength: int = Form(5)`, clamped to a safe range, and adds it to `censor_payload`.

### Censor worker ([censor_worker.py](../../../workers/censor_worker.py))
One strength value maps to all three blur paths so the result is consistent regardless of mode:
- **FFmpeg static-region blur** (`_build_video_filter`, the `gblur=sigma=15` line): `sigma = strength * 3` (so `5 → 15`, matching current).
- **OpenCV identity-aware face blur** (the per-region blur in the face-tracking path): scale the `GaussianBlur` kernel with strength (odd kernel size derived from strength).
- **Pixelate** down-scale factor: blockier as strength rises.
- Read `blur_strength` from the task payload with a default of `5`.

### Verification
- Censor the demo clip at a low and a high strength → visibly different blur in the side-by-side; default strength reproduces current output.
- Works for both the FFmpeg path (object/region blur) and the OpenCV path (reference-photo face blur).

---

## Out of scope
- No change to the analysis pipeline, the landing/motion work, or unrelated UI.
- No re-theming of the Security tab beyond removing the four cards.
- TOTP enrollment/confirm flow itself is unchanged.
