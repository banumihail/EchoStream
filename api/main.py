from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import time
import uvicorn
import uuid
import os
import sys

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

# Add parent directory to path to import shared modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.rabbitmq_client import RabbitMQClient
from shared.elasticsearch_client import ElasticsearchClient
from shared.schemas import VideoProcessingTask, VideoProcessingResponse
from shared.auth import (
    hash_password, verify_password,
    create_access_token, create_mfa_challenge_token,
    require_user, require_mfa_challenge,
    generate_backup_codes, hash_backup_code, consume_backup_code,
)
from shared.email_otp import (
    generate_email_otp, hash_email_otp, otp_expiry_iso, now_iso,
    verify_email_otp, seconds_until_resend_allowed, send_email_otp,
    OTP_RESEND_SECONDS,
)
from shared import fido2 as fido2_lib
from shared import telegram_push as tg
from pydantic import BaseModel
from fastapi import Request

class CensorRequest(BaseModel):
    censor_audio: bool = True
    blur_objects: list[str] = ["person"]
    video_mode: str = "blur"   # box | blur | pixelate
    audio_mode: str = "beep"   # silence | beep | muffle


class UrlUploadRequest(BaseModel):
    url: str

app = FastAPI(title="EchoStream API")

# Setup CORS for Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins, adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Resolve upload directory relative to the project root so it doesn't depend on
# which directory the API process is launched from.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_upload_dir_env = os.getenv("UPLOAD_DIR", "uploads")
UPLOAD_DIR = _upload_dir_env if os.path.isabs(_upload_dir_env) else os.path.join(_PROJECT_ROOT, _upload_dir_env)

RABBITMQ_QUEUE = "video_processing_queue"
AUDIO_EVENT_QUEUE = "audio_event_queue"
VISION_QUEUE = "vision_queue"
CENSOR_QUEUE = "censor_queue"

# Threshold (seconds) above which "auto" mode auto-selects long-form processing.
LONG_MODE_THRESHOLD_SECONDS = int(os.getenv("LONG_MODE_THRESHOLD_SECONDS", "600"))
FFPROBE_PATH = os.path.join(_PROJECT_ROOT, "ffmpeg", "ffprobe.exe") if os.name == "nt" else "ffprobe"


