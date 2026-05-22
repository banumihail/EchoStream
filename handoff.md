# EchoStream — Session Handoff

## Goal we're working toward

**Primary thesis project:** EchoStream — an AI video moderation pipeline with active censorship (face blur, audio redaction).

**Current sub-goal:** A Digital Security course project layered onto EchoStream:
- Audit + classify the existing system's vulnerabilities (Critic → Informațional)
- Implement 5 distinct MFA methods integrated into the existing FastAPI + React stack
- Build an unauthorized-access alerting module backed by Elasticsearch + Kibana
- Re-audit and ship a Word-format Romanian security report following the supplied template

## Current state of the code

### Last commit
`73386b1` on `origin/master`. Repo: https://github.com/banumihail/EchoStream

### Digital Security project status
Both required deliverables are **complete**:
- ✅ 5 MFA methods (Phase 1 TOTP, Phase 2 backup codes, Phase 3 email OTP via Mailtrap, Phase 4 FIDO2/WebAuthn, Phase 5 Telegram push)
- ✅ Unauthorized-access notification module (Phase 6 lockout + IP throttle, Phase 7 security_alerter → Telegram)

Remaining: **Phase 8** (HTTPS self-signed, optional polish) and the **security report** (Word, Romanian, worth 2.0/6.0 — scaffolded in `digitalsecurityproj.md`).

Demo accounts: `mihail` / `12345678` has all 5 MFA methods enrolled. `.env` holds the live Mailtrap + Telegram-bot secrets (gitignored).

### What's running
- **Docker:** RabbitMQ + Elasticsearch + Kibana (all 3 echostream_* containers)
- **API:** FastAPI on `:8000`, locked down with JWT auth on every `/tasks/*` and `/upload-*` endpoint
- **Workers (all on venv Python):** asr, ner, audio_event, vision, censor
- **Frontend:** Vite on `:5173`

### What ships in main features
1. **Interactive word-level transcript** (Whisper `return_timestamps="word"` + boundary clamp) — clickable per word, search, copy
2. **Censorship modes** — video: blur (gblur sigma=15), pixelate (scale trick), box; audio: silence, beep (1 kHz sine mix), muffle (lowpass 400 Hz)
3. **Identity-aware face-tracking blur** — OpenCV YuNet detector + SFace recognizer (ONNX in `models_cache/face/`), multi-reference support, "blur selected" or "blur others" modes, per-identity match stats
4. **URL ingest** — `/upload-url` via yt-dlp (capped at 720p), plus a Chrome MV3 extension in `extension/`
5. **Long-mode toggle** — auto-detected via ffprobe duration ≥10 min, sparser vision sampling (30 s), 60 s AST windows, audio-event timeline
6. **Auth (Phase 0):** Argon2id password hashing, JWT (HS256, 30 min), `/auth/register`, `/auth/login`, `/auth/me`, owner-scoped `/tasks/*` with 404-on-mismatch (IDOR fix)

### Where each big change lives
| Area | File |
|---|---|
| Auth backbone | `shared/auth.py` |
| ES schema for users + auth events | `shared/elasticsearch_client.py` |
| Auth endpoints + ownership enforcement | `api/main.py` |
| Login UI + token storage | `frontend/src/components/Login.jsx`, `frontend/src/lib/auth.js` |
| App gating | `frontend/src/App.jsx`, `frontend/src/components/Navbar.jsx` |
| Face engine (multi-identity) | `workers/face_utils.py`, `workers/censor_worker.py` |
| Word-level Whisper + clamp | `workers/asr_worker.py` |
| Long-mode AST timeline | `workers/audio_event_worker.py` |
| GPU optimizations (FP16, frame caps, allocator) | `workers/vision_worker.py`, `workers/audio_event_worker.py`, `workers/set_cuda_config.py` |
| Chrome extension | `extension/manifest.json`, `extension/background.js`, `extension/popup.html`, `extension/popup.js` |

## Files actively being edited

**Last session ended cleanly — no in-progress edits.**

When resuming, the next files to touch are:
- `api/main.py` — to add `/auth/mfa/totp/setup`, `/auth/mfa/totp/verify`, and a two-step login flow
- `shared/auth.py` — to add a short-lived "mfa-challenge" JWT (distinct from session JWT)
- `frontend/src/components/Login.jsx` (or a new `MfaChallenge.jsx`) — second-step UI
- `shared/elasticsearch_client.py` — methods to read/write `totp_secret` on user docs

## What we tried that failed

