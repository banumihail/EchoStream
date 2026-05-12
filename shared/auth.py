"""
Authentication primitives for EchoStream.

- Argon2id password hashing (OWASP-recommended; memory-hard, GPU-resistant).
- JWT session tokens (HS256, 30-min default expiry).
- FastAPI dependency `require_user` for protecting endpoints.

JWT_SECRET MUST be overridden in production via env var. The default value here
is documented as insecure to make the threat surface explicit.
"""
import os
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from fastapi import Depends, Header, HTTPException, status

JWT_SECRET = os.getenv("JWT_SECRET", "dev-insecure-secret-change-me-in-production")
JWT_ALG = "HS256"
JWT_EXPIRY_MINUTES = int(os.getenv("JWT_EXPIRY_MINUTES", "30"))

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
    """Issue a signed JWT. The caller should put at least {sub: username} inside."""
    minutes = expires_minutes if expires_minutes is not None else JWT_EXPIRY_MINUTES
    now = datetime.now(timezone.utc)
    data = {
        **payload,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
    }
    return jwt.encode(data, JWT_SECRET, algorithm=JWT_ALG)


def decode_access_token(token: str) -> dict | None:
    """Return the decoded JWT payload, or None if invalid/expired."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        return None


async def require_user(authorization: str | None = Header(default=None)) -> dict:
    """FastAPI dependency. Verifies the Bearer token and returns the payload.
    Raises 401 if missing or invalid."""
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
