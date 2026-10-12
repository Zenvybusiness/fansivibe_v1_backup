"""D9B Stage 2: Media attention persistence and repository tests.

Validates the dedicated `media_attention_observations` and
`media_attention_contributing_records` relational schema, Alembic migration 0029,
and `MediaAttentionRepositorySQL` adapter against the project's supported PostgreSQL
test environment.

Test Matrix:
- Protocol conformance and frozen architecture boundaries.
- Empirical zero vs positive observation persistence.
- All 4 approved status pairs and rejection of invalid status combinations.
- NOT NULL constraints, negative counts, negative values, and count hierarchy violations.
- PostgreSQL-specific NaN, +Infinity, and -Infinity numeric rejection.
- Natural-key idempotency and multi-version coexistence (query_config_version, clustering_version).
- Multi-threaded concurrent duplicate insertion.
- Transactional atomicity: partial persistence failure leaves zero orphan observations.
- Provenance cascade deletion on raw-record pruning while preserving observation metrics.
- Operational provenance pruning and safe relinking of existing observations.
- Window queries and contributing-record drilldown.
"""

from __future__ import annotations

import concurrent.futures
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.ports.repositories import MediaAttentionRepository
from app.domain.services.media_attention import (
    COMPLETENESS_COMPLETE,
    COMPLETENESS_TRUNCATED,
    COMPLETENESS_UNAVAILABLE,
    DEFAULT_CLUSTERING_VERSION,
    DEFAULT_QUERY_CONFIG_VERSION,
    DEFAULT_VALUE_SCALE,
    GEO_TYPE_COUNTRY,
    METRIC_MEDIA_ATTENTION,
    QUERY_KIND_CONCEPT,
    SOURCE_GDELT_DOC,
    STATUS_INVALID,
    STATUS_MISSING,
    STATUS_PRESENT,
    STATUS_SUPPRESSED,
    ContributingRecordAssignment,
    MediaAttentionEvidence,
    MediaAttentionObservation,
)
from app.domain.services.trends import DEMAND_SIGNAL_AVAILABLE
from app.infrastructure.db.models import (
    CollectionRun,
    MediaAttentionContributingRecord as MediaAttentionContributingRecordModel,
    MediaAttentionObservation as MediaAttentionObservationModel,
    RawSourceRecord,
)
from app.infrastructure.db.repositories import MediaAttentionRepositorySQL
from tests.conftest import make_session

pytestmark = pytest.mark.usefixtures("db")

_T0 = datetime(2026, 1, 5, 0, 0, 0, tzinfo=timezone.utc)
_T1 = datetime(2026, 1, 12, 0, 0, 0, tzinfo=timezone.utc)
_T2 = datetime(2026, 1, 19, 0, 0, 0, tzinfo=timezone.utc)


def _create_collection_run(session: Session, source: str = SOURCE_GDELT_DOC) -> CollectionRun:
    run = CollectionRun(source=source, status="completed")
    session.add(run)
    session.commit()
    return run


def _create_raw_records(
    session: Session,
    run_id: UUID,
    count: int = 3,
    source: str = SOURCE_GDELT_DOC,
    created_at: datetime | None = None,
) -> list[RawSourceRecord]:
    records: list[RawSourceRecord] = []
    for i in range(count):
        raw = RawSourceRecord(
            collection_run_id=run_id,
            source=source,
            source_record_id=f"doc-{uuid4()}",
            payload={"url": f"https://example.com/article-{i}", "title": f"Fashion Story {i}"},
            payload_hash=f"hash-{uuid4()}",
        )
        if created_at is not None:
            raw.created_at = created_at
        session.add(raw)
        records.append(raw)
    session.commit()
    return records


