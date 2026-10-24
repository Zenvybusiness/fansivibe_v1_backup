"""Media-attention observation aggregation service for fashion video signals (TRENDING-02).

Aggregates normalized video observations over rolling time windows into evidence-backed
fashion-attention signals.

Truthfulness & Evidence Boundary Invariants:
- Media/creator attention only: Video upload counts, creator coverage, velocity,
  and engagement describe creator attention and content velocity. They must NEVER
  be treated as search interest, catalog inventory, or consumer checkout demand.
- Baseline requirements: Growth / acceleration is NEVER computed across empty
  earlier periods (zero baseline returns ``upload_growth = None``).
- Transparent metric states: Distinguishes genuine zero values (e.g. 0 likes reported)
  from absent metrics (statistics omitted by provider -> ``None``).
- Deduplication: Identical videos observed repeatedly are deduplicated by ``video_id``
  to prevent artificial inflation from repeated collection runs.
- Deterministic: Pure Python, zero external calls, zero database access, and no clock
  inside the aggregation (caller provides window bounds).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from app.domain.services.fashion_concept_extraction import ExtractedVideoConcept

# Volume and quality heuristics (transparent, auditable heuristics)
VOLUME_TARGET = 10          # distinct videos for full volume credit
CHANNEL_TARGET = 2         # distinct channels for full coverage credit
FRESH_HOURS = 48.0         # age at or below which observation is fully fresh
STALE_HOURS = 168.0        # age at or above which freshness credit is zero
MIN_VIDEOS = 3             # minimum distinct videos to establish an admission baseline
GROWTH_RISING = 0.10       # upload velocity growth above 10% reads as rising
GROWTH_DECLINING = -0.10   # upload velocity drop below -10% reads as declining
MIN_PUBLISH_CONFIDENCE = 0.6

# Lifecycle stages
STAGE_INSUFFICIENT = "insufficient_evidence"
STAGE_RISING = "rising"
STAGE_FLAT = "plateau"
STAGE_DECLINING = "declining"

# Audit reasons
REASON_ZERO_BASELINE = "no distinct videos in the earlier window half (zero baseline)"
REASON_TOO_FEW_VIDEOS = "fewer than the minimum video observations for a stable comparison"
REASON_LOW_CONFIDENCE = "data-quality confidence below the publication threshold"
REASON_MEDIA_ATTENTION_ONLY = (
    "media attention signals describe creator upload activity and content velocity, "
    "never consumer demand or verified sales"
)


@dataclass(frozen=True)
class FashionVideoTrendSignal:
    """Aggregated media-attention signal for one fashion concept across a window."""

    concept_id: str
    canonical_name: str
    category: str
    window_start: datetime
    window_end: datetime
    distinct_videos: int
    distinct_channels: int
    upload_velocity_per_week: float
    upload_growth: Optional[float]
    total_views: Optional[int]
    total_likes: Optional[int]
    total_comments: Optional[int]
    first_published_at: datetime
    last_published_at: datetime
    confidence: float
    strength: Optional[float]
    stage: str
    publishable: bool
    reasons: tuple[str, ...]
    contributing_video_ids: tuple[str, ...]
    sample_videos: tuple[dict[str, Any], ...] = field(default_factory=tuple)


def aggregate_video_observations(
    observations: Sequence[ExtractedVideoConcept],
    *,
    window_start: datetime,
    window_end: datetime,
) -> tuple[FashionVideoTrendSignal, ...]:
    """Aggregate video concept observations over a half-open window [window_start, window_end).

    Handles deduplication, missing metrics, late-arriving records, zero baselines,
    and equal-window normalization deterministically.
    """
    if window_end <= window_start:
        raise ValueError("window_end must be strictly after window_start")

    # Filter observations to those published within the half-open window
    valid_obs: list[ExtractedVideoConcept] = [
        o for o in observations
        if window_start <= o.published_at < window_end
    ]

    # Group by concept_id
    grouped: dict[str, list[ExtractedVideoConcept]] = {}
    for o in valid_obs:
        grouped.setdefault(o.concept_id, []).append(o)

    signals: list[FashionVideoTrendSignal] = []

    for concept_id in sorted(grouped):
        concept_obs = grouped[concept_id]

        # 1. Deduplicate by video_id (preferring observations with statistics if available)
        deduped_by_id: dict[str, ExtractedVideoConcept] = {}
        for o in concept_obs:
            vid = o.video_id
            if vid not in deduped_by_id:
                deduped_by_id[vid] = o
            else:
                existing = deduped_by_id[vid]
                # If new observation has statistics while existing lacks them, or has higher stats or later timestamp, update
                if (
                    (existing.view_count is None and o.view_count is not None)
                    or (o.view_count is not None and existing.view_count is not None and o.view_count >= existing.view_count)
                    or o.published_at > existing.published_at
                ):
                    deduped_by_id[vid] = o

        unique_videos = sorted(deduped_by_id.values(), key=lambda v: (v.published_at, v.video_id))
        distinct_videos_count = len(unique_videos)
        if distinct_videos_count == 0:
            continue

        distinct_channels_set = {v.channel_id or v.channel_title for v in unique_videos if (v.channel_id or v.channel_title)}
        distinct_channels_count = len(distinct_channels_set) if distinct_channels_set else 1

        # 2. Window normalization and midpoint comparison (equal halves)
        midpoint = window_start + (window_end - window_start) / 2
        first_half = [v for v in unique_videos if v.published_at < midpoint]
        second_half = [v for v in unique_videos if v.published_at >= midpoint]

        first_half_ids = {v.video_id for v in first_half}
        second_half_ids = {v.video_id for v in second_half}

        upload_growth: Optional[float] = None
        if len(first_half_ids) > 0:
            upload_growth = (len(second_half_ids) - len(first_half_ids)) / len(first_half_ids)

        window_duration_days = max(0.1, (window_end - window_start).total_seconds() / 86400.0)
        upload_velocity_per_week = round(distinct_videos_count * (7.0 / window_duration_days), 4)

        # 3. Transparent metric accumulation (missing vs genuine 0)
        view_counts = [v.view_count for v in unique_videos if v.view_count is not None]
        total_views = sum(view_counts) if view_counts else None

        like_counts = [v.like_count for v in unique_videos if v.like_count is not None]
        total_likes = sum(like_counts) if like_counts else None

        comment_counts = [v.comment_count for v in unique_videos if v.comment_count is not None]
        total_comments = sum(comment_counts) if comment_counts else None

        first_published_at = unique_videos[0].published_at
        last_published_at = unique_videos[-1].published_at

        # 4. Data-quality confidence heuristic
        age_hours = max(0.0, (window_end - last_published_at).total_seconds() / 3600.0)
        volume_credit = min(1.0, distinct_videos_count / VOLUME_TARGET)
        coverage_credit = min(1.0, distinct_channels_count / CHANNEL_TARGET)

        if age_hours <= FRESH_HOURS:
            freshness_credit = 1.0
        elif age_hours >= STALE_HOURS:
            freshness_credit = 0.0
        else:
            freshness_credit = 1.0 - (age_hours - FRESH_HOURS) / (STALE_HOURS - FRESH_HOURS)

        confidence = round(0.4 * volume_credit + 0.3 * coverage_credit + 0.3 * freshness_credit, 4)

        # 5. Stage classification and documented audit reasons
        reasons: list[str] = [REASON_MEDIA_ATTENTION_ONLY]

        if upload_growth is None:
            reasons.append(REASON_ZERO_BASELINE)
        if distinct_videos_count < MIN_VIDEOS:
            reasons.append(REASON_TOO_FEW_VIDEOS)
        if confidence < MIN_PUBLISH_CONFIDENCE:
            reasons.append(REASON_LOW_CONFIDENCE)

        if distinct_videos_count < MIN_VIDEOS or upload_growth is None:
            stage = STAGE_INSUFFICIENT
        elif upload_growth > GROWTH_RISING:
            stage = STAGE_RISING
        elif upload_growth < GROWTH_DECLINING:
            stage = STAGE_DECLINING
        else:
            stage = STAGE_FLAT

        publishable = (stage != STAGE_INSUFFICIENT and confidence >= MIN_PUBLISH_CONFIDENCE)

        sample_videos = tuple(
            {
                "videoId": v.video_id,
                "title": v.matched_text,
                "channelTitle": v.channel_title,
                "videoUrl": v.video_url,
                "publishedAt": v.published_at.isoformat(),
                "viewCount": v.view_count,
            }
            for v in unique_videos[:5]
        )

        first_item = concept_obs[0]
        signals.append(
            FashionVideoTrendSignal(
                concept_id=concept_id,
                canonical_name=first_item.canonical_name,
                category=first_item.category,
                window_start=window_start,
                window_end=window_end,
                distinct_videos=distinct_videos_count,
                distinct_channels=distinct_channels_count,
                upload_velocity_per_week=upload_velocity_per_week,
                upload_growth=upload_growth,
                total_views=total_views,
                total_likes=total_likes,
                total_comments=total_comments,
                first_published_at=first_published_at,
                last_published_at=last_published_at,
                confidence=confidence,
                strength=upload_growth,
                stage=stage,
                publishable=publishable,
                reasons=tuple(reasons),
                contributing_video_ids=tuple(sorted(deduped_by_id.keys())),
                sample_videos=sample_videos,
            )
        )

    return tuple(signals)