def probe_duration_seconds(file_path: str) -> float | None:
    """Return media duration in seconds via ffprobe, or None on failure."""
    import subprocess
    try:
        result = subprocess.run(
            [FFPROBE_PATH, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", file_path],
            capture_output=True, text=True, timeout=20,
        )
        if result.returncode == 0:
            return float(result.stdout.strip())
    except Exception:
        pass
    return None


def resolve_processing_mode(requested: str, file_path: str) -> tuple[str, float | None]:
    """Resolve processing_mode='auto'|'short'|'long' to a concrete mode.
    Returns (mode, duration_seconds)."""
    duration = probe_duration_seconds(file_path)
    if requested == "long":
        return "long", duration
    if requested == "short":
        return "short", duration
    # 'auto' or anything else
    if duration is not None and duration >= LONG_MODE_THRESHOLD_SECONDS:
        return "long", duration
    return "short", duration

# Ensure upload directory exists
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Serve static files for frontend video player
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Initialize clients (will connect lazily)
rabbitmq_client = None
es_client = None


def cleanup_old_files(max_age_seconds=None):
    """Delete files in UPLOAD_DIR older than max_age_seconds (default from env or 1 hour)"""
    if max_age_seconds is None:
        max_age_seconds = int(os.getenv("CLEANUP_MAX_AGE_SECONDS", "3600"))
    if not os.path.exists(UPLOAD_DIR):
        return
    now = time.time()
    for filename in os.listdir(UPLOAD_DIR):
        file_path = os.path.join(UPLOAD_DIR, filename)
        if os.path.isfile(file_path):
            if os.stat(file_path).st_mtime < now - max_age_seconds:
                try:
                    os.remove(file_path)
                    print(f"Deleted old file: {file_path}")
                except Exception as e:
                    print(f"Failed to delete {file_path}: {e}")


def get_rabbitmq_client():
    """Initialize a fresh RabbitMQ client to avoid heartbeat timeouts"""
    client = RabbitMQClient()
    client.connect()
    client.declare_queue(RABBITMQ_QUEUE)
    client.declare_queue(AUDIO_EVENT_QUEUE)
    client.declare_queue(VISION_QUEUE)
    client.declare_queue(CENSOR_QUEUE)
    return client


def get_es_client():
    """Lazy initialization of Elasticsearch client"""
    global es_client
    if es_client is None:
        es_client = ElasticsearchClient()
        es_client.connect()
    return es_client


# ─────────────────────────────────────────────────────────────────
# Authentication endpoints (Phase 0 — password only; MFA added later)
# ─────────────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    username: str
    password: str
    email: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"


# ── Brute-force protection ────────────────────────────────────────
# Per-account lockout: N consecutive password failures locks the account for
# a cooldown. Per-IP throttle: a sliding window caps login attempts from one
# source to slow distributed / username-enumeration attacks.
LOCKOUT_THRESHOLD = int(os.getenv("LOCKOUT_THRESHOLD", "5"))
LOCKOUT_MINUTES = int(os.getenv("LOCKOUT_MINUTES", "15"))
IP_RATE_LIMIT = int(os.getenv("LOGIN_IP_RATE_LIMIT", "10"))
IP_RATE_WINDOW_SECONDS = int(os.getenv("LOGIN_IP_RATE_WINDOW", "60"))

from collections import defaultdict, deque
_login_attempts_by_ip: dict[str, deque] = defaultdict(deque)


def _ip_rate_exceeded(ip: str) -> bool:
    """Sliding-window per-IP rate check for the login endpoint. In-memory
    (single API process); a distributed deployment would back this with Redis."""
    now = time.time()
    dq = _login_attempts_by_ip[ip]
    cutoff = now - IP_RATE_WINDOW_SECONDS
    while dq and dq[0] < cutoff:
        dq.popleft()
    if len(dq) >= IP_RATE_LIMIT:
        return True
    dq.append(now)
    return False


def _account_locked_remaining(user: dict) -> int:
    """Seconds remaining on an account lock, or 0 if not locked."""
    locked_until = user.get("locked_until")
    if not locked_until:
        return 0
    try:
        lu = datetime.fromisoformat(locked_until)
    except ValueError:
        return 0
    remaining = (lu - datetime.now(timezone.utc)).total_seconds()
    return max(0, int(remaining))


@app.post("/auth/register")
def auth_register(payload: RegisterRequest, request: Request):
    es = get_es_client()
    username = payload.username.strip().lower()
    if len(username) < 3 or len(username) > 32 or not username.isalnum():
        raise HTTPException(status_code=400, detail="Username must be 3-32 alphanumeric characters.")
    if len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")
    if es.get_user(username):
        es.log_auth_event({"username": username, "ip": _client_ip(request),
                           "event_type": "register", "outcome": "denied",
                           "reason": "username exists"})
        raise HTTPException(status_code=409, detail="Username already exists.")
    user_doc = {
        "username": username,
        "password_hash": hash_password(payload.password),
        "email": (payload.email or "").strip().lower() or None,
        "created_at": datetime.now().isoformat(),
        "mfa_methods": [],
        "failed_logins": 0,
        "locked_until": None,
    }
    es.create_user(user_doc)
    es.log_auth_event({"username": username, "ip": _client_ip(request),
                       "event_type": "register", "outcome": "ok"})
    token = create_access_token({"sub": username, "mfa": False})
    return {"access_token": token, "token_type": "bearer", "username": username}


@app.post("/auth/login")
def auth_login(payload: LoginRequest, request: Request):
    es = get_es_client()
    username = payload.username.strip().lower()
    ip = _client_ip(request)

    # 1) Per-IP throttle — runs before any DB work so it also absorbs
    #    username-spray against non-existent accounts.
    if _ip_rate_exceeded(ip):
        es.log_auth_event({"username": username, "ip": ip,
                           "event_type": "rate_limited", "mfa_method": "password",
                           "outcome": "denied", "reason": "ip rate limit"})
        raise HTTPException(status_code=429, detail="Too many attempts. Slow down and try again shortly.")

    user = es.get_user(username)

    # 2) Account lockout — a locked account stays locked regardless of whether
    #    the password is now correct.
    if user:
        remaining = _account_locked_remaining(user)
        if remaining > 0:
            es.log_auth_event({"username": username, "ip": ip,
                               "event_type": "lockout_block", "mfa_method": "password",
                               "outcome": "locked", "reason": f"{remaining}s remaining"})
            raise HTTPException(status_code=429,
                                detail=f"Account temporarily locked. Try again in {remaining // 60 + 1} min.")

    # 3) Password check
    if not user or not verify_password(payload.password, user["password_hash"]):
        if user:
            fails = (user.get("failed_logins") or 0) + 1
            update = {"failed_logins": fails}
            if fails >= LOCKOUT_THRESHOLD:
                update["locked_until"] = (datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)).isoformat()
                update["failed_logins"] = 0  # reset counter once locked
                es.update_user(username, update)
                es.log_auth_event({"username": username, "ip": ip,
                                   "event_type": "lockout", "mfa_method": "password",
                                   "outcome": "locked",
                                   "reason": f"{LOCKOUT_THRESHOLD} consecutive failures"})
                raise HTTPException(status_code=429,
                                    detail=f"Too many failed attempts. Account locked for {LOCKOUT_MINUTES} min.")
            es.update_user(username, update)
        es.log_auth_event({"username": username, "ip": ip,
                           "event_type": "login_fail", "mfa_method": "password",
                           "outcome": "denied", "reason": "bad credentials"})
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    # 4) Success — reset the failure counter / clear any stale lock.
    if user.get("failed_logins") or user.get("locked_until"):
        es.update_user(username, {"failed_logins": 0, "locked_until": None})

    es.log_auth_event({"username": username, "ip": ip,
                       "event_type": "login_success", "mfa_method": "password",
                       "outcome": "ok"})

    methods = user.get("mfa_methods") or []
    if methods:
        # Two-step login — issue a short-lived challenge token. Caller must hit
        # /auth/mfa/{method}/verify with it to obtain a real session JWT.
        challenge = create_mfa_challenge_token(username, methods)
        return {
            "mfa_required": True,
            "challenge_token": challenge,
            "methods": methods,
            "username": username,
        }

    # No MFA enrolled — issue a session JWT directly.
    token = create_access_token({"sub": username, "mfa": False})
    return {"access_token": token, "token_type": "bearer", "username": username,
            "mfa_methods": []}


@app.get("/auth/me")
def auth_me(user=Depends(require_user)):
    es = get_es_client()
    u = es.get_user(user["sub"]) or {}
    return {
        "username": user["sub"],
        "mfa_passed": user.get("mfa", False),
        "mfa_methods": u.get("mfa_methods", []),
        "email": u.get("email"),
        "backup_codes_remaining": len(u.get("backup_codes_hashed") or []),
    }


# ─────────────────────────────────────────────────────────────────
# MFA — TOTP (RFC 6238, Google Authenticator compatible)
# ─────────────────────────────────────────────────────────────────
class TotpConfirmRequest(BaseModel):
    code: str


class TotpVerifyRequest(BaseModel):
    code: str


def _qr_data_url_for(uri: str) -> str:
    """Return a base64 data URL for a QR code rendering the given URI."""
    import io, base64, qrcode
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


@app.post("/auth/mfa/totp/setup")
def totp_setup(user=Depends(require_user)):
    """Begin TOTP enrollment. Generates a new secret, stores it on the user
    doc, and returns a QR code (PNG data URL) the user can scan with Google
    Authenticator / Authy. TOTP is not active until /auth/mfa/totp/confirm
    succeeds with the first 6-digit code."""
    import pyotp
    es = get_es_client()
    username = user["sub"]
    u = es.get_user(username)
    if u and "totp" in (u.get("mfa_methods") or []):
        raise HTTPException(status_code=409, detail="TOTP is already enrolled.")
    secret = pyotp.random_base32()
    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=username, issuer_name="EchoStream")
    es.update_user(username, {"totp_secret": secret})
    return {"secret": secret, "otpauth_uri": uri, "qr_data_url": _qr_data_url_for(uri)}


