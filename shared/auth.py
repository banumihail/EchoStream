"""
Authentication primitives for EchoStream.

- Argon2id password hashing (OWASP-recommended; memory-hard, GPU-resistant).
- JWT session tokens (HS256, 30-min default expiry).
- FastAPI dependency `require_user` for protecting endpoints.
- Backup-code generator + HMAC-SHA256 hasher (Phase 2 MFA).

JWT_SECRET MUST be overridden in production via env var. The default value here
is documented as insecure to make the threat surface explicit.
"""
import os
import hmac
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from fastapi import Depends, Header, HTTPException, status

JWT_SECRET = os.getenv("JWT_SECRET", "dev-insecure-secret-change-me-in-production")
JWT_ALG = "HS256"
JWT_EXPIRY_MINUTES = int(os.getenv("JWT_EXPIRY_MINUTES", "30"))
MFA_CHALLENGE_EXPIRY_MINUTES = 5

# Token purposes — prevents a challenge token from being accepted as a session
# token (or vice versa) by accident.
PURPOSE_SESSION = "session"
PURPOSE_MFA_CHALLENGE = "mfa-challenge"

# Argon2id is the OWASP-recommended choice. Tuning the parameters here is one
# of the engineering decisions to document in the security report.
_password_hasher = PasswordHasher(
    time_cost=3,        # iterations
    memory_cost=65536,  # 64 MiB
    parallelism=2,
)


def hash_password(password: str) -> str:
    """Return an Argon2id hash for the password."""
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against a stored Argon2id hash."""
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_access_token(payload: dict, expires_minutes: int | None = None) -> str:
    """Issue a signed session JWT. The caller should put at least
    {sub: username} inside; this function tags it with purpose='session'."""
    minutes = expires_minutes if expires_minutes is not None else JWT_EXPIRY_MINUTES
    now = datetime.now(timezone.utc)
    data = {
        **payload,
        "purpose": PURPOSE_SESSION,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
    }
    return jwt.encode(data, JWT_SECRET, algorithm=JWT_ALG)


def create_mfa_challenge_token(username: str, methods: list[str]) -> str:
    """Issued after a successful password check when the user has MFA enrolled.
    Short-lived (5 min) and purpose-restricted so it can ONLY be used to
    complete an MFA challenge, never to access protected endpoints."""
    now = datetime.now(timezone.utc)
    data = {
        "sub": username,
        "purpose": PURPOSE_MFA_CHALLENGE,
        "methods": methods,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=MFA_CHALLENGE_EXPIRY_MINUTES)).timestamp()),
    }
    return jwt.encode(data, JWT_SECRET, algorithm=JWT_ALG)


def decode_access_token(token: str) -> dict | None:
    """Return the decoded JWT payload, or None if invalid/expired."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        return None


def _extract_bearer(authorization: str | None) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


async def require_user(authorization: str | None = Header(default=None)) -> dict:
    """FastAPI dependency. Verifies a session-purpose Bearer token."""
    payload = _extract_bearer(authorization)
    if payload.get("purpose") != PURPOSE_SESSION:
        # An MFA-challenge token cannot be used to access protected resources.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This token cannot be used here.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


async def require_mfa_challenge(authorization: str | None = Header(default=None)) -> dict:
    """FastAPI dependency for endpoints that complete an MFA challenge.
    Accepts ONLY challenge-purpose tokens."""
    payload = _extract_bearer(authorization)
    if payload.get("purpose") != PURPOSE_MFA_CHALLENGE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="MFA challenge token required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload
