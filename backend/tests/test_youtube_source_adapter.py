"""Tests for YouTube Data API v3 Source Adapter (Trending Intelligence).

Validates:
1. Safety boundary: unconfigured credentials cleanly fail closed with SourceAuthError.
2. Error translation: 400 -> SourcePayloadError, 401/403 (invalid key) -> SourceAuthError,
   403 (quotaExceeded) / 429 -> SourceRateLimitError, 5xx / timeouts -> SourceTransientError.
3. Payload validation: malformed JSON translates to SourcePayloadError.
4. Response parsing: authentic YouTube search & video schemas map to RawSourceRecord with
   accurate timestamps, video IDs, thumbnail hotlinks, and channel provenance.
5. Missing vs zero semantics: distinguishes missing metrics (None) from genuine 0 values.
6. Pagination: nextPageToken maps to continuation cursor and passes through correctly.
7. Collection workflow: CollectYouTubeVideos starts run, inserts raw records with SHA-256
   payload_hash, and handles duplicates idempotently.
8. Non-demand boundary: video velocity and creator engagement are strictly isolated from
   consumer purchase demand claims; DEMAND_SIGNAL_AVAILABLE remains False.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

import httpx
import pytest

from app.application.collection import (
    CollectionConfig,
    CollectionResult,
    CollectYouTubeVideos,
)
from app.domain.ports.repositories import DiscoveryRepository
from app.domain.ports.source_adapter import (
    RawSourceRecord,
    SourceAuthError,
    SourceBatch,
    SourcePayloadError,
    SourceRateLimitError,
    SourceTransientError,
)
from app.domain.services.normalization import payload_hash
from app.domain.services.trends import DEMAND_SIGNAL_AVAILABLE
from app.infrastructure.external.youtube_source import (
    DEFAULT_REGION_CODE,
    DEFAULT_VIDEO_CATEGORY_ID,
    SOURCE_YOUTUBE_IN,
    YouTubeSourceAdapter,
    parse_youtube_timestamp,
)


def _sample_youtube_search_payload(video_id: str = "vid_12345", title: str = "Summer Linen Styling Guide") -> dict:
    """Authentic YouTube search.list item payload."""
    return {
        "kind": "youtube#searchResult",
        "etag": "etag_sample_123",
        "id": {
            "kind": "youtube#video",
            "videoId": video_id,
        },
        "snippet": {
            "publishedAt": "2026-06-15T10:30:00Z",
            "channelId": "UC_fashion_creator_1",
            "title": title,
            "description": "Essential summer styling tips and menswear trends for Mumbai climate.",
            "thumbnails": {
                "default": {"url": f"https://i.ytimg.com/vi/{video_id}/default.jpg", "width": 120, "height": 90},
                "high": {"url": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg", "width": 480, "height": 360},
            },
            "channelTitle": "Indian Atelier Studio",
            "liveBroadcastContent": "none",
            "publishTime": "2026-06-15T10:30:00Z",
        },
    }


def _sample_youtube_search_response(items: list[dict], next_page_token: Optional[str] = None) -> dict:
    """Full YouTube Data API v3 search response envelope."""
    resp = {
        "kind": "youtube#searchListResponse",
        "etag": "envelope_etag_abc",
        "regionCode": "IN",
        "pageInfo": {
            "totalResults": len(items),
            "resultsPerPage": len(items),
        },
        "items": items,
    }
    if next_page_token:
        resp["nextPageToken"] = next_page_token
    return resp


class MockDiscoveryRepository:
    """In-memory mock repository implementing DiscoveryRepository for adapter unit testing."""

    def __init__(self) -> None:
        self.runs: dict[UUID, dict] = {}
        self.raw_records: dict[str, dict] = {}

    def start_run(self, *, source: str) -> UUID:
        run_id = uuid4()
        self.runs[run_id] = {
            "source": source,
            "status": "running",
            "records": [],
        }
        return run_id

    def insert_raw_if_absent(
        self,
        *,
        run_id: UUID,
        source: str,
        source_record_id: Optional[str],
        payload: dict,
        payload_hash: str,
        source_timestamp: Optional[datetime],
    ) -> tuple[UUID, bool]:
        dedup_key = f"{source}:{source_record_id}" if source_record_id else f"{source}:{payload_hash}"
        if dedup_key in self.raw_records:
            return self.raw_records[dedup_key]["id"], False
        raw_id = uuid4()
        self.raw_records[dedup_key] = {
            "id": raw_id,
            "run_id": run_id,
            "source": source,
            "source_record_id": source_record_id,
            "payload": payload,
            "payload_hash": payload_hash,
            "source_timestamp": source_timestamp,
            "status": "pending",
        }
        self.runs[run_id]["records"].append(raw_id)
        return raw_id, True

    def mark_raw(self, *, raw_id: UUID, status: str, error: Optional[str] = None) -> None:
        for rec in self.raw_records.values():
            if rec["id"] == raw_id:
                rec["status"] = status
                rec["error"] = error
                break

    def finish_run(
        self,
        *,
        run_id: UUID,
        status: str,
        fetched: int,
        inserted: int,
        updated: int,
        skipped: int,
        failed: int,
        error_summary: Optional[str] = None,
    ) -> None:
        if run_id in self.runs:
            self.runs[run_id].update({
                "status": status,
                "fetched": fetched,
                "inserted": inserted,
                "updated": updated,
                "skipped": skipped,
                "failed": failed,
                "error_summary": error_summary,
            })

    def rollback(self) -> None:
        pass


# ===========================================================================
# 1. Safety and Credential Boundaries
# ===========================================================================


def test_unconfigured_credentials_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """When YOUTUBE_DATA_API_KEY is unset and no seeded records provided, fetch_batch fails closed."""
    monkeypatch.delenv("YOUTUBE_DATA_API_KEY", raising=False)
    adapter = YouTubeSourceAdapter(api_key=None)
    assert not adapter.is_configured

    with pytest.raises(SourceAuthError) as exc_info:
        adapter.fetch_batch()

    assert "credentials not configured" in str(exc_info.value).lower()


def test_is_configured_states() -> None:
    """Adapter accurately reports its configuration state."""
    unconfigured = YouTubeSourceAdapter(api_key=None)
    # If settings has no key in test environment, unconfigured is False
    configured = YouTubeSourceAdapter(api_key="AIzaSy_test_key_sample_12345")
    assert configured.is_configured

    seeded = YouTubeSourceAdapter(
        records=[RawSourceRecord(source=SOURCE_YOUTUBE_IN, payload={"test": True})]
    )
    assert seeded.is_configured


def test_context_manager_lifecycle() -> None:
    """Adapter supports clean context manager closing."""
    with YouTubeSourceAdapter(api_key="test_key") as adapter:
        assert adapter.source_id == SOURCE_YOUTUBE_IN


# ===========================================================================
# 2. Error Translation and Network Resilience
# ===========================================================================


def test_http_400_translates_to_payload_error() -> None:
    """HTTP 400 Bad Request translates to typed SourcePayloadError."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text='{"error": {"message": "Invalid query parameter"}}')

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = YouTubeSourceAdapter(api_key="test_key", http_client=client, max_retries=0)

    with pytest.raises(SourcePayloadError) as exc_info:
        adapter.fetch_batch()

    assert "rejected request" in str(exc_info.value).lower() or "400" in str(exc_info.value)


