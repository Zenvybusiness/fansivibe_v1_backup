"""Wire schemas for the learning summary surface (#34, M10-B).

Shapes mirror `FEEDBACK_LEARNING_API.md` §4.4 / DEC-021: `LearningSummary`
carries exactly four top-level fields; `breakdown` is the frozen object
(`base`, `wardrobePoints`, `savedPoints`, `total`) — no additional M10 v1
fields. `recentSignals` holds server-owned signal `label` strings only.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LearningBreakdown(BaseModel):
    base: int = Field(ge=60, le=60)
    wardrobePoints: int = Field(ge=0, le=20)
    savedPoints: int = Field(ge=0, le=20)
    total: int = Field(ge=60, le=100)


class LearningSummary(BaseModel):
    styleScore: int = Field(ge=60, le=100)
    breakdown: LearningBreakdown
    streak: int = Field(ge=0)
    recentSignals: list[str]
