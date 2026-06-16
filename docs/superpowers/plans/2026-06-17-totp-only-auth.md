# TOTP-Only Authentication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce EchoStream's multi-factor auth to a single method — Google Authenticator (TOTP) — by removing the backup-code, email-OTP, FIDO2, and Telegram-push flows from the backend, shared helpers, a worker, and the frontend.

**Architecture:** This is a removal/simplification. Each MFA method is a self-contained group of FastAPI routes + Pydantic models (in `api/main.py`) plus, in some cases, a `shared/` helper module and frontend UI. We remove them method-by-method, keeping TOTP. `/auth/login` then filters offered methods to `['totp']` so existing multi-method accounts (e.g. `mihail`) are only challenged for TOTP — no data migration.

**Tech Stack:** FastAPI (Python), React (Vite), Elasticsearch. No test framework on either side — **verification is**: `import api.main` succeeds (catches broken backend imports/syntax), `npm run build` passes, `grep` confirms removed references are gone, and a live TOTP login.

**Spec correction:** the spec said "delete `shared/telegram_push.py`". That module is shared with `workers/security_alerter.py` (a separate alerting feature, not MFA), so it is **kept**; only `telegram_poller.py` (push-MFA polling) is deleted.

---

## File Structure

- **Delete:** `shared/fido2.py`, `shared/email_otp.py`, `workers/telegram_poller.py`
- **Keep (not MFA-only):** `shared/telegram_push.py`, `workers/security_alerter.py`, all TOTP routes/helpers
- **Modify:**
  - `api/main.py` — remove backup/email/fido2/push routes + their Pydantic models + their imports; filter `/auth/login` methods; trim `/auth/me`
  - `shared/auth.py` — remove backup-code helpers
  - `frontend/src/components/AuthModal.jsx` — MFA step → TOTP-only; remove non-TOTP handlers + the `@simplewebauthn/browser` import
  - `frontend/src/components/Security.jsx` — keep only the TOTP card
  - `frontend/package.json` — remove `@simplewebauthn/browser`

**Backend verification command (used throughout):**
```bash
cd "d:/LICENTA/EchoStream" && .venv/Scripts/python.exe -c "import api.main; print('import OK')"
```
This imports the FastAPI app module without starting the server (connections are lazy), so it fails loudly if a removal left a dangling reference.

Commits use no co-author trailer (per project preference).

---

## Task 1: Remove the Telegram-push MFA flow + poller

**Files:**
- Modify: `api/main.py` (push routes + the `tg` import)
- Delete: `workers/telegram_poller.py`

- [ ] **Step 1: Remove the push routes and models from `api/main.py`**

Delete these six route functions together with their `@app.post`/`@app.get` decorators:
`/auth/mfa/push/enroll/begin`, `/auth/mfa/push/enroll/status`, `/auth/mfa/push/request`, `/auth/mfa/push/status`, `/auth/mfa/push/verify`, `/auth/mfa/push/disable` (the block beginning at `@app.post("/auth/mfa/push/enroll/begin")`). Also remove any push-only Pydantic request model if present in that block.

- [ ] **Step 2: Remove the push import**

In `api/main.py`, delete the line:
```python
from shared import telegram_push as tg
```
(Leave `shared/telegram_push.py` on disk — `security_alerter.py` still imports it.)

- [ ] **Step 3: Delete the poller worker**

```bash
git rm workers/telegram_poller.py
```

- [ ] **Step 4: Verify**

