"""D9B search-interest foundation tests.

Two groups:

- DB-free: normalization (validation, timezone/period, missing/suppressed
  stay unknown, derived keys), the distinct signal kind, FFO trend-signal
  schema compatibility, and the collection service's adapter/failure handling
  against in-memory fakes.
- DB-backed (opt in via the ``db`` fixture; skip when PostgreSQL is not
  reachable — see ``tests/conftest.py``): a full synthetic run, provenance,
  idempotency/dedup, NULL semantics, period window reads, storage-level
  distinctness from the product path, and the migration upgrade/downgrade.

No real provider, no network, no Google Trends, no LLM. Every record used here
is clearly synthetic (``synthetic: true``).
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.application.collection import (
    CollectSearchInterest,
    SearchInterestCollectionConfig,
)
from app.data.ffo.validation import trend_signal_errors
from app.domain.ports.source_adapter import (
    RawSourceRecord,
    SourceAuthError,
    SourceBatch,
)
from app.domain.services.normalization import payload_hash
from app.domain.services.search_interest import (
    METRIC_SEARCH_INTEREST,
    SIGNAL_KIND,
    normalize_search_interest,
)
from app.domain.services.trends import (
    CATALOG_OPERATIONAL,
    DEMAND_SIGNAL_AVAILABLE,
    DIRECT_DEMAND,
    SUPPORTING,
)
from app.infrastructure.db.models import (
    CollectionRun,
    ProductObservation,
    RawSourceRecord as RawSourceRecordModel,
    SearchInterestObservation,
)
from app.infrastructure.db.repositories import (
    DiscoveryRepositorySQL,
    SearchInterestRepositorySQL,
    TrendRepositorySQL,
)
from app.infrastructure.external.synthetic_search_interest_source import (
    SYNTHETIC_SEARCH_INTEREST_RECORDS,
    SYNTHETIC_SEARCH_INTEREST_SOURCE_ID,
    SyntheticSearchInterestAdapter,
    synthetic_search_interest_payload,
)
from tests.conftest import make_session

_WEEK = (datetime(2026, 1, 5, tzinfo=timezone.utc), datetime(2026, 1, 12, tzinfo=timezone.utc))
_WEEK_2 = (datetime(2026, 1, 12, tzinfo=timezone.utc), datetime(2026, 1, 19, tzinfo=timezone.utc))


# ---------------------------------------------------------------------------
# Fakes (DB-free)
# ---------------------------------------------------------------------------


class _FakeDiscovery:
    """Minimal in-memory DiscoveryRepository for the search-interest service."""

    def __init__(self) -> None:
        self.finished: list[dict] = []
        self.marked: list[tuple] = []
        self._raw: dict[tuple, object] = {}
        self.fail_insert: Exception | None = None
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


class _FakeObservations:
    """In-memory SearchInterestRepository keyed by the observation natural key."""

    def __init__(self) -> None:
        self._keys: dict[tuple, object] = {}

    def insert_observation(self, *, observation, run_id, raw_id, payload_hash):
        key = (
            observation.source, observation.metric, observation.query_kind,
            observation.query_key, observation.geo_scope,
            observation.aggregation_interval, observation.period_start,
            observation.period_end,
        )
        if key in self._keys:
            return self._keys[key], False
        obs_id = uuid4()
        self._keys[key] = obs_id
        return obs_id, True


class _StaticAdapter:
    source_id = SYNTHETIC_SEARCH_INTEREST_SOURCE_ID

    def __init__(self, records=(), *, batch_source=None, error=None):
        self._records = tuple(records)
        self._batch_source = batch_source or self.source_id
        self._error = error

    def fetch_batch(self, *, continuation=None, limit=50):
        if self._error is not None:
            raise self._error
        return SourceBatch(source=self._batch_source, records=self._records, continuation=None)


def _synth_payload(**kwargs) -> dict:
    kwargs.setdefault("query_display", "oversized denim jacket")
    kwargs.setdefault("period_start", _WEEK[0])
    kwargs.setdefault("period_end", _WEEK[1])
    kwargs.setdefault("value", 10.0)
    return synthetic_search_interest_payload(**kwargs)


def _raw(record_id="R-1", payload=None, *, source=SYNTHETIC_SEARCH_INTEREST_SOURCE_ID) -> RawSourceRecord:
    return RawSourceRecord(
        source=source,
        source_record_id=record_id,
        payload=payload if payload is not None else _synth_payload(),
    )


def _service(adapter, discovery=None, observations=None) -> tuple[CollectSearchInterest, _FakeDiscovery, _FakeObservations]:
    discovery = discovery or _FakeDiscovery()
    observations = observations or _FakeObservations()
    return (
        CollectSearchInterest(adapter=adapter, discovery=discovery, observations=observations),
        discovery,
        observations,
    )


# ---------------------------------------------------------------------------
# Signal distinctness and D6/D7 safeguards (DB-free)
# ---------------------------------------------------------------------------


def test_signal_kind_is_distinct_from_catalog_activity():
    assert METRIC_SEARCH_INTEREST == "search_interest"
    assert SIGNAL_KIND == METRIC_SEARCH_INTEREST
    assert SIGNAL_KIND not in {DIRECT_DEMAND, SUPPORTING, CATALOG_OPERATIONAL}


def test_demand_signal_remains_unavailable():
    assert DEMAND_SIGNAL_AVAILABLE is False


# ---------------------------------------------------------------------------
# Normalization (DB-free)
# ---------------------------------------------------------------------------


def test_normalize_valid_record():
    result = normalize_search_interest(SYNTHETIC_SEARCH_INTEREST_RECORDS[0])
    assert result.ok and result.status == "accepted"
    obs = result.observation
    assert obs is not None
    assert obs.metric == METRIC_SEARCH_INTEREST
    assert obs.query_key == "oversized_denim_jacket"
    assert obs.geo_scope == "worldwide"
    assert obs.aggregation_interval == "weekly"
    assert obs.value == 42.0
    assert obs.value_status == "present"
    assert obs.is_relative is True
    assert obs.synthetic is True
    assert obs.period_end > obs.period_start


def test_normalize_requires_mapping_payload():
    raw = RawSourceRecord(source=SYNTHETIC_SEARCH_INTEREST_SOURCE_ID, payload=["not", "a", "map"])
    result = normalize_search_interest(raw)
    assert not result.ok and result.status == "rejected"
    assert result.observation is None
    assert "payload must be a mapping" in result.errors


def test_normalize_derives_search_term_key():
    raw = _raw(payload=_synth_payload(query_display="Oversized   Denim Jacket"))
    obs = normalize_search_interest(raw).observation
    assert obs is not None and obs.query_key == "oversized_denim_jacket"


def test_normalize_rejects_topic_without_key():
    raw = _raw(
        payload=_synth_payload(query_kind="topic", query_display="/m/nope", query_key=None)
    )
    result = normalize_search_interest(raw)
    assert not result.ok
    assert any("query.key" in e for e in result.errors)


def test_normalize_rejects_naive_period():
    payload = _synth_payload(
        period_start=datetime(2026, 1, 5), period_end=datetime(2026, 1, 12)
    )
    result = normalize_search_interest(_raw(payload=payload))
    assert not result.ok
    assert any("period.start" in e for e in result.errors)


def test_normalize_rejects_unordered_period():
    payload = _synth_payload(period_start=_WEEK[1], period_end=_WEEK[0])
    result = normalize_search_interest(_raw(payload=payload))
    assert not result.ok
    assert any("period.end must be after period.start" in e for e in result.errors)


def test_normalize_rejects_present_value_missing_or_non_finite():
    missing = normalize_search_interest(
        _raw(payload=_synth_payload(value=None, value_status="present"))
    )
    assert not missing.ok
    assert any("finite number" in e for e in missing.errors)

    infinite = _synth_payload()
    infinite["value"] = float("inf")
    assert not normalize_search_interest(_raw(payload=infinite)).ok


def test_missing_and_suppressed_values_stay_unknown():
    for status in ("missing", "suppressed", "invalid"):
        payload = _synth_payload()
        payload["value_status"] = status
        payload.pop("value", None)
        result = normalize_search_interest(_raw(payload=payload))
        assert result.ok, result.errors
        assert result.observation is not None
        assert result.observation.value is None
        assert result.observation.value_status == status
        assert "value" in result.missing


def test_suppressed_value_with_a_number_is_rejected():
    payload = _synth_payload(value=5.0, value_status="suppressed")
    result = normalize_search_interest(_raw(payload=payload))
    assert not result.ok
    assert any("must be absent" in e for e in result.errors)


def test_normalize_rejects_inconsistent_geography_and_enum_drift():
    bad_geo = _synth_payload(geo_scope="IN", geo_scope_type="worldwide")
    assert not normalize_search_interest(_raw(payload=bad_geo)).ok

    bad_interval = _synth_payload(interval="hourly")
    assert not normalize_search_interest(_raw(payload=bad_interval)).ok

    bad_metric = _synth_payload()
    bad_metric["metric"] = "search_volume"
    assert not normalize_search_interest(_raw(payload=bad_metric)).ok

    no_scale = _synth_payload()
    no_scale.pop("value_scale", None)
    assert not normalize_search_interest(_raw(payload=no_scale)).ok


def test_source_timestamp_missing_is_marked_and_never_invented():
    payload = _synth_payload()
    result = normalize_search_interest(_raw(payload=payload))
    assert result.ok
    assert result.observation is not None
    assert result.observation.source_timestamp is None
    assert "source_timestamp" in result.missing


def test_ffo_trend_signal_schema_accepts_relative_search_interest_projection():
    obs = normalize_search_interest(SYNTHETIC_SEARCH_INTEREST_RECORDS[0]).observation
    assert obs is not None and obs.is_relative
    projection = {
        "trend": obs.query_key,
        "signals": [{"source": obs.source, "metric": obs.metric, "value": obs.value}],
        # D9B assigns no publication confidence; 0.0 is a placeholder, not a claim.
        "confidence": 0.0,
        "provenance": {"source": obs.source, "source_type": "INFERRED"},
    }
    assert trend_signal_errors(projection) == []


# ---------------------------------------------------------------------------
# Collection service failure handling (DB-free)
# ---------------------------------------------------------------------------


def test_config_source_must_match_adapter():
    service, _, _ = _service(_StaticAdapter())
    with pytest.raises(ValueError):
        service(SearchInterestCollectionConfig(source="not_the_adapter_source"))


def test_collection_persists_one_observation_per_record():
    adapter = _StaticAdapter([_raw("R-1"), _raw("R-2", payload=_synth_payload(query_display="a"))])
    service, discovery, observations = _service(adapter)
    result = service(SearchInterestCollectionConfig(source=adapter.source_id))
    assert result.status == "completed"
    assert (result.fetched, result.inserted, result.skipped, result.failed) == (2, 2, 0, 0)
    assert discovery.finished[-1]["status"] == "completed"
    assert len(observations._keys) == 2


def test_duplicate_payload_is_skipped_not_duplicated():
    record = _raw("R-1")
    duplicate = _raw("R-1-again")  # same payload -> same hash
    service, discovery, observations = _service(_StaticAdapter([record, duplicate]))
    result = service(SearchInterestCollectionConfig(source=_StaticAdapter.source_id))
    assert (result.inserted, result.skipped, result.failed) == (1, 1, 0)
    assert len(observations._keys) == 1


def test_record_claiming_another_source_is_counted_not_persisted():
    foreign = RawSourceRecord(source="other_src", source_record_id="X", payload=_synth_payload())
    service, discovery, _ = _service(_StaticAdapter([foreign]))
    result = service(SearchInterestCollectionConfig(source=_StaticAdapter.source_id))
    assert result.status == "completed"
    assert (result.inserted, result.failed) == (0, 1)


def test_invalid_record_is_counted_and_raw_marked_failed():
    adapter = _StaticAdapter([_raw("R-1", payload={"query": {}})])
    service, discovery, observations = _service(adapter)
    result = service(SearchInterestCollectionConfig(source=adapter.source_id))
    assert result.status == "completed"
    assert result.failed == 1
    assert discovery.marked[-1][1] == "failed"
    assert len(observations._keys) == 0


def test_natural_key_duplicate_from_changed_payload_counts_skipped():
    first = _raw("R-1")
    # Same natural key, different payload (reordered field set) -> new raw.
    changed = _synth_payload()
    changed["note"] = "different payload, same period"
    second = _raw("R-2", payload=changed)
    service, _, _ = _service(_StaticAdapter([first, second]))
    result = service(SearchInterestCollectionConfig(source=_StaticAdapter.source_id))
    assert (result.inserted, result.skipped, result.failed) == (1, 1, 0)


def test_source_failure_marks_run_failed_without_leaking_secret():
    adapter = _StaticAdapter(error=SourceAuthError("token=SECRET-ABC"))
    service, discovery, _ = _service(adapter)
    result = service(SearchInterestCollectionConfig(source=adapter.source_id))
    assert result.status == "failed"
    assert result.error_summary == "source authentication failed"
    assert "SECRET" not in (result.error_summary or "")
    assert discovery.finished[-1]["status"] == "failed"


def test_batch_source_mismatch_fails_the_run():
    adapter = _StaticAdapter([_raw("R-1")], batch_source="other_src")
    service, _, _ = _service(adapter)
    result = service(SearchInterestCollectionConfig(source=adapter.source_id))
    assert result.status == "failed"


def test_database_failure_rolls_back_and_finishes_run():
    discovery = _FakeDiscovery()
    discovery.fail_insert = SQLAlchemyError("db down")
    service, _, _ = _service(_StaticAdapter([_raw("R-1")]), discovery=discovery)
    result = service(SearchInterestCollectionConfig(source=_StaticAdapter.source_id))
    assert result.status == "failed"
    assert result.error_summary == "database failure: SQLAlchemyError"
    assert discovery.rollbacks == 1
    assert discovery.finished[-1]["status"] == "failed"


def test_bounded_collection_stops_at_max_records():
    records = [_raw(f"R-{i}", payload=_synth_payload(query_display=f"term {i}")) for i in range(6)]
    service, _, observations = _service(_StaticAdapter(records))
    result = service(
        SearchInterestCollectionConfig(source=_StaticAdapter.source_id, max_records=3)
    )
    assert result.fetched == 3
    assert len(observations._keys) == 3


# ---------------------------------------------------------------------------
# Migration head (DB-free)
# ---------------------------------------------------------------------------


def test_migration_head_is_0028_linear_off_0027():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config("alembic.ini")
    config.set_main_option("script_location", "alembic")
    script = ScriptDirectory.from_config(config)
    assert tuple(script.get_heads()) in (("0028",), ("0029",))
    rev = script.get_revision("0028")
    assert rev is not None and rev.down_revision == "0027"



# ---------------------------------------------------------------------------
# DB-backed
# ---------------------------------------------------------------------------


def _run(adapter):
    Session = make_session()
    with Session() as session:
        result = CollectSearchInterest(
            adapter=adapter,
            discovery=DiscoveryRepositorySQL(session),
            observations=SearchInterestRepositorySQL(session),
        )(SearchInterestCollectionConfig(source=adapter.source_id))
    return result, Session


def test_search_interest_table_exists_with_indexes(db):
    Session = make_session()
    with Session() as session:
        insp = inspect(session.bind)
        assert insp.has_table("search_interest_observations")
        index_names = {ix["name"] for ix in insp.get_indexes("search_interest_observations")}
        assert {
            "uq_search_interest_observations_raw_source_record",
            "ix_search_interest_observations_query_geo_period",
            "ix_search_interest_observations_source_observed_at",
        } <= index_names


def test_synthetic_run_persists_observations_and_provenance(db):
    result, Session = _run(SyntheticSearchInterestAdapter())
    assert result.status == "completed"
    assert result.inserted == len(SYNTHETIC_SEARCH_INTEREST_RECORDS)
    with Session() as session:
        rows = session.execute(
            select(SearchInterestObservation).order_by(SearchInterestObservation.query_key)
        ).scalars().all()
        assert len(rows) == len(SYNTHETIC_SEARCH_INTEREST_RECORDS)
        assert all(row.source == SYNTHETIC_SEARCH_INTEREST_SOURCE_ID for row in rows)
        assert all(row.synthetic for row in rows)
        assert all(row.is_relative for row in rows)
        # Provenance: every observation links a raw record and the run.
        assert all(row.raw_source_record_id is not None for row in rows)
        assert all(row.collection_run_id == result.run_id for row in rows)
        assert session.execute(
            select(func.count()).select_from(RawSourceRecordModel)
        ).scalar_one() == len(SYNTHETIC_SEARCH_INTEREST_RECORDS)
        assert session.execute(
            select(func.count()).select_from(CollectionRun)
        ).scalar_one() == 1


def test_collection_is_idempotent_for_identical_payloads(db):
    _run(SyntheticSearchInterestAdapter())
    second, Session = _run(SyntheticSearchInterestAdapter())
    assert (second.inserted, second.skipped) == (0, len(SYNTHETIC_SEARCH_INTEREST_RECORDS))
    with Session() as session:
        assert session.execute(
            select(func.count()).select_from(SearchInterestObservation)
        ).scalar_one() == len(SYNTHETIC_SEARCH_INTEREST_RECORDS)


def test_natural_key_dedup_keeps_one_observation_from_changed_payload(db):
    base = _synth_payload(query_display="cotton overshirt")
    changed = dict(base)
    changed["note"] = "re-fetched with an extra field"
    adapter = _StaticAdapter(
        [_raw("R-1", payload=base), _raw("R-2", payload=changed)]
    )
    result, Session = _run(adapter)
    assert (result.inserted, result.skipped) == (1, 1)
    with Session() as session:
        assert session.execute(
            select(func.count()).select_from(SearchInterestObservation)
        ).scalar_one() == 1


def test_missing_and_suppressed_values_persist_as_null(db):
    _run(SyntheticSearchInterestAdapter())
    Session = make_session()
    with Session() as session:
        row = session.execute(
            select(SearchInterestObservation).where(
                SearchInterestObservation.query_key == "cotton_overshirt"
            )
        ).scalar_one()
        assert row.value is None
        assert row.value_status == "suppressed"


def test_source_timestamp_is_distinct_from_collection_time(db):
    _run(SyntheticSearchInterestAdapter())
    Session = make_session()
    with Session() as session:
        row = session.execute(
            select(SearchInterestObservation).where(
                SearchInterestObservation.query_key == "oversized_denim_jacket"
            )
        ).scalar_one()
        assert row.source_timestamp == datetime(2026, 1, 12, tzinfo=timezone.utc)
        assert row.observed_at is not None
        assert row.observed_at > row.source_timestamp
        # ST-004 supplied no source timestamp; it is never invented.
        no_ts = session.execute(
            select(SearchInterestObservation).where(
                SearchInterestObservation.query_key == "m:synthetic_topic"
            )
        ).scalar_one()
        assert no_ts.source_timestamp is None


def test_observations_in_window_filters_by_period(db):
    _run(SyntheticSearchInterestAdapter())
    Session = make_session()
    with Session() as session:
        repo = SearchInterestRepositorySQL(session)
        first_week = repo.observations_in_window(
            window_start=_WEEK[0], window_end=_WEEK[1]
        )
        both_weeks = repo.observations_in_window(
            window_start=_WEEK[0], window_end=_WEEK_2[1]
        )
    assert {e.query_key for e in first_week} == {
        "oversized_denim_jacket",
        "wide_leg_cargo_pants",
        "m:synthetic_topic",
    }
    assert len(both_weeks) == len(SYNTHETIC_SEARCH_INTEREST_RECORDS)
    assert all(e.is_relative and e.synthetic for e in both_weeks)


def test_geographic_compatibility_keeps_series_separate(db):
    _run(SyntheticSearchInterestAdapter())
    Session = make_session()
    with Session() as session:
        rows = session.execute(
            select(SearchInterestObservation).where(
                SearchInterestObservation.query_key == "wide_leg_cargo_pants"
            )
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].geo_scope == "IN" and rows[0].geo_scope_type == "country"


def test_search_interest_rows_never_enter_the_product_path(db):
    result, Session = _run(SyntheticSearchInterestAdapter())
    assert result.inserted > 0
    with Session() as session:
        assert session.execute(
            select(func.count()).select_from(ProductObservation)
        ).scalar_one() == 0
        # D6's product-observation reader sees nothing from this table.
        evidence = TrendRepositorySQL(session).observations_in_window(
            window_start=_WEEK[0], window_end=_WEEK_2[1]
        )
        assert evidence == ()


def test_check_constraint_rejects_value_with_non_present_status(db):
    Session = make_session()
    with Session() as session:
        session.add(
            SearchInterestObservation(
                source=SYNTHETIC_SEARCH_INTEREST_SOURCE_ID,
                metric=METRIC_SEARCH_INTEREST,
                query_kind="search_term",
                query_key="k",
                query_display="k",
                geo_scope="worldwide",
                geo_scope_type="worldwide",
                aggregation_interval="weekly",
                period_start=_WEEK[0],
                period_end=_WEEK[1],
                value=5.0,
                value_scale="synthetic_relative_index_v1",
                value_status="missing",
                query_config_version="synthetic_v1",
                synthetic=True,
                payload_hash=payload_hash({"k": "k"}),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_search_interest_downgrade_removes_and_upgrade_restores(migrated_db):
    from alembic import command
    from alembic.config import Config

    config = Config("alembic.ini")
    config.set_main_option("script_location", "alembic")
    Session = make_session()
    try:
        command.downgrade(config, "0027")
        with Session() as session:
            insp = inspect(session.bind)
            assert not insp.has_table("search_interest_observations")
            assert insp.has_table("product_observations")  # D5 table untouched
    finally:
        command.upgrade(config, "head")
    with Session() as session:
        assert inspect(session.bind).has_table("search_interest_observations")
