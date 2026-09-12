"""Wire schemas for the auth surface (D-AUTH-1, M1, endpoints #02–05).

Shapes mirror `docs/api/AUTH_API.md` §5.1–§5.4: `RegisterRequest`,
`LoginRequest`, `SocialSignInRequest` in; `AuthResponse`
(`accessToken`/`tokenType`/`expiresIn` + the caller's `ProfileView`)
out. Keys are camelCase per API-19; field validation lives in the
application use cases (server-side, AUTH_API §6) so malformed bodies
surface as the frozen 422 shape — these models only enforce presence
and JSON types.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel

from app.api.schemas.users import ProfileView


class RegisterRequest(BaseModel):
    email: Any
    password: Any
    displayName: Optional[Any] = None


class LoginRequest(BaseModel):
    email: Any
    password: Any


class SocialSignInRequest(BaseModel):
    provider: Any
    providerToken: Any


class AuthResponse(BaseModel):
    accessToken: str
    tokenType: Literal["bearer"] = "bearer"
    expiresIn: int
    profile: ProfileView
