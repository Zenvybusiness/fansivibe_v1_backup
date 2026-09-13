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