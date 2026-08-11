"""Dependency seam — resolves a Bearer token to a ``user_id``.

**D-AUTH-1 placeholder (approved decision D1):** until a real auth provider
lands, a known dev token maps to a seeded dev user. Owner-scoping (OW-1) is
fully enforced in the repositories regardless of which seam produced the id;
when real auth arrives it swaps in behind this same dependency with no
contract change.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import ApiError, authentication_error
from app.config.settings import get_settings
from app.infrastructure.db.models import UserState, Users
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
    authorization: str | None,
    db: Session = Depends(get_db),
) -> UUID:
    """Bearer-token → dev user id (dev seam; D-AUTH-1 lands behind this)."""
    if not authorization or not authorization.startswith("Bearer "):
        raise authentication_error()
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise authentication_error()
    if token != DEV_TOKEN:
        raise authentication_error()
    try:
        return _seeded_dev_user(db)
    except Exception:
        raise ApiError(
            status_code=500,
            code="DATABASE_FAILURE",
            message="Something went wrong while saving your data. Please try again.",
        )