@app.post("/auth/mfa/totp/confirm")
def totp_confirm(payload: TotpConfirmRequest, request: Request,
                 user=Depends(require_user)):
    """Finalize TOTP enrollment by verifying the user's first code. Activates
    TOTP by adding it to the user's mfa_methods list."""
    import pyotp
    es = get_es_client()
    username = user["sub"]
    ip = _client_ip(request)
    u = es.get_user(username) or {}
    secret = u.get("totp_secret")
    if not secret:
        raise HTTPException(status_code=400, detail="No TOTP setup in progress. Call /auth/mfa/totp/setup first.")
    if not pyotp.TOTP(secret).verify(payload.code, valid_window=1):
        es.log_auth_event({"username": username, "ip": ip,
                           "event_type": "mfa_enroll_fail", "mfa_method": "totp",
                           "outcome": "denied", "reason": "bad code"})
        raise HTTPException(status_code=401, detail="Invalid TOTP code.")
    methods = list(u.get("mfa_methods") or [])
    if "totp" not in methods:
        methods.append("totp")
    es.update_user(username, {"mfa_methods": methods})
    es.log_auth_event({"username": username, "ip": ip,
                       "event_type": "mfa_enrolled", "mfa_method": "totp",
                       "outcome": "ok"})
    return {"ok": True, "mfa_methods": methods}


@app.post("/auth/mfa/totp/verify")
def totp_verify(payload: TotpVerifyRequest, request: Request,
                challenge=Depends(require_mfa_challenge)):
    """Complete the two-step login. Caller presents the MFA challenge token
    obtained from /auth/login and a current TOTP code; returns a real session
    JWT on success."""
    import pyotp
    es = get_es_client()
    username = challenge["sub"]
    ip = _client_ip(request)
    u = es.get_user(username) or {}
    secret = u.get("totp_secret")
    if not secret or "totp" not in (u.get("mfa_methods") or []):
        raise HTTPException(status_code=400, detail="TOTP is not enrolled for this user.")
    if not pyotp.TOTP(secret).verify(payload.code, valid_window=1):
        es.log_auth_event({"username": username, "ip": ip,
                           "event_type": "mfa_fail", "mfa_method": "totp",
                           "outcome": "denied", "reason": "bad code"})
        raise HTTPException(status_code=401, detail="Invalid TOTP code.")
    es.log_auth_event({"username": username, "ip": ip,
                       "event_type": "mfa_success", "mfa_method": "totp",
                       "outcome": "ok"})
    token = create_access_token({"sub": username, "mfa": True})
    return {"access_token": token, "token_type": "bearer", "username": username}


@app.post("/auth/mfa/totp/disable")
def totp_disable(user=Depends(require_user)):
    """Remove TOTP from the user's methods. The session must have completed
    MFA — prevents an attacker who somehow gets a password-only session from
    turning off the second factor."""
    if not user.get("mfa"):
        raise HTTPException(status_code=403, detail="Re-authenticate with MFA to disable it.")
    es = get_es_client()
    username = user["sub"]
    u = es.get_user(username) or {}
    methods = [m for m in (u.get("mfa_methods") or []) if m != "totp"]
    es.update_user(username, {"mfa_methods": methods, "totp_secret": None})
    es.log_auth_event({"username": username, "event_type": "mfa_disabled",
                       "mfa_method": "totp", "outcome": "ok"})
    return {"ok": True, "mfa_methods": methods}


# ─────────────────────────────────────────────────────────────────
# MFA — Backup codes
# ─────────────────────────────────────────────────────────────────
class BackupVerifyRequest(BaseModel):
    code: str


@app.post("/auth/mfa/backup/generate")
def backup_generate(request: Request, user=Depends(require_user)):
    """(Re)generate a fresh set of 10 backup codes. Plaintext codes are
    returned ONCE and never persisted server-side — only their HMAC-SHA256
    hashes are stored. Calling this twice invalidates the previous set.

    Generating requires that the session has already passed an MFA challenge
    — backup codes are an account-recovery factor, not a way to escalate
    from a single-factor session."""
    if not user.get("mfa"):
        raise HTTPException(status_code=403, detail="Re-authenticate with MFA to manage backup codes.")
    es = get_es_client()
    username = user["sub"]
    u = es.get_user(username) or {}
    codes = generate_backup_codes()
    hashed = [hash_backup_code(c) for c in codes]
    methods = list(u.get("mfa_methods") or [])
    if "backup" not in methods:
        methods.append("backup")
    es.update_user(username, {"backup_codes_hashed": hashed, "mfa_methods": methods})
    es.log_auth_event({"username": username, "ip": _client_ip(request),
                       "event_type": "mfa_enrolled", "mfa_method": "backup",
                       "outcome": "ok", "reason": f"{len(codes)} codes generated"})
    return {"codes": codes, "remaining": len(codes), "mfa_methods": methods}


@app.post("/auth/mfa/backup/verify")
def backup_verify(payload: BackupVerifyRequest, request: Request,
                  challenge=Depends(require_mfa_challenge)):
    """Complete the two-step login with a backup code. The matching hash is
    removed on success (single-use). If the consumed code was the last one,
    'backup' is automatically removed from mfa_methods."""
    es = get_es_client()
    username = challenge["sub"]
    ip = _client_ip(request)
    u = es.get_user(username) or {}
    hashed = list(u.get("backup_codes_hashed") or [])
    if not hashed or "backup" not in (u.get("mfa_methods") or []):
        raise HTTPException(status_code=400, detail="Backup codes are not enrolled for this user.")
    ok, remaining = consume_backup_code(payload.code, hashed)
    if not ok:
        es.log_auth_event({"username": username, "ip": ip,
                           "event_type": "mfa_fail", "mfa_method": "backup",
                           "outcome": "denied", "reason": "bad code"})
        raise HTTPException(status_code=401, detail="Invalid backup code.")
    update = {"backup_codes_hashed": remaining}
    if not remaining:
        methods = [m for m in (u.get("mfa_methods") or []) if m != "backup"]
        update["mfa_methods"] = methods
    es.update_user(username, update)
    es.log_auth_event({"username": username, "ip": ip,
                       "event_type": "mfa_success", "mfa_method": "backup",
                       "outcome": "ok", "reason": f"{len(remaining)} codes remaining"})
    token = create_access_token({"sub": username, "mfa": True})
    return {"access_token": token, "token_type": "bearer", "username": username,
            "remaining": len(remaining)}