def _make_domain_observation(
    *,
    period_start: datetime = _T0,
    period_end: datetime = _T1,
    query_key: str = "quiet_luxury",
    query_display: str = "Quiet Luxury",
    value_status: str = STATUS_PRESENT,
    completeness_status: str = COMPLETENESS_COMPLETE,
    value: float | None = 2.0,
    raw_article_count: int | None = None,
    distinct_outlet_count: int | None = None,
    estimated_deduplicated_story_count: int | None = None,
    query_config_version: str = DEFAULT_QUERY_CONFIG_VERSION,
    clustering_version: str = DEFAULT_CLUSTERING_VERSION,
    source: str = SOURCE_GDELT_DOC,
    geo_scope: str = "IN",
    synthetic: bool = False,
) -> MediaAttentionObservation:
    if value_status == STATUS_PRESENT:
        if value is None:
            value = 2.0
        if estimated_deduplicated_story_count is None:
            estimated_deduplicated_story_count = int(value)
        if raw_article_count is None:
            raw_article_count = max(3, estimated_deduplicated_story_count) if value > 0 else 0
        if distinct_outlet_count is None:
            distinct_outlet_count = min(raw_article_count, max(1, estimated_deduplicated_story_count)) if value > 0 else 0
    else:
        value = None
        raw_article_count = None
        distinct_outlet_count = None
        estimated_deduplicated_story_count = None

    return MediaAttentionObservation(
        source=source,
        metric=METRIC_MEDIA_ATTENTION,
        query_kind=QUERY_KIND_CONCEPT,
        query_key=query_key,
        query_display=query_display,
        geo_scope=geo_scope,
        geo_scope_type=GEO_TYPE_COUNTRY,
        aggregation_interval="rolling_7d",
        period_start=period_start,
        period_end=period_end,
        value_status=value_status,
        completeness_status=completeness_status,
        value=value,
        value_scale=DEFAULT_VALUE_SCALE,
        raw_article_count=raw_article_count,
        distinct_outlet_count=distinct_outlet_count,
        estimated_deduplicated_story_count=estimated_deduplicated_story_count,
        query_config_version=query_config_version,
        clustering_version=clustering_version,
        contributing_raw_record_count=raw_article_count or 0,
        provenance_pruned=False,
        is_relative=False,
        synthetic=synthetic,
    )


# ---------------------------------------------------------------------------
# 1. Architecture Boundaries & Protocol Conformance
# ---------------------------------------------------------------------------


def test_repository_protocol_conformance(db: None, migrated_db: str) -> None:
    SessionClass = make_session(migrated_db)
    with SessionClass() as session:
        repo = MediaAttentionRepositorySQL(session)
        assert isinstance(repo, MediaAttentionRepository)


def test_frozen_boundaries_invariants() -> None:
    assert DEMAND_SIGNAL_AVAILABLE is False
    assert METRIC_MEDIA_ATTENTION == "media_attention"


# ---------------------------------------------------------------------------
# 2. Empirical Zero & Positive Observation Persistence
# ---------------------------------------------------------------------------


def test_persist_empirical_zero_observation(db: None, migrated_db: str) -> None:
    SessionClass = make_session(migrated_db)
    with SessionClass() as session:
        run = _create_collection_run(session)
        repo = MediaAttentionRepositorySQL(session)

        zero_obs = _make_domain_observation(
            query_key="rare_trend",
            query_display="Rare Trend",
            value=0.0,
            raw_article_count=0,
            distinct_outlet_count=0,
            estimated_deduplicated_story_count=0,
        )

        obs_id, created = repo.insert_observation_with_contributing_records(
            observation=zero_obs,
            run_id=run.id,
            contributing_records=(),
        )

        assert created is True
        assert isinstance(obs_id, UUID)

        # Verify persisted state in PostgreSQL
        row = session.get(MediaAttentionObservationModel, obs_id)
        assert row is not None
        assert row.value == 0.0
        assert row.raw_article_count == 0
        assert row.distinct_outlet_count == 0
        assert row.estimated_deduplicated_story_count == 0
        assert row.contributing_raw_record_count == 0
        assert row.value_status == STATUS_PRESENT
        assert row.completeness_status == COMPLETENESS_COMPLETE
        assert row.provenance_pruned is False

        # Zero contributing records in join table
        links = repo.get_contributing_records(observation_id=obs_id)
        assert links == ()


