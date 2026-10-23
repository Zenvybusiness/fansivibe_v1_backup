"""Tests for YouTube Data API v3 retention compliance enforcement (TRENDING-03A).

Validates:
1. Expired YouTube records (> 30 calendar days) are permanently pruned.
2. Unexpired YouTube records (<= 30 calendar days) are strictly preserved.
3. Unrelated source records (GDELT, Amazon, Fashion Seed, Fixture) are strictly preserved,
   even if their fetched_at is identically expired.
4. Retention enforcement is idempotent and safe under repeated execution.
5. Batch execution is strictly bounded by batch_size and max_batches.
6. Dry-run mode accurately counts expired records without deleting them.
7. Policy deadline constraints (1..30 calendar days) are strictly validated.
8. Database failures fail safely with rollback and status="failed".
9. CLI entrypoints exit with standard codes (0 on success, 1 on error, 2 on invalid args).
10. End-to-end integration with test PostgreSQL database when available.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app.application.youtube_retention import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_RETENTION_DAYS,
    DEFAULT_YOUTUBE_SOURCE,
    EnforceYouTubeRetention,
    RetentionCleanupResult,
    main as retention_main,
)
from app.domain.ports.repositories import DiscoveryRepository
from app.infrastructure.db.models import (
    CollectionRun,
    RawSourceRecord as RawSourceRecordModel,
)
from app.infrastructure.db.repositories import DiscoveryRepositorySQL


# ---------------------------------------------------------------------------
# In-Memory Fake DiscoveryRepository for fast, deterministic unit testing
# ---------------------------------------------------------------------------


class _FakeRawRecord:
    def __init__(
        self,
        *,
        record_id: str,
        source: str,
        source_record_id: str,
        payload: dict,
        fetched_at: datetime,
    ) -> None:
        self.id = record_id
        self.source = source
        self.source_record_id = source_record_id
        self.payload = payload
        self.fetched_at = fetched_at


class FakeDiscoveryRepository:
    """In-memory fake implementing DiscoveryRepository for retention tests."""

    def __init__(self) -> None:
        self.records: dict[str, _FakeRawRecord] = {}
        self.rollbacks = 0
        self.fail_prune: Optional[Exception] = None
        self.fail_count: Optional[Exception] = None

    def add_record(
        self,
        *,
        source: str,
        source_record_id: str,
        fetched_at: datetime,
        payload: Optional[dict] = None,
    ) -> str:
        rec_id = str(uuid4())
        self.records[rec_id] = _FakeRawRecord(
            record_id=rec_id,
            source=source,
            source_record_id=source_record_id,
            payload=payload or {"videoId": source_record_id},
            fetched_at=fetched_at,
        )
        return rec_id

    def prune_expired_source_records(
        self,
        *,
        source: str,
        older_than: datetime,
        batch_limit: int = 1000,
    ) -> int:
        if self.fail_prune:
            raise self.fail_prune

        matching = [
            r for r in self.records.values()
            if r.source == source and r.fetched_at < older_than
        ]
        # Deterministic ordering by fetched_at
        matching.sort(key=lambda r: (r.fetched_at, r.id))
        to_delete = matching[:batch_limit]
        for r in to_delete:
            del self.records[r.id]
        return len(to_delete)

    def count_expired_source_records(
        self,
        *,
        source: str,
        older_than: datetime,
    ) -> int:
        if self.fail_count:
            raise self.fail_count

        return sum(
            1 for r in self.records.values()
            if r.source == source and r.fetched_at < older_than
        )

    def rollback(self) -> None:
        self.rollbacks += 1

    # Minimal stubs for DiscoveryRepository protocol
    def start_run(self, *, source: str):
        return uuid4()

    def insert_raw_if_absent(self, **kwargs):
        return uuid4(), True

    def mark_raw(self, **kwargs):
        pass

    def upsert_product(self, **kwargs):
        pass

    def finish_run(self, **kwargs):
        pass


# ---------------------------------------------------------------------------
# Unit Tests (DB-Free)
# ---------------------------------------------------------------------------


def test_retention_prunes_expired_youtube_records():
    """Records older than 30 calendar days for youtube_in are deleted."""
    repo = FakeDiscoveryRepository()
    now = datetime(2026, 10, 17, 12, 0, 0, tzinfo=timezone.utc)

    # 3 expired YouTube records (35 days old)
    r1 = repo.add_record(source="youtube_in", source_record_id="vid_exp_1", fetched_at=now - timedelta(days=35))
    r2 = repo.add_record(source="youtube_in", source_record_id="vid_exp_2", fetched_at=now - timedelta(days=31))
    r3 = repo.add_record(source="youtube_in", source_record_id="vid_exp_3", fetched_at=now - timedelta(days=40))

    # 1 unexpired YouTube record (5 days old)
    r_unexp = repo.add_record(source="youtube_in", source_record_id="vid_fresh", fetched_at=now - timedelta(days=5))

    service = EnforceYouTubeRetention(repo)
    result = service(now=now, max_age_days=30)

    assert result.status == "completed"
    assert result.pruned_count == 3
    assert result.batches_executed == 1
    assert result.dry_run is False

    # Expired records removed
    assert r1 not in repo.records
    assert r2 not in repo.records
    assert r3 not in repo.records

    # Unexpired record preserved
    assert r_unexp in repo.records


def test_retention_preserves_unexpired_youtube_records():
    """Records within the 30-day policy limit are not deleted."""
    repo = FakeDiscoveryRepository()
    now = datetime(2026, 10, 17, 12, 0, 0, tzinfo=timezone.utc)

    # All unexpired (1 day, 15 days, 29 days)
    r1 = repo.add_record(source="youtube_in", source_record_id="vid_1", fetched_at=now - timedelta(days=1))
    r2 = repo.add_record(source="youtube_in", source_record_id="vid_2", fetched_at=now - timedelta(days=15))
    r3 = repo.add_record(source="youtube_in", source_record_id="vid_3", fetched_at=now - timedelta(days=29))

    service = EnforceYouTubeRetention(repo)
    result = service(now=now, max_age_days=30)

    assert result.status == "completed"
    assert result.pruned_count == 0
    assert len(repo.records) == 3


def test_retention_strictly_preserves_unrelated_sources():
    """Unrelated sources (GDELT, Amazon, fashion seed, fixture) are NEVER pruned."""
    repo = FakeDiscoveryRepository()
    now = datetime(2026, 10, 17, 12, 0, 0, tzinfo=timezone.utc)
    expired_time = now - timedelta(days=45)

    # Expired records from other providers
    gdelt_id = repo.add_record(source="gdelt_doc_20", source_record_id="gdelt_art_1", fetched_at=expired_time)
    amazon_id = repo.add_record(source="amazon_in", source_record_id="B08N5WRWNW", fetched_at=expired_time)
    seed_id = repo.add_record(source="fashion_seed", source_record_id="SEED-001", fetched_at=expired_time)
    fixture_id = repo.add_record(source="fixture_catalog", source_record_id="FIX-001", fetched_at=expired_time)

    # Expired YouTube record
    yt_id = repo.add_record(source="youtube_in", source_record_id="yt_exp_1", fetched_at=expired_time)

    service = EnforceYouTubeRetention(repo)
    result = service(now=now, max_age_days=30)

    assert result.status == "completed"
    assert result.pruned_count == 1

    # YouTube record deleted
    assert yt_id not in repo.records

    # All other sources preserved
    assert gdelt_id in repo.records
    assert amazon_id in repo.records
    assert seed_id in repo.records
    assert fixture_id in repo.records


def test_retention_is_idempotent():
    """Executing retention cleanup repeatedly on a clean dataset does nothing and succeeds."""
    repo = FakeDiscoveryRepository()
    now = datetime(2026, 10, 17, 12, 0, 0, tzinfo=timezone.utc)

    repo.add_record(source="youtube_in", source_record_id="vid_exp", fetched_at=now - timedelta(days=35))
    service = EnforceYouTubeRetention(repo)

    # First run: deletes 1 record
    res1 = service(now=now, max_age_days=30)
    assert res1.pruned_count == 1
    assert res1.status == "completed"

    # Second run: deletes 0 records
    res2 = service(now=now, max_age_days=30)
    assert res2.pruned_count == 0
    assert res2.status == "completed"

    # Third run: deletes 0 records
    res3 = service(now=now, max_age_days=30)
    assert res3.pruned_count == 0
    assert res3.status == "completed"


def test_retention_bounded_batch_execution():
    """Cleanup processes records in bounded batches and honors max_batches."""
    repo = FakeDiscoveryRepository()
    now = datetime(2026, 10, 17, 12, 0, 0, tzinfo=timezone.utc)

    # Create 12 expired records
    for i in range(12):
        repo.add_record(
            source="youtube_in",
            source_record_id=f"vid_exp_{i}",
            fetched_at=now - timedelta(days=35 + i),
        )

    service = EnforceYouTubeRetention(repo)

    # Case A: batch_size=5, max_batches=2 -> should delete 10 records across 2 batches
    res_bounded = service(now=now, max_age_days=30, batch_size=5, max_batches=2)
    assert res_bounded.pruned_count == 10
    assert res_bounded.batches_executed == 2
    assert len(repo.records) == 2

    # Case B: next run cleans the remaining 2 records in 1 batch
    res_remaining = service(now=now, max_age_days=30, batch_size=5, max_batches=2)
    assert res_remaining.pruned_count == 2
    assert res_remaining.batches_executed == 1
    assert len(repo.records) == 0


def test_retention_dry_run_does_not_delete():
    """Dry run counts expired records but performs zero database deletions."""
    repo = FakeDiscoveryRepository()
    now = datetime(2026, 10, 17, 12, 0, 0, tzinfo=timezone.utc)

    for i in range(4):
        repo.add_record(
            source="youtube_in",
            source_record_id=f"vid_{i}",
            fetched_at=now - timedelta(days=40),
        )

    service = EnforceYouTubeRetention(repo)
    result = service(now=now, max_age_days=30, dry_run=True)

    assert result.status == "dry_run"
    assert result.dry_run is True
    assert result.expired_count == 4
    assert result.pruned_count == 0
    assert result.batches_executed == 0

    # Records still in repository
    assert len(repo.records) == 4


def test_retention_validates_policy_horizon():
    """Rejects invalid max_age_days (must be 1..30 calendar days)."""
    repo = FakeDiscoveryRepository()
    service = EnforceYouTubeRetention(repo)

    with pytest.raises(ValueError, match="between 1 and 30"):
        service(max_age_days=0)

    with pytest.raises(ValueError, match="between 1 and 30"):
        service(max_age_days=31)  # YouTube Developer Policies limit is <= 30 days

    with pytest.raises(ValueError, match="batch_size must be >= 1"):
        service(batch_size=0)

    with pytest.raises(ValueError, match="max_batches must be >= 1"):
        service(max_batches=0)


def test_retention_handles_database_error_gracefully():
    """When the repository fails, use case rolls back and returns status='failed'."""
    repo = FakeDiscoveryRepository()
    repo.fail_prune = OperationalError("statement", {}, Exception("DB connection dropped"))

    service = EnforceYouTubeRetention(repo)
    result = service()

    assert result.status == "failed"
    assert "database failure: OperationalError" in (result.error_summary or "")
    assert repo.rollbacks == 1


def test_retention_cli_validation(capsys):
    """CLI rejects invalid max_age_days with exit code 2."""
    code = retention_main(["--max-age-days", "45"])
    assert code == 2
    captured = capsys.readouterr()
    assert "Error: --max-age-days must be between 1 and 30" in captured.err


# ---------------------------------------------------------------------------
# DB-Backed Tests (Opt-in via db fixture against fansivibe_test)
# ---------------------------------------------------------------------------


def test_retention_sql_database_end_to_end(db):
    """DB-backed test: verifies real PostgreSQL row deletion and scoping."""
    now = datetime.now(timezone.utc)
    expired_time = now - timedelta(days=35)
    fresh_time = now - timedelta(days=5)

    with db() as session:
        # Create a collection run
        run = CollectionRun(source="youtube_in")
        session.add(run)
        session.commit()
        run_id = run.id

        # Insert 2 expired YouTube records
        yt_exp_1 = RawSourceRecordModel(
            collection_run_id=run_id,
            source="youtube_in",
            source_record_id="yt_exp_1",
            payload={"videoId": "yt_exp_1", "title": "Old Trend"},
            payload_hash="hash_exp_1",
            source_timestamp=expired_time,
            fetched_at=expired_time,
        )
        yt_exp_2 = RawSourceRecordModel(
            collection_run_id=run_id,
            source="youtube_in",
            source_record_id="yt_exp_2",
            payload={"videoId": "yt_exp_2", "title": "Old Trend 2"},
            payload_hash="hash_exp_2",
            source_timestamp=expired_time,
            fetched_at=expired_time,
        )

        # Insert 1 fresh YouTube record
        yt_fresh = RawSourceRecordModel(
            collection_run_id=run_id,
            source="youtube_in",
            source_record_id="yt_fresh_1",
            payload={"videoId": "yt_fresh_1", "title": "Fresh Trend"},
            payload_hash="hash_fresh_1",
            source_timestamp=fresh_time,
            fetched_at=fresh_time,
        )

        # Insert 1 expired Amazon record (should NOT be pruned)
        amazon_exp = RawSourceRecordModel(
            collection_run_id=run_id,
            source="amazon_in",
            source_record_id="B08TESTEXP",
            payload={"asin": "B08TESTEXP", "title": "Amazon Old Product"},
            payload_hash="hash_amz_exp_1",
            source_timestamp=expired_time,
            fetched_at=expired_time,
        )

        session.add_all([yt_exp_1, yt_exp_2, yt_fresh, amazon_exp])
        session.commit()

        # Execute retention pruning via DiscoveryRepositorySQL
        repo = DiscoveryRepositorySQL(session)
        service = EnforceYouTubeRetention(repo)

        # First verify dry-run
        dry_result = service(source="youtube_in", max_age_days=30, now=now, dry_run=True)
        assert dry_result.status == "dry_run"
        assert dry_result.expired_count == 2

        # Execute live pruning
        prune_result = service(source="youtube_in", max_age_days=30, now=now, dry_run=False)
        assert prune_result.status == "completed"
        assert prune_result.pruned_count == 2

        # Verify database state
        remaining_yt = session.execute(
            select(RawSourceRecordModel).where(RawSourceRecordModel.source == "youtube_in")
        ).scalars().all()
        assert len(remaining_yt) == 1
        assert remaining_yt[0].source_record_id == "yt_fresh_1"

        # Verify Amazon record was completely untouched
        remaining_amz = session.execute(
            select(RawSourceRecordModel).where(RawSourceRecordModel.source == "amazon_in")
        ).scalars().all()
        assert len(remaining_amz) == 1
        assert remaining_amz[0].source_record_id == "B08TESTEXP"

        # Verify idempotency on DB
        idempotent_result = service(source="youtube_in", max_age_days=30, now=now, dry_run=False)
        assert idempotent_result.status == "completed"
        assert idempotent_result.pruned_count == 0
