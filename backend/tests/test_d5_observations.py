"""D5 Discovery product observation history tests.

Observation history is append-only: every successfully normalized listing is
recorded once with the metrics the pipeline actually has, distinct observation
time vs. source time, and provenance back to the run and raw record. No trend
detection or scoring is tested or implemented here.

DB-free: migration head chain.
DB-backed (opt in via the ``db`` fixture; skip when PostgreSQL is unreachable,
see ``tests/conftest.py``): observation recording, multiple observations over
time, idempotency, changed/missing metrics, provenance, cross-source
observation, failed normalization, and the unique/provenance constraints.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError

from app.application.collection import CollectSource, CollectionConfig
from app.domain.ports.source_adapter import RawSourceRecord, SourceBatch
from app.domain.services.normalization import payload_hash
from app.infrastructure.db.models import (
    CollectionRun,
    Product,
    ProductObservation,
    RawSourceRecord as RawSourceRecordModel,
)
from app.infrastructure.db.repositories import DiscoveryRepositorySQL
from tests.conftest import make_session

_GTIN13 = "4006381333931"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _Adapter:
    def __init__(self, source_id: str, records) -> None:
        self.source_id = source_id
        self._records = tuple(records)

    def fetch_batch(self, *, continuation=None, limit=50):
        return SourceBatch(source=self.source_id, records=self._records, continuation=None)


def _raw(record_id, payload, *, source="src_a", source_timestamp=None):
    return RawSourceRecord(
        source=source,
        source_record_id=record_id,
        payload=payload,
        source_timestamp=source_timestamp,
    )


def _run(adapter: _Adapter):
    Session = make_session()
    with Session() as session:
        result = CollectSource(
            adapter=adapter, repository=DiscoveryRepositorySQL(session)
        )(CollectionConfig(source=adapter.source_id))
    return result, Session


def _observations(Session):
    with Session() as session:
        return session.execute(
            select(ProductObservation).order_by(ProductObservation.observed_at)
        ).scalars().all()


# ---------------------------------------------------------------------------
# Migration head (DB-free)
# ---------------------------------------------------------------------------


def test_migration_head_is_0028_linear_off_0027():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config("alembic.ini")
    config.set_main_option("script_location", "alembic")
    script = ScriptDirectory.from_config(config)
    assert tuple(script.get_heads()) == ("0028",)
    rev = script.get_revision("0028")
    assert rev is not None and rev.down_revision == "0027"


def test_observation_table_exists_with_indexes(db):
    Session = make_session()
    with Session() as session:
        insp = inspect(session.bind)
        assert insp.has_table("product_observations")
        index_names = {ix["name"] for ix in insp.get_indexes("product_observations")}
        assert {
            "uq_product_observations_raw_source_record",
            "ix_product_observations_product_observed_at",
            "ix_product_observations_source_observed_at",
        } <= index_names


# ---------------------------------------------------------------------------
# Observation recording
# ---------------------------------------------------------------------------


def test_new_listing_records_one_observation_with_provenance(db):
    record = _raw(
        "A-1",
        {"id": "A-1", "title": "T", "price": 100, "currency": "INR", "availability": True},
    )
    result, Session = _run(_Adapter("src_a", (record,)))
    assert result.inserted == 1

    observations = _observations(Session)
    assert len(observations) == 1
    obs = observations[0]
    assert obs.source == "src_a"
    assert obs.source_product_id == "A-1"
    assert float(obs.price) == 100.0
    assert obs.currency == "INR"
    assert obs.availability is True
    assert obs.observed_at is not None
    assert obs.collection_run_id == result.run_id
    with Session() as session:
        raw = session.get(RawSourceRecordModel, obs.raw_source_record_id)
        assert raw is not None
        assert obs.payload_hash == raw.payload_hash == payload_hash(raw.payload)


def test_multiple_observations_over_time_preserve_history(db):
    old = _raw("A-1", {"id": "A-1", "title": "T", "price": 100, "availability": True})
    new = _raw("A-1", {"id": "A-1", "title": "T", "price": 80, "availability": False})

    first, Session = _run(_Adapter("src_a", (old,)))
    assert first.inserted == 1
    second, _ = _run(_Adapter("src_a", (new,)))
    assert second.updated == 1

    observations = _observations(Session)
    assert len(observations) == 2  # history kept, not overwritten
    assert [float(o.price) for o in observations] == [100.0, 80.0]
    assert observations[0].availability is True
    assert observations[1].availability is False
    assert observations[0].observed_at <= observations[1].observed_at
    with Session() as session:
        assert session.execute(select(func.count()).select_from(Product)).scalar_one() == 1


def test_identical_observation_is_idempotent(db):
    record = _raw("A-1", {"id": "A-1", "title": "T", "price": 100})
    first, Session = _run(_Adapter("src_a", (record,)))
    assert first.inserted == 1
    second, _ = _run(_Adapter("src_a", (record,)))
    assert second.skipped == 1

    with Session() as session:
        assert session.execute(
            select(func.count()).select_from(ProductObservation)
        ).scalar_one() == 1
        assert session.execute(
            select(func.count()).select_from(RawSourceRecordModel)
        ).scalar_one() == 1


def test_missing_optional_metrics_are_null_not_zero(db):
    record = _raw("A-1", {"id": "A-1", "title": "No metrics"})
    result, Session = _run(_Adapter("src_a", (record,)))
    assert result.inserted == 1
    obs = _observations(Session)[0]
    assert obs.price is None
    assert obs.currency is None
    assert obs.availability is None


def test_source_timestamp_is_distinct_from_observation_time(db):
    supplied = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)
    stamped = _raw(
        "TS-1",
        {"id": "TS-1", "title": "T", "price": 5},
        source_timestamp=supplied,
    )
    unstamped = _raw("NS-1", {"id": "NS-1", "title": "U"})
    result, Session = _run(_Adapter("src_a", (stamped, unstamped)))
    assert result.inserted == 2

    by_id = {o.source_product_id: o for o in _observations(Session)}
    assert by_id["TS-1"].source_timestamp == supplied
    assert by_id["TS-1"].observed_at != supplied
    assert by_id["NS-1"].source_timestamp is None  # never invented


def test_verified_cross_source_records_observation_for_target(db):
    a = _raw("A-1", {"id": "A-1", "title": "Widget", "brand": "Acme", "category": "tops", "gtin": _GTIN13})
    b = _raw("B-1", {"id": "B-1", "title": "Widget Deluxe", "brand": "Acme", "category": "tops", "gtin": _GTIN13}, source="src_b")

    _run(_Adapter("src_a", (a,)))
    second, Session = _run(_Adapter("src_b", (b,)))
    assert second.verified == 1

    observations = _observations(Session)
    assert len(observations) == 2
    assert {o.source for o in observations} == {"src_a", "src_b"}
    assert len({o.product_id for o in observations}) == 1
    with Session() as session:
        assert session.execute(select(func.count()).select_from(Product)).scalar_one() == 1


def test_failed_normalization_creates_no_observation(db):
    records = (
        _raw("OK", {"id": "OK", "title": "Fine", "price": 10}),
        _raw("BAD", {"id": "BAD"}),  # missing title -> rejected
    )
    result, Session = _run(_Adapter("src_a", records))
    assert result.status == "completed"
    assert result.inserted == 1 and result.failed == 1

    observations = _observations(Session)
    assert len(observations) == 1
    assert observations[0].source_product_id == "OK"
    with Session() as session:
        assert session.execute(select(func.count()).select_from(Product)).scalar_one() == 1


def test_time_window_query_uses_observed_at(db):
    records = (
        _raw("A-1", {"id": "A-1", "title": "One"}),
        _raw("A-2", {"id": "A-2", "title": "Two"}),
    )
    _run_result, Session = _run(_Adapter("src_a", records))
    with Session() as session:
        by_source = session.execute(
            select(func.count())
            .select_from(ProductObservation)
            .where(ProductObservation.source == "src_a")
        ).scalar_one()
        assert by_source == 2
        # Ordered history is available via the (product_id, observed_at) path.
        cutoff = session.execute(select(func.min(ProductObservation.observed_at))).scalar_one()
        after = session.execute(
            select(func.count())
            .select_from(ProductObservation)
            .where(ProductObservation.observed_at >= cutoff)
        ).scalar_one()
        assert after == 2


def test_duplicate_observation_for_same_raw_is_rejected(db):
    record = _raw("A-1", {"id": "A-1", "title": "T"})
    _run(_Adapter("src_a", (record,)))

    Session = make_session()
    with Session() as session:
        existing = session.execute(select(ProductObservation)).scalar_one()
        session.add(
            ProductObservation(
                product_id=existing.product_id,
                source=existing.source,
                source_product_id=existing.source_product_id,
                raw_source_record_id=existing.raw_source_record_id,
                payload_hash=existing.payload_hash,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        # Session is usable again; no duplicate survived.
        assert session.execute(
            select(func.count()).select_from(ProductObservation)
        ).scalar_one() == 1


def test_fixture_run_records_observation_per_product(db):
    from app.infrastructure.external.fixture_source import FixtureSourceAdapter

    result, Session = _run(FixtureSourceAdapter())
    assert result.inserted == 3
    with Session() as session:
        assert session.execute(
            select(func.count()).select_from(ProductObservation)
        ).scalar_one() == 3
        runs = session.execute(
            select(func.count()).select_from(CollectionRun)
        ).scalar_one()
        assert runs == 1


def test_observation_downgrade_removes_and_upgrade_restores(migrated_db):
    from alembic import command
    from alembic.config import Config

    config = Config("alembic.ini")
    config.set_main_option("script_location", "alembic")
    Session = make_session()
    try:
        command.downgrade(config, "0026")
        with Session() as session:
            insp = inspect(session.bind)
            assert not insp.has_table("product_observations")
            assert insp.has_table("products")  # D2 tables untouched
    finally:
        command.upgrade(config, "head")
    with Session() as session:
        assert inspect(session.bind).has_table("product_observations")