@app.post("/auth/mfa/backup/disable")
def backup_disable(user=Depends(require_user)):
    """Invalidate all backup codes and remove 'backup' from mfa_methods."""
    if not user.get("mfa"):
        raise HTTPException(status_code=403, detail="Re-authenticate with MFA to disable it.")
    es = get_es_client()
    username = user["sub"]
    u = es.get_user(username) or {}
    methods = [m for m in (u.get("mfa_methods") or []) if m != "backup"]
    es.update_user(username, {"backup_codes_hashed": [], "mfa_methods": methods})
    es.log_auth_event({"username": username, "event_type": "mfa_disabled",
                       "mfa_method": "backup", "outcome": "ok"})
    return {"ok": True, "mfa_methods": methods}


# ─────────────────────────────────────────────────────────────────
# MFA — Email OTP
# ─────────────────────────────────────────────────────────────────
class EmailSetupRequest(BaseModel):
    email: str | None = None  # optional override; otherwise uses email on file


class EmailConfirmRequest(BaseModel):
    code: str


class EmailVerifyRequest(BaseModel):
    code: str


def _issue_email_otp(es, username: str, email: str, request: Request, audit_event: str):
    """Common OTP-issue path. Stores hash + expiry + sent-at, sends the email
    (or logs to console), returns the delivery channel. Throttled by
    OTP_RESEND_SECONDS to prevent the challenge step from spamming the inbox."""
    u = es.get_user(username) or {}
    wait = seconds_until_resend_allowed(u.get("email_otp_sent_at"))
    if wait > 0:
        raise HTTPException(
            status_code=429,
            detail=f"Please wait {wait}s before requesting another code.",
        )
    code = generate_email_otp()
    es.update_user(username, {
        "email_otp_hash": hash_email_otp(code),
        "email_otp_expires": otp_expiry_iso(),
        "email_otp_sent_at": now_iso(),
    })
    try:
        channel = send_email_otp(email, code)
    except Exception as e:
        # Don't leave a stale hash around if the send failed.
        es.update_user(username, {"email_otp_hash": None, "email_otp_expires": None, "email_otp_sent_at": None})
        es.log_auth_event({"username": username, "ip": _client_ip(request),
                           "event_type": audit_event, "mfa_method": "email",
                           "outcome": "denied", "reason": f"smtp error: {e}"})
        raise HTTPException(status_code=502, detail="Could not send the email.")
    es.log_auth_event({"username": username, "ip": _client_ip(request),
                       "event_type": audit_event, "mfa_method": "email",
                       "outcome": "ok", "reason": f"channel={channel} to={email}"})
    return channel


@app.post("/auth/mfa/email/setup")
def email_mfa_setup(payload: EmailSetupRequest, request: Request, user=Depends(require_user)):
    """Begin email-MFA enrollment. Optionally accepts a new email to associate
    with the account. Sends a confirmation OTP; the user must POST the code
    back to /auth/mfa/email/confirm to activate."""
    es = get_es_client()
    username = user["sub"]
    u = es.get_user(username) or {}
    email = (payload.email or u.get("email") or "").strip().lower()
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="A valid email address is required.")
    if "email" in (u.get("mfa_methods") or []):
        raise HTTPException(status_code=409, detail="Email MFA is already enrolled.")
    # Persist the email if it changed
    if email != (u.get("email") or ""):
        es.update_user(username, {"email": email})
    channel = _issue_email_otp(es, username, email, request, "mfa_enroll_request")
    return {"ok": True, "email": email, "channel": channel}


@app.post("/auth/mfa/email/confirm")
def email_mfa_confirm(payload: EmailConfirmRequest, request: Request, user=Depends(require_user)):
    """Finalize email-MFA enrollment by verifying the OTP that was sent."""
    es = get_es_client()
    username = user["sub"]
    u = es.get_user(username) or {}
    ok, reason = verify_email_otp(payload.code, u.get("email_otp_hash"), u.get("email_otp_expires"))
    if not ok:
        es.log_auth_event({"username": username, "ip": _client_ip(request),
                           "event_type": "mfa_enroll_fail", "mfa_method": "email",
                           "outcome": "denied", "reason": reason})
        raise HTTPException(status_code=401, detail="Invalid or expired code.")
    methods = list(u.get("mfa_methods") or [])
    if "email" not in methods:
        methods.append("email")
    es.update_user(username, {
        "mfa_methods": methods,
        "email_otp_hash": None, "email_otp_expires": None, "email_otp_sent_at": None,
    })
    es.log_auth_event({"username": username, "ip": _client_ip(request),
                       "event_type": "mfa_enrolled", "mfa_method": "email",
                       "outcome": "ok"})
    return {"ok": True, "mfa_methods": methods}


@app.post("/auth/mfa/email/request")
def email_mfa_request(request: Request, challenge=Depends(require_mfa_challenge)):
    """Login-flow: send a fresh OTP to the user's enrolled email address."""
    es = get_es_client()
    username = challenge["sub"]
    u = es.get_user(username) or {}
    if "email" not in (u.get("mfa_methods") or []):
        raise HTTPException(status_code=400, detail="Email MFA is not enrolled for this user.")
    email = (u.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="No email address on file.")
    channel = _issue_email_otp(es, username, email, request, "mfa_otp_sent")
    # Don't reveal the full address — partial masking for the UI hint.
    name, _, domain = email.partition("@")
    masked = f"{name[:2]}***@{domain}"
    return {"ok": True, "channel": channel, "to": masked, "resend_in": OTP_RESEND_SECONDS}


