"""Application use cases — authentication (D-AUTH-1, M1, UC-1…UC-4).

`RegisterAccount` (O-1 `POST /v1/auth/register`), `SignIn` (O-3
`POST /v1/auth/login`), `SignOut` (O-4 `POST /v1/auth/logout`) per
`docs/api/AUTH_API.md` §5. Each use case is a thin orchestration unit
over the `AuthRepository` port and raises typed `ApiError`s — business
rules live here, not in the routers (BA-7).

Contract notes (authoritative-first):
- Identity is the opaque (provider, subject) pair (BC-1). Email
  accounts use provider `"email"` with the normalized email as
  subject, so duplicate emails collide on the existing pair
  constraint — no new uniqueness invented.
- Login is a uniform 401 for "no such account" and "wrong password"
  (AUTH_API §5.3 enumeration control); the inherited UC-3 404 is
  deliberately not emitted.
- Register replay (same `Idempotency-Key` + same payload) resolves to
  the same account with a fresh session — never a duplicate; a reused
  key with a different payload, or a taken email under a fresh key,
  is a 409 `CONFLICT` (M7 replay/conflict semantics for creation).
- Refresh sessions do not exist (§3.1 — no endpoint, no secrets).
- Social sign-in (O-2) needs an external provider that is not
  configured in this instantiation: the router validates the shape
  (422) and the use case answers the honest 502
  `EXTERNAL_SERVICE_FAILURE` without minting anything.
- Passwords are never stored (only bcrypt hashes, provider-side in
  the infrastructure adapter) and never logged (ER-4).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional
from uuid import UUID, uuid4
import logging

from app.api.errors import ApiError, authentication_error, conflict, not_found
from app.domain.ports.repositories import AuthAccountRecord, AuthRepository
from app.infrastructure.auth import (
    decode_access_token,
    hash_password,
    mint_access_token,
    token_digest,
    verify_password,
)

_EMAIL_PROVIDER = "email"

logger = logging.getLogger("fansivibe.application.auth")


def _field_error(field: str, error: str) -> ApiError:
    return ApiError(
        status_code=422,
        code="VALIDATION_ERROR",
        message="Some of the provided values are not valid. Please check your input.",
        details={"field_errors": [{"field": field, "error": error}]},
    )


def normalize_email(raw: object) -> str:
    """Normalize + validate an email per AUTH_API §6 (RFC-shape, ≤254).

    Raises a 422 `ApiError` when malformed — never invents an address.
    """
    if not isinstance(raw, str):
        raise _field_error("email", "must be a valid email address")
    cleaned = raw.strip().lower()
    if (
        not cleaned
        or len(cleaned) > 254
        or "@" not in cleaned
        or cleaned.startswith("@")
        or cleaned.endswith("@")
    ):
        raise _field_error("email", "must be a valid email address")
    local, _, domain = cleaned.partition("@")
    if not local or not domain or "." not in domain:
        raise _field_error("email", "must be a valid email address")
    return cleaned


def validated_register_password(raw: object) -> str:
    """Validate a registration password (8..128, ≥1 letter + ≥1 digit)."""
    if not isinstance(raw, str) or not (8 <= len(raw) <= 128):
        raise _field_error(
            "password", "must be between 8 and 128 characters long"
        )
    if not any(ch.isalpha() for ch in raw) or not any(
        ch.isdigit() for ch in raw
    ):
        raise _field_error(
            "password", "must contain at least one letter and one digit"
        )
    return raw


def validated_display_name(raw: object) -> Optional[str]:
    """Validate an optional display name (trimmed, 1..100 when present)."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise _field_error("displayName", "must be between 1 and 100 characters")
    trimmed = raw.strip()
    if not trimmed:
        raise _field_error("displayName", "must be between 1 and 100 characters")
    if len(trimmed) > 100:
        raise _field_error("displayName", "must be between 1 and 100 characters")
    return trimmed


