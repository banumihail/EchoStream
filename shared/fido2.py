"""
FIDO2 / WebAuthn helpers — Phase 4 MFA.

WebAuthn is a W3C standard for public-key authentication. The user's
authenticator (Windows Hello, Touch ID, YubiKey, etc.) holds the private
key; we only store the public key + credential ID. Each ceremony binds a
challenge to the relying-party origin, which makes the protocol immune to
phishing — a malicious site at a different origin cannot use the credential.

Relying-party identifiers:
  RP_ID     — the domain the credential is scoped to. For local dev this is
              "localhost". For production it would be the actual host
              (echostream.example.com). Subdomains are allowed if RP_ID is set
              to a parent.
  RP_NAME   — human-readable name shown in the OS authenticator prompt.
  ORIGIN    — the full origin string used by the browser making the call.

Challenge handling is stateless: we sign a short-lived JWT containing the
challenge nonce + username + ceremony purpose. The frontend echoes it back
on /complete; we verify the signature and the embedded purpose. No server
state needed between begin and complete.
"""
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from webauthn import (
    generate_registration_options,
    generate_authentication_options,
    verify_registration_response,
    verify_authentication_response,
    options_to_json,
)
from webauthn.helpers import (
    base64url_to_bytes,
    bytes_to_base64url,
)
from webauthn.helpers.structs import (
    PublicKeyCredentialDescriptor,
    UserVerificationRequirement,
)

# These mirror shared/auth.py's JWT secret so we have one trust root for dev.
_JWT_SECRET = os.getenv("JWT_SECRET", "dev-insecure-secret-change-me-in-production")
_JWT_ALG = "HS256"

RP_ID = os.getenv("FIDO2_RP_ID", "localhost")
RP_NAME = os.getenv("FIDO2_RP_NAME", "EchoStream")
ORIGIN = os.getenv("FIDO2_ORIGIN", "http://localhost:5173")
CHALLENGE_TTL_SECONDS = 300


PURPOSE_REG = "fido2-reg"
PURPOSE_AUTH = "fido2-auth"


def _stamp_challenge(challenge: bytes, username: str, purpose: str) -> str:
    """Wrap the random challenge in a short-lived JWT bound to username +
    purpose. The frontend has no way to forge or tamper with this — they
    just send it back on /complete."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "purpose": purpose,
        "challenge": bytes_to_base64url(challenge),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=CHALLENGE_TTL_SECONDS)).timestamp()),
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALG)


def _open_challenge(token: str, username: str, expected_purpose: str) -> bytes:
    """Inverse of _stamp_challenge. Returns the raw challenge bytes if the
    JWT is valid, signed for the right user, and the purpose matches."""
    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALG])
    except jwt.PyJWTError:
        raise ValueError("Invalid or expired FIDO2 challenge.")
    if payload.get("sub") != username or payload.get("purpose") != expected_purpose:
        raise ValueError("Challenge does not match the requested ceremony.")
    return base64url_to_bytes(payload["challenge"])


def begin_registration(username: str, existing_credentials: list[dict]) -> tuple[str, str]:
    """Start a registration ceremony.

    Returns (options_json, challenge_token). The frontend feeds options_json
    into navigator.credentials.create(...), then posts the result + the
    challenge_token back to /complete.

    `existing_credentials` is the user's list of already-registered FIDO2
    credentials; we pass their IDs to exclude_credentials so the browser
    refuses to register the same authenticator twice."""
    exclude = [
        PublicKeyCredentialDescriptor(id=base64url_to_bytes(c["credential_id"]))
        for c in existing_credentials
        if c.get("credential_id")
    ]
    options = generate_registration_options(
        rp_id=RP_ID,
        rp_name=RP_NAME,
        user_id=username.encode(),
        user_name=username,
        user_display_name=username,
        exclude_credentials=exclude,
    )
    token = _stamp_challenge(options.challenge, username, PURPOSE_REG)
    return options_to_json(options), token


def complete_registration(username: str, challenge_token: str, attestation: dict) -> dict:
    """Verify the browser's attestation. On success returns a credential
    dict ready to be persisted on the user document:
        {credential_id, public_key, sign_count, transports, created_at}
    """
    challenge = _open_challenge(challenge_token, username, PURPOSE_REG)
    verification = verify_registration_response(
        credential=attestation,
        expected_challenge=challenge,
        expected_rp_id=RP_ID,
        expected_origin=ORIGIN,
        require_user_verification=False,
    )
    return {
        "credential_id": bytes_to_base64url(verification.credential_id),
        "public_key": bytes_to_base64url(verification.credential_public_key),
        "sign_count": verification.sign_count,
        # Some browsers omit transports; store whatever was sent.
        "transports": [t for t in (attestation.get("response", {}).get("transports") or [])],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def begin_authentication(username: str, credentials: list[dict]) -> tuple[str, str]:
    """Start an authentication ceremony for an enrolled user. We pass the
    user's allowed credential IDs so the browser only offers the right
    authenticator(s)."""
    if not credentials:
        raise ValueError("User has no FIDO2 credentials.")
    allow = [
        PublicKeyCredentialDescriptor(id=base64url_to_bytes(c["credential_id"]))
        for c in credentials
    ]
    options = generate_authentication_options(
        rp_id=RP_ID,
        allow_credentials=allow,
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    token = _stamp_challenge(options.challenge, username, PURPOSE_AUTH)
    return options_to_json(options), token


def complete_authentication(username: str, challenge_token: str, assertion: dict,
                            credentials: list[dict]) -> dict:
    """Verify the browser's signed assertion. Returns the credential dict
    with its sign_count bumped — the caller must persist that so cloning
    detection works."""
    challenge = _open_challenge(challenge_token, username, PURPOSE_AUTH)
    cred_id = assertion.get("id") or assertion.get("rawId")
    if not cred_id:
        raise ValueError("Assertion is missing the credential id.")
    cred_id_b = base64url_to_bytes(cred_id) if isinstance(cred_id, str) else cred_id
    # Find the matching credential — the browser tells us which one it used.
    matching = None
    for c in credentials:
        if base64url_to_bytes(c["credential_id"]) == cred_id_b:
            matching = c
            break
    if matching is None:
        raise ValueError("Unknown credential.")
    verification = verify_authentication_response(
        credential=assertion,
        expected_challenge=challenge,
        expected_rp_id=RP_ID,
        expected_origin=ORIGIN,
        credential_public_key=base64url_to_bytes(matching["public_key"]),
        credential_current_sign_count=matching.get("sign_count", 0),
        require_user_verification=False,
    )
    # The new sign_count must be greater than the stored one — otherwise the
    # authenticator may have been cloned. The webauthn lib already raises if
    # this is violated, but we surface the updated number for storage.
    updated = dict(matching)
    updated["sign_count"] = verification.new_sign_count
    updated["last_used_at"] = datetime.now(timezone.utc).isoformat()
    return updated
