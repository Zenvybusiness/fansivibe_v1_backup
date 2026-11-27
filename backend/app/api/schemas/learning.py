"""Wire schemas for the learning summary surface (#34, M10-B).

Shapes mirror `FEEDBACK_LEARNING_API.md` §4.4 / DEC-021: `LearningSummary`
carries exactly four top-level fields; `breakdown` is the frozen object
(`base`, `wardrobePoints`, `savedPoints`, `total`) — no additional M10 v1
fields. `recentSignals` holds server-owned signal `label` strings only.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

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


class WeeklyProgressItem(BaseModel):
    weekStart: date
    weekEnd: date
    timezone: str
    styleScore: int = Field(ge=60, le=100)
    breakdown: LearningBreakdown
    styledDaysCount: int = Field(ge=0, le=7)
    signalsCount: int = Field(ge=0)
    isCurrent: bool
    personalRank: int = Field(ge=1)
    recordedAt: Optional[datetime] = None
    aggregationPolicy: str


class StyleJourneyComparisonSchema(BaseModel):
    scoreDelta: Optional[int] = None
    trend: Optional[Literal["up", "down", "flat"]] = None
    currentWeekRank: int = Field(ge=1)
    totalRankedWeeks: int = Field(ge=1)
    isTiedWithBest: bool


class StyleJourneyHistoryResponse(BaseModel):
    timezone: str
    aggregationPolicy: str
    currentWeek: WeeklyProgressItem
    previousWeek: Optional[WeeklyProgressItem] = None
    bestHistoricalWeek: Optional[WeeklyProgressItem] = None
    comparison: StyleJourneyComparisonSchema
    weeks: list[WeeklyProgressItem]
    hasHistory: bool


class RecordWeeklySnapshotRequest(BaseModel):
    weekStart: Optional[date] = None
    timezone: Optional[str] = None


class WeeklySnapshotResponse(BaseModel):
    snapshot: WeeklyProgressItem
    created: bool