class RegisterAccount:
    """UC-1 — `POST /v1/auth/register` (AUTH_API §5.1)."""

    def __init__(self, *, auth: AuthRepository) -> None:
        self._auth = auth

    def __call__(
        self,
        *,
        email: object,
        password: object,
        display_name: object = None,
        idempotency_key: str,
        secret: str,
        expires_in_s: int,
        now: Optional[datetime] = None,
    ) -> tuple[AuthAccountRecord, str]:
        """Create the account + first session, or replay idempotently.

        Returns (account, access_token). Raises 409 on duplicate email
        under a fresh key, 422 on invalid fields. Commits exactly one
        account + one session on creation (replay adds one session).
        """
        clean_email = normalize_email(email)
        clean_password = validated_register_password(password)
        clean_name = validated_display_name(display_name) or clean_email.partition(
            "@"
        )[0]
        existing = self._auth.find_account(
            auth_provider=_EMAIL_PROVIDER, auth_subject=clean_email
        )
        if existing is not None:
            if (
                existing.register_idempotency_key == idempotency_key
                and existing.password_hash is not None
                and verify_password(clean_password, existing.password_hash)
                and existing.display_name == clean_name
            ):
                token = issue_session(
                    self._auth,
                    account=existing,
                    secret=secret,
                    expires_in_s=expires_in_s,
                    now=now,
                )
                self._auth.commit()
                return existing, token
            raise conflict(kind="duplicate")
        account = self._auth.create_account(
            auth_provider=_EMAIL_PROVIDER,
            auth_subject=clean_email,
            display_name=clean_name,
            password_hash=hash_password(clean_password),
            idempotency_key=idempotency_key,
        )
        token = issue_session(
            self._auth,
            account=account,
            secret=secret,
            expires_in_s=expires_in_s,
            now=now,
        )
        self._auth.commit()
        return account, token


class SignIn:
    """UC-3 — `POST /v1/auth/login` (AUTH_API §5.3)."""

    def __init__(self, *, auth: AuthRepository) -> None:
        self._auth = auth

    def __call__(
        self,
        *,
        email: object,
        password: object,
        secret: str,
        expires_in_s: int,
        now: Optional[datetime] = None,
    ) -> tuple[AuthAccountRecord, str]:
        """Verify credentials and issue one session (uniform 401)."""
        clean_email = normalize_email(email)
        if not isinstance(password, str) or not password:
            raise _field_error("password", "must be provided")
        account = self._auth.find_account(
            auth_provider=_EMAIL_PROVIDER, auth_subject=clean_email
        )
        if (
            account is None
            or account.password_hash is None
            or not verify_password(password, account.password_hash)
        ):
            raise authentication_error()
        token = issue_session(
            self._auth,
            account=account,
            secret=secret,
            expires_in_s=expires_in_s,
            now=now,
        )
        self._auth.commit()
        return account, token


class SignOut:
    """UC-4 — `POST /v1/auth/logout` (AUTH_API §5.4, idempotent revoke)."""

    def __init__(self, *, auth: AuthRepository) -> None:
        self._auth = auth

    def __call__(self, *, session_id: UUID) -> None:
        self._auth.revoke_session(session_id=session_id)
        self._auth.commit()


class DeleteAccount:
    """O-6 — `DELETE /v1/users/me` (AUTH_API §5.6, erasure TRX-8).

    One `DELETE users` cascades across all user-owned children at the FK
    (sessions, state, runs, saves, signals, feedback, wardrobe, wears,
    events, activity). Knowledge/vocabulary rows survive (no user FK).
    Retry-safe: a second call finds no account → 404, never another
    user's data. Completion is access-logged (owner id only, ER-4).
    """

    def __init__(self, *, auth: AuthRepository) -> None:
        self._auth = auth

    def __call__(self, *, user_id: UUID) -> None:
        deleted = self._auth.delete_account(user_id=user_id)
        if not deleted:
            self._auth.rollback()
            raise not_found()
        self._auth.commit()
        logger.info("Account erased [user_id=%s]", user_id)


