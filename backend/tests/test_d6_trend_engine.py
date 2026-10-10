"""D6 Trend Intelligence Engine tests.

The engine is deterministic and DB-free in its core (pure computation), with a
thin read-only repository adapter tested against the disposable database. No
trend scoring/ranking API, no provider, no Qwen/MediaPipe/LLM is involved.

Coverage: timestamped aggregation, comparable-window growth, missing/
incompatible observations, zero baselines, duplicate protection, stale data /
source coverage, confidence vs strength, fixture publication blocking,
insufficient-evidence outcomes, deterministic repeatability, the FFO
projection, and regression that D6 added no migration.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.domain.services.trends import (
    CATALOG_OPERATIONAL,
    DIRECT_DEMAND,
    REASON_FIXTURE,
    REASON_NO_DEMAND,
    REASON_TOO_FEW,
    REASON_ZERO_BASELINE,
    STAGE_FLAT,
    STAGE_INSUFFICIENT,
    STAGE_RISING,
    SUPPORTING,
    ObservationEvidence,
    compute_trend_candidates,
    to_ffo_trend,
)

W0 = datetime(2026, 10, 1, tzinfo=timezone.utc)
W1 = datetime(2026, 10, 8, tzinfo=timezone.utc)  # 7-day window; midpoint Oct 4 12:00
EARLY = datetime(2026, 10, 2, tzinfo=timezone.utc)  # first half
LATE = datetime(2026, 10, 6, tzinfo=timezone.utc)   # second half


def _obs(
    category,
    *,
    when,
    source="src_a",
    product=None,
    price=None,
    availability=None,
    is_fixture=False,
):
    return ObservationEvidence(
        product_id=product or uuid4(),
        category=category,
        source=source,
        observed_at=when,
        price=price,
        availability=availability,
        is_fixture=is_fixture,
    )


def _candidate(evidence, category="tops"):
    analysis = compute_trend_candidates(evidence, window_start=W0, window_end=W1)
    return next(c for c in analysis.candidates if c.category == category)


def _balanced_volume(at, *, is_fixture=False, concept="tops", products=None):
    """8 observations = 2 sources x 2 products, all at `at` (± minutes)."""
    rows = []
    p1, p2 = products or (uuid4(), uuid4())
    for i, source in enumerate(("s1", "s2")):
        for product in (p1, p2):
            rows.append(
                _obs(
                    concept,
                    when=at + timedelta(minutes=i),
                    source=source,
                    product=product,
                    is_fixture=is_fixture,
                )
            )
    return tuple(rows)


# ---------------------------------------------------------------------------
# Pure engine
# ---------------------------------------------------------------------------


def test_catalog_growth_across_compatible_halves():
    p1, p2, p3, p4 = uuid4(), uuid4(), uuid4(), uuid4()
    evidence = (
        _obs("outerwear", when=EARLY, product=p1),
        _obs("outerwear", when=EARLY, product=p2),
        _obs("outerwear", when=LATE, product=p1),
        _obs("outerwear", when=LATE, product=p2),
        _obs("outerwear", when=LATE, product=p3),
        _obs("outerwear", when=LATE, product=p4),
    )
    candidate = _candidate(evidence, category="outerwear")
    assert candidate.concept == "outerwear"
    assert candidate.observation_count == 6
    assert candidate.distinct_products == 4
    assert candidate.catalog_growth == 1.0  # (4 - 2) / 2
    assert candidate.stage == STAGE_RISING
    assert candidate.strength == 1.0


def test_missing_observations_yield_no_candidates():
    analysis = compute_trend_candidates((), window_start=W0, window_end=W1)
    assert analysis.candidates == ()
    assert analysis.demand_trend_status == STAGE_INSUFFICIENT
    assert analysis.demand_insufficient_reason == REASON_NO_DEMAND


def test_zero_baseline_is_insufficient_not_rising():
    evidence = tuple(_obs("bottoms", when=LATE, product=uuid4()) for _ in range(3))
    candidate = _candidate(evidence, category="bottoms")
    assert candidate.catalog_growth is None  # no comparable earlier half
    assert candidate.strength is None
    assert candidate.stage == STAGE_INSUFFICIENT
    assert REASON_ZERO_BASELINE in candidate.reasons


def test_price_change_uses_only_present_prices():
    evidence = (
        _obs("tops", when=EARLY, product=uuid4(), price=100.0),
        _obs("tops", when=LATE, product=uuid4(), price=None),  # not zero
        _obs("tops", when=LATE, product=uuid4(), price=80.0),
    )
    candidate = _candidate(evidence)
    assert candidate.price_change_ratio is not None
    assert abs(candidate.price_change_ratio - (-0.2)) < 1e-9


def test_price_ratio_none_for_single_price_or_zero_baseline():
    single = _candidate(
        (
            _obs("tops", when=EARLY, product=uuid4(), price=50.0),
            _obs("tops", when=LATE, product=uuid4()),
            _obs("tops", when=LATE, product=uuid4()),
        )
    )
    assert single.price_change_ratio is None

    zero = _candidate(
        (
            _obs("tops", when=EARLY, product=uuid4(), price=0.0),
            _obs("tops", when=LATE, product=uuid4(), price=80.0),
            _obs("tops", when=LATE, product=uuid4()),
        )
    )
    assert zero.price_change_ratio is None  # divide-by-zero guarded


def test_distinct_sources_reported_as_supporting_signal():
    p1, p2 = uuid4(), uuid4()
    evidence = (
        _obs("tops", when=EARLY, source="s1", product=p1),
        _obs("tops", when=LATE, source="s2", product=p1),
        _obs("tops", when=LATE, source="s1", product=p2),
    )
    candidate = _candidate(evidence)
    assert candidate.distinct_sources == 2
    signal = {s.name: s for s in candidate.signals}["distinct_sources"]
    assert signal.kind == SUPPORTING
    assert signal.available is True
    assert signal.value == 2.0


def test_duplicate_identical_observations_do_not_inflate_growth():
    p1, p2, p3 = uuid4(), uuid4(), uuid4()
    evidence = (
        _obs("tops", when=EARLY, product=p1),
        _obs("tops", when=EARLY, product=p2),
        *(_obs("tops", when=LATE, product=p1) for _ in range(10)),  # repeats
        _obs("tops", when=LATE, product=p3),
    )
    candidate = _candidate(evidence)
    assert candidate.observation_count == 13
    assert candidate.distinct_products == 3
    # distinct products: early {p1,p2}=2, late {p1,p3}=2 -> flat, not +400%.
    assert candidate.catalog_growth == 0.0
    assert candidate.stage == STAGE_FLAT


def test_stale_data_lowers_confidence():
    fresh = _candidate(_balanced_volume(W1 - timedelta(hours=2)))
    stale = _candidate(_balanced_volume(W0 + timedelta(hours=1)))
    assert fresh.confidence > stale.confidence


def test_confidence_and_strength_are_independent():
    # High data quality, no growth: same products observed in both halves.
    products = (uuid4(), uuid4())
    flat = _candidate(
        _balanced_volume(EARLY, products=products)
        + _balanced_volume(LATE, products=products)
    )
    assert flat.catalog_growth == 0.0
    assert flat.stage == STAGE_FLAT
    # Low data quality (one source, few observations), but clear growth.
    p3, p4 = uuid4(), uuid4()
    rising = _candidate(
        (
            _obs("jackets", when=EARLY, product=p3),
            _obs("jackets", when=LATE, product=p3),
            _obs("jackets", when=LATE, product=p4),
        ),
        category="jackets",
    )
    assert rising.strength == 1.0
    assert rising.confidence < flat.confidence


def test_low_volume_candidate_is_insufficient():
    candidate = _candidate((_obs("tops", when=EARLY, product=uuid4()),))
    assert candidate.stage == STAGE_INSUFFICIENT
    assert REASON_TOO_FEW in candidate.reasons


def test_uncategorized_observations_are_ignored():
    analysis = compute_trend_candidates(
        (
            _obs(None, when=EARLY, product=uuid4()),
            _obs("tops", when=EARLY, product=uuid4()),
        ),
        window_start=W0,
        window_end=W1,
    )
    assert [c.concept for c in analysis.candidates] == ["tops"]


def test_deterministic_repeatability_and_ordering():
    evidence = tuple(
        _obs(category, when=when, product=uuid4())
        for category in ("zebra", "alpha")
        for when in (EARLY, LATE)
    )
    first = compute_trend_candidates(evidence, window_start=W0, window_end=W1)
    second = compute_trend_candidates(evidence, window_start=W0, window_end=W1)
    assert first == second
    assert [c.concept for c in first.candidates] == ["alpha", "zebra"]


def test_signal_taxonomy_kinds_are_labeled():
    candidate = _candidate(_balanced_volume(LATE))
    kinds = {s.kind for s in candidate.signals}
    assert kinds <= {DIRECT_DEMAND, SUPPORTING, CATALOG_OPERATIONAL}
    demand = [s for s in candidate.signals if s.kind == DIRECT_DEMAND]
    assert demand and all(s.available is False for s in demand)


# ---------------------------------------------------------------------------
# Fixture safety, insufficient evidence, FFO projection
# ---------------------------------------------------------------------------


def test_fixture_evidence_is_not_publishable():
    candidate = _candidate(_balanced_volume(LATE, is_fixture=True))
    assert candidate.is_fixture is True
    assert candidate.publishable is False
    assert REASON_FIXTURE in candidate.reasons
    assert to_ffo_trend(candidate) is None


def test_absent_demand_signal_blocks_publication():
    candidate = _candidate(_balanced_volume(LATE))  # good data, not fixture
    assert candidate.demand_signal_available is False
    assert candidate.publishable is False
    assert REASON_NO_DEMAND in candidate.reasons
    assert to_ffo_trend(candidate) is None


def test_ffo_projection_shape_when_publishable():
    base = _candidate(_balanced_volume(LATE))
    publishable = replace(
        base,
        is_fixture=False,
        demand_signal_available=True,
        publishable=True,
        stage=STAGE_RISING,
    )
    ffo = to_ffo_trend(publishable)
    assert ffo is not None
    for key in (
        "trend_id",
        "canonical_name",
        "stage",
        "confidence",
        "growth",
        "first_detected",
        "last_updated",
        "provenance",
        "signals",
    ):
        assert key in ffo
    assert ffo["provenance"]["source_type"] == "INFERRED"
    assert all(isinstance(s["value"], float) for s in ffo["signals"])


def test_migration_head_is_single_revision_0028():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config("alembic.ini")
    config.set_main_option("script_location", "alembic")
    script = ScriptDirectory.from_config(config)
    # D6 added no migration of its own; D9B's 0028 is now the single head.
    assert tuple(script.get_heads()) == ("0028",)


# ---------------------------------------------------------------------------
# Repository adapter (disposable DB)
# ---------------------------------------------------------------------------


def _run_fixture():
    from app.application.collection import CollectSource, CollectionConfig
    from app.infrastructure.db.repositories import DiscoveryRepositorySQL
    from app.infrastructure.external.fixture_source import FixtureSourceAdapter
    from tests.conftest import make_session

    Session = make_session()
    adapter = FixtureSourceAdapter()
    with Session() as session:
        result = CollectSource(
            adapter=adapter, repository=DiscoveryRepositorySQL(session)
        )(CollectionConfig(source=adapter.source_id))
    return result, Session


_WIDE = (datetime(2000, 1, 1, tzinfo=timezone.utc), datetime(2100, 1, 1, tzinfo=timezone.utc))


def test_repository_shapes_fixture_evidence(db):
    from app.infrastructure.db.repositories import TrendRepositorySQL

    result, Session = _run_fixture()
    assert result.inserted == 3
    with Session() as session:
        evidence = TrendRepositorySQL(session).observations_in_window(
            window_start=_WIDE[0], window_end=_WIDE[1]
        )
    assert len(evidence) == 3
    assert {e.category for e in evidence} == {"outerwear", "bottoms"}
    assert all(e.source == "fixture_catalog" for e in evidence)
    assert all(e.is_fixture is True for e in evidence)
    assert all(e.price == 1299.0 for e in evidence)


def test_repository_window_excludes_observations_outside_bounds(db):
    from app.infrastructure.db.repositories import TrendRepositorySQL

    _, Session = _run_fixture()
    with Session() as session:
        repo = TrendRepositorySQL(session)
        past = repo.observations_in_window(
            window_start=datetime(2000, 1, 1, tzinfo=timezone.utc),
            window_end=datetime(2001, 1, 1, tzinfo=timezone.utc),
        )
    assert past == ()


def test_end_to_end_fixture_candidates_are_not_publishable(db):
    from app.application.trends import AnalyzeTrends, TrendConfig
    from app.infrastructure.db.repositories import TrendRepositorySQL

    _, Session = _run_fixture()
    with Session() as session:
        analysis = AnalyzeTrends(repository=TrendRepositorySQL(session))(
            TrendConfig(window_start=_WIDE[0], window_end=_WIDE[1])
        )
    assert analysis.demand_trend_status == STAGE_INSUFFICIENT
    assert {c.concept for c in analysis.candidates} == {"outerwear", "bottoms"}
    assert all(c.is_fixture and not c.publishable for c in analysis.candidates)
    assert all(to_ffo_trend(c) is None for c in analysis.candidates)
