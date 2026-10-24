"""Tests for fashion catalog seed adapter and collection integration (TASK DISCOVERY-02).

Covers:
- Source adapter contract compliance
- Fixture schema validation
- Category coverage (tops, bottoms, outerwear, footwear, accessories >= 50)
- Stable identifiers and deterministic payloads
- Product normalization and identity resolution
- Synthetic-fixture labeling
- Repeated-run idempotency
- Duplicate and invalid records
- Database persistence and observation integrity
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.application.collection import CollectSource, CollectionConfig, main
from app.domain.ports.source_adapter import RawSourceRecord, SourceBatch
from app.domain.services.normalization import (
    _clean_gtin,
    _gtin_check_digit_ok,
    normalize_product,
    payload_hash,
)
from app.domain.services.product_identity import (
    MATCH_EXACT,
    MATCH_NONE,
    MATCH_VERIFIED,
    IdentityCandidates,
    resolve_identity,
)
from app.infrastructure.db.models import (
    CollectionRun,
    Product,
    ProductObservation,
    ProductSourceMap,
    RawSourceRecord as RawSourceRecordModel,
)
from app.infrastructure.db.repositories import DiscoveryRepositorySQL
from app.infrastructure.external.fashion_catalog_seed import (
    FASHION_SEED_RECORDS,
    FASHION_SEED_SOURCE_ID,
    FashionCatalogSeedAdapter,
    compute_test_gtin14,
)
from tests.conftest import make_session


# ---------------------------------------------------------------------------
# Unit Tests (DB-Free)
# ---------------------------------------------------------------------------


def test_adapter_source_id() -> None:
    adapter = FashionCatalogSeedAdapter()
    assert adapter.source_id == FASHION_SEED_SOURCE_ID
    assert adapter.source_id == "fashion_seed"


def test_adapter_fetch_batch_default() -> None:
    adapter = FashionCatalogSeedAdapter(page_size=50)
    batch = adapter.fetch_batch(limit=50)
    assert batch.source == "fashion_seed"
    assert len(batch.records) == 50
    assert batch.continuation == "50"

    batch2 = adapter.fetch_batch(continuation=batch.continuation, limit=50)
    assert batch2.source == "fashion_seed"
    assert len(batch2.records) == 10
    assert batch2.continuation is None


def test_adapter_fetch_batch_custom_limit() -> None:
    adapter = FashionCatalogSeedAdapter(page_size=25)
    batch1 = adapter.fetch_batch(limit=20)
    assert len(batch1.records) == 20
    assert batch1.continuation == "20"

    batch2 = adapter.fetch_batch(continuation="20", limit=20)
    assert len(batch2.records) == 20
    assert batch2.continuation == "40"


def test_adapter_empty_records() -> None:
    adapter = FashionCatalogSeedAdapter(records=(), page_size=10)
    batch = adapter.fetch_batch()
    assert len(batch.records) == 0
    assert batch.continuation is None


def test_all_records_normalize_successfully() -> None:
    assert len(FASHION_SEED_RECORDS) >= 50
    for raw in FASHION_SEED_RECORDS:
        result = normalize_product(raw)
        assert result.ok, f"Record {raw.source_record_id} failed normalization: {result.errors}"
        prod = result.product
        assert prod is not None
        assert prod.title.startswith("[Seed]")
        assert prod.source == FASHION_SEED_SOURCE_ID
        assert prod.source_product_id == raw.source_record_id
        assert prod.brand is not None and len(prod.brand) > 0
        assert prod.category in {"tops", "bottoms", "outerwear", "footwear", "accessories"}
        assert prod.subcategory is not None and len(prod.subcategory) > 0
        assert prod.price is not None and prod.price > 0
        assert prod.currency == "INR"
        assert prod.availability is True
        assert prod.product_url is not None and prod.product_url.startswith("https://")
        assert len(prod.image_urls) > 0
        assert prod.image_urls[0].startswith("/static/fixtures/fashion/") or prod.image_urls[0].startswith("http")
        assert "cdn.fixture.test" not in prod.image_urls[0]


def test_category_coverage() -> None:
    categories: dict[str, int] = {}
    for raw in FASHION_SEED_RECORDS:
        cat = raw.payload.get("category")
        assert cat is not None
        categories[cat] = categories.get(cat, 0) + 1

    expected_categories = {"tops", "bottoms", "outerwear", "footwear", "accessories"}
    assert set(categories.keys()) == expected_categories
    assert categories["tops"] >= 10
    assert categories["bottoms"] >= 10
    assert categories["outerwear"] >= 10
    assert categories["footwear"] >= 10
    assert categories["accessories"] >= 10
    assert sum(categories.values()) == len(FASHION_SEED_RECORDS) == 60


def test_stable_identifiers_and_deterministic_payload_hash() -> None:
    record_ids = [r.source_record_id for r in FASHION_SEED_RECORDS]
    assert len(record_ids) == len(set(record_ids)), "All source_record_ids must be unique"

    for r in FASHION_SEED_RECORDS:
        assert r.source_record_id is not None
        assert r.source_record_id.startswith("SEED-")
        hash1 = payload_hash(r.payload)
        hash2 = payload_hash(r.payload)
        assert hash1 == hash2, "Payload hash must be deterministic"
        assert len(hash1) == 64


def test_gtin_validation_and_check_digits() -> None:
    for i in range(1, 61):
        gtin = compute_test_gtin14(i)
        assert len(gtin) == 14
        assert _gtin_check_digit_ok(gtin)
        assert _clean_gtin(gtin) == gtin

    for raw in FASHION_SEED_RECORDS:
        raw_gtin = raw.payload.get("gtin")
        assert raw_gtin is not None
        cleaned = _clean_gtin(raw_gtin)
        assert cleaned is not None
        assert len(cleaned) == 14
        assert _gtin_check_digit_ok(cleaned)


def test_synthetic_fixture_labeling() -> None:
    for raw in FASHION_SEED_RECORDS:
        attrs = raw.payload.get("attributes", {})
        assert attrs.get("fixture") is True, f"Record {raw.source_record_id} must have fixture=True"
        assert attrs.get("synthetic") is True, f"Record {raw.source_record_id} must have synthetic=True"
        assert "FIXTURE" in attrs.get("note", ""), "Note must declare fixture status"
        assert "color" in attrs
        assert "material" in attrs
        assert "fit" in attrs
        assert "silhouette" in attrs


def test_identity_resolution_for_seed_records() -> None:
    raw = FASHION_SEED_RECORDS[0]
    result = normalize_product(raw)
    assert result.product is not None
    prod = result.product

    # Case 1: Fresh record -> MATCH_NONE
    decision_fresh = resolve_identity(prod, IdentityCandidates())
    assert decision_fresh.match_status == MATCH_NONE
    assert decision_fresh.creates_new_product is True

    # Case 2: Exact source identity exists -> MATCH_EXACT
    existing_id = uuid4()
    decision_exact = resolve_identity(
        prod, IdentityCandidates(source_identity_product_id=existing_id)
    )
    assert decision_exact.match_status == MATCH_EXACT
    assert decision_exact.product_id == existing_id
    assert decision_exact.creates_new_product is False

    # Case 3: Same GTIN from another source -> MATCH_VERIFIED
    gtin_product_id = uuid4()
    decision_gtin = resolve_identity(
        prod, IdentityCandidates(stable_id_product_id=gtin_product_id)
    )
    assert decision_gtin.match_status == MATCH_VERIFIED
    assert decision_gtin.product_id == gtin_product_id
    assert decision_gtin.creates_new_product is False


def test_cli_lists_fashion_seed(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--list-sources"]) == 0
    out = capsys.readouterr().out
    assert "fashion_seed" in out
    assert "fixture_catalog" in out


# ---------------------------------------------------------------------------
# DB-Backed Persistence, Idempotency, and Error Tests
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.usefixtures("db")


def test_fashion_seed_collection_persistence_and_idempotency(db) -> None:
    Session = make_session()
    adapter = FashionCatalogSeedAdapter()

    # First execution: must ingest and normalize all 60 records
    with Session() as session:
        repo = DiscoveryRepositorySQL(session)
        service = CollectSource(adapter=adapter, repository=repo)
        res1 = service(CollectionConfig(source=FASHION_SEED_SOURCE_ID, max_records=200))
        assert res1.status == "completed"
        assert res1.fetched == 60
        assert res1.inserted == 60
        assert res1.updated == 0
        assert res1.skipped == 0
        assert res1.failed == 0

    # Verify database counts
    with Session() as session:
        prod_count = session.query(Product).count()
        map_count = session.query(ProductSourceMap).count()
        obs_count = session.query(ProductObservation).count()
        raw_count = session.query(RawSourceRecordModel).count()
        run_count = session.query(CollectionRun).count()

        assert prod_count == 60
        assert map_count == 60
        assert obs_count == 60
        assert raw_count == 60
        assert run_count == 1

        # Verify category counts in DB
        cat_counts = dict(
            session.query(Product.category, func.count(Product.id)).group_by(Product.category).all()
        )
        assert cat_counts == {
            "tops": 14,
            "bottoms": 12,
            "outerwear": 12,
            "footwear": 12,
            "accessories": 10,
        }

    # Second execution: must be 100% idempotent (all 60 skipped, zero duplicates)
    with Session() as session:
        repo = DiscoveryRepositorySQL(session)
        service = CollectSource(adapter=adapter, repository=repo)
        res2 = service(CollectionConfig(source=FASHION_SEED_SOURCE_ID, max_records=200))
        assert res2.status == "completed"
        assert res2.fetched == 60
        assert res2.inserted == 0
        assert res2.updated == 0
        assert res2.skipped == 60
        assert res2.failed == 0

    # Database counts must remain strictly identical (except 1 new collection_run row)
    with Session() as session:
        assert session.query(Product).count() == 60
        assert session.query(ProductSourceMap).count() == 60
        assert session.query(ProductObservation).count() == 60
        assert session.query(RawSourceRecordModel).count() == 60
        assert session.query(CollectionRun).count() == 2

        # Verify sample product structure in DB
        sample = session.query(Product).filter(Product.title.like("%Khadi Cotton Short Kurta%")).one()
        assert float(sample.price) == 1899.0
        assert sample.currency == "INR"
        assert sample.category == "tops"
        assert sample.subcategory == "kurta"
        assert sample.attributes["fixture"] is True
        assert sample.attributes["synthetic"] is True
        assert sample.attributes["identifiers"]["gtin"] == compute_test_gtin14(1)
        assert len(sample.image_urls) == 1


def test_updated_source_record_creates_observation_without_duplicate_product(db) -> None:
    Session = make_session()

    initial_record = RawSourceRecord(
        source=FASHION_SEED_SOURCE_ID,
        source_record_id="SEED-UPDATE-TEST",
        payload={
            "id": "SEED-UPDATE-TEST",
            "title": "[Seed] Test Updatable Jacket",
            "brand": "Test Brand",
            "category": "outerwear",
            "price": 3999.0,
            "currency": "INR",
            "availability": True,
            "product_url": "https://catalog.fixture.test/products/SEED-UPDATE-TEST",
            "image_urls": ["/static/fixtures/fashion/SEED-UPDATE-TEST.png"],
            "attributes": {"fixture": True, "synthetic": True, "note": "test"},
        },
    )

    with Session() as session:
        repo = DiscoveryRepositorySQL(session)
        adapter1 = FashionCatalogSeedAdapter(records=(initial_record,))
        service1 = CollectSource(adapter=adapter1, repository=repo)
        res1 = service1(CollectionConfig(source=FASHION_SEED_SOURCE_ID))
        assert res1.inserted == 1

    with Session() as session:
        prod = session.query(Product).filter(Product.title == "[Seed] Test Updatable Jacket").one()
        assert float(prod.price) == 3999.0
        prod_id = prod.id

        # Observation count for this product: 1
        obs_count_1 = session.query(ProductObservation).filter(ProductObservation.product_id == prod_id).count()
        assert obs_count_1 == 1

    # Second record with updated price (different payload hash)
    updated_record = RawSourceRecord(
        source=FASHION_SEED_SOURCE_ID,
        source_record_id="SEED-UPDATE-TEST",
        payload={
            "id": "SEED-UPDATE-TEST",
            "title": "[Seed] Test Updatable Jacket",
            "brand": "Test Brand",
            "category": "outerwear",
            "price": 3499.0,  # Price drop
            "currency": "INR",
            "availability": True,
            "product_url": "https://catalog.fixture.test/products/SEED-UPDATE-TEST",
            "image_urls": ["/static/fixtures/fashion/SEED-UPDATE-TEST.png"],
            "attributes": {"fixture": True, "synthetic": True, "note": "test"},
        },
    )

    with Session() as session:
        repo = DiscoveryRepositorySQL(session)
        adapter2 = FashionCatalogSeedAdapter(records=(updated_record,))
        service2 = CollectSource(adapter=adapter2, repository=repo)
        res2 = service2(CollectionConfig(source=FASHION_SEED_SOURCE_ID))
        assert res2.updated == 1
        assert res2.inserted == 0

    with Session() as session:
        # Still exactly 1 Product and 1 ProductSourceMap, but 2 observations
        assert session.query(Product).filter(Product.id == prod_id).count() == 1
        prod = session.get(Product, prod_id)
        assert prod is not None
        assert float(prod.price) == 3499.0  # Updated in-place

        obs_count_2 = session.query(ProductObservation).filter(ProductObservation.product_id == prod_id).count()
        assert obs_count_2 == 2


def test_invalid_fixture_fails_validation_and_is_audited(db) -> None:
    Session = make_session()

    invalid_record = RawSourceRecord(
        source=FASHION_SEED_SOURCE_ID,
        source_record_id="SEED-INVALID-001",
        payload={
            "id": "SEED-INVALID-001",
            "title": "",  # Empty title -> validation error
            "price": -50.0,  # Negative price -> validation error
            "category": "tops",
        },
    )

    with Session() as session:
        repo = DiscoveryRepositorySQL(session)
        adapter = FashionCatalogSeedAdapter(records=(invalid_record,))
        service = CollectSource(adapter=adapter, repository=repo)
        res = service(CollectionConfig(source=FASHION_SEED_SOURCE_ID))

        assert res.status == "completed"
        assert res.fetched == 1
        assert res.inserted == 0
        assert res.failed == 1
        assert "failed validation" in (res.error_summary or "")

    # Raw source record is stored with status="failed"
    with Session() as session:
        raw_row = session.query(RawSourceRecordModel).filter(
            RawSourceRecordModel.source_record_id == "SEED-INVALID-001"
        ).one()
        assert raw_row.processing_status == "failed"
        assert "title must be a non-empty string" in (raw_row.processing_error or "")

        # No product was created
        assert session.query(Product).count() == 0
        assert session.query(ProductObservation).count() == 0
