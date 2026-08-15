"""Wire schemas for the user/profile surface (endpoint #06, `GET /v1/users/me`).

Shapes mirror `FANSIVIBE_API_CONTRACT_V1.md` §6.2 and `AUTH_API.md` §5.5.
`ProfileView` is bare (no envelope). `preferences`/`settings`/`flags` are
sparse JSONB containers, passed through as stored (camelCase keys per API-19);
`styleProfile` is the frozen `StyleProfile` value with analysis-derived fields
mapped from the stored snake_case projection.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class StyleProfile(BaseModel):
    faceShape: Optional[str] = None
    skinTone: Optional[str] = None
    bodyType: Optional[str] = None
    styleType: Optional[str] = None
    sourceRunId: Optional[str] = None


class ProfileView(BaseModel):
    displayName: str
    styleProfile: StyleProfile
    preferences: dict[str, Any]
    settings: dict[str, Any]
    flags: dict[str, Any]
    version: int
    memorySummary: Optional[dict[str, Any]] = None