def test_persist_positive_observation_with_provenance(db: None, migrated_db: str) -> None:
    SessionClass = make_session(migrated_db)
    with SessionClass() as session:
        run = _create_collection_run(session)
        raw_recs = _create_raw_records(session, run.id, count=3)
        repo = MediaAttentionRepositorySQL(session)

        cluster_a = uuid4()
        cluster_b = uuid4()
        assignments = (
            ContributingRecordAssignment(
                raw_source_record_id=raw_recs[0].id,
                similarity_cluster_id=cluster_a,
                is_canonical=True,
                outlet_domain="vogue.in",
            ),
            ContributingRecordAssignment(
                raw_source_record_id=raw_recs[1].id,
                similarity_cluster_id=cluster_a,
                is_canonical=False,
                outlet_domain="gqindia.com",
            ),
            ContributingRecordAssignment(
                raw_source_record_id=raw_recs[2].id,
                similarity_cluster_id=cluster_b,
                is_canonical=True,
                outlet_domain="timesofindia.indiatimes.com",
            ),
        )

        obs = _make_domain_observation(
            query_key="quiet_luxury",
            value=2.0,
            raw_article_count=3,
            distinct_outlet_count=3,
            estimated_deduplicated_story_count=2,
        )

        obs_id, created = repo.insert_observation_with_contributing_records(
            observation=obs,
            run_id=run.id,
            contributing_records=assignments,
        )

        assert created is True
        row = session.get(MediaAttentionObservationModel, obs_id)
        assert row is not None
        assert row.value == 2.0
        assert row.raw_article_count == 3
        assert row.distinct_outlet_count == 3
        assert row.estimated_deduplicated_story_count == 2
        assert row.contributing_raw_record_count == 3

        # Verify drill-down contributing records
        retrieved = repo.get_contributing_records(observation_id=obs_id)
        assert len(retrieved) == 3
        # Canonical articles are sorted first by query
        assert retrieved[0].is_canonical is True
        assert {r.raw_source_record_id for r in retrieved} == {r.id for r in raw_recs}


# ---------------------------------------------------------------------------
# 3. All Four Approved Status Pairs and Rejected Status Combinations
# ---------------------------------------------------------------------------


def test_all_four_approved_status_pairs_persist(db: None, migrated_db: str) -> None:
    SessionClass = make_session(migrated_db)
    with SessionClass() as session:
        run = _create_collection_run(session)
        repo = MediaAttentionRepositorySQL(session)

        # 1. present, complete
        obs_1 = _make_domain_observation(
            period_start=_T0,
            period_end=_T1,
            query_key="concept_present",
            value_status=STATUS_PRESENT,
            completeness_status=COMPLETENESS_COMPLETE,
            value=1.0,
            raw_article_count=1,
            distinct_outlet_count=1,
            estimated_deduplicated_story_count=1,
        )
        id_1, _ = repo.insert_observation_with_contributing_records(observation=obs_1, run_id=run.id)
        assert id_1 is not None

        # 2. suppressed, truncated
        obs_2 = _make_domain_observation(
            period_start=_T0,
            period_end=_T1,
            query_key="concept_suppressed",
            value_status=STATUS_SUPPRESSED,
            completeness_status=COMPLETENESS_TRUNCATED,
            value=None,
            raw_article_count=None,
            distinct_outlet_count=None,
            estimated_deduplicated_story_count=None,
        )
        id_2, _ = repo.insert_observation_with_contributing_records(observation=obs_2, run_id=run.id)
        assert id_2 is not None

        # 3. missing, unavailable
        obs_3 = _make_domain_observation(
            period_start=_T0,
            period_end=_T1,
            query_key="concept_missing",
            value_status=STATUS_MISSING,
            completeness_status=COMPLETENESS_UNAVAILABLE,
            value=None,
            raw_article_count=None,
            distinct_outlet_count=None,
            estimated_deduplicated_story_count=None,
        )
        id_3, _ = repo.insert_observation_with_contributing_records(observation=obs_3, run_id=run.id)
        assert id_3 is not None

        # 4. invalid, unavailable
        obs_4 = _make_domain_observation(
            period_start=_T0,
            period_end=_T1,
            query_key="concept_invalid",
            value_status=STATUS_INVALID,
            completeness_status=COMPLETENESS_UNAVAILABLE,
            value=None,
            raw_article_count=None,
            distinct_outlet_count=None,
            estimated_deduplicated_story_count=None,
        )
        id_4, _ = repo.insert_observation_with_contributing_records(observation=obs_4, run_id=run.id)
        assert id_4 is not None


