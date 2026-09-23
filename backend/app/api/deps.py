"""Dependency seam — resolves a Bearer token to a ``user_id``.

D-AUTH-1 (real authentication): JWT access tokens minted by
`POST /v1/auth/register` / `/v1/auth/login` verify here against
signature, expiry, and the R51 session store (`user_sessions`) via
`application.auth.resolve_session` — the frozen
``verify_access_token(token) -> Principal`` seam. Owner-scoping (OW-1)
is fully enforced in the repositories regardless of which path
produced the id.

Dev fallback: the historical single dev token maps to the seeded dev
user ONLY when `FANSIVIBE_ALLOW_DEV_TOKEN` is true (tests/dev). It
defaults to false, so the shared bootstrap identity can never
silently become production identity.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import ApiError, authentication_error
from app.application.auth import resolve_session
from app.config.settings import get_settings
from app.infrastructure.db.models import UserState, Users
from app.infrastructure.db.repositories import AuthRepositorySQL
from app.infrastructure.db.session import get_db

DEV_TOKEN = get_settings().dev_token
_DEV_PROVIDER = "dev"
_DEV_SUBJECT = "dev-user"
_DEV_DISPLAY_NAME = "Dev User"


def _seeded_dev_user(session: Session) -> UUID:
    user = session.execute(
        select(Users).where(
            Users.auth_provider == _DEV_PROVIDER,
            Users.auth_subject == _DEV_SUBJECT,
        )
    ).scalar_one_or_none()
    if user is None:
        user = Users(
            auth_provider=_DEV_PROVIDER,
            auth_subject=_DEV_SUBJECT,
            display_name=_DEV_DISPLAY_NAME,
        )
        session.add(user)
        session.flush()
        session.add(UserState(user_id=user.id))
        session.commit()
    return user.id


def get_current_user_id(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> UUID:
    """Bearer-token → authenticated ``user_id`` (D-AUTH-1)."""
    if not authorization or not authorization.startswith("Bearer "):
        raise authentication_error()
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise authentication_error()
    settings = get_settings()
    try:
        user_id, _ = resolve_session(
            AuthRepositorySQL(db), token=token, secret=settings.auth_secret
        )
        return user_id
    except ApiError:
        pass
    if settings.allow_dev_token and token == DEV_TOKEN:
        try:
            return _seeded_dev_user(db)
        except Exception:
            raise ApiError(
                status_code=500,
                code="DATABASE_FAILURE",
                message="Something went wrong while saving your data. Please try again.",
            )
    raise authentication_error()


def get_fashion_reasoner():
    """Dependency provider for the fashion reasoning service (Phase 3AJ).

    Instantiates the OllamaFashionReasoner adapter configured from Settings,
    allowing tests and mocks to override via FastAPI's `app.dependency_overrides`.
    """
    from app.ai.ollama_reasoner import OllamaFashionReasoner, ReasoningConfig
    from app.config.settings import get_settings

    settings = get_settings()
    config = ReasoningConfig.from_env(
        base_url=settings.reasoning_host,
        model=settings.reasoning_model,
        timeout_s=settings.reasoning_timeout_s,
        temperature=settings.reasoning_temperature,
        max_retries=settings.reasoning_max_retries,
        keep_alive=settings.reasoning_keep_alive,
    )
    return OllamaFashionReasoner(config=config)


def get_lifecycle_manager():
    """Dependency provider for the Ollama lifecycle manager (Phase 3AL)."""
    from app.ai.lifecycle import OllamaLifecycleManager

    return OllamaLifecycleManager()
