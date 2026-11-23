"""Stage F0 mock try-on wire schemas (typed, additive-only)."""

from __future__ import annotations

from pydantic import BaseModel


class TryOnJobSubmitted(BaseModel):
    job_id: str
    status: str
    is_mock: bool = True


class TryOnJobStatus(BaseModel):
    job_id: str
    status: str
    progress: int
    is_mock: bool = True
    outfit_source: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    retry_count: int = 0
    created_at: str | None = None
    completed_at: str | None = None
    garment_ids: list[str] = []
    result_media_ref: dict | None = None

