"""Wire schemas for the analysis surface (endpoints #37/#39/#40/#44).

Shapes mirror `FANSIVIBE_API_CONTRACT_V1.md` §4.2/§6.6 and
`HAIRSTYLE_RECOMMENDATION_API.md` §4.2/§4.3. `AnalysisRun` is bare (no
envelope); the list endpoint returns summary rows with no `result`/`error`.

Grooming creation endpoint #38 uses a JSON request body (G1).
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


class CreateGroomingRunRequest(BaseModel):
    """JSON request body for grooming creation endpoint #38 (G1)."""

    face_profile_ref: str


class CreateOutfitScanRequest(BaseModel):
    """Multipart request body for outfit scan creation endpoint #44 (S-1).

    Exactly one of `image` or `faceProfileRef` must be provided; both present
    is a validation error per catalog §12.11.
    """

    image: Optional[dict[str, Any]] = None
    faceProfileRef: Optional[str] = None


class CreateHairstyleScanRequest(BaseModel):
    """Multipart request body for hairstyle scan creation endpoint #43 (S-2).

    Either `image` (image-based pass) or `faceProfileRef` (profile-only pass)
    must be provided, but not both per catalog §12.11.
    """

    image: Optional[dict[str, Any]] = None
    faceProfileRef: Optional[str] = None