```bash
cd "d:/LICENTA/EchoStream" && .venv/Scripts/python.exe -c "import api.main; print('import OK')"
grep -nE '/auth/mfa/push/' api/main.py || echo "no push routes ✓"
grep -n "telegram_push" api/main.py || echo "no telegram_push import in main ✓"
```
Expected: `import OK`, no push routes, no `telegram_push` in `api/main.py`. (`security_alerter.py` still references it — that's fine.)

- [ ] **Step 5: Commit**

```bash
git add api/main.py workers/telegram_poller.py
git commit -m "refactor(auth): remove Telegram-push MFA flow and poller worker"
```

---

## Task 2: Remove FIDO2 / WebAuthn

**Files:**
- Modify: `api/main.py` (fido2 routes, models, import)
- Delete: `shared/fido2.py`

- [ ] **Step 1: Remove the FIDO2 routes and models from `api/main.py`**

Delete the route functions for: `/auth/mfa/fido2/register/begin`, `/auth/mfa/fido2/register/complete`, `/auth/mfa/fido2/auth/begin`, `/auth/mfa/fido2/auth/complete`, `/auth/mfa/fido2/credentials` (GET), and `/auth/mfa/fido2/credentials/{credential_id}` (DELETE). Also delete the two models `class Fido2RegisterCompleteRequest(BaseModel)` and `class Fido2AuthCompleteRequest(BaseModel)`.

- [ ] **Step 2: Remove the FIDO2 import**

Delete the line:
```python
from shared import fido2 as fido2_lib
```

- [ ] **Step 3: Delete the helper module**

```bash
git rm shared/fido2.py
```

- [ ] **Step 4: Verify**

```bash
cd "d:/LICENTA/EchoStream" && .venv/Scripts/python.exe -c "import api.main; print('import OK')"
grep -niE 'fido2|webauthn' api/main.py || echo "no fido2 refs ✓"
```
Expected: `import OK`, no fido2/webauthn references in `api/main.py`.

- [ ] **Step 5: Commit**

```bash
git add api/main.py shared/fido2.py
git commit -m "refactor(auth): remove FIDO2/WebAuthn MFA"
```

---

## Task 3: Remove email-OTP MFA

**Files:**
- Modify: `api/main.py` (email routes, models, helper, import)
- Delete: `shared/email_otp.py`

- [ ] **Step 1: Remove the email routes, helper, and models from `api/main.py`**

Delete the route functions: `/auth/mfa/email/setup`, `/auth/mfa/email/confirm`, `/auth/mfa/email/request`, `/auth/mfa/email/verify`, and `/auth/mfa/email/disable`. Delete the helper `def _issue_email_otp(...)`. Delete the models `class EmailSetupRequest(BaseModel)`, `class EmailConfirmRequest(BaseModel)`, `class EmailVerifyRequest(BaseModel)`.

- [ ] **Step 2: Remove the email-OTP import**

Delete the import block:
```python
from shared.email_otp import (
    generate_email_otp, hash_email_otp, otp_expiry_iso, now_iso,
    verify_email_otp, seconds_until_resend_allowed, send_email_otp,
)
```
(The `now_iso` helper is from this module — if it is used elsewhere in `api/main.py`, search first: `grep -n "now_iso" api/main.py`. If used outside the email flow, define a tiny local `now_iso` instead of importing; otherwise just remove the import.)

- [ ] **Step 3: Delete the helper module**

```bash
git rm shared/email_otp.py
```

- [ ] **Step 4: Verify**

```bash
cd "d:/LICENTA/EchoStream" && .venv/Scripts/python.exe -c "import api.main; print('import OK')"
grep -nE '/auth/mfa/email/|email_otp|_issue_email_otp' api/main.py || echo "no email-MFA refs ✓"
```
Expected: `import OK`, no email-MFA references. (The `email_otp_*` mapping fields in `shared/elasticsearch_client.py` may stay — harmless, unused.)

- [ ] **Step 5: Commit**

```bash
git add api/main.py shared/email_otp.py
git commit -m "refactor(auth): remove email-OTP MFA"
```

---

## Task 4: Remove backup codes

**Files:**
- Modify: `api/main.py` (backup routes, model, import names)
- Modify: `shared/auth.py` (backup helpers)

- [ ] **Step 1: Remove the backup routes and model from `api/main.py`**

Delete the route functions `/auth/mfa/backup/generate`, `/auth/mfa/backup/verify`, `/auth/mfa/backup/disable`, and the model `class BackupVerifyRequest(BaseModel)`.

- [ ] **Step 2: Drop the backup helper names from the `shared.auth` import**

In `api/main.py`, the `from shared.auth import (...)` block includes:
```python
    generate_backup_codes, hash_backup_code, consume_backup_code,
```
Remove exactly those three names from the import list (keep the rest of the import — password/JWT/TOTP helpers).

- [ ] **Step 3: Remove the helpers from `shared/auth.py`**

Delete the function definitions `generate_backup_codes`, `hash_backup_code`, and `consume_backup_code` from `shared/auth.py`. Leave all password-hashing, JWT, and TOTP helpers intact.

- [ ] **Step 4: Verify**

```bash
cd "d:/LICENTA/EchoStream" && .venv/Scripts/python.exe -c "import api.main; print('import OK')"
grep -nE '/auth/mfa/backup/|backup_code' api/main.py shared/auth.py || echo "no backup refs ✓"
```
Expected: `import OK`, no backup references in either file.

- [ ] **Step 5: Commit**

```bash
git add api/main.py shared/auth.py
git commit -m "refactor(auth): remove backup-code MFA"
```

---

## Task 5: Make login and /auth/me TOTP-only

**Files:**
- Modify: `api/main.py` (`/auth/login`, `/auth/me`)

- [ ] **Step 1: Filter offered methods in `/auth/login`**

In the `auth_login` function, find:
```python
    methods = user.get("mfa_methods") or []
```
Replace with:
```python
    # Only TOTP is supported; ignore any legacy enrolled methods on the user doc.
    methods = [m for m in (user.get("mfa_methods") or []) if m == "totp"]
```

- [ ] **Step 2: Trim `/auth/me`**

In `auth_me`, delete the line:
```python
        "backup_codes_remaining": len(u.get("backup_codes_hashed") or []),
```

- [ ] **Step 3: Verify**

```bash
cd "d:/LICENTA/EchoStream" && .venv/Scripts/python.exe -c "import api.main; print('import OK')"
grep -n "backup_codes_remaining" api/main.py || echo "trimmed ✓"
```
Expected: `import OK`, no `backup_codes_remaining`.

- [ ] **Step 4: Commit**

```bash
git add api/main.py
git commit -m "refactor(auth): offer only TOTP at login; trim /auth/me"
```

---

## Task 6: AuthModal — TOTP-only MFA step

**Files:**
- Modify: `frontend/src/components/AuthModal.jsx`

- [ ] **Step 1: Remove the non-TOTP imports and handlers**

In `AuthModal.jsx`:
- Delete the import `import { startAuthentication } from '@simplewebauthn/browser';`.
- Delete the handler functions `startPushApproval`, `verifyWithFido2`, and `requestEmailOtp`.
- Delete the state hooks that only those used: `mfaMethods`, `mfaMethod`, `emailRequested`, `emailMaskedTo`, `pushState` (keep `challengeToken` and `mfaCode`). In `resetToStart`, remove the setters for the deleted state.
- In `submit`, where the MFA branch sets state, replace:
  ```js
        setChallengeToken(data.challenge_token);
        setMfaMethods(data.methods || []);
        setMfaMethod((data.methods || [])[0] || null);
        setStep('mfa');
  ```
  with:
  ```js
        setChallengeToken(data.challenge_token);
        setStep('mfa');
  ```
- In `submitMfa`, hard-code the TOTP verify endpoint — replace `` `${API_URL}/auth/mfa/${mfaMethod}/verify` `` with `` `${API_URL}/auth/mfa/totp/verify` `` and drop the `if (!mfaMethod ...)` guard so it only checks `mfaCode`.

- [ ] **Step 2: Replace the MFA-step JSX with a TOTP-only version**

Replace the entire `if (step === 'mfa') { return (...) }` block with:

```jsx
  if (step === 'mfa') {
    return (
      <div className="modal-overlay" onMouseDown={onOverlayMouseDown}>
        <div className="modal-card">
          <button className="modal-close" onClick={onClose} aria-label="Close"><Icon name="close" size={18} /></button>
          <div style={{ textAlign: 'center', marginBottom: 24 }}>
            <h1 className="modal-title">Echo<em>Stream</em><span className="lm-cursor" /></h1>
            <p className="modal-subtitle">Two-factor authentication</p>
          </div>
          <form onSubmit={submitMfa}>
            <label className="login-label">Code from authenticator app</label>
            <input
              className="login-input"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              placeholder="6 digits"
              value={mfaCode}
              onChange={(e) => setMfaCode(e.target.value)}
              disabled={busy}
              autoFocus
              maxLength={8}
            />
            {error && (
              <div className="error-banner shake" style={{ marginTop: 14 }}>
                <span className="error-icon"><Icon name="alert" size={16} /></span>
                <p>{error}</p>
              </div>
            )}
            <button className="btn btn-primary" type="submit" disabled={busy || !mfaCode.trim()} style={{ width: '100%', marginTop: 18 }}>
              {busy ? 'Verifying…' : 'Verify'}
            </button>
            <button type="button" className="btn btn-outline" style={{ width: '100%', marginTop: 10 }} onClick={resetToStart} disabled={busy}>
              Back
            </button>
          </form>
        </div>
      </div>
    );
  }
```

- [ ] **Step 3: Verify**

```bash
cd "d:/LICENTA/EchoStream/frontend" && npm run build 2>&1 | tail -3
grep -nE "simplewebauthn|startPushApproval|verifyWithFido2|requestEmailOtp|mfaMethods" src/components/AuthModal.jsx || echo "AuthModal clean ✓"
```
Expected: build succeeds; no leftover references.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/AuthModal.jsx
git commit -m "refactor(ui): AuthModal MFA step is TOTP-only"
```

---

## Task 7: Security tab — TOTP only; drop the FIDO2 dependency

**Files:**
- Modify: `frontend/src/components/Security.jsx`
- Modify: `frontend/package.json`

- [ ] **Step 1: Strip the non-TOTP sections from `Security.jsx`**

Read the file, then remove everything tied to the four removed methods, keeping the TOTP enrollment card and its handlers:
- Imports: remove the `@simplewebauthn/browser` import (`startRegistration`).
- State: remove `backupCodes`, all email-OTP enrollment state, `fido2Credentials`, `fido2Label`, `pushDeepLink`, `pushPolling` (and any siblings used only by those flows).
- Handlers: remove `refreshFido2`, the FIDO2 register/delete handlers, `generateBackupCodes`, `copyBackupCodes`, `downloadBackupCodes`, `disableBackupCodes`, and all email/push enrollment handlers + their `useEffect`s.
- JSX: remove the Backup codes, Email OTP, FIDO2 / WebAuthn, and Push (Telegram) cards. Keep only the "Authenticator app (TOTP)" card.

Keep the page shell (heading, error/info banners, the `me`/loading fetch) intact.

- [ ] **Step 2: Remove the dependency**

In `frontend/package.json`, delete the `"@simplewebauthn/browser": "..."` line from `dependencies`. (No need to edit `package-lock.json` by hand; it's fine to leave, or run `npm install` to prune.)

- [ ] **Step 3: Verify**

```bash
cd "d:/LICENTA/EchoStream/frontend" && npm run build 2>&1 | tail -3
cd "d:/LICENTA/EchoStream" && grep -rnE "simplewebauthn|/auth/mfa/(backup|email|fido2|push)/" frontend/src || echo "frontend clean of removed methods ✓"
```
Expected: build succeeds; no references to removed methods anywhere in `frontend/src`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/Security.jsx frontend/package.json
git commit -m "refactor(ui): Security tab keeps only TOTP; drop @simplewebauthn/browser"
```

---

## Task 8: Final end-to-end verification

**Files:** none (verification only)

- [ ] **Step 1: Static checks**

```bash
cd "d:/LICENTA/EchoStream"
.venv/Scripts/python.exe -c "import api.main; print('backend import OK')"
( cd frontend && npm run build 2>&1 | tail -2 )
grep -rnE "/auth/mfa/(backup|email|fido2|push)/|simplewebauthn|telegram_poller" api shared frontend/src workers | grep -v "telegram_push" || echo "no removed-method refs ✓"
```
Expected: backend import OK, build OK, no stray references (the only `telegram_*` hit allowed is `telegram_push`, kept for the alerter).

- [ ] **Step 2: Live login check (stack must be running)**

Boot the stack if needed (Docker + `api/main.py` + workers + frontend), then verify a TOTP-enrolled account is challenged for TOTP only:
```bash
curl.exe -k -s -X POST -H "Content-Type: application/json" -d '{"username":"mihail","password":"12345678"}' https://localhost:8000/auth/login | python -c "import sys,json;d=json.load(sys.stdin);print('mfa_required:',d.get('mfa_required'),'methods:',d.get('methods'))"
```
Expected: `mfa_required: True methods: ['totp']` (even though `mihail` is enrolled in all five). Then complete a real login from the browser with the authenticator code.

- [ ] **Step 3: Confirm removed endpoints are gone**

```bash
curl.exe -k -s -o NUL -w "%{http_code}\n" -X POST https://localhost:8000/auth/mfa/push/request
```
Expected: `404` (route no longer exists).

---

## Self-Review notes (author)

- **Spec coverage:** spec Change A asks to remove backup/email/fido2/push from backend, shared, worker, and frontend, keep TOTP, filter login, drop the dep. Tasks 1–4 remove each method; Task 5 filters login + trims `/auth/me`; Tasks 6–7 do the frontend + dependency. ✓ Correction logged: `telegram_push.py` kept (alerter dependency), only `telegram_poller.py` deleted.
- **Placeholder scan:** removals are specified by exact route/function/model/import names; the one transformation needing new code (AuthModal MFA step, login filter) shows complete code; verification steps give exact commands + expected output. ✓
- **Consistency:** `methods` filter, the `submitMfa` TOTP URL, and the kept state (`challengeToken`, `mfaCode`) line up across Tasks 5–6. The import-check command is identical everywhere. ✓
