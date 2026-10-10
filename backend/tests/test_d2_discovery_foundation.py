"""D2 Discovery database foundation + source adapter contract tests.

Two groups:

- DB-free: the ``SourceAdapter`` port contract/typed errors and the
  deterministic normalization boundary (raw payload -> adapter output ->
  normalized product -> validation errors).
- DB-backed (opt in via the ``db`` fixture; skip when PostgreSQL is not
  reachable — see ``tests/conftest.py``): migration 0026 schema,
  constraints, source-identity uniqueness, raw-record provenance and the
  collection-run relationship, plus downgrade/upgrade round-trip.

No real external collection, no network, no LLM, no trend scoring.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.domain.ports.source_adapter import (
    RawSourceRecord as PortRawRecord,
    SourceAdapter,
    SourceAuthError,
    SourceBatch,
    SourceError,
    SourcePayloadError,
    SourceRateLimitError,
    SourceTransientError,
)
from app.domain.services.normalization import (
    normalize_product,
    payload_hash,
)
from app.infrastructure.db.models import (
    CollectionRun,
    Product,
    ProductSourceMap,
    RawSourceRecord,
)
from app.infrastructure.db.session import DATABASE_URL
from tests.conftest import make_session

NOW = datetime(2026, 10, 10, 2, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# SourceAdapter contract (DB-free)
# ---------------------------------------------------------------------------


class _FakeAdapter:
    """Deterministic in-memory adapter — never a live provider connector."""

    source_id = "test_commerce"

    def __init__(self, pages):
        self._pages = pages
        self.calls = []

    def fetch_batch(self, *, continuation=None, limit=50):
        self.calls.append((continuation, limit))
        index = int(continuation) if continuation is not None else 0
        records = tuple(self._pages[index])
        nxt = str(index + 1) if index + 1 < len(self._pages) else None
        return SourceBatch(source=self.source_id, records=records, continuation=nxt)


def _collect(adapter: SourceAdapter, *, max_pages: int = 10) -> list[PortRawRecord]:
    """Typed consumer — proves an adapter only needs the port surface."""
    collected: list[PortRawRecord] = []
    continuation = None
    for _ in range(max_pages):
        batch = adapter.fetch_batch(continuation=continuation)
        assert batch.source == adapter.source_id
        collected.extend(batch.records)
        continuation = batch.continuation
        if continuation is None:
            break
    return collected


def test_adapter_batching_and_continuation():
    first = PortRawRecord(source="test_commerce", source_record_id="p1", payload={"id": "p1"})
    second = PortRawRecord(source="test_commerce", source_record_id="p2", payload={"id": "p2"})
    adapter = _FakeAdapter([[first], [second]])

    assert adapter.source_id == "test_commerce"
    records = _collect(adapter)
    assert [r.source_record_id for r in records] == ["p1", "p2"]
    # Continuation was passed back verbatim ("1"), then terminated.
    assert adapter.calls == [(None, 50), ("1", 50)]

    single = _FakeAdapter([[first]])
    assert single.fetch_batch(continuation=None).continuation is None


def test_adapter_error_hierarchy_is_typed():
    for exc in (SourceAuthError, SourceRateLimitError, SourceTransientError, SourcePayloadError):
        assert issubclass(exc, SourceError)
    rate = SourceRateLimitError(retry_after_s=5)
    assert rate.retry_after_s == 5
    assert SourceRateLimitError().retry_after_s is None


# ---------------------------------------------------------------------------
# Normalization boundary (DB-free)
# ---------------------------------------------------------------------------


def test_normalize_valid_payload():
    raw = PortRawRecord(
        source="test_commerce",
        source_record_id="SKU-1",
        payload={
            "title": "  Oversized Denim Jacket ",
            "brand": "Test Brand",
            "category": "outerwear",
            "price": 1299,
            "currency": "INR",
            "availability": True,
            "product_url": "https://example.test/p/SKU-1",
            "image_urls": ["https://cdn.test/a.jpg", "https://cdn.test/b.jpg"],
            "attributes": {"material": "denim"},
        },
        source_timestamp=NOW,
    )
    result = normalize_product(raw)
    assert result.ok
    product = result.product
    assert product.title == "Oversized Denim Jacket"
    assert product.source == "test_commerce"
    assert product.source_product_id == "SKU-1"
    assert product.price == 1299.0
    assert product.currency == "INR"
    assert product.availability is True
    assert product.image_urls == ("https://cdn.test/a.jpg", "https://cdn.test/b.jpg")
    assert product.attributes == {"material": "denim"}
    assert product.observed_at == NOW


def test_normalize_missing_title_is_validation_error():
    raw = PortRawRecord(source="s", source_record_id="X", payload={"price": 10})
    result = normalize_product(raw)
    assert not result.ok
    assert result.product is None
    assert any("title" in e for e in result.errors)


def test_normalize_non_mapping_payload():
    raw = PortRawRecord(source="s", payload=["not", "a", "mapping"])  # type: ignore[arg-type]
    result = normalize_product(raw)
    assert result.product is None
    assert result.errors == ("payload must be a mapping",)


def test_normalize_invalid_price_and_images():
    raw = PortRawRecord(
        source="s",
        source_record_id="X",
        payload={"title": "T", "price": -1, "image_urls": [""]},
    )
    result = normalize_product(raw)
    assert result.product is None
    assert any("price" in e for e in result.errors)
    assert any("image_urls" in e for e in result.errors)


def test_normalize_unprovided_fields_stay_none():
    raw = PortRawRecord(source="s", source_record_id="X", payload={"title": "Plain"})
    result = normalize_product(raw)
    assert result.ok
    product = result.product
    assert product.brand is None
    assert product.price is None
    assert product.availability is None
    assert product.product_url is None
    assert product.image_urls == ()
    assert product.attributes == {}


def test_payload_hash_deterministic_and_order_independent():
    assert payload_hash({"a": 1, "b": 2}) == payload_hash({"b": 2, "a": 1})
    assert payload_hash({"a": 1}) != payload_hash({"a": 2})
    digest = payload_hash({"a": 1})
    assert len(digest) == 64 and all(c in "0123456789abcdef" for c in digest)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _alembic_config() -> Config:
    config = Config("alembic.ini")
    config.set_main_option("script_location", "alembic")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    config.attributes["configure_logger"] = False
    return config


def _new_run(session, **kwargs) -> CollectionRun:
    run = CollectionRun(source=kwargs.pop("source", "test_commerce"), **kwargs)
    session.add(run)
    session.flush()
    return run


def _new_raw(session, run, *, source="test_commerce", record_id="r1", payload=None, digest=None):
    payload = payload if payload is not None else {"id": record_id, "title": "T"}
    row = RawSourceRecord(
        collection_run_id=run.id,
        source=source,
        source_record_id=record_id,
        payload=payload,
        payload_hash=digest or payload_hash(payload),
    )
    session.add(row)
    session.flush()
    return row


def _new_product(session, *, title="Denim Jacket", **kwargs) -> Product:
    product = Product(title=title, **kwargs)
    session.add(product)
    session.flush()
    return product


# ---------------------------------------------------------------------------
# Migration 0026 schema
# ---------------------------------------------------------------------------


def test_migration_creates_discovery_tables(db):
    Session = make_session()
    with Session() as session:
        insp = inspect(session.bind)
        for table in ("collection_runs", "raw_source_records", "products", "product_source_map"):
            assert insp.has_table(table)


def test_head_is_0028_linear_off_0026():
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(_alembic_config())
    assert tuple(script.get_heads()) == ("0028",)
    rev = script.get_revision("0028")
    assert rev is not None and rev.down_revision == "0027"
    rev27 = script.get_revision("0027")
    assert rev27 is not None and rev27.down_revision == "0026"
    rev26 = script.get_revision("0026")
    assert rev26 is not None and rev26.down_revision == "0025"


def test_collection_runs_constraints(db):
    Session = make_session()
    with Session() as session:
        with pytest.raises(IntegrityError):
            _new_run(session, status="bogus")
        session.rollback()

        with pytest.raises(IntegrityError):
            _new_run(session, fetched_count=-1)
        session.rollback()

        with pytest.raises(IntegrityError):
            _new_run(
                session,
                started_at=datetime(2026, 10, 10, 3, 0, tzinfo=timezone.utc),
                finished_at=datetime(2026, 10, 10, 2, 0, tzinfo=timezone.utc),
            )
        session.rollback()

        run = _new_run(session, source="youtube_in")
        session.commit()
        assert run.status == "running"
        assert run.fetched_count == 0


def test_products_constraints(db):
    Session = make_session()
    with Session() as session:
        with pytest.raises(IntegrityError):
            _new_product(session, title="")
        session.rollback()

        with pytest.raises(IntegrityError):
            _new_product(session, title="x" * 301)
        session.rollback()

        with pytest.raises(IntegrityError):
            _new_product(session, price=-0.01)
        session.rollback()

        product = _new_product(session, price=1299.0, currency="INR")
        session.commit()
        assert float(product.price) == 1299.0
        assert product.attributes == {}
        assert product.image_urls == []


def test_products_never_store_image_binaries(db):
    Session = make_session()
    with Session() as session:
        columns = {c["name"] for c in inspect(session.bind).get_columns("products")}
        assert "image_urls" in columns
        assert not any("bytes" in c or "blob" in c or "binary" in c for c in columns)


# ---------------------------------------------------------------------------
# Provenance + uniqueness
# ---------------------------------------------------------------------------


def test_raw_record_payload_hash_unique_per_source(db):
    Session = make_session()
    with Session() as session:
        run = _new_run(session)
        _new_raw(session, run, source="flipkart", record_id="F1", digest="abc")
        with pytest.raises(IntegrityError):
            _new_raw(session, run, source="flipkart", record_id="F2", digest="abc")
        session.rollback()

        # Same digest under a different source is a distinct raw record.
        run2 = _new_run(session)
        _new_raw(session, run2, source="amazon", record_id="A1", digest="abc")
        session.commit()


def test_raw_record_preserves_verbatim_provenance(db):
    Session = make_session()
    with Session() as session:
        run = _new_run(session, source="youtube_in")
        payload = {"id": "v1", "title": "raw unnormalized  ", "views": 12}
        raw = _new_raw(session, run, source="youtube_in", record_id="v1", payload=payload)
        session.commit()

        fetched = session.get(RawSourceRecord, raw.id)
        assert fetched.payload == payload  # verbatim, not normalized
        assert fetched.collection_run_id == run.id
        assert fetched.fetched_at is not None
        assert fetched.source_timestamp is None
        assert fetched.processing_status == "pending"


def test_collection_run_delete_cascades_raw_records(db):
    Session = make_session()
    with Session() as session:
        run = _new_run(session)
        raw = _new_raw(session, run)
        session.commit()
        raw_id = raw.id

        session.execute(text("DELETE FROM collection_runs WHERE id = :id"), {"id": str(run.id)})
        session.commit()
        session.expire_all()
        assert session.get(RawSourceRecord, raw_id) is None


def test_product_source_identity_uniqueness(db):
    Session = make_session()
    with Session() as session:
        product = _new_product(session)
        other = _new_product(session, title="Other")
        session.add(
            ProductSourceMap(product_id=product.id, source="flipkart", source_product_id="FSN1")
        )
        session.flush()
        with pytest.raises(IntegrityError):
            session.add(
                ProductSourceMap(
                    product_id=other.id, source="flipkart", source_product_id="FSN1"
                )
            )
            session.flush()
        session.rollback()


def test_product_supports_multiple_sources(db):
    Session = make_session()
    with Session() as session:
        product = _new_product(session)
        session.add_all(
            [
                ProductSourceMap(product_id=product.id, source="flipkart", source_product_id="FSN1"),
                ProductSourceMap(product_id=product.id, source="amazon", source_product_id="ASIN1"),
            ]
        )
        session.commit()
        rows = session.execute(
            select(ProductSourceMap).where(ProductSourceMap.product_id == product.id)
        ).scalars().all()
        assert {r.source for r in rows} == {"flipkart", "amazon"}


def test_product_source_map_lineage_and_cascades(db):
    Session = make_session()
    with Session() as session:
        run = _new_run(session)
        raw = _new_raw(session, run)
        product = _new_product(session)
        mapping = ProductSourceMap(
            product_id=product.id,
            source="test_commerce",
            source_product_id="SKU-1",
            raw_source_record_id=raw.id,
        )
        session.add(mapping)
        session.commit()
        map_id, raw_id, product_id = mapping.id, raw.id, product.id

    # Deleting the raw record keeps the mapping via SET NULL (fresh session).
    with Session() as session:
        session.execute(text("DELETE FROM raw_source_records WHERE id = :id"), {"id": str(raw_id)})
        session.commit()
    with Session() as session:
        refreshed = session.get(ProductSourceMap, map_id)
        assert refreshed is not None
        assert refreshed.raw_source_record_id is None

    # Deleting the product removes the mapping (CASCADE).
    with Session() as session:
        session.execute(text("DELETE FROM products WHERE id = :id"), {"id": str(product_id)})
        session.commit()
    with Session() as session:
        assert session.get(ProductSourceMap, map_id) is None


# ---------------------------------------------------------------------------
# Downgrade / upgrade round-trip
# ---------------------------------------------------------------------------


def test_downgrade_removes_and_upgrade_restores(migrated_db):
    Session = make_session()
    config = _alembic_config()
    try:
        command.downgrade(config, "0025")
        with Session() as session:
            insp = inspect(session.bind)
            for table in ("collection_runs", "raw_source_records", "products", "product_source_map"):
                assert not insp.has_table(table)
    finally:
        command.upgrade(config, "head")
    with Session() as session:
        insp = inspect(session.bind)
        for table in ("collection_runs", "raw_source_records", "products", "product_source_map"):
            assert insp.has_table(table)