@pytest.mark.parametrize(
    "v_status, c_status",
    [
        ("present", "truncated"),
        ("present", "unavailable"),
        ("suppressed", "complete"),
        ("missing", "complete"),
        ("invalid", "complete"),
        ("invalid", "truncated"),
        ("present", "unknown_completeness"),
        ("unapproved_status", "complete"),
    ],
)
def test_rejected_status_combinations_db_check(
    db: None, migrated_db: str, v_status: str, c_status: str
) -> None:
    SessionClass = make_session(migrated_db)
    with SessionClass() as session:
        run = _create_collection_run(session)

        # Directly insert into DB to bypass python domain validation and test SQL check constraint
        row = MediaAttentionObservationModel(
            collection_run_id=run.id,
            source="gdelt_doc",
            metric="media_attention",
            query_kind="concept",
            query_key="bad_status_test",
            query_display="Bad Status Test",
            geo_scope="IN",
            geo_scope_type="country",
            aggregation_interval="rolling_7d",
            period_start=_T0,
            period_end=_T1,
            value=1.0 if v_status == "present" else None,
            value_scale="estimated_deduplicated_stories_v1",
            value_status=v_status,
            completeness_status=c_status,
            raw_article_count=1 if v_status == "present" else None,
            distinct_outlet_count=1 if v_status == "present" else None,
            estimated_deduplicated_story_count=1 if v_status == "present" else None,
            query_config_version="v1",
            clustering_version="v1",
        )
        session.add(row)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


# ---------------------------------------------------------------------------
# 4. Numeric Constraints, NULL Checks, NaN, Infinity on PostgreSQL
# ---------------------------------------------------------------------------


