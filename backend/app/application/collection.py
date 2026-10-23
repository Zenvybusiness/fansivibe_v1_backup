"""Discovery collection workflow (D3).

One bounded collection against one authorized source: create a run, page
the adapter, persist each verbatim raw payload with its deterministic hash,
normalize it, upsert the canonical product and write the source→product
mapping, then finish the run with truthful counters.

Canonical identity strategy (D4, conservative): a canonical product is keyed
by its source identity ``(source, source_product_id)`` through the unique
``product_source_map`` constraint. Re-observing a source identity updates
that product (``updated``). A listing whose valid GTIN already belongs to
another source's product is attached to that product (``verified``), never
merged on similar names. Products that only share brand/category are kept
separate and reported as a possible match (``possible``). See
``app.domain.services.product_identity`` for the full policy.

Status rule: per-record validation failures are counted (``failed``) and
the run still completes; a source-level failure (auth / rate limit /
transient / payload) or a database failure makes the run ``failed``. Errors
are sanitized to fixed messages — raw payloads, credentials and exception
text are never persisted or logged.

Real providers stay disabled: the CLI only wires the bundled fixture
adapter, and any other source is refused until authorized access exists.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from app.domain.ports.repositories import (
    DiscoveryRepository,
    MediaAttentionRepository,
    SearchInterestRepository,
)
from app.domain.ports.source_adapter import (
    RawSourceRecord,
    SourceAdapter,
    SourceDeadlineError,
    SourceError,
    SourcePayloadError,
    SourceRateLimitError,
    SourceTransientError,
)
from app.domain.services.media_attention import (
    COMPLETENESS_COMPLETE,
    COMPLETENESS_TRUNCATED,
    DEFAULT_CLUSTERING_VERSION,
    DEFAULT_QUERY_CONFIG_VERSION,
    DEFAULT_VALUE_SCALE,
    GEO_TYPE_COUNTRY,
    SOURCE_GDELT_DOC,
    STATUS_PRESENT,
    STATUS_SUPPRESSED,
    normalize_media_attention,
)
from app.domain.services.normalization import normalize_product, payload_hash
from app.domain.services.product_identity import (
    MATCH_POSSIBLE,
    MATCH_VERIFIED,
    IdentityDecision,
)
from app.domain.services.search_interest import normalize_search_interest
from app.infrastructure.external.gdelt_source import GdeltSliceResult

_MAX_ERROR_SUMMARY = 2000

# Sanitized, fixed summaries — an adapter's own message may contain
# credentials or payload fragments, so it is never copied into the run row.
_SAFE_SOURCE_ERRORS = {
    "SourceAuthError": "source authentication failed",
    "SourceRateLimitError": "source rate limit reached",
    "SourceTransientError": "source temporarily unavailable",
    "SourceDeadlineError": "cooperative deadline exceeded",
    "SourcePayloadError": "source returned an unusable payload",
}


@dataclass(frozen=True)
class CollectionConfig:
    """Bounds for one collection. ``max_records``/``max_pages`` keep the
    loop finite even if a source never signals the last page."""

    source: str
    batch_size: int = 50
    max_records: int = 200
    max_pages: int = 100


@dataclass(frozen=True)
class CollectionResult:
    run_id: UUID
    source: str
    status: str
    fetched: int
    inserted: int
    updated: int
    skipped: int
    failed: int
    error_summary: Optional[str]
    verified: int = 0
    possible: int = 0


def _safe_source_error(exc: SourceError) -> str:
    summary = _SAFE_SOURCE_ERRORS.get(type(exc).__name__, "source error")
    retry_after = getattr(exc, "retry_after_s", None)
    if retry_after is not None:
        summary = f"{summary} (retry_after_s={retry_after})"
    return summary[:_MAX_ERROR_SUMMARY]


class CollectSource:
    """Run one bounded collection for a single adapter."""

    def __init__(self, *, adapter: SourceAdapter, repository: DiscoveryRepository) -> None:
        self._adapter = adapter
        self._repo = repository

    def __call__(self, config: CollectionConfig) -> CollectionResult:
        adapter = self._adapter
        if config.source != adapter.source_id:
            raise ValueError(
                f"config source {config.source!r} does not match adapter "
                f"source {adapter.source_id!r}"
            )

        run_id = self._repo.start_run(source=adapter.source_id)
        fetched = inserted = updated = skipped = failed = 0
        verified = possible = 0
        continuation: Optional[str] = None
        pages = 0

        try:
            while fetched < config.max_records and pages < config.max_pages:
                limit = min(config.batch_size, config.max_records - fetched)
                batch = adapter.fetch_batch(continuation=continuation, limit=limit)
                if batch.source != adapter.source_id:
                    raise SourcePayloadError(
                        "adapter returned a batch for a different source"
                    )
                if not batch.records:
                    break
                for raw in batch.records:
                    if fetched >= config.max_records:
                        break
                    fetched += 1
                    outcome, match_status = self._process_record(run_id, raw)
                    if outcome == "inserted":
                        inserted += 1
                    elif outcome == "updated":
                        updated += 1
                    elif outcome == "skipped":
                        skipped += 1
                    else:
                        failed += 1
                    if match_status == MATCH_VERIFIED:
                        verified += 1
                    elif match_status == MATCH_POSSIBLE:
                        possible += 1
                pages += 1
                continuation = batch.continuation
                if continuation is None:
                    break
        except SourceError as exc:
            summary = _safe_source_error(exc)
            return self._finish(
                run_id, "failed", fetched, inserted, updated, skipped, failed, summary,
                verified, possible,
            )
        except SQLAlchemyError as exc:
            summary = f"database failure: {type(exc).__name__}"
            try:
                self._repo.rollback()
                self._finish(
                    run_id, "failed", fetched, inserted, updated, skipped, failed, summary,
                    verified, possible,
                )
            except SQLAlchemyError:
                raise exc
            return CollectionResult(
                run_id, adapter.source_id, "failed",
                fetched, inserted, updated, skipped, failed, summary,
                verified, possible,
            )

        summary = f"{failed} record(s) failed validation" if failed else None
        return self._finish(
            run_id, "completed", fetched, inserted, updated, skipped, failed, summary,
            verified, possible,
        )

    def _process_record(self, run_id: UUID, raw: RawSourceRecord) -> tuple[str, str]:
        adapter_source = self._adapter.source_id
        if raw.source != adapter_source:
            # A record claiming another source is a contract violation: it is
            # counted, not persisted under a source it does not belong to.
            return "failed", ""

        raw_id, created = self._repo.insert_raw_if_absent(
            run_id=run_id,
            source=adapter_source,
            source_record_id=raw.source_record_id,
            payload=raw.payload,
            payload_hash=payload_hash(raw.payload),
            source_timestamp=raw.source_timestamp,
        )
        if not created:
            # Duplicate observation: the raw payload was already ingested.
            return "skipped", ""

        result = normalize_product(raw)
        if not result.ok:
            self._repo.mark_raw(
                raw_id=raw_id,
                status="failed",
                error="; ".join(result.errors)[:_MAX_ERROR_SUMMARY],
            )
            return "failed", ""

        product = result.product
        assert product is not None  # result.ok guarantees it
        decision: IdentityDecision = self._repo.upsert_product(
            product=product,
            run_id=run_id,
            source=adapter_source,
            source_product_id=product.source_product_id,
            raw_id=raw_id,
            payload_hash=payload_hash(raw.payload),
        )
        self._repo.mark_raw(raw_id=raw_id, status="processed", error=None)
        # A verified/possible match creates no new product of its own; both
        # attach to or duplicate an existing canonical product respectively.
        if decision.creates_new_product:
            return "inserted", decision.match_status
        return "updated", decision.match_status

    def _finish(
        self,
        run_id: UUID,
        status: str,
        fetched: int,
        inserted: int,
        updated: int,
        skipped: int,
        failed: int,
        error_summary: Optional[str],
        verified: int,
        possible: int,
    ) -> CollectionResult:
        self._repo.finish_run(
            run_id=run_id,
            status=status,
            fetched=fetched,
            inserted=inserted,
            updated=updated,
            skipped=skipped,
            failed=failed,
            error_summary=error_summary,
        )
        return CollectionResult(
            run_id, self._adapter.source_id, status,
            fetched, inserted, updated, skipped, failed, error_summary,
            verified, possible,
        )


class CollectYouTubeVideos:
    """Run one bounded fashion-video collection for a single adapter."""

    def __init__(self, *, adapter: SourceAdapter, discovery: DiscoveryRepository) -> None:
        self._adapter = adapter
        self._discovery = discovery

    def __call__(self, config: CollectionConfig) -> CollectionResult:
        adapter = self._adapter
        if config.source != adapter.source_id:
            raise ValueError(
                f"config source {config.source!r} does not match adapter "
                f"source {adapter.source_id!r}"
            )

        run_id = self._discovery.start_run(source=adapter.source_id)
        fetched = inserted = updated = skipped = failed = 0
        continuation: Optional[str] = None
        pages = 0

        try:
            while fetched < config.max_records and pages < config.max_pages:
                limit = min(config.batch_size, config.max_records - fetched)
                batch = adapter.fetch_batch(continuation=continuation, limit=limit)
                if batch.source != adapter.source_id:
                    raise SourcePayloadError("adapter returned a batch for a different source")
                if not batch.records:
                    break
                for raw in batch.records:
                    if fetched >= config.max_records:
                        break
                    fetched += 1
                    outcome = self._process_record(run_id, raw)
                    if outcome == "inserted":
                        inserted += 1
                    elif outcome == "skipped":
                        skipped += 1
                    else:
                        failed += 1
                pages += 1
                continuation = batch.continuation
                if continuation is None:
                    break
        except SourceError as exc:
            summary = _safe_source_error(exc)
            return self._finish(run_id, "failed", fetched, inserted, updated, skipped, failed, summary)
        except SQLAlchemyError as exc:
            summary = f"database failure: {type(exc).__name__}"
            try:
                self._discovery.rollback()
                self._finish(run_id, "failed", fetched, inserted, updated, skipped, failed, summary)
            except SQLAlchemyError:
                raise exc
            return CollectionResult(
                run_id, adapter.source_id, "failed",
                fetched, inserted, updated, skipped, failed, summary,
            )

        summary = f"{failed} record(s) failed validation" if failed else None
        return self._finish(run_id, "completed", fetched, inserted, updated, skipped, failed, summary)

    def _process_record(self, run_id: UUID, raw: RawSourceRecord) -> str:
        adapter_source = self._adapter.source_id
        if raw.source != adapter_source:
            return "failed"

        raw_id, created = self._discovery.insert_raw_if_absent(
            run_id=run_id,
            source=adapter_source,
            source_record_id=raw.source_record_id,
            payload=raw.payload,
            payload_hash=payload_hash(raw.payload),
            source_timestamp=raw.source_timestamp,
        )
        if not created:
            return "skipped"

        self._discovery.mark_raw(raw_id=raw_id, status="processed", error=None)
        return "inserted"

    def _finish(
        self,
        run_id: UUID,
        status: str,
        fetched: int,
        inserted: int,
        updated: int,
        skipped: int,
        failed: int,
        error_summary: Optional[str],
    ) -> CollectionResult:
        self._discovery.finish_run(
            run_id=run_id,
            status=status,
            fetched=fetched,
            inserted=inserted,
            updated=updated,
            skipped=skipped,
            failed=failed,
            error_summary=error_summary,
        )
        return CollectionResult(
            run_id, self._adapter.source_id, status,
            fetched, inserted, updated, skipped, failed, error_summary,
        )



@dataclass(frozen=True)
class SearchInterestCollectionConfig:
    """Bounds for one search-interest collection (D9B)."""

    source: str
    batch_size: int = 50
    max_records: int = 200
    max_pages: int = 100


@dataclass(frozen=True)
class SearchInterestCollectionResult:
    run_id: UUID
    source: str
    status: str
    fetched: int
    inserted: int
    skipped: int
    failed: int
    error_summary: Optional[str]


class CollectSearchInterest:
    """Run one bounded search-interest collection for a single adapter (D9B).

    Reuses the existing run + verbatim raw-record bookkeeping
    (``DiscoveryRepository``) and only adds the observation write
    (``SearchInterestRepository``) — no duplicate collection or
    error-handling framework. Per-record failures complete the run with a
    truthful ``failed`` count; a source or database failure fails the run.
    Errors stay sanitized. The real provider is not wired here.
    """

    def __init__(
        self,
        *,
        adapter: SourceAdapter,
        discovery: DiscoveryRepository,
        observations: SearchInterestRepository,
    ) -> None:
        self._adapter = adapter
        self._discovery = discovery
        self._observations = observations

    def __call__(self, config: SearchInterestCollectionConfig) -> SearchInterestCollectionResult:
        adapter = self._adapter
        if config.source != adapter.source_id:
            raise ValueError(
                f"config source {config.source!r} does not match adapter "
                f"source {adapter.source_id!r}"
            )

        run_id = self._discovery.start_run(source=adapter.source_id)
        fetched = inserted = skipped = failed = 0
        continuation: Optional[str] = None
        pages = 0

        try:
            while fetched < config.max_records and pages < config.max_pages:
                limit = min(config.batch_size, config.max_records - fetched)
                batch = adapter.fetch_batch(continuation=continuation, limit=limit)
                if batch.source != adapter.source_id:
                    raise SourcePayloadError(
                        "adapter returned a batch for a different source"
                    )
                if not batch.records:
                    break
                for raw in batch.records:
                    if fetched >= config.max_records:
                        break
                    fetched += 1
                    outcome = self._process_record(run_id, raw)
                    if outcome == "inserted":
                        inserted += 1
                    elif outcome == "skipped":
                        skipped += 1
                    else:
                        failed += 1
                pages += 1
                continuation = batch.continuation
                if continuation is None:
                    break
        except SourceError as exc:
            summary = _safe_source_error(exc)
            return self._finish(run_id, "failed", fetched, inserted, skipped, failed, summary)
        except SQLAlchemyError as exc:
            summary = f"database failure: {type(exc).__name__}"
            try:
                self._discovery.rollback()
                self._finish(run_id, "failed", fetched, inserted, skipped, failed, summary)
            except SQLAlchemyError:
                raise exc
            return SearchInterestCollectionResult(
                run_id, adapter.source_id, "failed",
                fetched, inserted, skipped, failed, summary,
            )

        summary = f"{failed} record(s) failed validation" if failed else None
        return self._finish(run_id, "completed", fetched, inserted, skipped, failed, summary)

    def _process_record(self, run_id: UUID, raw: RawSourceRecord) -> str:
        adapter_source = self._adapter.source_id
        if raw.source != adapter_source:
            # A record claiming another source is a contract violation: it is
            # counted, never persisted under a source it does not belong to.
            return "failed"

        raw_id, created = self._discovery.insert_raw_if_absent(
            run_id=run_id,
            source=adapter_source,
            source_record_id=raw.source_record_id,
            payload=raw.payload,
            payload_hash=payload_hash(raw.payload),
            source_timestamp=raw.source_timestamp,
        )
        if not created:
            # Duplicate payload: already ingested under this source.
            return "skipped"

        result = normalize_search_interest(raw)
        if not result.ok:
            self._discovery.mark_raw(
                raw_id=raw_id,
                status="failed",
                error="; ".join(result.errors)[:_MAX_ERROR_SUMMARY],
            )
            return "failed"

        observation = result.observation
        assert observation is not None  # result.ok guarantees it
        _, observation_created = self._observations.insert_observation(
            observation=observation,
            run_id=run_id,
            raw_id=raw_id,
            payload_hash=payload_hash(raw.payload),
        )
        self._discovery.mark_raw(raw_id=raw_id, status="processed", error=None)
        # A new raw payload whose natural key already exists adds no new
        # observation, so a series is never inflated.
        return "inserted" if observation_created else "skipped"

    def _finish(
        self,
        run_id: UUID,
        status: str,
        fetched: int,
        inserted: int,
        skipped: int,
        failed: int,
        error_summary: Optional[str],
    ) -> SearchInterestCollectionResult:
        self._discovery.finish_run(
            run_id=run_id,
            status=status,
            fetched=fetched,
            inserted=inserted,
            updated=0,
            skipped=skipped,
            failed=failed,
            error_summary=error_summary,
        )
        return SearchInterestCollectionResult(
            run_id, self._adapter.source_id, status,
            fetched, inserted, skipped, failed, error_summary,
        )


@dataclass(frozen=True)
class MediaAttentionCollectionConfig:
    """Bounds and parameters for one media-attention collection run."""

    window_start: datetime
    window_end: datetime
    query_key: str = "streetwear"
    source: str = SOURCE_GDELT_DOC
    query_display: Optional[str] = None
    geo_scope: str = "IN"
    geo_scope_type: str = GEO_TYPE_COUNTRY
    aggregation_interval: str = "rolling_7d"
    query_config_version: str = DEFAULT_QUERY_CONFIG_VERSION
    clustering_version: str = DEFAULT_CLUSTERING_VERSION
    value_scale: str = DEFAULT_VALUE_SCALE
    max_depth: int = 5
    min_slice_duration: timedelta = timedelta(minutes=15)
    deadline: Optional[datetime] = None
    timeout_s: Optional[float] = None


@dataclass(frozen=True)
class MediaAttentionCollectionResult:
    """Outcome of one media-attention collection run."""

    run_id: UUID
    source: str
    status: str
    observation_id: Optional[UUID]
    value_status: Optional[str]
    completeness_status: Optional[str]
    value: Optional[float]
    fetched: int
    inserted: int
    skipped: int
    failed: int
    window_covered: bool
    error_summary: Optional[str]


def verify_window_coverage(
    intervals: Sequence[tuple[datetime, datetime]],
    window_start: datetime,
    window_end: datetime,
) -> bool:
    """Verify that a set of closed-open [start, end) intervals completely and
    contiguously covers the requested [window_start, window_end) without gaps.
    """
    if not intervals:
        return False
    sorted_ints = sorted(intervals, key=lambda iv: iv[0])
    curr_start, curr_end = sorted_ints[0]
    if curr_start > window_start:
        return False
    for s, e in sorted_ints[1:]:
        if s > curr_end:
            return False
        curr_end = max(curr_end, e)
    return curr_start <= window_start and curr_end >= window_end


class CollectMediaAttention:
    """Run one bounded media-attention collection with adaptive time slicing.

    Orchestrates collection across query and time slices from GDELT DOC API (or
    conforming adapter).

    Discipline & Invariants:
    - Adaptive time-slicing with recursive bisection on provider-cap truncation.
    - Recursion/depth limits prevent infinite subdivision.
    - Cooperative deadline enforcement throughout pacing and requests.
    - Full-window coverage is explicitly tracked.
    - An individual empty slice NEVER implies an empty complete window.
    - Publishes present/complete ONLY after every required slice succeeds
      and the entire requested window is covered.
    - When depth limit is reached on provider-capped slices, publishes
      suppressed/truncated observation with null metrics.
    - When transport, rate limit, timeout or deadline interruptions occur,
      never publishes present/complete.
    - Preserves query_config_version and clustering_version throughout.
    - Normalization and story clustering remain in the pure domain layer.
    """

    def __init__(
        self,
        *,
        adapter: GdeltSourceAdapter | SourceAdapter,
        discovery: DiscoveryRepository,
        observations: MediaAttentionRepository,
    ) -> None:
        self._adapter = adapter
        self._discovery = discovery
        self._observations = observations

    def __call__(
        self, config: MediaAttentionCollectionConfig
    ) -> MediaAttentionCollectionResult:
        adapter = self._adapter
        if config.source != adapter.source_id:
            raise ValueError(
                f"config source {config.source!r} does not match adapter "
                f"source {adapter.source_id!r}"
            )

        if config.window_end <= config.window_start:
            raise ValueError("window_end must be strictly after window_start")

        effective_deadline = config.deadline
        if effective_deadline is None and config.timeout_s is not None:
            effective_deadline = datetime.now(timezone.utc) + timedelta(
                seconds=config.timeout_s
            )

        run_id = self._discovery.start_run(source=adapter.source_id)
        fetched = inserted = skipped = failed = 0

        collected_records: list[RawSourceRecord] = []
        covered_slices: list[tuple[datetime, datetime]] = []
        cap_truncated = False
        truncated_slice: Optional[tuple[datetime, datetime]] = None

        query_display = config.query_display or config.query_key
        geo_filter = (
            f" sourcecountry:{config.geo_scope}"
            if config.geo_scope and config.geo_scope != "worldwide"
            else ""
        )
        query_str = f"{config.query_key}{geo_filter}"

        def _collect_slice(start: datetime, end: datetime, depth: int) -> bool:
            nonlocal cap_truncated, truncated_slice

            if (
                effective_deadline is not None
                and datetime.now(timezone.utc) >= effective_deadline
            ):
                raise SourceDeadlineError(
                    "cooperative deadline exceeded during collection"
                )

            if hasattr(adapter, "query_slice"):
                slice_res = adapter.query_slice(
                    query=query_str,
                    start_datetime=start,
                    end_datetime=end,
                    deadline=effective_deadline,
                )
            else:
                batch = adapter.fetch_batch(limit=250)
                slice_res = GdeltSliceResult(
                    slice_start=start,
                    slice_end=end,
                    records=batch.records,
                    is_capped=False,
                    articles_count=len(batch.records),
                    raw_payload={},
                )

            if not slice_res.is_capped:
                collected_records.extend(slice_res.records)
                covered_slices.append((start, end))
                return True

            duration = end - start
            if depth >= config.max_depth or duration <= config.min_slice_duration:
                cap_truncated = True
                truncated_slice = (start, end)
                return False

            mid = start + duration / 2
            if not _collect_slice(start, mid, depth + 1):
                return False
            if not _collect_slice(mid, end, depth + 1):
                return False
            return True

        try:
            slice_ok = _collect_slice(config.window_start, config.window_end, 0)
        except SourceDeadlineError:
            summary = "cooperative deadline interrupted collection"
            return self._finish_failure(run_id, summary)
        except SourceRateLimitError as exc:
            summary = _safe_source_error(exc)
            return self._finish_failure(run_id, summary)
        except SourceTransientError as exc:
            summary = _safe_source_error(exc)
            return self._finish_failure(run_id, summary)
        except SourcePayloadError as exc:
            summary = _safe_source_error(exc)
            return self._finish_failure(run_id, summary)
        except SourceError as exc:
            summary = _safe_source_error(exc)
            return self._finish_failure(run_id, summary)
        except SQLAlchemyError as exc:
            summary = f"database failure: {type(exc).__name__}"
            try:
                self._discovery.rollback()
                self._discovery.finish_run(
                    run_id=run_id,
                    status="failed",
                    fetched=0,
                    inserted=0,
                    updated=0,
                    skipped=0,
                    failed=0,
                    error_summary=summary,
                )
            except SQLAlchemyError:
                raise exc
            return MediaAttentionCollectionResult(
                run_id=run_id,
                source=adapter.source_id,
                status="failed",
                observation_id=None,
                value_status=None,
                completeness_status=None,
                value=None,
                fetched=0,
                inserted=0,
                skipped=0,
                failed=0,
                window_covered=False,
                error_summary=summary,
            )

        # Provider cap truncation at max depth
        if cap_truncated:
            summary = f"provider-cap truncation encountered on slice {truncated_slice}"
            norm_res = normalize_media_attention(
                records=(),
                period_start=config.window_start,
                period_end=config.window_end,
                query_key=config.query_key,
                query_display=query_display,
                geo_scope=config.geo_scope,
                geo_scope_type=config.geo_scope_type,
                aggregation_interval=config.aggregation_interval,
                value_status=STATUS_SUPPRESSED,
                completeness_status=COMPLETENESS_TRUNCATED,
                query_config_version=config.query_config_version,
                clustering_version=config.clustering_version,
                value_scale=config.value_scale,
            )
            assert norm_res.observation is not None
            obs_id, _ = self._observations.insert_observation_with_contributing_records(
                observation=norm_res.observation,
                run_id=run_id,
                contributing_records=(),
            )
            self._discovery.finish_run(
                run_id=run_id,
                status="completed",
                fetched=0,
                inserted=0,
                updated=0,
                skipped=0,
                failed=0,
                error_summary=summary,
            )
            return MediaAttentionCollectionResult(
                run_id=run_id,
                source=adapter.source_id,
                status="completed",
                observation_id=obs_id,
                value_status=STATUS_SUPPRESSED,
                completeness_status=COMPLETENESS_TRUNCATED,
                value=None,
                fetched=0,
                inserted=0,
                skipped=0,
                failed=0,
                window_covered=False,
                error_summary=summary,
            )

        # Check full window coverage
        window_covered = verify_window_coverage(
            covered_slices, config.window_start, config.window_end
        )
        if not window_covered or not slice_ok:
            summary = "requested window was not fully covered"
            return self._finish_failure(run_id, summary)

        # Full window is covered! Persist raw records and normalize
        records_for_norm: list[RawSourceRecord] = []
        for r in collected_records:
            fetched += 1
            raw_hash = payload_hash(r.payload)
            raw_id, created = self._discovery.insert_raw_if_absent(
                run_id=run_id,
                source=adapter.source_id,
                source_record_id=r.source_record_id,
                payload=r.payload,
                payload_hash=raw_hash,
                source_timestamp=r.source_timestamp,
            )
            if created:
                inserted += 1
            else:
                skipped += 1
            self._discovery.mark_raw(raw_id=raw_id, status="processed", error=None)
            records_for_norm.append(
                RawSourceRecord(
                    source=adapter.source_id,
                    payload=r.payload,
                    source_record_id=str(raw_id),
                    source_timestamp=r.source_timestamp,
                )
            )

        norm_res = normalize_media_attention(
            records=records_for_norm,
            period_start=config.window_start,
            period_end=config.window_end,
            query_key=config.query_key,
            query_display=query_display,
            geo_scope=config.geo_scope,
            geo_scope_type=config.geo_scope_type,
            aggregation_interval=config.aggregation_interval,
            value_status=STATUS_PRESENT,
            completeness_status=COMPLETENESS_COMPLETE,
            query_config_version=config.query_config_version,
            clustering_version=config.clustering_version,
            value_scale=config.value_scale,
        )

        if not norm_res.ok or norm_res.observation is None:
            failed_count = len(norm_res.errors)
            summary = "; ".join(norm_res.errors)[:_MAX_ERROR_SUMMARY]
            self._discovery.finish_run(
                run_id=run_id,
                status="failed",
                fetched=fetched,
                inserted=inserted,
                updated=0,
                skipped=skipped,
                failed=failed_count,
                error_summary=summary,
            )
            return MediaAttentionCollectionResult(
                run_id=run_id,
                source=adapter.source_id,
                status="failed",
                observation_id=None,
                value_status=None,
                completeness_status=None,
                value=None,
                fetched=fetched,
                inserted=inserted,
                skipped=skipped,
                failed=failed_count,
                window_covered=True,
                error_summary=summary,
            )

        obs_id, _ = self._observations.insert_observation_with_contributing_records(
            observation=norm_res.observation,
            run_id=run_id,
            contributing_records=norm_res.contributing_records,
        )

        self._discovery.finish_run(
            run_id=run_id,
            status="completed",
            fetched=fetched,
            inserted=inserted,
            updated=0,
            skipped=skipped,
            failed=0,
            error_summary=None,
        )

        return MediaAttentionCollectionResult(
            run_id=run_id,
            source=adapter.source_id,
            status="completed",
            observation_id=obs_id,
            value_status=STATUS_PRESENT,
            completeness_status=COMPLETENESS_COMPLETE,
            value=norm_res.observation.value,
            fetched=fetched,
            inserted=inserted,
            skipped=skipped,
            failed=0,
            window_covered=True,
            error_summary=None,
        )

    def _finish_failure(
        self,
        run_id: UUID,
        summary: str,
    ) -> MediaAttentionCollectionResult:
        self._discovery.finish_run(
            run_id=run_id,
            status="failed",
            fetched=0,
            inserted=0,
            updated=0,
            skipped=0,
            failed=0,
            error_summary=summary,
        )
        return MediaAttentionCollectionResult(
            run_id=run_id,
            source=self._adapter.source_id,
            status="failed",
            observation_id=None,
            value_status=None,
            completeness_status=None,
            value=None,
            fetched=0,
            inserted=0,
            skipped=0,
            failed=0,
            window_covered=False,
            error_summary=summary,
        )


def _source_registry() -> dict:
    """Bundled adapters, keyed by explicit source id.

    Deterministic fixture and catalog seed adapters ship for development and testing.
    Live providers (e.g. amazon_in, youtube_in) require configured credentials and will fail closed
    with SourceAuthError when unconfigured.
    """
    from app.infrastructure.external.amazon_source import AmazonProductAdapter
    from app.infrastructure.external.fashion_catalog_seed import FashionCatalogSeedAdapter
    from app.infrastructure.external.fixture_source import FixtureSourceAdapter
    from app.infrastructure.external.youtube_source import YouTubeSourceAdapter

    return {
        "fixture_catalog": FixtureSourceAdapter,
        "fashion_seed": FashionCatalogSeedAdapter,
        "amazon_in": AmazonProductAdapter,
        "youtube_in": YouTubeSourceAdapter,
    }


def main(argv: Optional[list[str]] = None) -> int:
    """Run one bounded collection: ``python -m app.application.collection``."""
    from app.infrastructure.db.repositories import DiscoveryRepositorySQL
    from app.infrastructure.db.session import SessionLocal

    parser = argparse.ArgumentParser(
        description="Run one bounded Discovery collection (D3). Fixture-only."
    )
    parser.add_argument("--source", default=None, help="explicit source id to collect")
    parser.add_argument(
        "--max-records", type=int, default=200, help="hard bound on records fetched"
    )
    parser.add_argument("--list-sources", action="store_true", help="list bundled sources")
    parser.add_argument(
        "--prune-expired",
        action="store_true",
        help="prune expired raw records for this source before collecting (YouTube retention)",
    )
    args = parser.parse_args(argv)

    registry = _source_registry()
    if args.list_sources:
        print("\n".join(sorted(registry)))
        return 0

    if args.source is None:
        parser.error("--source is required")

    factory = registry.get(args.source)
    if factory is None:
        print(
            f"source '{args.source}' is not configured; live sources require "
            "authorized credentials and are not bundled",
            file=sys.stderr,
        )
        return 2

    session = SessionLocal()
    try:
        repo = DiscoveryRepositorySQL(session)
        if args.prune_expired and args.source == "youtube_in":
            from app.application.youtube_retention import EnforceYouTubeRetention
            retention_service = EnforceYouTubeRetention(repo)
            ret_result = retention_service(source=args.source)
            print(
                f"[retention] pruned {ret_result.pruned_count} expired record(s) "
                f"for {args.source}"
            )
        if args.source == "youtube_in":
            service = CollectYouTubeVideos(
                adapter=factory(), discovery=repo
            )
        else:
            service = CollectSource(
                adapter=factory(), repository=repo
            )
        result = service(
            CollectionConfig(source=args.source, max_records=args.max_records)
        )
    finally:
        session.close()

    print(
        f"run {result.run_id} [{result.source}] status={result.status} "
        f"fetched={result.fetched} inserted={result.inserted} "
        f"updated={result.updated} skipped={result.skipped} failed={result.failed} "
        f"verified={result.verified} possible={result.possible}"
    )
    if result.error_summary:
        print(f"error_summary: {result.error_summary}", file=sys.stderr)
    return 0 if result.status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