- **InsightFace pip install** failed because it needs Visual C++ Build Tools. Pivoted to **OpenCV's built-in `FaceDetectorYN` (YuNet) + `FaceRecognizerSF` (SFace)** with ONNX models from the OpenCV Zoo — no compiler needed.
- **`PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`** is Linux-only; PyTorch logged a warning and ignored it on Windows. Replaced with `max_split_size_mb:128,garbage_collection_threshold:0.6`.
- **Whisper-small for long mode** caused GPU contention crashes when sharing the 8 GB 3070 with DETR/AST/BERT. Reverted to whisper-base for both modes; word-level timestamps + the clamp pass give acceptable accuracy.
- **CUDA OOM / fragmentation on 10-min videos** with all 5 workers loaded simultaneously. Fixes that worked: FP16 for DETR + AST, frame cap at 480p in long mode, `torch.cuda.empty_cache()` between inferences, **moving BERT NER to CPU** (frees 430 MB VRAM).
- **`/plugin install frontend-design@claude-plugins-official`** — slash command not available in the user's Claude Code environment (`/plugin isn't available in this environment`).
- **Docker containers stopped silently several times** (machine restart, sleep). When all workers die mysteriously, check `docker ps` first.
- **Python stdout buffering when redirected to log files** — workers write nothing to logs until they exit or buffers fill. Don't conclude a worker is dead from empty logs; check `Get-Process python` memory usage. 200+ MB = model loaded successfully.
- **API + Worker race on upload** (pre-existing bug fixed earlier in the chain): ES `create_task` must happen before publishing to RabbitMQ, or workers nack with `document_missing_exception`.

## Next step

**Phase 1: TOTP (Google Authenticator)**

1. `pip install pyotp qrcode[pil]`
2. Backend:
   - `/auth/mfa/totp/setup` — requires authenticated user, generates a secret, returns provisioning URI + QR PNG (base64), stores secret pending verification
   - `/auth/mfa/totp/confirm` — user provides first 6-digit code; on success, persists secret and adds "totp" to `user.mfa_methods`
   - Modify `/auth/login` to return a `{mfa_required: true, challenge_token, methods: [...]}` shape (with a short-lived 5-min JWT carrying `purpose: "mfa-challenge"`) instead of the full session JWT when the user has MFA enrolled
   - New `/auth/mfa/totp/verify` accepts the challenge token + 6-digit code, returns the full session JWT with `mfa: true`
3. Frontend:
   - In `Login.jsx`, after password success, branch on `mfa_required` and render an MFA challenge step
   - Add a "Settings → MFA enrollment" flow somewhere (probably a new tab in the navbar or a button in the user chip)
4. Log every TOTP attempt to `echostream_auth_events` with `event_type: "mfa_success"` or `mfa_fail` and `mfa_method: "totp"`

After TOTP works end-to-end, Phases 2-7 follow the same pattern (different verify endpoint per method). See `digitalsecurityproj.md` for the full method roster.

## Quick "boot everything" command for the next session

```powershell
$root='d:\LICENTA\EchoStream'; $py = "$root\.venv\Scripts\python.exe"
docker start echostream_rabbitmq echostream_elasticsearch echostream_kibana
Start-Sleep 14   # wait for Elasticsearch — the poller/alerter crash if ES isn't reachable yet
# 5 ML workers + telegram_poller (push MFA) + security_alerter (Phase 7 alerts)
foreach ($w in 'asr_worker','ner_worker','audio_event_worker','vision_worker','censor_worker','telegram_poller','security_alerter') {
  Start-Process $py -ArgumentList "$root\workers\${w}.py" -WorkingDirectory "$root\workers" -RedirectStandardOutput "$root\scratch\${w}_stdout.log" -RedirectStandardError "$root\scratch\${w}_stderr.log" -WindowStyle Hidden
}
Start-Process $py -ArgumentList "$root\api\main.py" -WorkingDirectory $root -RedirectStandardOutput "$root\scratch\api_stdout.log" -RedirectStandardError "$root\scratch\api_stderr.log" -WindowStyle Hidden
Start-Process 'npm.cmd' -ArgumentList 'run','dev' -WorkingDirectory "$root\frontend" -RedirectStandardOutput "$root\scratch\frontend_stdout.log" -RedirectStandardError "$root\scratch\frontend_stderr.log" -WindowStyle Hidden
```

Verify the two easy-to-miss background processes are real python.exe procs (not just log files):
`Get-CimInstance Win32_Process | ? { $_.Name -eq 'python.exe' -and $_.CommandLine -match 'telegram_poller|security_alerter' }`

Demo login: `mihail` / `12345678` (TOTP + backup + email + FIDO2 + push all enrolled).