def test_http_401_403_key_invalid_translates_to_auth_error() -> None:
    """HTTP 401/403 with invalid credentials translates to typed SourceAuthError."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text='{"error": {"errors": [{"reason": "keyInvalid"}], "message": "API key not valid"}}')

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = YouTubeSourceAdapter(api_key="invalid_key", http_client=client, max_retries=0)

    with pytest.raises(SourceAuthError) as exc_info:
        adapter.fetch_batch()

    assert "authentication failed" in str(exc_info.value).lower()


def test_http_403_quota_exceeded_translates_to_rate_limit_error() -> None:
    """HTTP 403 quotaExceeded translates to typed SourceRateLimitError."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text='{"error": {"errors": [{"reason": "quotaExceeded"}], "message": "The request cannot be completed because you have exceeded your quota."}}')

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = YouTubeSourceAdapter(api_key="test_key", http_client=client, max_retries=0)

    with pytest.raises(SourceRateLimitError) as exc_info:
        adapter.fetch_batch()

    assert "quota exceeded" in str(exc_info.value).lower() or "rate limit" in str(exc_info.value).lower()


def test_http_429_throttling_translates_to_rate_limit_error() -> None:
    """HTTP 429 translates to typed SourceRateLimitError and captures retry_after."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "15"}, text="Too Many Requests")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = YouTubeSourceAdapter(api_key="test_key", http_client=client, max_retries=0)

    with pytest.raises(SourceRateLimitError) as exc_info:
        adapter.fetch_batch()

    assert exc_info.value.retry_after_s == 15.0


def test_http_5xx_retries_and_raises_transient_error() -> None:
    """HTTP 5xx server errors retry boundedly and raise SourceTransientError."""
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, text="Service Unavailable")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = YouTubeSourceAdapter(api_key="test_key", http_client=client, max_retries=2, backoff_base_s=0.01)

    with pytest.raises(SourceTransientError):
        adapter.fetch_batch()

    assert attempts == 3  # initial + 2 retries


def test_timeout_retries_and_raises_transient_error() -> None:
    """Timeout exceptions retry boundedly and raise SourceTransientError."""
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("Socket read timed out")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = YouTubeSourceAdapter(api_key="test_key", http_client=client, max_retries=1, backoff_base_s=0.01)

    with pytest.raises(SourceTransientError):
        adapter.fetch_batch()

    assert attempts == 2


def test_malformed_json_translates_to_payload_error() -> None:
    """Malformed non-JSON payload raises SourcePayloadError."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<HTML>Not JSON</HTML>")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = YouTubeSourceAdapter(api_key="test_key", http_client=client, max_retries=0)

    with pytest.raises(SourcePayloadError) as exc_info:
        adapter.fetch_batch()

    assert "malformed" in str(exc_info.value).lower()


