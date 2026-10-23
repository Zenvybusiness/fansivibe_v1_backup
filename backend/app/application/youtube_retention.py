"""YouTube Data API v3 retention compliance enforcement service (TRENDING-03A).

Enforces data retention compliance in accordance with YouTube API Services Developer Policies
Section III.E.4:
- Policy Limit: API Clients are prohibited from storing API data for more than 30 calendar days
  unless refreshed.
- Scope: Deletes stored verbatim API data from ``raw_source_records`` strictly where
  ``source == 'youtube_in'`` and the record retrieval time (``fetched_at``) exceeds the policy
  retention deadline (default: 30 calendar days).
- Invariants & Safety:
  * Strictly source-scoped: Never touches or prunes GDELT (``gdelt_doc_20``), Amazon (``amazon_in``),
    catalog seed (``fashion_seed``), or development fixture (``fixture_catalog``) data.
  * Idempotent: Repeated execution on a clean dataset returns 0 deleted records with no errors.
  * Bounded: Executes in discrete batches of bounded size (default: 500 records per transaction)
    with a configurable maximum batch cap (default: 100 batches) to prevent table locks,
    memory exhaustion, or runaway transactions.
  * Cascading safety: Deleting raw source records cleanly cascades to referencing junction tables
    (``ON DELETE CASCADE`` / ``ON DELETE SET NULL``) without corrupting observation history.
  * Deterministic & auditable: Emits structured telemetry logs with counts, timestamps, and status.
  * Operational enforcement: Provides a standalone CLI entrypoint for crontab, systemd timer,
    or Kubernetes CronJob execution.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
import sys
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError

from app.domain.ports.repositories import DiscoveryRepository

logger = logging.getLogger("fansivibe.youtube_retention")

DEFAULT_YOUTUBE_SOURCE = "youtube_in"
DEFAULT_RETENTION_DAYS = 30  # YouTube Developer Policies Section III.E.4 limit
DEFAULT_BATCH_SIZE = 500
DEFAULT_MAX_BATCHES = 100


@dataclass(frozen=True)
class RetentionCleanupResult:
    """Outcome of one bounded retention cleanup invocation."""

    source: str
    cutoff: datetime
    max_age_days: int
    dry_run: bool
    expired_count: int
    pruned_count: int
    batches_executed: int
    status: str  # "completed", "failed", "dry_run"
    error_summary: Optional[str] = None


class EnforceYouTubeRetention:
    """Use case to enforce YouTube Data API retention policy on raw records."""

    def __init__(self, repository: DiscoveryRepository) -> None:
        self._repo = repository

    def __call__(
        self,
        *,
        source: str = DEFAULT_YOUTUBE_SOURCE,
        max_age_days: int = DEFAULT_RETENTION_DAYS,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_batches: int = DEFAULT_MAX_BATCHES,
        now: Optional[datetime] = None,
        dry_run: bool = False,
    ) -> RetentionCleanupResult:
        """Execute bounded, idempotent retention pruning for the specified source.

        Args:
            source: Source identifier to prune (defaults to "youtube_in").
            max_age_days: Retention horizon in calendar days (must be between 1 and 30).
            batch_size: Max rows to delete in a single database transaction.
            max_batches: Max batch iterations per invocation.
            now: Reference timestamp (defaults to current UTC time).
            dry_run: If True, counts expired records without deleting them.
        """
        if max_age_days < 1 or max_age_days > DEFAULT_RETENTION_DAYS:
            raise ValueError(
                f"max_age_days must be between 1 and {DEFAULT_RETENTION_DAYS} "
                f"(YouTube Developer Policies Section III.E.4 limit: <= 30 calendar days), "
                f"got {max_age_days}"
            )
        if batch_size < 1:
            raise ValueError(f"batch_size must be >= 1, got {batch_size}")
        if max_batches < 1:
            raise ValueError(f"max_batches must be >= 1, got {max_batches}")

        ref_time = now or datetime.now(timezone.utc)
        cutoff = ref_time - timedelta(days=max_age_days)

        if dry_run:
            try:
                expired = self._repo.count_expired_source_records(
                    source=source,
                    older_than=cutoff,
                )
                logger.info(
                    "YouTube retention dry-run: %d record(s) older than %s for source '%s'",
                    expired,
                    cutoff.isoformat(),
                    source,
                )
                return RetentionCleanupResult(
                    source=source,
                    cutoff=cutoff,
                    max_age_days=max_age_days,
                    dry_run=True,
                    expired_count=expired,
                    pruned_count=0,
                    batches_executed=0,
                    status="dry_run",
                )
            except SQLAlchemyError as exc:
                logger.error("YouTube retention dry-run database error: %s", exc)
                return RetentionCleanupResult(
                    source=source,
                    cutoff=cutoff,
                    max_age_days=max_age_days,
                    dry_run=True,
                    expired_count=0,
                    pruned_count=0,
                    batches_executed=0,
                    status="failed",
                    error_summary=f"database failure: {type(exc).__name__}",
                )

        total_pruned = 0
        batches = 0

        try:
            for _ in range(max_batches):
                pruned = self._repo.prune_expired_source_records(
                    source=source,
                    older_than=cutoff,
                    batch_limit=batch_size,
                )
                batches += 1
                total_pruned += pruned
                if pruned < batch_size:
                    # Cleaned all remaining expired records
                    break

            logger.info(
                "YouTube retention completed: %d record(s) pruned in %d batch(es) "
                "for source '%s' (cutoff: %s)",
                total_pruned,
                batches,
                source,
                cutoff.isoformat(),
            )
            return RetentionCleanupResult(
                source=source,
                cutoff=cutoff,
                max_age_days=max_age_days,
                dry_run=False,
                expired_count=total_pruned,
                pruned_count=total_pruned,
                batches_executed=batches,
                status="completed",
            )
        except SQLAlchemyError as exc:
            try:
                self._repo.rollback()
            except SQLAlchemyError:
                pass
            error_summary = f"database failure: {type(exc).__name__}"
            logger.error("YouTube retention enforcement failed: %s", error_summary)
            return RetentionCleanupResult(
                source=source,
                cutoff=cutoff,
                max_age_days=max_age_days,
                dry_run=False,
                expired_count=total_pruned,
                pruned_count=total_pruned,
                batches_executed=batches,
                status="failed",
                error_summary=error_summary,
            )


def main(argv: Optional[list[str]] = None) -> int:
    """Run operational YouTube data retention cleanup.

    Callable via CLI:
        python -m app.application.youtube_retention [--max-age-days 30] [--dry-run]
    """
    from app.infrastructure.db.repositories import DiscoveryRepositorySQL
    from app.infrastructure.db.session import SessionLocal

    parser = argparse.ArgumentParser(
        description=(
            "Enforce YouTube API Services Developer Policies Section III.E.4 data retention. "
            "Prunes raw records older than the policy deadline (<= 30 calendar days)."
        )
    )
    parser.add_argument(
        "--source",
        default=DEFAULT_YOUTUBE_SOURCE,
        help=f"source identifier to prune (default: {DEFAULT_YOUTUBE_SOURCE})",
    )
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=DEFAULT_RETENTION_DAYS,
        help=f"maximum retention age in calendar days (1..30, default: {DEFAULT_RETENTION_DAYS})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"batch size per delete transaction (default: {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--max-batches",
        type=int,
        default=DEFAULT_MAX_BATCHES,
        help=f"maximum batch iterations per run (default: {DEFAULT_MAX_BATCHES})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="count expired records without deleting them",
    )
    args = parser.parse_args(argv)

    if args.max_age_days < 1 or args.max_age_days > DEFAULT_RETENTION_DAYS:
        print(
            f"Error: --max-age-days must be between 1 and {DEFAULT_RETENTION_DAYS} "
            f"(YouTube Developer Policies limit: <= 30 calendar days), got {args.max_age_days}",
            file=sys.stderr,
        )
        return 2

    session = SessionLocal()
    try:
        repo = DiscoveryRepositorySQL(session)
        service = EnforceYouTubeRetention(repo)
        result = service(
            source=args.source,
            max_age_days=args.max_age_days,
            batch_size=args.batch_size,
            max_batches=args.max_batches,
            dry_run=args.dry_run,
        )
    finally:
        session.close()

    if result.status == "dry_run":
        print(
            f"[DRY RUN] source={result.source} expired={result.expired_count} "
            f"cutoff={result.cutoff.isoformat()} max_age_days={result.max_age_days}"
        )
        return 0

    if result.status == "completed":
        print(
            f"[COMPLETED] source={result.source} pruned={result.pruned_count} "
            f"batches={result.batches_executed} cutoff={result.cutoff.isoformat()}"
        )
        return 0

    print(
        f"[FAILED] source={result.source} error={result.error_summary} "
        f"pruned={result.pruned_count} batches={result.batches_executed}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
