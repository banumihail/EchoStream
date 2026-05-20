"""
Email OTP helpers — Phase 3 MFA.

Random 6-digit codes, 5-min expiry, single-use, HMAC-SHA256 hashed at rest.
SMTP delivery is opt-in via env vars (Mailtrap or any other server):

    SMTP_HOST  — required to actually send; missing → console fallback
    SMTP_PORT  — default 2525 (Mailtrap sandbox)
    SMTP_USER, SMTP_PASS  — optional credentials
    SMTP_FROM  — From: header, default "EchoStream <noreply@echostream.local>"
    SMTP_TLS   — default true; calls STARTTLS unless server refuses

If SMTP_HOST is not set, the OTP is printed to the API's stdout. This is
intentional for dev — it lets the auth flow be exercised end-to-end before
Mailtrap credentials are configured. In production this must NOT be relied on.
"""
import os
import hmac
import hashlib
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid

OTP_EXPIRY_MINUTES = 5
OTP_RESEND_SECONDS = 30

OTP_HMAC_KEY = (
    os.getenv("EMAIL_OTP_KEY")
    or (os.getenv("JWT_SECRET", "dev-insecure-secret-change-me-in-production") + ":emailotp")
).encode()

SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "2525"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", "EchoStream <noreply@echostream.local>")
SMTP_TLS = os.getenv("SMTP_TLS", "true").strip().lower() in ("1", "true", "yes")


def generate_email_otp() -> str:
    """A fresh random 6-digit code. Random (not time-based) so it can't be
    pre-computed by an attacker who knows the time."""
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_email_otp(code: str) -> str:
    """HMAC-SHA256 with a server-side key. DB leak alone doesn't reveal the
    plaintext OTP without also leaking EMAIL_OTP_KEY."""
    return hmac.new(OTP_HMAC_KEY, code.strip().encode(), hashlib.sha256).hexdigest()


def otp_expiry_iso() -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRY_MINUTES)).isoformat()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def verify_email_otp(code: str, stored_hash: str | None, expires_iso: str | None) -> tuple[bool, str | None]:
    """Return (ok, reason_if_failed). Constant-time compare; explicit reasons
    so callers can audit-log them without leaking detail to the user."""
    if not stored_hash or not expires_iso:
        return False, "no_pending"
    try:
        expires = datetime.fromisoformat(expires_iso)
    except ValueError:
        return False, "bad_expiry"
    if datetime.now(timezone.utc) > expires:
        return False, "expired"
    if not hmac.compare_digest(stored_hash, hash_email_otp(code)):
        return False, "mismatch"
    return True, None


def seconds_until_resend_allowed(last_sent_iso: str | None) -> int:
    """Returns 0 if a new OTP can be sent now, else how many seconds to wait."""
    if not last_sent_iso:
        return 0
    try:
        last = datetime.fromisoformat(last_sent_iso)
    except ValueError:
        return 0
    delta = (datetime.now(timezone.utc) - last).total_seconds()
    return max(0, int(OTP_RESEND_SECONDS - delta))


def send_email_otp(to: str, code: str) -> str:
    """Deliver the OTP. Returns 'smtp' if sent over SMTP, 'console' if SMTP
    isn't configured and we logged it to stdout instead. Raises on SMTP error
    when SMTP_HOST is set (the caller should turn that into a 502)."""
    body = (
        f"Your EchoStream verification code is:\n\n"
        f"    {code}\n\n"
        f"This code expires in {OTP_EXPIRY_MINUTES} minutes. "
        f"If you didn't request it, ignore this email."
    )
    if not SMTP_HOST:
        print(f"[EMAIL OTP / console fallback] to={to} code={code}", flush=True)
        return "console"
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = "EchoStream verification code"
    msg["From"] = SMTP_FROM
    msg["To"] = to
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="echostream.local")
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
        s.ehlo()
        if SMTP_TLS:
            try:
                s.starttls()
                s.ehlo()
            except smtplib.SMTPNotSupportedError:
                pass
        if SMTP_USER:
            s.login(SMTP_USER, SMTP_PASS)
        s.sendmail(SMTP_FROM, [to], msg.as_string())
    return "smtp"
