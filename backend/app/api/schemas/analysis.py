"""Wire schemas for the analysis surface (endpoints #37/#39/#40/#44).

Shapes mirror `FANSIVIBE_API_CONTRACT_V1.md` §4.2/§6.6 and
`HAIRSTYLE_RECOMMENDATION_API.md` §4.2/§4.3. `AnalysisRun` is bare (no
envelope); the list endpoint returns summary rows with no `result`/`error`.

Grooming creation endpoint #38 takes no request body (Phase 28: obsolete
`face_profile_ref` removed — the authenticated user's `style_profile` is
resolved by `user_id`). The Flutter client still posts empty JSON `{}` to
preserve the JSON transport.
Outfit creation endpoint #44 uses multipart form data (S-1).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel


class AsyncAccepted(BaseModel):
    """202 response for async analysis submissions."""

    run_id: UUID


class AnalysisRun(BaseModel):
    run_id: UUID
    run_type: str
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    engine_version: Optional[str] = None
    knowledge_version: Optional[str] = None
    input_media: Optional[dict[str, Any]] = None
    result: Optional[dict[str, Any]] = None
    error: Optional[dict[str, Any]] = None


class AnalysisRunSummary(BaseModel):
    """List-row summary — no `result`, no `error` (PR-5, no history detail)."""

    run_id: UUID
    run_type: str
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    engine_version: Optional[str] = None
    knowledge_version: Optional[str] = None
    input_media: Optional[dict[str, Any]] = None


class AnalysisRunList(BaseModel):
    items: list[AnalysisRunSummary]
    page: int
    page_size: int
    total: int


class CreateOutfitScanRequest(BaseModel):
    """Multipart request body for outfit scan creation endpoint #44 (S-1).

    Image-only pass (S-1); no face-profile reference exists.
    """

    image: Optional[dict[str, Any]] = None


class CreateHairstyleScanRequest(BaseModel):
    """Multipart request body for hairstyle scan creation endpoint #43 (S-2).

    Either `image` (image-based pass) or the profile-only pass over the
    authenticated user's stored `style_profile` (no face-profile reference).
    """

    image: Optional[dict[str, Any]] = None


class EphemeralGroomingProfile(BaseModel):
    """Request-supplied appearance profile for ephemeral grooming (D-01).

    Guests own no stored `style_profile`, so every attribute arrives in
    the request. `face_shape` is required (no server-side default is ever
    invented); the remaining attributes default to empty (sparse grounding
    the engine reports honestly via `needs_more_data`).
    """

    face_shape: str
    skin_tone: str = ""
    body_type: str = ""
    style_type: str = ""


class CreateGroomingRunRequest(BaseModel):
    """Request payload for authenticated grooming analysis (endpoint #38).

    Allows users to provide manual grooming preferences (face shape, beard style,
    density, color) which are used for grounding the recommendation.
    Backward-compatible: all fields optional; empty `{}` accepted.
    """

    face_shape: Optional[str] = None
    faceShape: Optional[str] = None
    beard_style: Optional[str] = None
    beardStyle: Optional[str] = None
    beard_density: Optional[str] = None
    beardDensity: Optional[str] = None
    beard_color: Optional[str] = None
    beardColor: Optional[str] = None
    skin_tone: Optional[str] = None
    skinTone: Optional[str] = None
    body_type: Optional[str] = None
    bodyType: Optional[str] = None
    style_type: Optional[str] = None
    styleType: Optional[str] = None

    @property
    def resolved_face_shape(self) -> str:
        return (self.face_shape or self.faceShape or "").strip()

    @property
    def resolved_beard_style(self) -> str:
        return (self.beard_style or self.beardStyle or "").strip()

    @property
    def resolved_beard_density(self) -> str:
        return (self.beard_density or self.beardDensity or "").strip()

    @property
    def resolved_beard_color(self) -> str:
        return (self.beard_color or self.beardColor or "").strip()

    @property
    def resolved_skin_tone(self) -> str:
        return (self.skin_tone or self.skinTone or "").strip()

    @property
    def resolved_body_type(self) -> str:
        return (self.body_type or self.bodyType or "").strip()

    @property
    def resolved_style_type(self) -> str:
        return (self.style_type or self.styleType or "").strip()