def test_null_status_rejected_by_not_null(db: None, migrated_db: str) -> None:
    SessionClass = make_session(migrated_db)
    with SessionClass() as session:
        # value_status is NULL
        session.add(
            MediaAttentionObservationModel(
                source="gdelt_doc",
                metric="media_attention",
                query_kind="concept",
                query_key="k1",
                query_display="K1",
                geo_scope="IN",
                geo_scope_type="country",
                aggregation_interval="rolling_7d",
                period_start=_T0,
                period_end=_T1,
                value=None,
                value_scale="v1",
                value_status=None,  # type: ignore[arg-type]
                completeness_status="complete",
                query_config_version="v1",
                clustering_version="v1",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_present_with_null_metrics_rejected_by_check(db: None, migrated_db: str) -> None:
    SessionClass = make_session(migrated_db)
    with SessionClass() as session:
        # value_status = 'present' but value is NULL
        session.add(
            MediaAttentionObservationModel(
                source="gdelt_doc",
                metric="media_attention",
                query_kind="concept",
                query_key="k2",
                query_display="K2",
                geo_scope="IN",
                geo_scope_type="country",
                aggregation_interval="rolling_7d",
                period_start=_T0,
                period_end=_T1,
                value=None,
                value_scale="v1",
                value_status="present",
                completeness_status="complete",
                raw_article_count=1,
                distinct_outlet_count=1,
                estimated_deduplicated_story_count=1,
                query_config_version="v1",
                clustering_version="v1",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_negative_counts_rejected_by_check(db: None, migrated_db: str) -> None:
    SessionClass = make_session(migrated_db)
    with SessionClass() as session:
        # raw_article_count = -1
        session.add(
            MediaAttentionObservationModel(
                source="gdelt_doc",
                metric="media_attention",
                query_kind="concept",
                query_key="k3",
                query_display="K3",
                geo_scope="IN",
                geo_scope_type="country",
                aggregation_interval="rolling_7d",
                period_start=_T0,
                period_end=_T1,
                value=1.0,
                value_scale="v1",
                value_status="present",
                completeness_status="complete",
                raw_article_count=-1,
                distinct_outlet_count=1,
                estimated_deduplicated_story_count=1,
                query_config_version="v1",
                clustering_version="v1",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_count_hierarchy_violations_rejected_by_check(db: None, migrated_db: str) -> None:
    SessionClass = make_session(migrated_db)
    with SessionClass() as session:
        # Violation 1: distinct_outlets > raw
        session.add(
            MediaAttentionObservationModel(
                source="gdelt_doc",
                metric="media_attention",
                query_kind="concept",
                query_key="k4",
                query_display="K4",
                geo_scope="IN",
                geo_scope_type="country",
                aggregation_interval="rolling_7d",
                period_start=_T0,
                period_end=_T1,
                value=2.0,
                value_scale="v1",
                value_status="present",
                completeness_status="complete",
                raw_article_count=2,
                distinct_outlet_count=3,  # > raw
                estimated_deduplicated_story_count=2,
                query_config_version="v1",
                clustering_version="v1",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        # Violation 2: value != stories
        session.add(
            MediaAttentionObservationModel(
                source="gdelt_doc",
                metric="media_attention",
                query_kind="concept",
                query_key="k5",
                query_display="K5",
                geo_scope="IN",
                geo_scope_type="country",
                aggregation_interval="rolling_7d",
                period_start=_T0,
                period_end=_T1,
                value=3.0,  # != 2.0
                value_scale="v1",
                value_status="present",
                completeness_status="complete",
                raw_article_count=2,
                distinct_outlet_count=2,
                estimated_deduplicated_story_count=2,
                query_config_version="v1",
                clustering_version="v1",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_postgresql_nan_and_infinity_rejected(db: None, migrated_db: str) -> None:
    from sqlalchemy.exc import DataError

    SessionClass = make_session(migrated_db)
    with SessionClass() as session:
        # 1. Test NaN insertion via raw SQL: rejected by check constraint
        nan_insert = text("""
            INSERT INTO media_attention_observations (
                source, metric, query_kind, query_key, query_display,
                geo_scope, geo_scope_type, aggregation_interval,
                period_start, period_end, value, value_scale,
                value_status, completeness_status,
                raw_article_count, distinct_outlet_count, estimated_deduplicated_story_count,
                query_config_version, clustering_version
            ) VALUES (
                'gdelt_doc', 'media_attention', 'concept', 'nan_test', 'NaN Test',
                'IN', 'country', 'rolling_7d',
                '2026-01-05 00:00:00+00', '2026-01-12 00:00:00+00',
                'NaN'::numeric, 'scale_v1',
                'present', 'complete',
                1, 1, 1,
                'v1', 'v1'
            );
        """)
        with pytest.raises((IntegrityError, DataError)):
            session.execute(nan_insert)
            session.commit()
        session.rollback()

        # 2. Test +Infinity insertion via raw SQL: rejected by numeric column type / check
        inf_insert = text("""
            INSERT INTO media_attention_observations (
                source, metric, query_kind, query_key, query_display,
                geo_scope, geo_scope_type, aggregation_interval,
                period_start, period_end, value, value_scale,
                value_status, completeness_status,
                raw_article_count, distinct_outlet_count, estimated_deduplicated_story_count,
                query_config_version, clustering_version
            ) VALUES (
                'gdelt_doc', 'media_attention', 'concept', 'inf_test', 'Inf Test',
                'IN', 'country', 'rolling_7d',
                '2026-01-05 00:00:00+00', '2026-01-12 00:00:00+00',
                'Infinity'::numeric, 'scale_v1',
                'present', 'complete',
                1, 1, 1,
                'v1', 'v1'
            );
        """)
        with pytest.raises((IntegrityError, DataError)):
            session.execute(inf_insert)
            session.commit()
        session.rollback()

        # 3. Test -Infinity insertion via raw SQL: rejected by numeric column type / check
        neg_inf_insert = text("""
            INSERT INTO media_attention_observations (
                source, metric, query_kind, query_key, query_display,
                geo_scope, geo_scope_type, aggregation_interval,
                period_start, period_end, value, value_scale,
                value_status, completeness_status,
                raw_article_count, distinct_outlet_count, estimated_deduplicated_story_count,
                query_config_version, clustering_version
            ) VALUES (
                'gdelt_doc', 'media_attention', 'concept', 'neg_inf_test', 'Neg Inf Test',
                'IN', 'country', 'rolling_7d',
                '2026-01-05 00:00:00+00', '2026-01-12 00:00:00+00',
                '-Infinity'::numeric, 'scale_v1',
                'present', 'complete',
                1, 1, 1,
                'v1', 'v1'
            );
        """)
        with pytest.raises((IntegrityError, DataError)):
            session.execute(neg_inf_insert)
            session.commit()
        session.rollback()



# ---------------------------------------------------------------------------
# 5. Natural-Key Idempotency and Version Coexistence
# ---------------------------------------------------------------------------


def test_natural_key_idempotency(db: None, migrated_db: str) -> None:
    SessionClass = make_session(migrated_db)
    with SessionClass() as session:
        run = _create_collection_run(session)
        repo = MediaAttentionRepositorySQL(session)

        obs = _make_domain_observation(query_key="quiet_luxury", value=1.0)

        # First insert
        id_1, created_1 = repo.insert_observation_with_contributing_records(
            observation=obs, run_id=run.id
        )
        assert created_1 is True

        # Second insert with identical natural key
        id_2, created_2 = repo.insert_observation_with_contributing_records(
            observation=obs, run_id=run.id
        )
        assert created_2 is False
        assert id_2 == id_1

        # Exactly 1 row in table
        count = session.execute(
            select(func.count()).select_from(MediaAttentionObservationModel)
        ).scalar()
        assert count == 1


def test_multi_version_coexistence(db: None, migrated_db: str) -> None:
    SessionClass = make_session(migrated_db)
    with SessionClass() as session:
        run = _create_collection_run(session)
        repo = MediaAttentionRepositorySQL(session)

        obs_v1 = _make_domain_observation(
            query_config_version="cfg_v1",
            clustering_version="cluster_v1",
            value=2.0,
            estimated_deduplicated_story_count=2,
        )
        obs_v2 = _make_domain_observation(
            query_config_version="cfg_v2",  # Different query config version
            clustering_version="cluster_v1",
            value=3.0,
            estimated_deduplicated_story_count=3,
        )
        obs_v3 = _make_domain_observation(
            query_config_version="cfg_v1",
            clustering_version="cluster_v2",  # Different clustering version
            value=4.0,
            estimated_deduplicated_story_count=4,
        )

        id_1, created_1 = repo.insert_observation_with_contributing_records(
            observation=obs_v1, run_id=run.id
        )
        id_2, created_2 = repo.insert_observation_with_contributing_records(
            observation=obs_v2, run_id=run.id
        )
        id_3, created_3 = repo.insert_observation_with_contributing_records(
            observation=obs_v3, run_id=run.id
        )

        assert created_1 is True
        assert created_2 is True
        assert created_3 is True
        assert len({id_1, id_2, id_3}) == 3

        # All 3 exist without overwriting each other
        rows = session.execute(
            select(MediaAttentionObservationModel).order_by(
                MediaAttentionObservationModel.created_at
            )
        ).scalars().all()
        assert len(rows) == 3
        assert rows[0].value == 2.0
        assert rows[1].value == 3.0
        assert rows[2].value == 4.0


# ---------------------------------------------------------------------------
# 6. Multi-Threaded Concurrent Duplicate Insertion
# ---------------------------------------------------------------------------


def test_concurrent_duplicate_insertion(db: None, migrated_db: str) -> None:
    SessionClass = make_session(migrated_db)

    with SessionClass() as init_session:
        run = _create_collection_run(init_session)
        run_id = run.id

    obs = _make_domain_observation(query_key="concurrent_luxury", value=1.0)

    def worker_insert() -> tuple[UUID, bool]:
        with SessionClass() as worker_session:
            worker_repo = MediaAttentionRepositorySQL(worker_session)
            return worker_repo.insert_observation_with_contributing_records(
                observation=obs,
                run_id=run_id,
                contributing_records=(),
            )

    # Launch 4 concurrent insertion workers
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(worker_insert) for _ in range(4)]
        results = [f.result() for f in futures]

    created_flags = [r[1] for r in results]
    returned_ids = {r[0] for r in results}

    # Exactly 1 created=True, exactly 1 unique observation ID returned
    assert created_flags.count(True) == 1
    assert created_flags.count(False) == 3
    assert len(returned_ids) == 1

    with SessionClass() as verify_session:
        total = verify_session.execute(
            select(func.count()).select_from(MediaAttentionObservationModel)
        ).scalar()
        assert total == 1


# ---------------------------------------------------------------------------
# 7. Transactional Atomicity Between Observations and Provenance Links
# ---------------------------------------------------------------------------


def test_atomicity_partial_persistence_failure_rolls_back(
    db: None, migrated_db: str
) -> None:
    SessionClass = make_session(migrated_db)
    with SessionClass() as session:
        run = _create_collection_run(session)
        raw_recs = _create_raw_records(session, run.id, count=1)
        repo = MediaAttentionRepositorySQL(session)

        # 1 valid raw ID and 1 non-existent raw ID to trigger foreign key violation
        bad_raw_id = uuid4()
        assignments = (
            ContributingRecordAssignment(
                raw_source_record_id=raw_recs[0].id,
                similarity_cluster_id=uuid4(),
                is_canonical=True,
                outlet_domain="vogue.in",
            ),
            ContributingRecordAssignment(
                raw_source_record_id=bad_raw_id,
                similarity_cluster_id=uuid4(),
                is_canonical=False,
                outlet_domain="fake.com",
            ),
        )

        obs = _make_domain_observation(query_key="atomicity_test", value=1.0)

        with pytest.raises(IntegrityError):
            repo.insert_observation_with_contributing_records(
                observation=obs,
                run_id=run.id,
                contributing_records=assignments,
            )

        # Zero rows persisted in both tables!
        obs_count = session.execute(
            select(func.count()).select_from(MediaAttentionObservationModel)
        ).scalar()
        contrib_count = session.execute(
            select(func.count()).select_from(MediaAttentionContributingRecordModel)
        ).scalar()
        assert obs_count == 0
        assert contrib_count == 0


# ---------------------------------------------------------------------------
# 8. Provenance Pruning and Safe Relinking
# ---------------------------------------------------------------------------


def test_cascade_deletion_on_raw_record_deletion(db: None, migrated_db: str) -> None:
    SessionClass = make_session(migrated_db)
    with SessionClass() as session:
        run = _create_collection_run(session)
        raw_recs = _create_raw_records(session, run.id, count=2)
        repo = MediaAttentionRepositorySQL(session)

        assignments = (
            ContributingRecordAssignment(
                raw_source_record_id=raw_recs[0].id,
                similarity_cluster_id=uuid4(),
                is_canonical=True,
                outlet_domain="vogue.in",
            ),
            ContributingRecordAssignment(
                raw_source_record_id=raw_recs[1].id,
                similarity_cluster_id=uuid4(),
                is_canonical=False,
                outlet_domain="elle.in",
            ),
        )

        obs = _make_domain_observation(query_key="cascade_test", value=1.0)
        obs_id, _ = repo.insert_observation_with_contributing_records(
            observation=obs, run_id=run.id, contributing_records=assignments
        )

        # Verify initial link count = 2
        assert len(repo.get_contributing_records(observation_id=obs_id)) == 2

        # Delete raw_recs[0] from raw_source_records
        session.delete(raw_recs[0])
        session.commit()

        # Join row was cascaded and removed, 1 link remains
        remaining_links = repo.get_contributing_records(observation_id=obs_id)
        assert len(remaining_links) == 1
        assert remaining_links[0].raw_source_record_id == raw_recs[1].id

        # Parent observation metrics remain permanent and intact!
        parent_obs = session.get(MediaAttentionObservationModel, obs_id)
        assert parent_obs is not None
        assert parent_obs.value == 1.0
        assert parent_obs.raw_article_count == 3


def test_prune_expired_raw_records_and_safe_relink(db: None, migrated_db: str) -> None:
    SessionClass = make_session(migrated_db)
    with SessionClass() as session:
        run = _create_collection_run(session)
        cutoff = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        expired_date = cutoff - timedelta(days=10)

        # Create expired raw records
        expired_raws = _create_raw_records(
            session, run.id, count=2, created_at=expired_date
        )
        repo = MediaAttentionRepositorySQL(session)

        assignments = tuple(
            ContributingRecordAssignment(
                raw_source_record_id=r.id,
                similarity_cluster_id=uuid4(),
                is_canonical=(i == 0),
                outlet_domain="domain.com",
            )
            for i, r in enumerate(expired_raws)
        )

        obs = _make_domain_observation(query_key="pruning_test", value=1.0)
        obs_id, _ = repo.insert_observation_with_contributing_records(
            observation=obs, run_id=run.id, contributing_records=assignments
        )

        # Prune expired raw records older than cutoff
        pruned_count = repo.prune_expired_raw_records(older_than=cutoff)
        assert pruned_count == 2

        # Raw records deleted, links cascaded away, observation marked provenance_pruned
        obs_row = session.get(MediaAttentionObservationModel, obs_id)
        assert obs_row is not None
        assert obs_row.provenance_pruned is True
        assert len(repo.get_contributing_records(observation_id=obs_id)) == 0

        # Safe relinking: new raw records ingested
        new_raws = _create_raw_records(session, run.id, count=2)
        new_assignments = tuple(
            ContributingRecordAssignment(
                raw_source_record_id=r.id,
                similarity_cluster_id=uuid4(),
                is_canonical=(i == 0),
                outlet_domain="newdomain.com",
            )
            for i, r in enumerate(new_raws)
        )

        newly_linked = repo.relink_contributing_records(
            observation_id=obs_id,
            contributing_records=new_assignments,
        )
        assert newly_linked == 2

        # Reset provenance_pruned = False and updated contributing_raw_record_count
        refreshed_obs = session.get(MediaAttentionObservationModel, obs_id)
        assert refreshed_obs is not None
        assert refreshed_obs.provenance_pruned is False
        assert refreshed_obs.contributing_raw_record_count == 2


# ---------------------------------------------------------------------------
# 9. Window Query (observations_in_window)
# ---------------------------------------------------------------------------


def test_observations_in_window(db: None, migrated_db: str) -> None:
    SessionClass = make_session(migrated_db)
    with SessionClass() as session:
        run = _create_collection_run(session)
        repo = MediaAttentionRepositorySQL(session)

        # Observation 1 in Week 1
        obs_w1 = _make_domain_observation(
            period_start=_T0,
            period_end=_T1,
            query_key="streetwear",
            value=5.0,
            estimated_deduplicated_story_count=5,
        )
        # Observation 2 in Week 2
        obs_w2 = _make_domain_observation(
            period_start=_T1,
            period_end=_T2,
            query_key="streetwear",
            value=7.0,
            estimated_deduplicated_story_count=7,
        )

        repo.insert_observation_with_contributing_records(observation=obs_w1, run_id=run.id)
        repo.insert_observation_with_contributing_records(observation=obs_w2, run_id=run.id)

        # Query only Week 1
        results_w1 = repo.observations_in_window(
            window_start=_T0,
            window_end=_T1,
            query_key="streetwear",
        )
        assert len(results_w1) == 1
        assert isinstance(results_w1[0], MediaAttentionEvidence)
        assert results_w1[0].value == 5.0

        # Query full fortnight [_T0, _T2)
        results_all = repo.observations_in_window(
            window_start=_T0,
            window_end=_T2,
        )
        assert len(results_all) == 2
        assert [r.value for r in results_all] == [5.0, 7.0]
