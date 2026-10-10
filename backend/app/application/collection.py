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
from typing import Optional
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from app.domain.ports.repositories import DiscoveryRepository, SearchInterestRepository
from app.domain.ports.source_adapter import (
    RawSourceRecord,
    SourceAdapter,
    SourceError,
    SourcePayloadError,
)
from app.domain.services.normalization import normalize_product, payload_hash
from app.domain.services.product_identity import (
    MATCH_POSSIBLE,
    MATCH_VERIFIED,
    IdentityDecision,
)
from app.domain.services.search_interest import normalize_search_interest

_MAX_ERROR_SUMMARY = 2000

# Sanitized, fixed summaries — an adapter's own message may contain
# credentials or payload fragments, so it is never copied into the run row.
_SAFE_SOURCE_ERRORS = {
    "SourceAuthError": "source authentication failed",
    "SourceRateLimitError": "source rate limit reached",
    "SourceTransientError": "source temporarily unavailable",
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


def _source_registry() -> dict:
    """Bundled adapters, keyed by explicit source id.

    Only the deterministic fixture adapter ships in this phase. Live
    providers are deliberately absent — they require approved access and
    configured credentials, so an unknown source is refused, never guessed.
    """
    from app.infrastructure.external.fixture_source import FixtureSourceAdapter

    return {"fixture_catalog": FixtureSourceAdapter}


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
        service = CollectSource(
            adapter=factory(), repository=DiscoveryRepositorySQL(session)
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
