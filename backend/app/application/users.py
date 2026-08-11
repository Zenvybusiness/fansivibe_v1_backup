"""Application use cases — user/profile surface (M2, UC-6).

Each use case is a thin orchestration unit that composes the repository ports
and raises typed `ApiError`s on failure. Business rules live here, not in the
routers (BA-7).
"""

from __future__ import annotations

from uuid import UUID

from app.api.errors import not_found
from app.domain.ports.repositories import UserProfileRecord, UserStateRepository


class GetProfile:
    """UC-6 — `GET /v1/users/me`.

    Returns the caller's own profile projection (owner-only, OW-1). A valid
    token whose account/profile projection is gone resolves to `404` per
    `AUTH_API.md` §5.5 — never an existence oracle on another user.
    """

    def __init__(self, *, user_state: UserStateRepository) -> None:
        self._user_state = user_state

    def __call__(self, *, user_id: UUID) -> UserProfileRecord:
        record = self._user_state.get_profile(user_id=user_id)
        if record is None:
            raise not_found()
        return record