@app.post("/auth/mfa/email/verify")
def email_mfa_verify(payload: EmailVerifyRequest, request: Request,
                     challenge=Depends(require_mfa_challenge)):
    """Complete the two-step login with an email OTP. The stored hash is
    cleared on success (single-use)."""
    es = get_es_client()
    username = challenge["sub"]
    u = es.get_user(username) or {}
    if "email" not in (u.get("mfa_methods") or []):
        raise HTTPException(status_code=400, detail="Email MFA is not enrolled for this user.")
    ok, reason = verify_email_otp(payload.code, u.get("email_otp_hash"), u.get("email_otp_expires"))
    if not ok:
        es.log_auth_event({"username": username, "ip": _client_ip(request),
                           "event_type": "mfa_fail", "mfa_method": "email",
                           "outcome": "denied", "reason": reason})
        raise HTTPException(status_code=401, detail="Invalid or expired code.")
    # Single-use — wipe the hash so a leaked code can't be replayed.
    es.update_user(username, {"email_otp_hash": None, "email_otp_expires": None, "email_otp_sent_at": None})
    es.log_auth_event({"username": username, "ip": _client_ip(request),
                       "event_type": "mfa_success", "mfa_method": "email",
                       "outcome": "ok"})
    token = create_access_token({"sub": username, "mfa": True})
    return {"access_token": token, "token_type": "bearer", "username": username}


# ─────────────────────────────────────────────────────────────────
# MFA — FIDO2 / WebAuthn
# ─────────────────────────────────────────────────────────────────
class Fido2RegisterCompleteRequest(BaseModel):
    challenge_token: str
    attestation: dict
    label: str | None = None


class Fido2AuthCompleteRequest(BaseModel):
    challenge_token: str
    assertion: dict


@app.post("/auth/mfa/fido2/register/begin")
def fido2_register_begin(user=Depends(require_user)):
    """Start a WebAuthn registration ceremony. Returns the
    PublicKeyCredentialCreationOptions JSON the browser feeds to
    navigator.credentials.create()."""
    if not user.get("mfa"):
        raise HTTPException(status_code=403, detail="Re-authenticate with MFA to enroll a security key.")
    es = get_es_client()
    username = user["sub"]
    u = es.get_user(username) or {}
    existing = u.get("fido2_credentials") or []
    options_json, challenge_token = fido2_lib.begin_registration(username, existing)
    return {"options": options_json, "challenge_token": challenge_token}


@app.post("/auth/mfa/fido2/register/complete")
def fido2_register_complete(payload: Fido2RegisterCompleteRequest, request: Request,
                            user=Depends(require_user)):
    """Verify the attestation, persist the new credential, add 'fido2' to
    the user's mfa_methods."""
    if not user.get("mfa"):
        raise HTTPException(status_code=403, detail="Re-authenticate with MFA to enroll a security key.")
    es = get_es_client()
    username = user["sub"]
    u = es.get_user(username) or {}
    try:
        cred = fido2_lib.complete_registration(username, payload.challenge_token, payload.attestation)
    except ValueError as e:
        es.log_auth_event({"username": username, "ip": _client_ip(request),
                           "event_type": "mfa_enroll_fail", "mfa_method": "fido2",
                           "outcome": "denied", "reason": str(e)})
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        es.log_auth_event({"username": username, "ip": _client_ip(request),
                           "event_type": "mfa_enroll_fail", "mfa_method": "fido2",
                           "outcome": "denied", "reason": f"verify error: {e}"})
        raise HTTPException(status_code=400, detail="Registration verification failed.")
    cred["label"] = (payload.label or "Security key").strip()[:64]
    credentials = list(u.get("fido2_credentials") or [])
    credentials.append(cred)
    methods = list(u.get("mfa_methods") or [])
    if "fido2" not in methods:
        methods.append("fido2")
    es.update_user(username, {"fido2_credentials": credentials, "mfa_methods": methods})
    es.log_auth_event({"username": username, "ip": _client_ip(request),
                       "event_type": "mfa_enrolled", "mfa_method": "fido2",
                       "outcome": "ok", "reason": f"label={cred['label']}"})
    # Don't return public_key bytes to the browser — minimize surface.
    return {"ok": True, "mfa_methods": methods,
            "credential": {"label": cred["label"], "created_at": cred["created_at"]}}


@app.post("/auth/mfa/fido2/auth/begin")
def fido2_auth_begin(challenge=Depends(require_mfa_challenge)):
    """Start an authentication ceremony for the user identified by the MFA
    challenge token. Returns PublicKeyCredentialRequestOptions JSON."""
    es = get_es_client()
    username = challenge["sub"]
    u = es.get_user(username) or {}
    creds = u.get("fido2_credentials") or []
    if "fido2" not in (u.get("mfa_methods") or []) or not creds:
        raise HTTPException(status_code=400, detail="FIDO2 is not enrolled for this user.")
    try:
        options_json, token = fido2_lib.begin_authentication(username, creds)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"options": options_json, "challenge_token": token}


@app.post("/auth/mfa/fido2/auth/complete")
def fido2_auth_complete(payload: Fido2AuthCompleteRequest, request: Request,
                        challenge=Depends(require_mfa_challenge)):
    """Verify the signed assertion, bump the sign_count, issue a session JWT."""
    es = get_es_client()
    username = challenge["sub"]
    u = es.get_user(username) or {}
    creds = list(u.get("fido2_credentials") or [])
    try:
        updated = fido2_lib.complete_authentication(
            username, payload.challenge_token, payload.assertion, creds,
        )
    except ValueError as e:
        es.log_auth_event({"username": username, "ip": _client_ip(request),
                           "event_type": "mfa_fail", "mfa_method": "fido2",
                           "outcome": "denied", "reason": str(e)})
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        es.log_auth_event({"username": username, "ip": _client_ip(request),
                           "event_type": "mfa_fail", "mfa_method": "fido2",
                           "outcome": "denied", "reason": f"verify error: {e}"})
        raise HTTPException(status_code=401, detail="FIDO2 verification failed.")
    # Persist the bumped sign_count back into the right credential slot.
    new_creds = []
    for c in creds:
        if c["credential_id"] == updated["credential_id"]:
            new_creds.append(updated)
        else:
            new_creds.append(c)
    es.update_user(username, {"fido2_credentials": new_creds})
    es.log_auth_event({"username": username, "ip": _client_ip(request),
                       "event_type": "mfa_success", "mfa_method": "fido2",
                       "outcome": "ok", "reason": f"label={updated.get('label')}"})
    token = create_access_token({"sub": username, "mfa": True})
    return {"access_token": token, "token_type": "bearer", "username": username}


