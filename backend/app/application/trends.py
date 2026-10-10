"""Application use case — compute Discovery trend candidates (D6).

Thin orchestration over the pure engine in ``app.domain.services.trends``:
load the observation window from the repository, then compute. It is strictly
read-only (no writes, no migration), takes no clock and no network, and never
uses Qwen / MediaPipe / an LLM. No API endpoint is added: M14 Trending and the
Flutter Trending screen are untouched, and the engine is exercised directly by
tests and any future internal caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.ports.repositories import TrendRepository
from app.domain.services.trends import TrendAnalysis, compute_trend_candidates


@dataclass(frozen=True)
class TrendConfig:
    """The half-open observation window ``[window_start, window_end)``."""

    window_start: datetime
    window_end: datetime


class AnalyzeTrends:
    """Compute trend candidates for one window from historical observations."""

    def __init__(self, *, repository: TrendRepository) -> None:
        self._repository = repository

    def __call__(self, config: TrendConfig) -> TrendAnalysis:
        evidence = self._repository.observations_in_window(
            window_start=config.window_start, window_end=config.window_end
        )
        return compute_trend_candidates(
            evidence,
            window_start=config.window_start,
            window_end=config.window_end,
        )
