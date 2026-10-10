"""SYNTHETIC search-interest source adapter (D9B) — NOT real provider data.

Deterministic, invented records for exercising the search-interest collection
workflow **entirely offline**. Every record sets ``synthetic: true`` and the
source id is ``synthetic_search_interest``; the query terms, geographies and
values below are fabricated test values and must never be presented as real
Google Trends (or any provider) evidence.

The payloads conform to the canonical *search-interest payload shape* that
``app.domain.services.search_interest.normalize_search_interest`` validates —
this is deliberately **not** Google's response schema, whose contract is still
unknown pending alpha access. The real adapter (D9C) is gated on verified
access + the actual contract + permitted storage/display and is not implemented
here.

Values are a relative index on an invented scale (``synthetic_relative_index_v1``),
never a search volume, sales figure or purchasing intent.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.domain.ports.source_adapter import RawSourceRecord, SourceBatch

SYNTHETIC_SEARCH_INTEREST_SOURCE_ID = "synthetic_search_interest"
SYNTHETIC_VALUE_SCALE = "synthetic_relative_index_v1"
SYNTHETIC_QUERY_CONFIG_VERSION = "synthetic_v1"


def synthetic_search_interest_payload(
    *,
    query_display: str,
    query_kind: str = "search_term",
    query_key: Optional[str] = None,
    geo_scope: str = "worldwide",
    geo_scope_type: str = "worldwide",
    interval: str = "weekly",
    period_start: datetime,
    period_end: datetime,
    value: Optional[float] = None,
    value_status: Optional[str] = None,
    source_timestamp: Optional[datetime] = None,
) -> dict:
    """Build one canonical synthetic search-interest payload.

    ``value`` is a relative index value; when ``value_status`` is not
    ``present`` the value stays unknown (never coerced to zero). ``query_key``
    is derived from the display term by the normalizer when omitted.
    """
    query: dict = {"kind": query_kind, "display": query_display}
    if query_key is not None:
        query["key"] = query_key
    payload: dict = {
        "metric": "search_interest",
        "query": query,
        "geo": {"scope": geo_scope, "scope_type": geo_scope_type},
        "interval": interval,
        "period": {"start": period_start.isoformat(), "end": period_end.isoformat()},
        "value_scale": SYNTHETIC_VALUE_SCALE,
        "query_config_version": SYNTHETIC_QUERY_CONFIG_VERSION,
        "synthetic": True,
    }
    if value_status is not None:
        payload["value_status"] = value_status
    if value is not None:
        payload["value"] = value
    if source_timestamp is not None:
        payload["source_timestamp"] = source_timestamp.isoformat()
    return payload


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


_WEEK = (_utc(2026, 1, 5), _utc(2026, 1, 12))
_WEEK_2 = (_utc(2026, 1, 12), _utc(2026, 1, 19))


def _record(
    record_id: str, *, source_timestamp: Optional[datetime], **payload: object
) -> RawSourceRecord:
    return RawSourceRecord(
        source=SYNTHETIC_SEARCH_INTEREST_SOURCE_ID,
        source_record_id=record_id,
        payload=synthetic_search_interest_payload(**payload),  # type: ignore[arg-type]
        source_timestamp=source_timestamp,
    )


# Deterministic, clearly-synthetic records spanning present / missing /
# suppressed values, two geographies, two periods and a topic query.
SYNTHETIC_SEARCH_INTEREST_RECORDS: tuple[RawSourceRecord, ...] = (
    _record(
        "ST-001",
        query_display="oversized denim jacket",
        period_start=_WEEK[0],
        period_end=_WEEK[1],
        value=42.0,
        source_timestamp=_utc(2026, 1, 12),
    ),
    _record(
        "ST-002",
        query_display="wide leg cargo pants",
        period_start=_WEEK[0],
        period_end=_WEEK[1],
        value=57.5,
        geo_scope="IN",
        geo_scope_type="country",
        source_timestamp=_utc(2026, 1, 12),
    ),
    _record(
        "ST-003",
        query_display="cotton overshirt",
        period_start=_WEEK_2[0],
        period_end=_WEEK_2[1],
        value=None,
        value_status="suppressed",
        source_timestamp=_utc(2026, 1, 19),
    ),
    _record(
        "ST-004",
        query_display="/m/0synthetic_topic",
        query_kind="topic",
        query_key="m:synthetic_topic",
        period_start=_WEEK[0],
        period_end=_WEEK[1],
        value=18.0,
        # No source timestamp — the provider supplied none; never invented.
        source_timestamp=None,
    ),
)


class SyntheticSearchInterestAdapter:
    """Deterministic synthetic adapter conforming to ``SourceAdapter``."""

    source_id = SYNTHETIC_SEARCH_INTEREST_SOURCE_ID

    def __init__(
        self,
        records: tuple[RawSourceRecord, ...] = SYNTHETIC_SEARCH_INTEREST_RECORDS,
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