@app.get("/auth/mfa/fido2/credentials")
def fido2_list_credentials(user=Depends(require_user)):
    """Return the labels + timestamps of the user's enrolled credentials,
    without the public-key bytes."""
    es = get_es_client()
    u = es.get_user(user["sub"]) or {}
    creds = u.get("fido2_credentials") or []
    return [
        {"credential_id": c["credential_id"], "label": c.get("label"),
         "created_at": c.get("created_at"), "last_used_at": c.get("last_used_at")}
        for c in creds
    ]


@app.delete("/auth/mfa/fido2/credentials/{credential_id}")
def fido2_delete_credential(credential_id: str, user=Depends(require_user)):
    """Remove a specific FIDO2 credential. If it's the last one, 'fido2' is
    removed from mfa_methods automatically."""
    if not user.get("mfa"):
        raise HTTPException(status_code=403, detail="Re-authenticate with MFA to manage security keys.")
    es = get_es_client()
    username = user["sub"]
    u = es.get_user(username) or {}
    creds = u.get("fido2_credentials") or []
    new_creds = [c for c in creds if c["credential_id"] != credential_id]
    if len(new_creds) == len(creds):
        raise HTTPException(status_code=404, detail="Credential not found.")
    update = {"fido2_credentials": new_creds}
    if not new_creds:
        methods = [m for m in (u.get("mfa_methods") or []) if m != "fido2"]
        update["mfa_methods"] = methods
    es.update_user(username, update)
    es.log_auth_event({"username": username, "event_type": "mfa_credential_removed",
                       "mfa_method": "fido2", "outcome": "ok"})
    return {"ok": True, "remaining": len(new_creds)}


@app.post("/auth/mfa/email/disable")
def email_mfa_disable(user=Depends(require_user)):
    """Remove 'email' from mfa_methods and clear any pending OTP."""
    if not user.get("mfa"):
        raise HTTPException(status_code=403, detail="Re-authenticate with MFA to disable it.")
    es = get_es_client()
    username = user["sub"]
    u = es.get_user(username) or {}
    methods = [m for m in (u.get("mfa_methods") or []) if m != "email"]
    es.update_user(username, {
        "mfa_methods": methods,
        "email_otp_hash": None, "email_otp_expires": None, "email_otp_sent_at": None,
    })
    es.log_auth_event({"username": username, "event_type": "mfa_disabled",
                       "mfa_method": "email", "outcome": "ok"})
    return {"ok": True, "mfa_methods": methods}


# ─────────────────────────────────────────────────────────────────
# MFA — Push notification (Telegram bot, Approve/Deny)
# ─────────────────────────────────────────────────────────────────
PUSH_REQUEST_TTL_SECONDS = 120


@app.post("/auth/mfa/push/enroll/begin")
def push_enroll_begin(user=Depends(require_user)):
    """Generate a one-time pairing token and return a deep link to the bot.
    The user opens it in Telegram and taps Start; the poller links their
    chat_id. Requires an MFA-passed session."""
    if not user.get("mfa"):
        raise HTTPException(status_code=403, detail="Re-authenticate with MFA to connect push.")
    if not tg.is_configured():
        raise HTTPException(status_code=503, detail="Push is not configured on the server (TELEGRAM_BOT_TOKEN missing).")
    es = get_es_client()
    username = user["sub"]
    pairing_token = uuid.uuid4().hex
    es.update_user(username, {"telegram_pairing_token": pairing_token})
    try:
        bot = tg.get_me()
        bot_username = bot.get("username")
    except Exception:
        raise HTTPException(status_code=502, detail="Could not reach Telegram.")
    deep_link = f"https://t.me/{bot_username}?start={pairing_token}"
    return {"deep_link": deep_link, "bot_username": bot_username}


@app.get("/auth/mfa/push/enroll/status")
def push_enroll_status(user=Depends(require_user)):
    """Polled by the Security page; reports whether pairing has completed."""
    es = get_es_client()
    u = es.get_user(user["sub"]) or {}
    enrolled = "push" in (u.get("mfa_methods") or []) and bool(u.get("telegram_chat_id"))
    return {"enrolled": enrolled}


@app.post("/auth/mfa/push/request")
def push_request(request: Request, challenge=Depends(require_mfa_challenge)):
    """Login-flow: create a pending request and send the Approve/Deny prompt
    to the user's Telegram."""
    es = get_es_client()
    username = challenge["sub"]
    u = es.get_user(username) or {}
    chat_id = u.get("telegram_chat_id")
    if "push" not in (u.get("mfa_methods") or []) or not chat_id:
        raise HTTPException(status_code=400, detail="Push is not enrolled for this user.")
    request_id = uuid.uuid4().hex[:12]
    expires = (datetime.now(timezone.utc) + timedelta(seconds=PUSH_REQUEST_TTL_SECONDS)).isoformat()
    es.update_user(username, {"pending_push": {
        "request_id": request_id, "status": "pending", "expires": expires,
        "created": datetime.now(timezone.utc).isoformat(),
    }})
    ip = _client_ip(request)
    text = (f"EchoStream sign-in request\n\nUser: {username}\nIP: {ip}\n\n"
            f"Approve only if this is you. Expires in {PUSH_REQUEST_TTL_SECONDS // 60} min.")
    try:
        tg.send_approval_request(chat_id, text, request_id, username)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not send push: {e}")
    es.log_auth_event({"username": username, "ip": ip, "event_type": "push_sent",
                       "mfa_method": "push", "outcome": "ok"})
    return {"ok": True, "request_id": request_id, "expires_in": PUSH_REQUEST_TTL_SECONDS}


@app.get("/auth/mfa/push/status")
def push_status(challenge=Depends(require_mfa_challenge)):
    """Polled by the login screen. Returns pending | approved | denied | expired | none."""
    es = get_es_client()
    u = es.get_user(challenge["sub"]) or {}
    pending = u.get("pending_push") or {}
    status = pending.get("status", "none")
    # Lazily mark expiry so the UI doesn't hang on a never-answered request.
    if status == "pending":
        try:
            if datetime.now(timezone.utc) > datetime.fromisoformat(pending["expires"]):
                status = "expired"
        except (KeyError, ValueError):
            pass
    return {"status": status}