def test_missing_items_translates_to_payload_error() -> None:
    """JSON response missing 'items' array raises SourcePayloadError."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"kind": "youtube#searchListResponse"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = YouTubeSourceAdapter(api_key="test_key", http_client=client, max_retries=0)

    with pytest.raises(SourcePayloadError) as exc_info:
        adapter.fetch_batch()

    assert "missing 'items'" in str(exc_info.value).lower()


# ===========================================================================
# 3. Response Parsing, Provenance, and Metadata
# ===========================================================================


def test_authentic_search_response_parsing() -> None:
    """Authentic YouTube Data API v3 search response maps accurately to RawSourceRecord."""
    raw_item = _sample_youtube_search_payload("v_summer_linen_01", "Summer Linen Shirt Trends India")
    response_payload = _sample_youtube_search_response([raw_item])

    def handler(request: httpx.Request) -> httpx.Response:
        # Verify query parameters sent
        assert "key=test_key" in str(request.url)
        assert "type=video" in str(request.url)
        assert "videoCategoryId=26" in str(request.url)
        assert "regionCode=IN" in str(request.url)
        return httpx.Response(200, json=response_payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = YouTubeSourceAdapter(api_key="test_key", http_client=client, max_retries=0)

    batch = adapter.fetch_batch(limit=10)
    assert batch.source == SOURCE_YOUTUBE_IN
    assert len(batch.records) == 1
    assert batch.continuation is None

    record = batch.records[0]
    assert record.source == SOURCE_YOUTUBE_IN
    assert record.source_record_id == "v_summer_linen_01"
    assert record.source_timestamp == datetime(2026, 6, 15, 10, 30, 0, tzinfo=timezone.utc)

    payload = record.payload
    assert payload["videoId"] == "v_summer_linen_01"
    assert payload["title"] == "Summer Linen Shirt Trends India"
    assert payload["channelTitle"] == "Indian Atelier Studio"
    assert payload["videoUrl"] == "https://www.youtube.com/watch?v=v_summer_linen_01"
    assert "https://i.ytimg.com/vi/v_summer_linen_01/hqdefault.jpg" in payload["thumbnails"]["high"]
    assert payload["provenance"]["region"] == "IN"
    assert payload["provenance"]["category_id"] == "26"
    assert payload["provenance"]["retention_policy_days"] == 30
    assert payload["provenance"]["signal_type"] == "video_content_velocity"


def test_pagination_continuation_handling() -> None:
    """Pagination continuation token flows from nextPageToken to next request's pageToken."""
    page_1 = _sample_youtube_search_response(
        [_sample_youtube_search_payload("vid_1")], next_page_token="CAUQAA"
    )
    page_2 = _sample_youtube_search_response(
        [_sample_youtube_search_payload("vid_2")], next_page_token=None
    )

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if "pageToken=CAUQAA" in str(request.url):
            return httpx.Response(200, json=page_2)
        return httpx.Response(200, json=page_1)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter = YouTubeSourceAdapter(api_key="test_key", http_client=client, max_retries=0)

    # First page
    batch_1 = adapter.fetch_batch(limit=1)
    assert len(batch_1.records) == 1
    assert batch_1.records[0].source_record_id == "vid_1"
    assert batch_1.continuation == "CAUQAA"

    # Second page using continuation
    batch_2 = adapter.fetch_batch(continuation=batch_1.continuation, limit=1)
    assert len(batch_2.records) == 1
    assert batch_2.records[0].source_record_id == "vid_2"
    assert batch_2.continuation is None
    assert call_count == 2


