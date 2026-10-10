"""D3 Discovery collection workflow tests.

Two groups:

- DB-free: the collection service's adapter/failure handling against an
  in-memory repository fake (auth, rate limit, batch provenance, database
  failure, config/adapter identity).
- DB-backed (opt in via the ``db`` fixture; skip when PostgreSQL is not
  reachable — see ``tests/conftest.py``): a full fixture-backed run,
  persistence, mapping, idempotency, duplicate payloads, invalid records
  and provenance/URL-only storage.

No real external collection, no network, no LLM, no trend scoring.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import OperationalError

from app.application.collection import CollectSource, CollectionConfig, main
from app.domain.ports.source_adapter import (
    RawSourceRecord,
    SourceAuthError,
    SourceBatch,
    SourceRateLimitError,
)
from app.domain.services.normalization import payload_hash
from app.domain.services.product_identity import (
    MATCH_EXACT,
    MATCH_NONE,
    IdentityDecision,
)
from app.infrastructure.db.models import (
    CollectionRun,
    Product,
    ProductSourceMap,
    RawSourceRecord as RawSourceRecordModel,
)
from app.infrastructure.db.repositories import DiscoveryRepositorySQL
from app.infrastructure.external.fixture_source import (
    FIXTURE_SOURCE_ID,
    FixtureSourceAdapter,
)
from tests.conftest import make_session


# ---------------------------------------------------------------------------
# Fakes (DB-free)
# ---------------------------------------------------------------------------


class _FakeRepo:
    """Minimal in-memory DiscoveryRepository for failure-path tests."""

    def __init__(self) -> None:
        self.finished: list[dict] = []
        self.marked: list[tuple] = []
        self._raw: dict[tuple, object] = {}
        self._products: dict[tuple, object] = {}
        self.fail_insert = None
        self.rollbacks = 0

    def start_run(self, *, source):
        return uuid4()

    def insert_raw_if_absent(
        self, *, run_id, source, source_record_id, payload, payload_hash, source_timestamp
    ):
        if self.fail_insert is not None:
            raise self.fail_insert
        key = (source, payload_hash)
        if key in self._raw:
            return self._raw[key], False
        raw_id = uuid4()
        self._raw[key] = raw_id
        return raw_id, True

    def mark_raw(self, *, raw_id, status, error):
        self.marked.append((raw_id, status, error))

    def upsert_product(self, *, product, run_id, source, source_product_id, raw_id, payload_hash):
        key = (source, source_product_id)
        if key in self._products:
            return IdentityDecision(MATCH_EXACT, self._products[key])
        self._products[key] = uuid4()
        return IdentityDecision(MATCH_NONE)

    def finish_run(self, *, run_id, status, fetched, inserted, updated, skipped, failed, error_summary):
        self.finished.append(
            dict(
                run_id=run_id, status=status, fetched=fetched, inserted=inserted,
                updated=updated, skipped=skipped, failed=failed,
                error_summary=error_summary,
            )
        )

    def rollback(self):
        self.rollbacks += 1


class _StaticAdapter:
    """Returns a fixed record list once; can raise or spoof the batch source."""

    source_id = "test_src"

    def __init__(self, records=(), *, batch_source=None, error=None):
        self._records = tuple(records)
        self._batch_source = batch_source or self.source_id
        self._error = error

    def fetch_batch(self, *, continuation=None, limit=50):
        if self._error is not None:
            raise self._error
        return SourceBatch(
            source=self._batch_source, records=self._records, continuation=None
        )


def _raw(record_id: str = "X", payload=None, *, source: str = "test_src") -> RawSourceRecord:
    return RawSourceRecord(
        source=source,
        source_record_id=record_id,
        payload=payload if payload is not None else {"id": record_id, "title": "T"},
    )


# ---------------------------------------------------------------------------
# Adapter and failure handling (DB-free)
# ---------------------------------------------------------------------------


def test_config_source_must_match_adapter():
    service = CollectSource(adapter=_StaticAdapter(), repository=_FakeRepo())
    with pytest.raises(ValueError):
        service(CollectionConfig(source="not_the_adapter_source"))


def test_cli_lists_sources_and_refuses_unknown(capsys):
    assert main(["--list-sources"]) == 0
    assert "fixture_catalog" in capsys.readouterr().out
    # Unknown (live) source is refused before any database work.
    assert main(["--source", "amazon_in"]) == 2
    assert "not configured" in capsys.readouterr().err


def test_adapter_auth_error_marks_run_failed_without_leaking_secret():
    repo = _FakeRepo()
    adapter = _StaticAdapter(error=SourceAuthError("token=SUPERSECRET123"))
    result = CollectSource(adapter=adapter, repository=repo)(
        CollectionConfig(source="test_src")
    )
    assert result.status == "failed"
    assert result.inserted == 0
    assert "SUPERSECRET123" not in (result.error_summary or "")
    assert repo.finished[-1]["status"] == "failed"


def test_adapter_rate_limit_marks_run_failed_with_retry_after():
    repo = _FakeRepo()
    adapter = _StaticAdapter(error=SourceRateLimitError(retry_after_s=7))
    result = CollectSource(adapter=adapter, repository=repo)(
        CollectionConfig(source="test_src")
    )
    assert result.status == "failed"
    assert "retry_after_s=7" in (result.error_summary or "")


def test_adapter_batch_source_mismatch_marks_run_failed():
    repo = _FakeRepo()
    adapter = _StaticAdapter([_raw("X")], batch_source="other_source")
    result = CollectSource(adapter=adapter, repository=repo)(
        CollectionConfig(source="test_src")
    )
    assert result.status == "failed"
    assert result.fetched == 0
    assert repo.finished[-1]["status"] == "failed"


def test_database_failure_marks_run_failed():
    repo = _FakeRepo()
    repo.fail_insert = OperationalError("INSERT ...", {}, Exception("db down"))
    adapter = _StaticAdapter([_raw("X")])
    result = CollectSource(adapter=adapter, repository=repo)(
        CollectionConfig(source="test_src")
    )
    assert result.status == "failed"
    assert result.error_summary == "database failure: OperationalError"
    assert repo.finished[-1]["status"] == "failed"
    assert repo.rollbacks == 1


# ---------------------------------------------------------------------------
# DB-backed collection
# ---------------------------------------------------------------------------


def _run(records_or_adapter, *, max_records: int = 200):
    adapter = (
        records_or_adapter
        if hasattr(records_or_adapter, "fetch_batch")
        else FixtureSourceAdapter(records_or_adapter)
    )
    Session = make_session()
    with Session() as session:
        return CollectSource(
            adapter=adapter, repository=DiscoveryRepositorySQL(session)
        )(CollectionConfig(source=adapter.source_id, max_records=max_records)), Session


def test_complete_fixture_collection_run(db):
    result, Session = _run(FixtureSourceAdapter())
    assert result.status == "completed"
    assert (result.fetched, result.inserted, result.updated, result.skipped, result.failed) == (
        3, 3, 0, 0, 0,
    )

    with Session() as session:
        run = session.get(CollectionRun, result.run_id)
        assert run is not None and run.status == "completed"
        assert run.finished_at is not None
        assert run.fetched_count == 3 and run.inserted_count == 3
        assert session.execute(
            select(func.count()).select_from(RawSourceRecordModel)
        ).scalar_one() == 3
        assert session.execute(
            select(func.count()).select_from(Product)
        ).scalar_one() == 3
        maps = session.execute(select(ProductSourceMap)).scalars().all()
        assert len(maps) == 3
        assert {m.source for m in maps} == {FIXTURE_SOURCE_ID}


def test_repeated_collection_is_idempotent(db):
    first, Session = _run(FixtureSourceAdapter())
    assert first.inserted == 3

    second, _ = _run(FixtureSourceAdapter())
    assert second.status == "completed"
    assert second.skipped == 3
    assert second.inserted == 0 and second.updated == 0

    with Session() as session:
        assert session.execute(
            select(func.count()).select_from(RawSourceRecordModel)
        ).scalar_one() == 3
        assert session.execute(
            select(func.count()).select_from(Product)
        ).scalar_one() == 3
        assert session.execute(
            select(func.count()).select_from(ProductSourceMap)
        ).scalar_one() == 3


def test_same_source_identity_reobserved_updates_product(db):
    old = _raw("SKU-9", {"id": "SKU-9", "title": "Old Title", "price": 100}, source=FIXTURE_SOURCE_ID)
    new = _raw("SKU-9", {"id": "SKU-9", "title": "New Title", "price": 150}, source=FIXTURE_SOURCE_ID)

    first, Session = _run((old,))
    assert first.inserted == 1
    second, _ = _run((new,))
    assert second.updated == 1 and second.inserted == 0

    with Session() as session:
        products = session.execute(select(Product)).scalars().all()
        assert len(products) == 1
        assert products[0].title == "New Title"
        assert float(products[0].price) == 150.0
        assert session.execute(
            select(func.count()).select_from(ProductSourceMap)
        ).scalar_one() == 1


def test_duplicate_payload_in_batch_is_skipped(db):
    dup = {"id": "DUP", "title": "Duplicate"}
    records = (
        _raw("A", dup, source=FIXTURE_SOURCE_ID),
        _raw("B", dup, source=FIXTURE_SOURCE_ID),  # identical payload -> same hash
    )
    result, Session = _run(records)
    assert result.status == "completed"
    assert result.fetched == 2
    assert result.inserted == 1
    assert result.skipped == 1
    with Session() as session:
        assert session.execute(
            select(func.count()).select_from(RawSourceRecordModel)
        ).scalar_one() == 1


def test_invalid_record_counts_failed_and_marks_raw(db):
    records = (
        _raw("OK", {"id": "OK", "title": "Fine"}, source=FIXTURE_SOURCE_ID),
        _raw("BAD", {"id": "BAD"}, source=FIXTURE_SOURCE_ID),  # missing title -> normalization error
    )
    result, Session = _run(records)
    assert result.status == "completed"
    assert result.inserted == 1
    assert result.failed == 1
    assert result.error_summary is not None

    with Session() as session:
        rows = session.execute(select(RawSourceRecordModel)).scalars().all()
        assert len(rows) == 2
        by_status = {r.processing_status: r for r in rows}
        assert set(by_status) == {"processed", "failed"}
        assert "title" in by_status["failed"].processing_error
        assert by_status["failed"].processing_error is not None


def test_record_from_other_source_is_counted_failed(db):
    result, Session = _run((_raw("X", source="other_source"),))
    assert result.status == "completed"
    assert result.failed == 1
    assert result.inserted == 0
    with Session() as session:
        # Never persisted under a source it does not belong to.
        assert session.execute(
            select(func.count()).select_from(RawSourceRecordModel)
        ).scalar_one() == 0


def test_source_provenance_and_url_only_image_storage(db):
    result, Session = _run(FixtureSourceAdapter())
    with Session() as session:
        raw = session.execute(
            select(RawSourceRecordModel).where(
                RawSourceRecordModel.source_record_id == "FIX-001"
            )
        ).scalar_one()
        assert raw.payload["title"] == "[Fixture] Oversized Denim Jacket"  # verbatim
        assert raw.payload_hash == payload_hash(raw.payload)
        assert raw.collection_run_id == result.run_id
        assert raw.source_timestamp is None  # never invented

        mapping = session.execute(
            select(ProductSourceMap).where(
                ProductSourceMap.raw_source_record_id == raw.id
            )
        ).scalar_one()
        product = session.get(Product, mapping.product_id)
        assert all(
            isinstance(url, str) and url.startswith("https://")
            for url in product.image_urls
        )

        columns = {c["name"] for c in inspect(session.bind).get_columns("products")}
        assert not any("byte" in c or "blob" in c or "binary" in c for c in columns)