@app.post("/auth/mfa/push/verify")
def push_verify(request: Request, challenge=Depends(require_mfa_challenge)):
    """Issue a session JWT iff the pending request was approved. Clears the
    pending request so it can't be replayed."""
    es = get_es_client()
    username = challenge["sub"]
    u = es.get_user(username) or {}
    pending = u.get("pending_push") or {}
    if pending.get("status") != "approved":
        raise HTTPException(status_code=401, detail="Push not approved.")
    # Single-use: clear the pending request.
    es.update_user(username, {"pending_push": None})
    es.log_auth_event({"username": username, "ip": _client_ip(request),
                       "event_type": "mfa_success", "mfa_method": "push", "outcome": "ok"})
    token = create_access_token({"sub": username, "mfa": True})
    return {"access_token": token, "token_type": "bearer", "username": username}


@app.post("/auth/mfa/push/disable")
def push_disable(user=Depends(require_user)):
    """Unlink Telegram and remove 'push' from mfa_methods."""
    if not user.get("mfa"):
        raise HTTPException(status_code=403, detail="Re-authenticate with MFA to disable it.")
    es = get_es_client()
    username = user["sub"]
    u = es.get_user(username) or {}
    methods = [m for m in (u.get("mfa_methods") or []) if m != "push"]
    es.update_user(username, {
        "mfa_methods": methods,
        "telegram_chat_id": None, "telegram_pairing_token": None, "pending_push": None,
    })
    es.log_auth_event({"username": username, "event_type": "mfa_disabled",
                       "mfa_method": "push", "outcome": "ok"})
    return {"ok": True, "mfa_methods": methods}


@app.get("/")
def read_root():
    return {
        "message": "EchoStream API is online!",
        "version": "1.1",
        "endpoints": {
            "upload": "/upload-video",
            "task": "/tasks/{task_id}",
            "tasks": "/tasks",
            "docs": "/docs"
        }
    }


@app.get("/tasks")
def list_tasks(user=Depends(require_user)):
    """List the current user's tasks. IDOR mitigation: scoped to owner."""
    es = get_es_client()
    return es.list_tasks(size=50, owner_username=user["sub"])


def _task_or_404(es, task_id: str, username: str, request: Request | None = None):
    """Fetch a task and enforce ownership. Returns 404 (NOT 403) on either a
    missing task or a foreign-owner one so attackers can't enumerate valid IDs."""
    task = es.get_task(task_id)
    if not task or task.get("owner_username") != username:
        if task and request is not None:
            # Log the ownership violation — useful for the alerting module.
            es.log_auth_event({
                "username": username,
                "ip": _client_ip(request),
                "event_type": "idor_attempt",
                "outcome": "denied",
                "reason": f"task {task_id} owner={task.get('owner_username')}",
            })
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.get("/tasks/{task_id}")
def get_task(task_id: str, request: Request, user=Depends(require_user)):
    """Get the current progress and results of a task (owner-scoped)."""
    es = get_es_client()
    return _task_or_404(es, task_id, user["sub"], request)

@app.post("/tasks/{task_id}/censor")
async def censor_video(
    task_id: str,
    censor_audio: bool = Form(True),
    blur_objects: str = Form("person"),    # comma-separated to keep multipart simple
    video_mode: str = Form("blur"),
    audio_mode: str = Form("beep"),
    face_mode: str = Form("selected"),     # 'selected' | 'others'
    reference_names: str = Form(""),       # comma-separated, aligned with reference_faces
    reference_faces: list[UploadFile] = File(default=[]),
    request: Request = None,
    user=Depends(require_user),
):
    """Trigger the Active Censorship pipeline. If reference photos are uploaded,
    the worker switches to per-frame face-tracking blur. With face_mode='selected'
    it blurs faces matching any reference; with 'others' it blurs everyone NOT
    matching a reference (anonymize-bystanders)."""
    es = get_es_client()
    task = _task_or_404(es, task_id, user["sub"], request)

    if face_mode not in ("selected", "others"):
        raise HTTPException(status_code=400, detail="face_mode must be 'selected' or 'others'")

    names = [n.strip() for n in reference_names.split(",")] if reference_names else []
    face_refs = []
    if reference_faces:
        ref_dir = os.path.join(UPLOAD_DIR, "refs")
        os.makedirs(ref_dir, exist_ok=True)
        for i, rf in enumerate(reference_faces):
            if not rf or not rf.filename:
                continue
            ext = os.path.splitext(rf.filename)[1].lower() or ".jpg"
            if ext not in (".jpg", ".jpeg", ".png", ".webp"):
                raise HTTPException(status_code=400, detail=f"Unsupported reference image type: {ext}")
            ref_filename = f"{task_id}_{i}_{uuid.uuid4().hex[:8]}{ext}"
            ref_full_path = os.path.join(ref_dir, ref_filename)
            with open(ref_full_path, "wb") as f:
                f.write(await rf.read())
            rel = os.path.relpath(ref_full_path, _PROJECT_ROOT).replace("\\", "/")
            face_refs.append({
                "path": rel,
                "name": (names[i] if i < len(names) and names[i] else f"Person {i + 1}"),
            })

    if face_mode == "selected" and not face_refs:
        # 'selected' without references is a no-op for face blur — fall through to FFmpeg path.
        pass

    censor_payload = {
        "task_id": task_id,
        "file_path": task.get("file_path"),
        "censor_audio": censor_audio,
        "blur_objects": [s.strip() for s in blur_objects.split(",") if s.strip()],
        "video_mode": video_mode,
        "audio_mode": audio_mode,
        "face_mode": face_mode,
        "face_references": face_refs,
    }
    client = get_rabbitmq_client()
    client.publish_message(CENSOR_QUEUE, censor_payload)
    client.close()
    es.update_worker_status(task_id, "censor", "pending")
    return {"message": "Censorship task queued successfully", "task_id": task_id}


@app.delete("/tasks/{task_id}")
def delete_task(task_id: str, request: Request, user=Depends(require_user)):
    """Delete a task and its associated files (owner-scoped)."""
    es = get_es_client()
    task = _task_or_404(es, task_id, user["sub"], request)
        
    # Delete from DB
    es.delete_task(task_id)
    
    # Delete associated files from disk
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def safe_delete(filepath):
        """Resolve path and delete file if it exists"""
        if not filepath:
            return
        if not os.path.isabs(filepath):
            filepath = os.path.join(project_root, filepath)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
                print(f"Deleted file: {filepath}")
            except Exception as e:
                print(f"Failed to delete {filepath}: {e}")

    safe_delete(task.get("file_path"))
    safe_delete(task.get("censored_file_path"))
    safe_delete(task.get("audio_path"))

    return {"message": "Task and files deleted successfully"}