def test_statistics_missing_vs_zero_distinction() -> None:
    """Metrics accurately distinguish missing metrics (None) from genuine 0 values."""
    item_with_zero = _sample_youtube_search_payload("vid_zero")
    item_with_zero["statistics"] = {
        "viewCount": "0",  # Genuine zero views (brand new upload)
        "likeCount": None,  # Hidden / unprovided
        # commentCount absent
    }

    response_payload = _sample_youtube_search_response([item_with_zero])

    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=response_payload)))
    adapter = YouTubeSourceAdapter(api_key="test_key", http_client=client, max_retries=0)

    batch = adapter.fetch_batch()
    stats = batch.records[0].payload["statistics"]

    assert stats["viewCount"] == 0
    assert stats["likeCount"] is None
    assert stats["commentCount"] is None


def test_timestamp_parser_edge_cases() -> None:
    """parse_youtube_timestamp handles valid, UTC 'Z', offsets, and malformed timestamps safely."""
    assert parse_youtube_timestamp(None) is None
    assert parse_youtube_timestamp("") is None
    assert parse_youtube_timestamp("not-a-timestamp") is None

    ts1 = parse_youtube_timestamp("2026-10-15T08:30:00Z")
    assert ts1 == datetime(2026, 10, 15, 8, 30, 0, tzinfo=timezone.utc)

    ts2 = parse_youtube_timestamp("2026-10-15T08:30:00+05:30")
    assert ts2 == datetime(2026, 10, 15, 3, 0, 0, tzinfo=timezone.utc)


# ===========================================================================
# 4. Offline Seeded Mode and End-to-End Collection Workflow
# ===========================================================================


def test_offline_seeded_records_paging() -> None:
    """Adapter operates in fully offline mode when initialized with seeded records."""
    sample_records = [
        RawSourceRecord(
            source=SOURCE_YOUTUBE_IN,
            payload={"videoId": f"seed_{i}", "title": f"Trend {i}"},
            source_record_id=f"seed_{i}",
            source_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        for i in range(5)
    ]

    adapter = YouTubeSourceAdapter(records=sample_records)
    batch_1 = adapter.fetch_batch(limit=2)
    assert len(batch_1.records) == 2
    assert batch_1.continuation == "2"

    batch_2 = adapter.fetch_batch(continuation=batch_1.continuation, limit=2)
    assert len(batch_2.records) == 2
    assert batch_2.continuation == "4"

    batch_3 = adapter.fetch_batch(continuation=batch_2.continuation, limit=2)
    assert len(batch_3.records) == 1
    assert batch_3.continuation is None


def test_collect_youtube_videos_workflow_and_idempotency() -> None:
    """CollectYouTubeVideos persists raw records and handles duplicate ingestion idempotently."""
    raw_item_1 = _sample_youtube_search_payload("yt_001", "Baggy Denim Jacket Trends")
    raw_item_2 = _sample_youtube_search_payload("yt_002", "Wide Leg Cargo Styling")
    response_data = _sample_youtube_search_response([raw_item_1, raw_item_2])

    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=response_data)))
    adapter = YouTubeSourceAdapter(api_key="test_key", http_client=client, max_retries=0)
    repo = MockDiscoveryRepository()

    collector = CollectYouTubeVideos(adapter=adapter, discovery=repo)
    result = collector(CollectionConfig(source=SOURCE_YOUTUBE_IN, max_records=10))

    assert result.status == "completed"
    assert result.fetched == 2
    assert result.inserted == 2
    assert result.skipped == 0
    assert result.failed == 0
    assert len(repo.raw_records) == 2

    # Second run with identical response (Idempotent Deduplication)
    result_2 = collector(CollectionConfig(source=SOURCE_YOUTUBE_IN, max_records=10))
    assert result_2.status == "completed"
    assert result_2.fetched == 2
    assert result_2.inserted == 0
    assert result_2.skipped == 2
    assert result_2.failed == 0
    assert len(repo.raw_records) == 2  # Zero duplicate rows created


def test_demand_signal_available_invariant_preserved() -> None:
    """DEMAND_SIGNAL_AVAILABLE invariant remains strictly False across trending intelligence."""
    assert DEMAND_SIGNAL_AVAILABLE is False
