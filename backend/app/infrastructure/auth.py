"""Local auth provider adapter (D-AUTH-1).

The frozen contract (`docs/api/AUTH_API.md`, `docs/backend/
AUTH_AUTHORIZATION_ARCHITECTURE.md`) fixes the seam —
``verify_access_token(token) -> Principal`` — and leaves the provider
(D-AUTH-1) open. This module instantiates that seam with a local
email/password provider: the backend acts as its own IdentityProvider,
so "provider-side hashing" lives here.

- Passwords: never stored. Only a bcrypt hash of a SHA-256 pre-hash is
  persisted (`users.password_hash`). The pre-hash keeps the 8..128-char
  contract passwords (UTF-8) within bcrypt's 72-byte input limit.
- Access tokens: HS256 JWTs (`sub` = user id, `jti` = session id,
  `iat`/`exp`). Format was provider-dependent per the contract; JWT is
  the D-AUTH-1 instantiation recorded in CURRENT_STATE.
- Revocation: the R51 session store is instantiated as the
  `user_sessions` table (one row per device/session). The bearer token
  itself is never persisted — rows are keyed by its SHA-256 digest.
- Nothing here logs tokens, passwords, or hashes (ER-4).
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from uuid import UUID

import bcrypt
import jwt

_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """Hash a plaintext password for storage (bcrypt over SHA-256)."""
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return bcrypt.hashpw(digest, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-shape password check (False on any mismatch/error)."""
    try:
        digest = hashlib.sha256(password.encode("utf-8")).digest()
        return bcrypt.checkpw(digest, password_hash.encode("utf-8"))
    except Exception:
        return False


def mint_access_token(
    *,
    user_id: UUID,
    session_id: UUID,
    secret: str,
    expires_in_s: int,
    now: datetime | None = None,
) -> str:
    """Mint a signed JWT access token for one session."""
    moment = now or datetime.now(timezone.utc)
    stamp = int(moment.timestamp())
    payload = {
        "sub": str(user_id),
        "jti": str(session_id),
        "iat": stamp,
        "exp": stamp + int(expires_in_s),
    }
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def decode_access_token(*, token: str, secret: str) -> tuple[UUID, UUID]:
    """Verify signature+expiry and return (user_id, session_id).

    Raises ValueError on any malformed/expired/mis-signed token.
    """
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[_ALGORITHM],
            options={"require": ["sub", "jti", "exp"]},
        )
        return UUID(str(payload["sub"])), UUID(str(payload["jti"]))
    except Exception as exc:
        raise ValueError("invalid access token") from exc


def token_digest(token: str) -> str:
    """SHA-256 digest identifying a session row without storing the token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def digests_equal(left: str, right: str) -> bool:
    """Constant-time digest comparison."""
    return hmac.compare_digest(left, right)