class UrlUploadRequestExt(BaseModel):
    url: str
    processing_mode: str = "auto"


@app.post("/upload-url", response_model=VideoProcessingResponse)
def upload_url(payload: UrlUploadRequestExt, user=Depends(require_user)):
    """Download a video by URL via yt-dlp, then enqueue it through the same
    pipeline as direct uploads. Supports YouTube, Twitter, Vimeo, and ~1000
    other sites yt-dlp covers."""
    import yt_dlp

    url = (payload.url or "").strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")

    task_id = str(uuid.uuid4())
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Force the output to .mp4 so the rest of the pipeline (which assumes .mp4
    # for the censored-output path replacement) works without special-casing.
    out_template = os.path.join(UPLOAD_DIR, f"{timestamp}_{task_id}.%(ext)s")
    # Cap at 720p — DETR/Whisper don't benefit from 1080p+ for moderation, and
    # the smaller files dramatically reduce memory pressure on long videos.
    ydl_opts = {
        "outtmpl": out_template,
        "format": "bv*[ext=mp4][height<=720]+ba[ext=m4a]/b[ext=mp4][height<=720]/bv*[height<=720]+ba/b[height<=720]/b",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
        downloaded_path = ydl.prepare_filename(info).rsplit(".", 1)[0] + ".mp4"
    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=400, detail=f"Could not download video: {str(e)[:200]}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"yt-dlp failure: {str(e)[:200]}")

    if not os.path.exists(downloaded_path):
        # Fallback: yt-dlp sometimes keeps the original ext when no merge is needed
        for cand_ext in ("webm", "mkv", "mov"):
            cand = os.path.join(UPLOAD_DIR, f"{timestamp}_{task_id}.{cand_ext}")
            if os.path.exists(cand):
                downloaded_path = cand
                break
        else:
            raise HTTPException(status_code=500, detail="Download finished but file not found.")

    relative_file_path = os.path.relpath(downloaded_path, _PROJECT_ROOT).replace("\\", "/")
    title = info.get("title") or os.path.basename(downloaded_path)

    mode, duration = resolve_processing_mode(payload.processing_mode, downloaded_path)
    task = VideoProcessingTask(
        task_id=task_id,
        filename=title,
        file_path=relative_file_path,
        uploaded_at=datetime.now().isoformat(),
        status="pending",
        processing_mode=mode,
        duration_seconds=duration,
        owner_username=user["sub"],
    )

    es = get_es_client()
    es.create_task(task.model_dump())

    client = get_rabbitmq_client()
    client.publish_message(RABBITMQ_QUEUE, task.model_dump())
    client.publish_message(AUDIO_EVENT_QUEUE, task.model_dump())
    client.publish_message(VISION_QUEUE, task.model_dump())
    client.close()

    return VideoProcessingResponse(
        task_id=task_id,
        filename=title,
        status="queued",
        message=f"Video downloaded and queued for processing (mode={mode})",
    )


@app.post("/upload-video", response_model=VideoProcessingResponse)
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    processing_mode: str = Form("auto"),
    user=Depends(require_user),
):
    """
    Upload a video file for processing

    The video will be:
    1. Saved to disk
    2. Added to RabbitMQ queue for processing by AI workers
    3. Return a task_id for tracking
    4. Clean up old files in the background
    """
    background_tasks.add_task(cleanup_old_files)
    allowed_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.webm']
    file_ext = os.path.splitext(file.filename)[1].lower()

    if file_ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"Invalid file type. Allowed: {', '.join(allowed_extensions)}")

    task_id = str(uuid.uuid4())
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = f"{timestamp}_{task_id}{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)
    # Store path relative to project root with forward slashes so workers and the
    # frontend URL both resolve it consistently regardless of OS path separators.
    relative_file_path = os.path.relpath(file_path, _PROJECT_ROOT).replace("\\", "/")

    try:
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        mode, duration = resolve_processing_mode(processing_mode, file_path)
        task = VideoProcessingTask(
            task_id=task_id, filename=file.filename,
            file_path=relative_file_path, uploaded_at=datetime.now().isoformat(),
            status="pending",
            processing_mode=mode,
            duration_seconds=duration,
            owner_username=user["sub"],
        )

        # Create the ES document FIRST so workers can update its status the
        # instant they pick up the queue message. Publishing before create_task
        # races the workers and produces document_missing_exception 404s.
        es = get_es_client()
        es.create_task(task.model_dump())

        client = get_rabbitmq_client()
        client.publish_message(RABBITMQ_QUEUE, task.model_dump())
        client.publish_message(AUDIO_EVENT_QUEUE, task.model_dump())
        client.publish_message(VISION_QUEUE, task.model_dump())
        client.close()

        return VideoProcessingResponse(
            task_id=task_id, filename=file.filename,
            status="queued", message="Video uploaded successfully and queued for processing"
        )

    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@app.on_event("shutdown")
def shutdown_event():
    """Close connections on shutdown"""
    global rabbitmq_client, es_client
    if rabbitmq_client:
        rabbitmq_client.close()
    if es_client:
        es_client.close()


if __name__ == "__main__":
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    # Serve over HTTPS if a cert pair is present (generate via tools/gen_cert.py).
    # Falls back to plain HTTP so the app still runs without certs.
    cert_path = os.path.join(_PROJECT_ROOT, "certs", "localhost-cert.pem")
    key_path = os.path.join(_PROJECT_ROOT, "certs", "localhost-key.pem")
    if os.getenv("API_HTTPS", "1") == "1" and os.path.exists(cert_path) and os.path.exists(key_path):
        print(f"[API] HTTPS enabled (cert: {cert_path})")
        uvicorn.run(app, host=host, port=port, ssl_certfile=cert_path, ssl_keyfile=key_path)
    else:
        print("[API] HTTPS disabled — serving plain HTTP")
        uvicorn.run(app, host=host, port=port)
