"""D4 Discovery normalization, validation and canonical identity tests.

Two groups:

- DB-free: deterministic normalization rules (whitespace/Unicode/multilingual
  titles, missing vs invalid fields, prices/currencies/URLs, GTIN validation,
  availability) and the pure identity resolver.
- DB-backed (opt in via the ``db`` fixture; skip when PostgreSQL is not
  reachable — see ``tests/conftest.py``): repeated/conflicting observations,
  exact source identity, verified cross-source matching via a valid GTIN,
  ambiguous products that must stay separate, raw provenance preservation and
  database constraint / rollback behavior.

No real external collection, no network, no LLM, no trend scoring.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.application.collection import CollectSource, CollectionConfig
from app.domain.ports.source_adapter import RawSourceRecord, SourceBatch
from app.domain.services.normalization import NormalizedProduct, normalize_product, payload_hash
from app.domain.services.product_identity import (
    MATCH_EXACT,
    MATCH_NONE,
    MATCH_POSSIBLE,
    MATCH_VERIFIED,
    IdentityCandidates,
    resolve_identity,
)
from app.infrastructure.db.models import (
    Product,
    ProductSourceMap,
    RawSourceRecord as RawSourceRecordModel,
)
from app.infrastructure.db.repositories import DiscoveryRepositorySQL
from tests.conftest import make_session

# Valid EAN-13 (correct check digit) -> canonical GTIN-14.
_GTIN13 = "4006381333931"
_GTIN14 = "04006381333931"


def _raw(record_id: str, payload: dict, *, source: str = "src_a") -> RawSourceRecord:
    return RawSourceRecord(source=source, source_record_id=record_id, payload=payload)


def _product(record_id: str, payload: dict, *, source: str = "src_a") -> NormalizedProduct:
    result = normalize_product(_raw(record_id, payload, source=source))
    assert result.ok, result.errors
    assert result.product is not None
    return result.product


# ---------------------------------------------------------------------------
# Normalization (DB-free)
# ---------------------------------------------------------------------------


def test_complete_record_is_accepted():
    result = normalize_product(
        _raw(
            "A-1",
            {
                "title": "Oversized Denim Jacket",
                "brand": "Acme",
                "category": "outerwear",
                "subcategory": "jackets",
                "attributes": {"material": "denim"},
                "price": 2499.5,
                "currency": "inr",
                "availability": "in_stock",
                "product_url": "https://shop.example/p/A-1",
                "image_urls": ["https://cdn.example/a.jpg"],
                "gtin": _GTIN13,
                "mpn": "ACME-JKT-1",
            },
        )
    )
    assert result.status == "accepted"
    assert result.missing == ()
    product = result.product
    assert product is not None
    assert product.currency == "INR"  # normalized case
    assert product.availability is True
    assert product.gtin == _GTIN14
    assert product.manufacturer_id == "ACME-JKT-1"


def test_minimal_record_is_accepted_with_missing_optional():
    result = normalize_product(_raw("A-1", {"title": "Plain Tee"}))
    assert result.status == "accepted_with_missing_optional"
    assert "brand" in result.missing
    assert "price" in result.missing
    assert result.product is not None
    assert result.product.brand is None
    assert result.product.price is None


def test_blank_optional_fields_become_none_not_error():
    result = normalize_product(
        _raw("A-1", {"title": "Tee", "brand": "   ", "category": "", "subcategory": "\t"})
    )
    assert result.ok
    assert result.product is not None
    assert result.product.brand is None
    assert result.product.category is None
    assert result.product.subcategory is None


@pytest.mark.parametrize(
    "payload, needle",
    [
        ({"price": 10}, "title"),  # title absent -> required
        ({"title": 123}, "title must be a string"),
        ({"title": "   "}, "title must be a non-empty string"),
    ],
)
def test_missing_or_invalid_title_is_rejected(payload, needle):
    result = normalize_product(_raw("A-1", payload))
    assert not result.ok
    assert result.product is None
    assert any(needle in e for e in result.errors)


def test_non_mapping_payload_is_rejected():
    result = normalize_product(RawSourceRecord(source="src_a", payload=["nope"]))
    assert result.errors == ("payload must be a mapping",)


@pytest.mark.parametrize(
    "value, needle",
    [
        (-1, "price must be >= 0"),
        ("12", "price must be a number"),
        (True, "price must be a number"),
        (float("inf"), "price must be a finite number"),
        (float("nan"), "price must be a finite number"),
    ],
)
def test_invalid_prices_are_rejected(value, needle):
    result = normalize_product(_raw("A-1", {"title": "T", "price": value}))
    assert not result.ok
    assert any(needle in e for e in result.errors)


@pytest.mark.parametrize("value", ["rupees", "in", "12", 5])
def test_invalid_currencies_are_rejected(value):
    result = normalize_product(_raw("A-1", {"title": "T", "currency": value}))
    assert not result.ok
    assert any("3-letter code" in e for e in result.errors)


@pytest.mark.parametrize("value", ["inr", "USD", " eur "])
def test_valid_currencies_are_upper_cased(value):
    result = normalize_product(_raw("A-1", {"title": "T", "currency": value}))
    assert result.ok
    assert result.product is not None
    assert result.product.currency == value.strip().upper()


@pytest.mark.parametrize(
    "payload",
    [
        {"title": "T", "product_url": "javascript:alert(1)"},
        {"title": "T", "product_url": "/relative/path"},
        {"title": "T", "image_urls": ["not-a-url"]},
        {"title": "T", "image_urls": [""]},
    ],
)
def test_invalid_urls_are_rejected(payload):
    result = normalize_product(_raw("A-1", payload))
    assert not result.ok
    assert any("URL" in e or "url" in e for e in result.errors)


def test_valid_image_urls_are_kept():
    result = normalize_product(
        _raw("A-1", {"title": "T", "image_urls": ["https://cdn.example/x.jpg"]})
    )
    assert result.ok
    assert result.product is not None
    assert result.product.image_urls == ("https://cdn.example/x.jpg",)


def test_unicode_and_multilingual_titles_are_preserved_and_cleaned():
    nbsp = "\u00a0"
    result = normalize_product(
        _raw(
            "A-1",
            {
                "title": f"  Caf\u00e9   \u00c0{nbsp}C\u00f4t\u00e9  ",  # NFC already
                "brand": "Cafe\u0301",  # decomposed -> NFC
                "category": "Bad\u0000Category",  # control char removed
            },
        )
    )
    assert result.ok
    product = result.product
    assert product is not None
    assert product.title == "Caf\u00e9 \u00c0 C\u00f4t\u00e9"
    assert product.brand == "Caf\u00e9"  # composed
    assert product.category == "BadCategory"


def test_japanese_title_is_preserved():
    result = normalize_product(_raw("A-1", {"title": "\u30e6\u30cb\u30af\u30ed \u30b7\u30e3\u30c4"}))
    assert result.ok
    assert result.product is not None
    assert result.product.title == "\u30e6\u30cb\u30af\u30ed \u30b7\u30e3\u30c4"


def test_normalization_is_deterministic():
    payload = {"title": "Same", "brand": "Acme", "price": 10, "attributes": {"a": 1}}
    first = normalize_product(_raw("A-1", payload, source="src_a"))
    second = normalize_product(_raw("A-1", payload, source="src_a"))
    assert first == second
    assert payload_hash(payload) == payload_hash(dict(reversed(list(payload.items()))))


@pytest.mark.parametrize(
    "value, expected",
    [
        (_GTIN13, _GTIN14),
        ("4006381333932", None),  # bad check digit
        ("12345", None),  # unsupported length
        ("abc", None),
        (None, None),
    ],
)
def test_gtin_validation(value, expected):
    result = normalize_product(_raw("A-1", {"title": "T", "gtin": value}))
    assert result.ok
    assert result.product is not None
    assert result.product.gtin == expected


@pytest.mark.parametrize(
    "value, expected",
    [(True, True), (False, False), ("in_stock", True), ("sold_out", False), (None, None)],
)
def test_availability_representation(value, expected):
    result = normalize_product(_raw("A-1", {"title": "T", "availability": value}))
    assert result.ok
    assert result.product is not None
    assert result.product.availability is expected


def test_invalid_availability_is_rejected():
    result = normalize_product(_raw("A-1", {"title": "T", "availability": "maybe"}))
    assert not result.ok
    assert any("availability" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Identity resolver (DB-free)
# ---------------------------------------------------------------------------


def test_resolver_exact_source_identity_wins():
    product_id = uuid4()
    decision = resolve_identity(
        _product("A-1", {"title": "T", "gtin": _GTIN13}),
        IdentityCandidates(source_identity_product_id=product_id, stable_id_product_id=uuid4()),
    )
    assert decision.match_status == MATCH_EXACT
    assert decision.product_id == product_id


def test_resolver_verified_cross_source_requires_valid_gtin():
    product_id = uuid4()
    decision = resolve_identity(
        _product("B-1", {"title": "Different name", "gtin": _GTIN13}),
        IdentityCandidates(stable_id_product_id=product_id),
    )
    assert decision.match_status == MATCH_VERIFIED
    assert decision.product_id == product_id


def test_resolver_never_verifies_without_gtin():
    decision = resolve_identity(
        _product("B-1", {"title": "Same name"}),
        IdentityCandidates(stable_id_product_id=uuid4()),  # impossible from repo: no gtin
    )
    assert decision.match_status == MATCH_NONE


def test_resolver_possible_match_is_reported_but_not_merged():
    candidates = (uuid4(), uuid4())
    decision = resolve_identity(
        _product("B-1", {"title": "Tee", "brand": "Acme", "category": "tops"}),
        IdentityCandidates(possible_match_product_ids=candidates),
    )
    assert decision.match_status == MATCH_POSSIBLE
    assert decision.product_id is None
    assert decision.creates_new_product
    assert decision.possible_match_product_ids == candidates


def test_resolver_no_match():
    decision = resolve_identity(
        _product("B-1", {"title": "Tee"}), IdentityCandidates()
    )
    assert decision.match_status == MATCH_NONE
    assert decision.creates_new_product


# ---------------------------------------------------------------------------
# DB-backed collection
# ---------------------------------------------------------------------------


class _Adapter:
    def __init__(self, source_id: str, records) -> None:
        self.source_id = source_id
        self._records = tuple(records)

    def fetch_batch(self, *, continuation=None, limit=50):
        return SourceBatch(source=self.source_id, records=self._records, continuation=None)


def _run(adapter: _Adapter):
    Session = make_session()
    with Session() as session:
        result = CollectSource(
            adapter=adapter, repository=DiscoveryRepositorySQL(session)
        )(CollectionConfig(source=adapter.source_id))
    return result, Session


def test_repeated_observation_updates_without_erasing(db):
    old = _raw("A-1", {"id": "A-1", "title": "Old", "brand": "Acme", "price": 100})
    new = _raw("A-1", {"id": "A-1", "title": "New", "price": 120})  # brand omitted

    first, Session = _run(_Adapter("src_a", (old,)))
    assert first.inserted == 1

    second, _ = _run(_Adapter("src_a", (new,)))
    assert second.updated == 1 and second.inserted == 0

    with Session() as session:
        products = session.execute(select(Product)).scalars().all()
        assert len(products) == 1
        product = products[0]
        assert product.title == "New"
        assert float(product.price) == 120.0
        assert product.brand == "Acme"  # not erased by the sparse observation
        assert product.first_seen_at is not None
        assert session.execute(
            select(func.count()).select_from(ProductSourceMap)
        ).scalar_one() == 1


def test_verified_cross_source_match_attaches_without_overwriting(db):
    a = _raw("A-1", {"id": "A-1", "title": "Widget", "brand": "Acme", "category": "tops", "price": 100, "gtin": _GTIN13})
    b = _raw("B-1", {"id": "B-1", "title": "Acme Widget Deluxe", "brand": "Acme", "category": "tops", "price": 90, "gtin": _GTIN13}, source="src_b")

    first, Session = _run(_Adapter("src_a", (a,)))
    assert first.inserted == 1

    second, _ = _run(_Adapter("src_b", (b,)))
    assert second.inserted == 0 and second.updated == 1
    assert second.verified == 1 and second.possible == 0

    with Session() as session:
        products = session.execute(select(Product)).scalars().all()
        assert len(products) == 1
        product = products[0]
        # The first listing owns the canonical fields; a cross-source listing
        # must not overwrite them.
        assert product.title == "Widget"
        assert float(product.price) == 100.0
        maps = session.execute(select(ProductSourceMap)).scalars().all()
        assert {m.source for m in maps} == {"src_a", "src_b"}
        assert {m.product_id for m in maps} == {product.id}


def test_ambiguous_products_stay_separate_and_are_reported(db):
    a = _raw("A-1", {"id": "A-1", "title": "Blue Shirt", "brand": "Acme", "category": "tops"})
    b = _raw("B-1", {"id": "B-1", "title": "Acme Blue Shirt", "brand": "Acme", "category": "tops"}, source="src_b")

    first, Session = _run(_Adapter("src_a", (a,)))
    assert first.inserted == 1

    second, _ = _run(_Adapter("src_b", (b,)))
    assert second.verified == 0
    assert second.possible == 1
    assert second.inserted == 1  # still a separate product, never merged

    with Session() as session:
        assert session.execute(
            select(func.count()).select_from(Product)
        ).scalar_one() == 2


def test_exact_source_identity_is_not_duplicated(db):
    record = _raw("A-1", {"id": "A-1", "title": "T", "gtin": _GTIN13})
    first, Session = _run(_Adapter("src_a", (record,)))
    assert first.inserted == 1
    # Re-collecting the identical payload is skipped at the raw layer.
    second, _ = _run(_Adapter("src_a", (record,)))
    assert second.skipped == 1
    with Session() as session:
        assert session.execute(
            select(func.count()).select_from(Product)
        ).scalar_one() == 1
        assert session.execute(
            select(func.count()).select_from(ProductSourceMap)
        ).scalar_one() == 1


def test_raw_payloads_and_provenance_are_preserved(db):
    record = _raw("A-1", {"id": "A-1", "title": "T"})
    result, Session = _run(_Adapter("src_a", (record,)))
    with Session() as session:
        raw = session.execute(select(RawSourceRecordModel)).scalar_one()
        assert raw.payload == {"id": "A-1", "title": "T"}  # verbatim
        assert raw.payload_hash == payload_hash(raw.payload)
        assert raw.collection_run_id == result.run_id
        mapping = session.execute(select(ProductSourceMap)).scalar_one()
        assert mapping.raw_source_record_id == raw.id
        assert mapping.source == raw.source
        assert mapping.source_product_id == "A-1"


def test_db_constraints_and_rollback_keep_session_usable(db):
    Session = make_session()
    with Session() as session:
        repo = DiscoveryRepositorySQL(session)
        payload = {"id": "A-1", "title": "T"}
        digest = payload_hash(payload)
        run_id = repo.start_run(source="src_a")

        raw_id, created = repo.insert_raw_if_absent(
            run_id=run_id, source="src_a", source_record_id="A-1",
            payload=payload, payload_hash=digest, source_timestamp=None,
        )
        assert created
        # Same (source, payload_hash) is deduplicated, not duplicated.
        raw_id2, created2 = repo.insert_raw_if_absent(
            run_id=run_id, source="src_a", source_record_id="A-1b",
            payload=payload, payload_hash=digest, source_timestamp=None,
        )
        assert not created2 and raw_id2 == raw_id

        product = normalize_product(_raw("A-1", payload)).product
        assert product is not None
        repo.upsert_product(
            product=product, run_id=run_id, source="src_a",
            source_product_id="A-1", raw_id=raw_id, payload_hash=digest,
        )

        # A duplicate source identity mapping violates the unique constraint.
        session.add(
            ProductSourceMap(
                product_id=session.execute(select(Product.id)).scalar_one(),
                source="src_a", source_product_id="A-1",
                raw_source_record_id=raw_id, observed_at=None,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()

        repo.rollback()
        # The session is still usable after the failed transaction.
        assert session.execute(
            select(func.count()).select_from(Product)
        ).scalar_one() == 1