class EraseAccount:
    """Complete account erasure across R2 storage, Genlook, and PostgreSQL.

    Deletes external media objects and external provider customer references
    BEFORE deleting the PostgreSQL `users` row so that any transient external
    failure leaves the user's session and media references intact for safe,
    idempotent retry without orphaned R2 objects.
    """

    def __init__(
        self,
        *,
        auth: AuthRepository,
        storage: Any = None,
        genlook_eraser: Optional[Callable[[UUID], bool]] = None,
    ) -> None:
        self._auth = auth
        self._storage = storage
        self._genlook_eraser = genlook_eraser

    async def __call__(self, *, user_id: UUID) -> dict[str, Any]:
        exists_fn = getattr(self._auth, "account_exists", None)
        if callable(exists_fn) and not exists_fn(user_id=user_id):
            self._auth.rollback()
            raise not_found()

        db_keys: list[str] = []
        tryon_job_ids: list[UUID] = []
        collect_fn = getattr(self._auth, "collect_user_media_keys", None)
        if callable(collect_fn):
            db_keys, tryon_job_ids = collect_fn(user_id=user_id)

        all_keys: set[str] = set(db_keys)
        if self._storage is not None:
            list_fn = getattr(self._storage, "list_keys", None)
            if callable(list_fn):
                for prefix in (f"users/{user_id}/", f"staging/users/{user_id}/"):
                    try:
                        listed = await list_fn(prefix)
                        for key in listed or []:
                            if isinstance(key, str) and (
                                key.startswith(f"users/{user_id}/")
                                or key.startswith(f"staging/users/{user_id}/")
                            ):
                                all_keys.add(key)
                    except Exception as exc:
                        self._auth.rollback()
                        logger.warning(
                            "Account erasure storage scan failed [user_id=%s, prefix=%s, err=%s]",
                            user_id,
                            prefix,
                            type(exc).__name__,
                        )
                        raise ApiError(
                            status_code=503,
                            code="ERASURE_STORAGE_FAILURE",
                            message="Unable to complete media erasure right now. Please retry.",
                        )

            sorted_keys = sorted(all_keys)
            if sorted_keys:
                delete_safe_fn = getattr(self._storage, "delete_objects_safe", None)
                failed_keys: list[str] = []
                if callable(delete_safe_fn):
                    _, failed_keys = await delete_safe_fn(sorted_keys)
                else:
                    for key in sorted_keys:
                        try:
                            await self._storage.delete_object(key)
                        except Exception:
                            failed_keys.append(key)

                if failed_keys:
                    self._auth.rollback()
                    logger.warning(
                        "Account erasure incomplete in storage [user_id=%s, failed_count=%d]",
                        user_id,
                        len(failed_keys),
                    )
                    raise ApiError(
                        status_code=503,
                        code="ERASURE_STORAGE_FAILURE",
                        message="Unable to erase all user media from storage. Please retry.",
                    )

        # Genlook customer erasure via official DELETE /customers/{externalUserId}
        # Only executed when Genlook is active (or injected in tests); mock mode makes zero calls.
        genlook_erased: bool | None = None
        if self._genlook_eraser is not None:
            try:
                res = self._genlook_eraser(user_id)
                if asyncio.iscoroutine(res):
                    res = await res
                genlook_erased = bool(res)
            except Exception as exc:
                self._auth.rollback()
                logger.warning(
                    "Account erasure external provider failure [user_id=%s, err=%s]",
                    user_id,
                    type(exc).__name__,
                )
                raise ApiError(
                    status_code=503,
                    code="ERASURE_EXTERNAL_FAILURE",
                    message="Unable to erase external try-on references right now. Please retry.",
                )
        else:
            from app.config.settings import get_settings

            settings = get_settings()
            if (
                getattr(settings, "tryon_provider", "mock") == "genlook"
                and getattr(settings, "genlook_api_key", None)
            ):
                from app.infrastructure.external.genlook_tryon import (
                    GENLOOK_DEFAULT_BASE_URL,
                    GenlookTryOnConfig,
                    GenlookTryOnProvider,
                )

                try:
                    g_config = GenlookTryOnConfig(
                        api_key=settings.genlook_api_key or "",
                        base_url=getattr(settings, "genlook_api_base_url", GENLOOK_DEFAULT_BASE_URL),
                        connect_timeout_s=getattr(settings, "genlook_connect_timeout_s", 10.0),
                        request_timeout_s=getattr(settings, "genlook_request_timeout_s", 30.0),
                        poll_interval_s=getattr(settings, "genlook_poll_interval_s", 1.0),
                        poll_timeout_s=getattr(settings, "genlook_poll_timeout_s", 120.0),
                        max_retries=getattr(settings, "genlook_max_retries", 2),
                        keep_for_days=getattr(settings, "genlook_keep_for_days", 1),
                        ai_label=getattr(settings, "genlook_ai_label", True),
                    )
                    g_provider = GenlookTryOnProvider(g_config)
                    genlook_erased = await asyncio.to_thread(
                        g_provider.delete_customer, str(user_id)
                    )
                except Exception as exc:
                    self._auth.rollback()
                    logger.warning(
                        "Account erasure Genlook deletion failed [user_id=%s, err=%s]",
                        user_id,
                        type(exc).__name__,
                    )
                    raise ApiError(
                        status_code=503,
                        code="ERASURE_EXTERNAL_FAILURE",
                        message="Unable to erase external try-on references right now. Please retry.",
                    )

        deleted = self._auth.delete_account(user_id=user_id)
        if not deleted:
            self._auth.rollback()
            raise not_found()
        self._auth.commit()

        if tryon_job_ids:
            try:
                from app.application.tryon import _BYTE_CACHE, _POLL_COUNTS

                for jid in tryon_job_ids:
                    _BYTE_CACHE.pop(str(jid), None)
                    _POLL_COUNTS.pop(str(jid), None)
            except Exception:
                pass

        logger.info(
            "Account erased [user_id=%s, media_objects=%d, genlook_erased=%s]",
            user_id,
            len(all_keys),
            genlook_erased,
        )
        return {
            "media_objects_deleted": len(all_keys),
            "genlook_erased": genlook_erased,
        }


