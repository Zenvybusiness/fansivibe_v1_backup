"""Bundled FIXTURE source adapter (D3) — NOT real commerce data.

Deterministic, synthetic records for exercising the collection workflow.
Every record is marked ``attributes.fixture = true`` and the source id is
``fixture_catalog``; the titles, prices, availability and URLs below are
invented test values and must never be presented as a real catalogue or
provider response. No source timestamp is supplied — one is never invented.

Live sources (Amazon, Flipkart, ...) are absent by design: they require an
approved access mechanism and configured credentials (see
``docs/architecture/TRENDING_PROVIDER_ACCESS_MATRIX.md``).
"""

from __future__ import annotations

from typing import Optional

from app.domain.ports.source_adapter import RawSourceRecord, SourceBatch

FIXTURE_SOURCE_ID = "fixture_catalog"
_FIXTURE_NOTE = "FIXTURE — synthetic test data, not real commerce data"


def _fixture_payload(
    record_id: str, title: str, *, category: str = "outerwear", price: float = 1299.0
) -> dict:
    return {
        "id": record_id,
        "title": title,
        "brand": "Fixture Brand",
        "category": category,
        "price": price,
        "currency": "INR",
        "availability": True,
        "product_url": f"https://shop.fixture.test/p/{record_id}",
        "image_urls": [f"https://cdn.fixture.test/{record_id}.jpg"],
        "attributes": {"fixture": True, "note": _FIXTURE_NOTE},
    }


FIXTURE_RECORDS: tuple[RawSourceRecord, ...] = (
    RawSourceRecord(
        source=FIXTURE_SOURCE_ID,
        source_record_id="FIX-001",
        payload=_fixture_payload("FIX-001", "[Fixture] Oversized Denim Jacket"),
    ),
    RawSourceRecord(
        source=FIXTURE_SOURCE_ID,
        source_record_id="FIX-002",
        payload=_fixture_payload(
            "FIX-002", "[Fixture] Wide Leg Cargo Pants", category="bottoms"
        ),
    ),
    RawSourceRecord(
        source=FIXTURE_SOURCE_ID,
        source_record_id="FIX-003",
        payload=_fixture_payload("FIX-003", "[Fixture] Cotton Overshirt"),
    ),
)


class FixtureSourceAdapter:
    """Deterministic fixture adapter conforming to ``SourceAdapter``."""

    source_id = FIXTURE_SOURCE_ID

    def __init__(
        self,
        records: tuple[RawSourceRecord, ...] = FIXTURE_RECORDS,
        *,
        page_size: int = 2,
    ) -> None:
        self._records = tuple(records)
        self._page_size = max(1, page_size)

    def fetch_batch(
        self,
        *,
        continuation: Optional[str] = None,
        limit: int = 50,
    ) -> SourceBatch:
        start = int(continuation) if continuation is not None else 0
        size = min(limit, self._page_size)
        chunk = self._records[start : start + size]
        next_start = start + size
        nxt = str(next_start) if next_start < len(self._records) else None
        return SourceBatch(source=self.source_id, records=chunk, continuation=nxt)
