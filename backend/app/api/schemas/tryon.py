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