def issue_session(
    auth: AuthRepository,
    *,
    account: AuthAccountRecord,
    secret: str,
    expires_in_s: int,
    now: Optional[datetime] = None,
) -> str:
    """Create one session row + mint its JWT (single transaction unit).

    The session id is generated here so the JWT `jti` and the row id
    are identical by construction; the row stores only the token
    digest, never the bearer token itself.
    """
    moment = now or datetime.now(timezone.utc)
    expires_at = moment + timedelta(seconds=int(expires_in_s))
    session_id = uuid4()
    token = mint_access_token(
        user_id=account.user_id,
        session_id=session_id,
        secret=secret,
        expires_in_s=int(expires_in_s),
        now=moment,
    )
    auth.create_session(
        session_id=session_id,
        user_id=account.user_id,
        token_digest=token_digest(token),
        expires_at=expires_at,
    )
    return token


def resolve_session(
    auth: AuthRepository,
    *,
    token: str,
    secret: str,
    now: Optional[datetime] = None,
) -> tuple[UUID, UUID]:
    """Verify a bearer token against signature, expiry, and session store.

    Returns (user_id, session_id). Raises `authentication_error()` on
    any malformed/expired/revoked/unknown token — the single
    verify→Principal seam behind `api/deps.py` (D-AUTH-1).
    """
    try:
        user_id, session_id = decode_access_token(token=token, secret=secret)
    except ValueError:
        raise authentication_error()
    row = auth.find_session(token_digest=token_digest(token))
    if row is None or row.user_id != user_id or row.id != session_id:
        raise authentication_error()
    moment = now or datetime.now(timezone.utc)
    if row.revoked_at is not None or row.expires_at <= moment:
        raise authentication_error()
    return user_id, session_id
