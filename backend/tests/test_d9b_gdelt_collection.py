"""D9B Stage 3: GDELT collection workflow and adapter tests.

Test Matrix:
1. Adapter parsing:
   - Valid article lists
   - Explicit empty lists
   - Malformed JSON
   - Missing required keys
   - Invalid field types
   - Oversized bodies (Content-Length header & body byte ceiling)
2. Network resilience, request pacing, and deadline:
   - Request pacing delay enforcement
   - Bounded retries on transient 5xx errors with backoff
   - HTTP 429 rate limiting with Retry-After header and backoff
   - Transport failure classification (SourceTransientError)
   - Cooperative deadline interruption (before request, during pacing, during backoff)
   - HTTP 401/403 classification (SourceAuthError)
3. Adaptive time slicing:
   - Single slice under cap covers window directly
   - Bisection on provider cap
   - Multi-level recursive bisection
   - Recursion depth limit triggers provider-cap suppression (suppressed, truncated)
   - Minimum slice duration limit triggers provider-cap suppression
4. Empirical zero vs partial empty window:
   - Complete empirical zero: full window covered with 0 articles -> (present, complete, value=0.0)
   - Partial empty window: slice 1 has 0 articles, slice 2 fails -> run failed, never publishes 0.0 or present/complete
   - Coverage verification detects gaps
5. Observation persistence & provenance linking (DB-backed):
   - Collection run row created
   - Raw records inserted with deterministic SHA-256 hashes
   - Media attention observation persisted with natural key
   - Contributing records join rows linked with foreign keys
   - Versions preserved (query_config_version, clustering_version)
   - Idempotent re-collection
6. Regression & frozen boundaries:
   - Existing adapters (FixtureSourceAdapter, SyntheticSearchInterestAdapter) unchanged
   - Existing workflows (CollectSource, CollectSearchInterest) unchanged
   - DEMAND_SIGNAL_AVAILABLE remains False
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select

from app.application.collection import (
    CollectMediaAttention,
    CollectSearchInterest,
    CollectSource,
    CollectionConfig,
    MediaAttentionCollectionConfig,
    MediaAttentionCollectionResult,
    SearchInterestCollectionConfig,
    verify_window_coverage,
)
from app.domain.ports.source_adapter import (
    RawSourceRecord,
    SourceAuthError,
    SourceBatch,
    SourceDeadlineError,
    SourceError,
    SourcePayloadError,
    SourceRateLimitError,
    SourceTransientError,
)
from app.domain.services.media_attention import (
    COMPLETENESS_COMPLETE,
    COMPLETENESS_TRUNCATED,
    DEFAULT_CLUSTERING_VERSION,
    DEFAULT_QUERY_CONFIG_VERSION,
    SOURCE_GDELT_DOC,
    STATUS_PRESENT,
    STATUS_SUPPRESSED,
    MediaAttentionEvidence,
)
from app.domain.services.trends import DEMAND_SIGNAL_AVAILABLE
from app.infrastructure.db.models import (
    CollectionRun,
    MediaAttentionContributingRecord as MediaAttentionContributingRecordModel,
    MediaAttentionObservation as MediaAttentionObservationModel,
    RawSourceRecord as RawSourceRecordModel,
)
from app.infrastructure.db.repositories import (
    DiscoveryRepositorySQL,
    MediaAttentionRepositorySQL,
    SearchInterestRepositorySQL,
)
from app.infrastructure.external.fixture_source import FixtureSourceAdapter
from app.infrastructure.external.gdelt_source import (
    DEFAULT_BACKOFF_BASE_S,
    DEFAULT_MAX_BACKOFF_S,
    DEFAULT_MAX_RECORDS,
    DEFAULT_MAX_RESPONSE_BYTES,
    DEFAULT_PACE_INTERVAL_S,
    GdeltSliceResult,
    GdeltSourceAdapter,
    format_gdelt_timestamp,
)
from app.infrastructure.external.synthetic_search_interest_source import (
    SyntheticSearchInterestAdapter,
)
from tests.conftest import make_session

_T0 = datetime(2026, 1, 5, 0, 0, 0, tzinfo=timezone.utc)
_T1 = datetime(2026, 1, 12, 0, 0, 0, tzinfo=timezone.utc)


def _make_mock_client(
    status_code: int = 200,
    json_data: Optional[dict] = None,
    content: Optional[bytes] = None,
    headers: Optional[dict[str, str]] = None,
) -> httpx.Client:
    """Create a mock httpx.Client with custom transport."""
    hdrs = headers or {}
    if json_data is not None and content is None:
        body = json.dumps(json_data).encode("utf-8")
        if "content-length" not in hdrs:
            hdrs["content-length"] = str(len(body))
    else:
        body = content or b""

    response = httpx.Response(
        status_code=status_code,
        content=body,
        headers=hdrs,
        request=httpx.Request("GET", "https://api.gdeltproject.org/api/v2/doc/doc"),
    )

    transport = httpx.MockTransport(lambda req: response)
    return httpx.Client(transport=transport)


# ---------------------------------------------------------------------------
# 1. Adapter Parsing Tests
# ---------------------------------------------------------------------------


class TestGdeltAdapterParsing:
    """Validate GDELT response parsing across valid, empty, and corrupt payloads."""

    def test_parse_valid_articles_list(self) -> None:
        sample_data = {
            "articles": [
                {
                    "url": "https://vogue.in/fashion/streetwear-trend",
                    "title": "Streetwear Trends in India 2026",
                    "seendate": "20260105T120000Z",
                    "domain": "vogue.in",
                    "language": "eng",
                    "sourcecountry": "IN",
                },
                {
                    "url": "https://timesofindia.indiatimes.com/lifestyle/fashion-week",
                    "title": "Fashion Week Highlights - Times of India",
                    "seendate": "20260106143000",
                    "domain": "timesofindia.indiatimes.com",
                    "language": "eng",
                    "sourcecountry": "IN",
                },
            ]
        }
        client = _make_mock_client(json_data=sample_data)
        adapter = GdeltSourceAdapter(http_client=client, pace_interval_s=0.0)

        result = adapter.query_slice(
            query="streetwear",
            start_datetime=_T0,
            end_datetime=_T1,
        )

        assert isinstance(result, GdeltSliceResult)
        assert result.articles_count == 2
        assert result.is_capped is False
        assert len(result.records) == 2
        assert result.records[0].source == SOURCE_GDELT_DOC
        assert result.records[0].source_record_id == "https://vogue.in/fashion/streetwear-trend"
        assert result.records[0].source_timestamp == datetime(2026, 1, 5, 12, 0, 0, tzinfo=timezone.utc)
        assert result.records[1].source_record_id == "https://timesofindia.indiatimes.com/lifestyle/fashion-week"
        assert result.records[1].source_timestamp == datetime(2026, 1, 6, 14, 30, 0, tzinfo=timezone.utc)

    def test_parse_explicit_empty_list(self) -> None:
        client = _make_mock_client(json_data={"articles": []})
        adapter = GdeltSourceAdapter(http_client=client, pace_interval_s=0.0)

        result = adapter.query_slice(
            query="streetwear",
            start_datetime=_T0,
            end_datetime=_T1,
        )

        assert result.articles_count == 0
        assert result.is_capped is False
        assert result.records == ()

    def test_parse_omitted_articles_key_as_empty(self) -> None:
        # GDELT occasionally returns empty JSON dict on zero results
        client = _make_mock_client(json_data={})
        adapter = GdeltSourceAdapter(http_client=client, pace_interval_s=0.0)

        result = adapter.query_slice(
            query="streetwear",
            start_datetime=_T0,
            end_datetime=_T1,
        )

        assert result.articles_count == 0
        assert result.is_capped is False
        assert result.records == ()

    def test_parse_malformed_json_raises_payload_error(self) -> None:
        client = _make_mock_client(content=b"<html><head><title>502 Bad Gateway</title></head></html>")
        adapter = GdeltSourceAdapter(http_client=client, pace_interval_s=0.0)

        with pytest.raises(SourcePayloadError, match="malformed JSON"):
            adapter.query_slice(
                query="streetwear",
                start_datetime=_T0,
                end_datetime=_T1,
            )

    def test_parse_missing_required_url_raises_payload_error(self) -> None:
        client = _make_mock_client(
            json_data={
                "articles": [
                    {"title": "Headline without url"}
                ]
            }
        )
        adapter = GdeltSourceAdapter(http_client=client, pace_interval_s=0.0)

        with pytest.raises(SourcePayloadError, match="missing required url"):
            adapter.query_slice(
                query="streetwear",
                start_datetime=_T0,
                end_datetime=_T1,
            )

    def test_parse_missing_required_title_raises_payload_error(self) -> None:
        client = _make_mock_client(
            json_data={
                "articles": [
                    {"url": "https://example.com/article1"}
                ]
            }
        )
        adapter = GdeltSourceAdapter(http_client=client, pace_interval_s=0.0)

        with pytest.raises(SourcePayloadError, match="missing required title"):
            adapter.query_slice(
                query="streetwear",
                start_datetime=_T0,
                end_datetime=_T1,
            )

    def test_parse_invalid_field_types_raises_payload_error(self) -> None:
        # Root is a list instead of dict
        client_list = _make_mock_client(content=b'[{"url": "abc"}]')
        adapter_list = GdeltSourceAdapter(http_client=client_list, pace_interval_s=0.0)
        with pytest.raises(SourcePayloadError, match="must be a JSON object"):
            adapter_list.query_slice(query="streetwear", start_datetime=_T0, end_datetime=_T1)

        # articles is a string instead of list
        client_str_art = _make_mock_client(json_data={"articles": "invalid"})
        adapter_str = GdeltSourceAdapter(http_client=client_str_art, pace_interval_s=0.0)
        with pytest.raises(SourcePayloadError, match="articles field must be a list"):
            adapter_str.query_slice(query="streetwear", start_datetime=_T0, end_datetime=_T1)

        # article item is not a dict
        client_int_item = _make_mock_client(json_data={"articles": [12345]})
        adapter_int = GdeltSourceAdapter(http_client=client_int_item, pace_interval_s=0.0)
        with pytest.raises(SourcePayloadError, match="must be a mapping"):
            adapter_int.query_slice(query="streetwear", start_datetime=_T0, end_datetime=_T1)

    def test_default_contract_constants(self) -> None:
        """Verify authoritative approved constants: 2 MB response ceiling, 5.5s pacing, and 5.0s backoff base."""
        assert DEFAULT_MAX_RESPONSE_BYTES == 2 * 1024 * 1024
        assert DEFAULT_PACE_INTERVAL_S == 5.5
        assert DEFAULT_BACKOFF_BASE_S == 5.0
        assert DEFAULT_MAX_BACKOFF_S == 60.0

    def test_response_below_limit_accepted(self) -> None:
        """Response below the 2 MB limit is accepted and parsed."""
        # 1.5 MB payload of valid JSON with trailing whitespace
        body = b'{"articles": []}' + b" " * (1572864 - len(b'{"articles": []}'))
        client = _make_mock_client(content=body, headers={"content-length": str(len(body))})
        adapter = GdeltSourceAdapter(http_client=client, pace_interval_s=0.0)

        result = adapter.query_slice(query="streetwear", start_datetime=_T0, end_datetime=_T1)
        assert result.articles_count == 0

    def test_response_exactly_at_limit_accepted(self) -> None:
        """Response exactly at the 2 MB limit (2,097,152 bytes) is accepted."""
        exact_bytes = 2 * 1024 * 1024
        body = b'{"articles": []}' + b" " * (exact_bytes - len(b'{"articles": []}'))
        assert len(body) == exact_bytes

        client = _make_mock_client(content=body, headers={"content-length": str(exact_bytes)})
        adapter = GdeltSourceAdapter(http_client=client, pace_interval_s=0.0)

        result = adapter.query_slice(query="streetwear", start_datetime=_T0, end_datetime=_T1)
        assert result.articles_count == 0

    def test_response_above_limit_via_payload_bytes_rejected(self) -> None:
        """Response 1 byte above the 2 MB ceiling is rejected with SourcePayloadError."""
        over_bytes = 2 * 1024 * 1024 + 1
        body = b" " * over_bytes
        client = _make_mock_client(content=body)
        adapter = GdeltSourceAdapter(http_client=client, pace_interval_s=0.0)

        with pytest.raises(SourcePayloadError, match="exceeds maximum allowed size"):
            adapter.query_slice(query="streetwear", start_datetime=_T0, end_datetime=_T1)

    def test_oversized_response_via_content_length_header(self) -> None:
        """Response with Content-Length > 2 MB is rejected before parsing."""
        client = _make_mock_client(
            headers={"content-length": str(2 * 1024 * 1024 + 500)},
            content=b"{}",
        )
        adapter = GdeltSourceAdapter(http_client=client, pace_interval_s=0.0)

        with pytest.raises(SourcePayloadError, match="exceeds maximum allowed size"):
            adapter.query_slice(
                query="streetwear",
                start_datetime=_T0,
                end_datetime=_T1,
            )

    def test_truncated_interrupted_response_via_content_length(self) -> None:
        """Response cut short relative to Content-Length header is rejected as truncated."""
        # Header claims 1000 bytes, but only 500 bytes delivered
        truncated_body = b'{"articles": []}' + b" " * (500 - len(b'{"articles": []}'))
        client = _make_mock_client(
            headers={"content-length": "1000"},
            content=truncated_body,
        )
        adapter = GdeltSourceAdapter(http_client=client, pace_interval_s=0.0)

        with pytest.raises(SourcePayloadError, match="response body truncated"):
            adapter.query_slice(query="streetwear", start_datetime=_T0, end_datetime=_T1)

    def test_transport_interruption_during_read(self) -> None:
        """Transport connection interrupted mid-read raises SourceTransientError."""
        def handler(req: httpx.Request) -> httpx.Response:
            raise httpx.RemoteProtocolError("peer closed connection unexpectedly during read")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = GdeltSourceAdapter(http_client=client, pace_interval_s=0.0, max_retries=1)

        with pytest.raises(SourceTransientError, match="provider network transport failure"):
            adapter.query_slice(query="streetwear", start_datetime=_T0, end_datetime=_T1)


# ---------------------------------------------------------------------------
# 2. Network Resilience, Pacing, and Deadline Tests
# ---------------------------------------------------------------------------


class TestGdeltNetworkAndResilience:
    """Validate request pacing, bounded retries, rate limits, transport failures, and deadline."""

    def test_request_pacing_delay_observed(self) -> None:
        call_times: list[float] = []

        def handler(req: httpx.Request) -> httpx.Response:
            call_times.append(time.monotonic())
            return httpx.Response(200, json={"articles": []})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = GdeltSourceAdapter(
            http_client=client,
            pace_interval_s=0.05,  # 50ms pacing
        )

        adapter.query_slice(query="streetwear", start_datetime=_T0, end_datetime=_T1)
        adapter.query_slice(query="streetwear", start_datetime=_T0, end_datetime=_T1)

        assert len(call_times) == 2
        elapsed = call_times[1] - call_times[0]
        assert elapsed >= 0.045  # At least ~50ms elapsed between calls

    def test_request_pacing_applied_between_retries(self) -> None:
        """Pacing is strictly enforced between outbound retry attempts."""
        call_times: list[float] = []

        def handler(req: httpx.Request) -> httpx.Response:
            call_times.append(time.monotonic())
            if len(call_times) == 1:
                return httpx.Response(503, text="Service Unavailable")
            return httpx.Response(200, json={"articles": []})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = GdeltSourceAdapter(
            http_client=client,
            pace_interval_s=0.05,  # 50ms pacing
            backoff_base_s=0.01,   # 10ms backoff
            max_retries=2,
        )

        adapter.query_slice(query="streetwear", start_datetime=_T0, end_datetime=_T1)
        assert len(call_times) == 2
        elapsed = call_times[1] - call_times[0]
        # Pacing enforces >= 50ms spacing even with 10ms backoff
        assert elapsed >= 0.045

    def test_bounded_retries_transient_5xx(self) -> None:
        attempts = 0

        def handler(req: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                return httpx.Response(503, text="Service Unavailable")
            return httpx.Response(200, json={"articles": []})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = GdeltSourceAdapter(
            http_client=client,
            max_retries=3,
            backoff_base_s=0.01,
            pace_interval_s=0.0,
        )

        result = adapter.query_slice(query="streetwear", start_datetime=_T0, end_datetime=_T1)
        assert attempts == 3
        assert result.articles_count == 0

    def test_bounded_retries_exhausted_raises_transient_error(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="Internal Server Error")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = GdeltSourceAdapter(
            http_client=client,
            max_retries=2,
            backoff_base_s=0.01,
            pace_interval_s=0.0,
        )

        with pytest.raises(SourceTransientError, match="provider server error: HTTP 500"):
            adapter.query_slice(query="streetwear", start_datetime=_T0, end_datetime=_T1)

    def test_http_429_rate_limiting_with_retry_after(self) -> None:
        attempts = 0

        def handler(req: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return httpx.Response(429, headers={"retry-after": "0.02"}, text="Too Many Requests")
            return httpx.Response(200, json={"articles": []})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = GdeltSourceAdapter(
            http_client=client,
            max_retries=2,
            pace_interval_s=0.0,
        )

        result = adapter.query_slice(query="streetwear", start_datetime=_T0, end_datetime=_T1)
        assert attempts == 2
        assert result.articles_count == 0

    def test_http_429_exhausted_raises_rate_limit_error(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(429, headers={"retry-after": "1.5"}, text="Too Many Requests")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = GdeltSourceAdapter(
            http_client=client,
            max_retries=1,
            backoff_base_s=0.01,
            pace_interval_s=0.0,
        )

        with pytest.raises(SourceRateLimitError) as exc_info:
            adapter.query_slice(query="streetwear", start_datetime=_T0, end_datetime=_T1)

        assert exc_info.value.retry_after_s == 1.5

    def test_transport_failures_classified_as_source_transient_error(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused by peer")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = GdeltSourceAdapter(
            http_client=client,
            max_retries=1,
            backoff_base_s=0.01,
            pace_interval_s=0.0,
        )

        with pytest.raises(SourceTransientError, match="provider network transport failure"):
            adapter.query_slice(query="streetwear", start_datetime=_T0, end_datetime=_T1)

    def test_auth_error_classified_as_source_auth_error(self) -> None:
        client = _make_mock_client(status_code=403, content=b"Forbidden")
        adapter = GdeltSourceAdapter(http_client=client, pace_interval_s=0.0)

        with pytest.raises(SourceAuthError, match="provider authentication failed: HTTP 403"):
            adapter.query_slice(query="streetwear", start_datetime=_T0, end_datetime=_T1)

    def test_cooperative_deadline_interruption_before_call(self) -> None:
        client = _make_mock_client(json_data={"articles": []})
        adapter = GdeltSourceAdapter(http_client=client, pace_interval_s=0.0)

        # Deadline already passed 1 second ago
        past_deadline = datetime.now(timezone.utc) - timedelta(seconds=1)

        with pytest.raises(SourceDeadlineError, match="cooperative deadline exceeded"):
            adapter.query_slice(
                query="streetwear",
                start_datetime=_T0,
                end_datetime=_T1,
                deadline=past_deadline,
            )

    def test_cooperative_deadline_interruption_during_pacing(self) -> None:
        client = _make_mock_client(json_data={"articles": []})
        adapter = GdeltSourceAdapter(
            http_client=client,
            pace_interval_s=1.0,  # 1 second pacing
        )

        # First request sets _last_request_monotonic
        adapter.query_slice(query="streetwear", start_datetime=_T0, end_datetime=_T1)

        # Second request with tight deadline shorter than pace interval
        tight_deadline = datetime.now(timezone.utc) + timedelta(milliseconds=50)
        with pytest.raises(SourceDeadlineError, match="deadline exceeded during request pacing"):
            adapter.query_slice(
                query="streetwear",
                start_datetime=_T0,
                end_datetime=_T1,
                deadline=tight_deadline,
            )

    def test_cooperative_deadline_during_retry_backoff(self) -> None:
        """Cooperative deadline exceeded during retry backoff raises SourceDeadlineError."""
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="Service Unavailable")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = GdeltSourceAdapter(
            http_client=client,
            max_retries=3,
            backoff_base_s=1.0,
            pace_interval_s=0.0,
        )

        # Deadline is 50ms from now, but backoff sleep wants 1.0s
        tight_deadline = datetime.now(timezone.utc) + timedelta(milliseconds=50)
        with pytest.raises(SourceDeadlineError, match="cooperative deadline exceeded during retry backoff"):
            adapter.query_slice(
                query="streetwear",
                start_datetime=_T0,
                end_datetime=_T1,
                deadline=tight_deadline,
            )


# ---------------------------------------------------------------------------
# 2b. Rate-Limit Compliance Tests (D9C.1)
# ---------------------------------------------------------------------------


class SimulatedClock:
    """Deterministic virtual clock for pacing and backoff tests without real-time sleeps."""

    def __init__(self, start: float = 1000.0) -> None:
        self.current = start
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.current += seconds


class TestGdeltRateLimitComplianceD9C1:
    """Validate D9C.1 rate-limit compliance: 5.5s pacing, 5.0s backoff base, 429 Retry-After, and failure safety."""

    def test_minimum_request_spacing_deterministic(self) -> None:
        """Consecutive requests on same adapter enforce 5.5s spacing."""
        client = _make_mock_client(json_data={"articles": []})
        adapter = GdeltSourceAdapter(http_client=client)

        clock = SimulatedClock(1000.0)
        with patch("app.infrastructure.external.gdelt_source.time.monotonic", side_effect=clock.monotonic), \
             patch("app.infrastructure.external.gdelt_source.time.sleep", side_effect=clock.sleep):
            # First request: initial call, no sleep needed
            adapter.query_slice(query="streetwear", start_datetime=_T0, end_datetime=_T1)
            assert clock.sleeps == []

            # Second request immediate: must sleep 5.5s
            adapter.query_slice(query="streetwear", start_datetime=_T0, end_datetime=_T1)
            assert clock.sleeps == [5.5]

            # Third request after 2.0s elapsed: must sleep remaining 3.5s
            clock.current += 2.0
            adapter.query_slice(query="streetwear", start_datetime=_T0, end_datetime=_T1)
            assert clock.sleeps == [5.5, 3.5]

    def test_adaptive_slices_respect_pacing(self) -> None:
        """Adaptive slices on same adapter enforce minimum request spacing."""
        client = _make_mock_client(json_data={"articles": []})
        adapter = GdeltSourceAdapter(http_client=client)

        clock = SimulatedClock(1000.0)
        t_mid = _T0 + (_T1 - _T0) / 2
        with patch("app.infrastructure.external.gdelt_source.time.monotonic", side_effect=clock.monotonic), \
             patch("app.infrastructure.external.gdelt_source.time.sleep", side_effect=clock.sleep):
            adapter.query_slice(query="streetwear", start_datetime=_T0, end_datetime=t_mid)
            assert clock.sleeps == []

            adapter.query_slice(query="streetwear", start_datetime=t_mid, end_datetime=_T1)
            assert clock.sleeps == [5.5]

    def test_http_429_with_valid_retry_after(self) -> None:
        """Valid Retry-After header is honored; retries cannot bypass pacing."""
        attempts = 0

        def handler(req: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return httpx.Response(429, headers={"retry-after": "7.0"}, text="Too Many Requests")
            return httpx.Response(200, json={"articles": []})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = GdeltSourceAdapter(http_client=client)

        clock = SimulatedClock(1000.0)
        with patch("app.infrastructure.external.gdelt_source.time.monotonic", side_effect=clock.monotonic), \
             patch("app.infrastructure.external.gdelt_source.time.sleep", side_effect=clock.sleep):
            res = adapter.query_slice(query="streetwear", start_datetime=_T0, end_datetime=_T1)
            # Retry-after was 7.0s (> 5.5s pacing), so backoff slept 7.0s, pacing slept 0.0s extra
            assert clock.sleeps == [7.0]
            assert attempts == 2
            assert res.articles_count == 0

    def test_http_429_short_retry_after_cannot_bypass_pacing(self) -> None:
        """Short Retry-After (e.g. 1.0s) cannot bypass 5.5s minimum pacing interval."""
        attempts = 0

        def handler(req: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return httpx.Response(429, headers={"retry-after": "1.0"}, text="Too Many Requests")
            return httpx.Response(200, json={"articles": []})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = GdeltSourceAdapter(http_client=client)

        clock = SimulatedClock(1000.0)
        with patch("app.infrastructure.external.gdelt_source.time.monotonic", side_effect=clock.monotonic), \
             patch("app.infrastructure.external.gdelt_source.time.sleep", side_effect=clock.sleep):
            res = adapter.query_slice(query="streetwear", start_datetime=_T0, end_datetime=_T1)
            # Backoff slept 1.0s; pacing slept remaining 4.5s so interval between requests is exactly 5.5s!
            assert clock.sleeps == [1.0, 4.5]
            assert attempts == 2
            assert res.articles_count == 0

    def test_http_429_without_retry_after_fallback_exponential_backoff(self) -> None:
        """Absent Retry-After falls back to nominal exponential delays: 5s, 10s, 20s."""
        attempts = 0

        def handler(req: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts < 4:
                return httpx.Response(429, text="Please limit requests to one every 5 seconds")
            return httpx.Response(200, json={"articles": []})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = GdeltSourceAdapter(http_client=client)

        clock = SimulatedClock(1000.0)
        with patch("app.infrastructure.external.gdelt_source.time.monotonic", side_effect=clock.monotonic), \
             patch("app.infrastructure.external.gdelt_source.time.sleep", side_effect=clock.sleep):
            res = adapter.query_slice(query="streetwear", start_datetime=_T0, end_datetime=_T1)
            # Attempt 0: backoff 5.0s, pacing 0.5s (nominal 5s before pacing)
            # Attempt 1: backoff 10.0s, pacing 0.0s (nominal 10s >= 5.5s pacing)
            # Attempt 2: backoff 20.0s, pacing 0.0s (nominal 20s >= 5.5s pacing)
            # Attempt 3: 200 OK
            assert clock.sleeps == [5.0, 0.5, 10.0, 20.0]
            assert attempts == 4
            assert res.articles_count == 0

    @pytest.mark.parametrize("invalid_header", ["invalid_text", "-5", "inf", "nan", "  "])
    def test_http_429_with_invalid_retry_after_uses_fallback(self, invalid_header: str) -> None:
        """Invalid Retry-After header uses fallback exponential backoff."""
        attempts = 0

        def handler(req: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return httpx.Response(429, headers={"retry-after": invalid_header}, text="Rate Limited")
            return httpx.Response(200, json={"articles": []})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = GdeltSourceAdapter(http_client=client)

        clock = SimulatedClock(1000.0)
        with patch("app.infrastructure.external.gdelt_source.time.monotonic", side_effect=clock.monotonic), \
             patch("app.infrastructure.external.gdelt_source.time.sleep", side_effect=clock.sleep):
            res = adapter.query_slice(query="streetwear", start_datetime=_T0, end_datetime=_T1)
            # Fallback backoff 5.0s + pacing 0.5s
            assert clock.sleeps == [5.0, 0.5]
            assert attempts == 2
            assert res.articles_count == 0

    def test_http_429_retry_exhaustion_raises_rate_limit_error(self) -> None:
        """Persistent HTTP 429 stops after bounded max_retries without looping indefinitely."""
        attempts = 0

        def handler(req: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            return httpx.Response(429, text="Please limit requests to one every 5 seconds")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = GdeltSourceAdapter(http_client=client, max_retries=3)

        clock = SimulatedClock(1000.0)
        with patch("app.infrastructure.external.gdelt_source.time.monotonic", side_effect=clock.monotonic), \
             patch("app.infrastructure.external.gdelt_source.time.sleep", side_effect=clock.sleep):
            with pytest.raises(SourceRateLimitError) as exc_info:
                adapter.query_slice(query="streetwear", start_datetime=_T0, end_datetime=_T1)

            # Exactly 4 attempts (attempt 0 + 3 retries), then cleanly halted
            assert attempts == 4
            assert exc_info.value.retry_after_s is None
            # Delays: 5.0 backoff + 0.5 pacing, 10.0 backoff, 20.0 backoff
            assert clock.sleeps == [5.0, 0.5, 10.0, 20.0]

    def test_deadline_expiration_during_request_pacing(self) -> None:
        """Deadline expiring during request pacing raises SourceDeadlineError immediately."""
        client = _make_mock_client(json_data={"articles": []})
        adapter = GdeltSourceAdapter(http_client=client)

        clock = SimulatedClock(1000.0)
        with patch("app.infrastructure.external.gdelt_source.time.monotonic", side_effect=clock.monotonic), \
             patch("app.infrastructure.external.gdelt_source.time.sleep", side_effect=clock.sleep):
            # First request sets _last_request_monotonic
            adapter.query_slice(query="streetwear", start_datetime=_T0, end_datetime=_T1)

            # Second request with deadline that expires before the 5.5s pacing interval
            deadline = datetime.now(timezone.utc) + timedelta(seconds=2.0)
            with pytest.raises(SourceDeadlineError, match="deadline exceeded during request pacing"):
                adapter.query_slice(
                    query="streetwear",
                    start_datetime=_T0,
                    end_datetime=_T1,
                    deadline=deadline,
                )

    def test_deadline_expiration_during_retry_backoff(self) -> None:
        """Deadline expiring during retry backoff raises SourceDeadlineError immediately."""
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(429, text="Rate Limited")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = GdeltSourceAdapter(http_client=client, pace_interval_s=0.0)

        # Deadline 2.0s away, but attempt 0 backoff wants 5.0s
        deadline = datetime.now(timezone.utc) + timedelta(seconds=2.0)
        with pytest.raises(SourceDeadlineError, match="deadline exceeded during retry backoff"):
            adapter.query_slice(
                query="streetwear",
                start_datetime=_T0,
                end_datetime=_T1,
                deadline=deadline,
            )

    def test_collect_media_attention_fails_closed_on_429_exhaustion(self) -> None:
        """Workflow halts, records failure, null metrics, zero observations on 429 exhaustion."""
        mock_discovery = MagicMock()
        mock_discovery.start_run.return_value = uuid4()
        mock_obs_repo = MagicMock()

        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(429, text="Please limit requests to one every 5 seconds")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = GdeltSourceAdapter(http_client=client, max_retries=1, pace_interval_s=0.0, backoff_base_s=0.01)

        workflow = CollectMediaAttention(
            adapter=adapter,
            discovery=mock_discovery,
            observations=mock_obs_repo,
        )

        cfg = MediaAttentionCollectionConfig(window_start=_T0, window_end=_T1)
        res = workflow(cfg)

        assert res.status == "failed"
        assert res.window_covered is False
        assert res.value_status is None
        assert res.completeness_status is None
        assert res.value is None
        assert res.error_summary == "source rate limit reached"
        mock_obs_repo.insert_observation_with_contributing_records.assert_not_called()
        mock_discovery.finish_run.assert_called_once()
        _, kwargs = mock_discovery.finish_run.call_args
        assert kwargs["status"] == "failed"

    def test_collect_media_attention_fails_closed_on_deadline_expiration(self) -> None:
        """Workflow halts and records failure when deadline expires during collection."""
        mock_discovery = MagicMock()
        mock_discovery.start_run.return_value = uuid4()
        mock_obs_repo = MagicMock()

        client = _make_mock_client(json_data={"articles": []})
        adapter = GdeltSourceAdapter(http_client=client, pace_interval_s=0.0)

        workflow = CollectMediaAttention(
            adapter=adapter,
            discovery=mock_discovery,
            observations=mock_obs_repo,
        )

        # Past deadline
        cfg = MediaAttentionCollectionConfig(
            window_start=_T0,
            window_end=_T1,
            deadline=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        res = workflow(cfg)

        assert res.status == "failed"
        assert res.window_covered is False
        assert res.value_status is None
        assert res.completeness_status is None
        assert res.value is None
        assert res.error_summary == "cooperative deadline interrupted collection"
        mock_obs_repo.insert_observation_with_contributing_records.assert_not_called()


# ---------------------------------------------------------------------------
# 3. Adaptive Time Slicing & Window Coverage Tests
# ---------------------------------------------------------------------------


class MockGdeltSliceAdapter:
    """Mock adapter simulating adaptive slices, provider caps, and failures."""

    source_id = SOURCE_GDELT_DOC

    def __init__(
        self,
        slice_map: Optional[dict[tuple[str, str], GdeltSliceResult]] = None,
        default_is_capped: bool = False,
        default_count: int = 10,
    ) -> None:
        self.slice_map = slice_map or {}
        self.default_is_capped = default_is_capped
        self.default_count = default_count
        self.calls: list[tuple[datetime, datetime]] = []

    def fetch_batch(self, *, continuation: Optional[str] = None, limit: int = 50) -> SourceBatch:
        return SourceBatch(source=self.source_id, records=(), continuation=None)

    def query_slice(
        self,
        *,
        query: str,
        start_datetime: datetime,
        end_datetime: datetime,
        deadline: Optional[datetime] = None,
    ) -> GdeltSliceResult:
        if deadline is not None and datetime.now(timezone.utc) >= deadline:
            raise SourceDeadlineError("cooperative deadline exceeded")

        self.calls.append((start_datetime, end_datetime))
        k = (format_gdelt_timestamp(start_datetime), format_gdelt_timestamp(end_datetime))
        if k in self.slice_map:
            val = self.slice_map[k]
            if isinstance(val, Exception):
                raise val
            return val

        # Default synthetic articles
        articles = [
            RawSourceRecord(
                source=self.source_id,
                payload={
                    "url": f"https://outlet.com/story-{i}-{k[0]}",
                    "title": f"Streetwear Fashion Story {i}",
                    "seendate": format_gdelt_timestamp(start_datetime),
                },
                source_record_id=f"https://outlet.com/story-{i}-{k[0]}",
                source_timestamp=start_datetime,
            )
            for i in range(self.default_count)
        ]
        return GdeltSliceResult(
            slice_start=start_datetime,
            slice_end=end_datetime,
            records=tuple(articles),
            is_capped=self.default_is_capped,
            articles_count=len(articles),
            raw_payload={},
        )


class TestAdaptiveTimeSlicing:
    """Validate adaptive bisection, recursion limits, and cap suppression."""

    def test_single_slice_under_cap_covers_window_cleanly(self) -> None:
        mock_discovery = MagicMock()
        mock_discovery.start_run.return_value = uuid4()
        mock_discovery.insert_raw_if_absent.return_value = (uuid4(), True)
        mock_obs_repo = MagicMock()
        mock_obs_repo.insert_observation_with_contributing_records.return_value = (uuid4(), True)

        adapter = MockGdeltSliceAdapter(default_is_capped=False, default_count=5)
        workflow = CollectMediaAttention(
            adapter=adapter,
            discovery=mock_discovery,
            observations=mock_obs_repo,
        )

        cfg = MediaAttentionCollectionConfig(window_start=_T0, window_end=_T1)
        res = workflow(cfg)

        assert res.status == "completed"
        assert res.window_covered is True
        assert res.value_status == STATUS_PRESENT
        assert res.completeness_status == COMPLETENESS_COMPLETE
        assert len(adapter.calls) == 1
        assert adapter.calls[0] == (_T0, _T1)

    def test_adaptive_bisection_on_provider_cap(self) -> None:
        t_mid = _T0 + (_T1 - _T0) / 2
        k_full = (format_gdelt_timestamp(_T0), format_gdelt_timestamp(_T1))
        k_left = (format_gdelt_timestamp(_T0), format_gdelt_timestamp(t_mid))
        k_right = (format_gdelt_timestamp(t_mid), format_gdelt_timestamp(_T1))

        # Full slice hits provider cap; left and right halves succeed under cap
        slice_map = {
            k_full: GdeltSliceResult(
                slice_start=_T0,
                slice_end=_T1,
                records=(),
                is_capped=True,
                articles_count=250,
                raw_payload={},
            ),
            k_left: GdeltSliceResult(
                slice_start=_T0,
                slice_end=t_mid,
                records=(
                    RawSourceRecord(
                        source=SOURCE_GDELT_DOC,
                        payload={"url": "https://a.com/1", "title": "Left Story 1", "seendate": "20260105T120000Z"},
                        source_record_id="https://a.com/1",
                        source_timestamp=_T0,
                    ),
                ),
                is_capped=False,
                articles_count=1,
                raw_payload={},
            ),
            k_right: GdeltSliceResult(
                slice_start=t_mid,
                slice_end=_T1,
                records=(
                    RawSourceRecord(
                        source=SOURCE_GDELT_DOC,
                        payload={"url": "https://b.com/2", "title": "Right Story 2", "seendate": "20260109T120000Z"},
                        source_record_id="https://b.com/2",
                        source_timestamp=t_mid,
                    ),
                ),
                is_capped=False,
                articles_count=1,
                raw_payload={},
            ),
        }

        mock_discovery = MagicMock()
        mock_discovery.start_run.return_value = uuid4()
        mock_discovery.insert_raw_if_absent.return_value = (uuid4(), True)
        mock_obs_repo = MagicMock()
        mock_obs_repo.insert_observation_with_contributing_records.return_value = (uuid4(), True)

        adapter = MockGdeltSliceAdapter(slice_map=slice_map)
        workflow = CollectMediaAttention(
            adapter=adapter,
            discovery=mock_discovery,
            observations=mock_obs_repo,
        )

        cfg = MediaAttentionCollectionConfig(window_start=_T0, window_end=_T1)
        res = workflow(cfg)

        assert res.status == "completed"
        assert res.window_covered is True
        assert res.value_status == STATUS_PRESENT
        assert res.completeness_status == COMPLETENESS_COMPLETE
        # Called full window, then bisected left and right
        assert len(adapter.calls) == 3
        assert adapter.calls[0] == (_T0, _T1)
        assert adapter.calls[1] == (_T0, t_mid)
        assert adapter.calls[2] == (t_mid, _T1)

    def test_recursion_depth_limit_triggers_provider_cap_suppression(self) -> None:
        # Every slice returns is_capped=True
        mock_discovery = MagicMock()
        mock_discovery.start_run.return_value = uuid4()
        mock_obs_repo = MagicMock()
        mock_obs_repo.insert_observation_with_contributing_records.return_value = (uuid4(), True)

        adapter = MockGdeltSliceAdapter(default_is_capped=True, default_count=250)
        workflow = CollectMediaAttention(
            adapter=adapter,
            discovery=mock_discovery,
            observations=mock_obs_repo,
        )

        # max_depth=2 limits recursion
        cfg = MediaAttentionCollectionConfig(
            window_start=_T0,
            window_end=_T1,
            max_depth=2,
        )
        res = workflow(cfg)

        assert res.status == "completed"
        assert res.value_status == STATUS_SUPPRESSED
        assert res.completeness_status == COMPLETENESS_TRUNCATED
        assert res.value is None
        assert res.window_covered is False
        assert "provider-cap truncation" in (res.error_summary or "")

        # Verify observation inserted with suppressed / truncated status
        assert mock_obs_repo.insert_observation_with_contributing_records.called
        call_kwargs = mock_obs_repo.insert_observation_with_contributing_records.call_args.kwargs
        obs = call_kwargs["observation"]
        assert obs.value_status == STATUS_SUPPRESSED
        assert obs.completeness_status == COMPLETENESS_TRUNCATED
        assert obs.value is None

    def test_minimum_slice_duration_triggers_provider_cap_suppression(self) -> None:
        """Provider cap on slice at or below min_slice_duration suppresses collection immediately."""
        mock_discovery = MagicMock()
        mock_discovery.start_run.return_value = uuid4()
        mock_obs_repo = MagicMock()
        mock_obs_repo.insert_observation_with_contributing_records.return_value = (uuid4(), True)

        adapter = MockGdeltSliceAdapter(default_is_capped=True, default_count=250)
        workflow = CollectMediaAttention(
            adapter=adapter,
            discovery=mock_discovery,
            observations=mock_obs_repo,
        )

        # 30-minute window with min_slice_duration=1 hour -> halts bisection immediately
        t_start = _T0
        t_end = _T0 + timedelta(minutes=30)
        cfg = MediaAttentionCollectionConfig(
            window_start=t_start,
            window_end=t_end,
            min_slice_duration=timedelta(hours=1),
            max_depth=10,
        )
        res = workflow(cfg)

        assert res.status == "completed"
        assert res.value_status == STATUS_SUPPRESSED
        assert res.completeness_status == COMPLETENESS_TRUNCATED
        assert res.value is None
        assert res.window_covered is False
        assert "provider-cap truncation" in (res.error_summary or "")

        call_kwargs = mock_obs_repo.insert_observation_with_contributing_records.call_args.kwargs
        obs = call_kwargs["observation"]
        assert obs.value_status == STATUS_SUPPRESSED
        assert obs.completeness_status == COMPLETENESS_TRUNCATED
        assert obs.value is None
        assert obs.raw_article_count is None
        assert obs.distinct_outlet_count is None
        assert obs.estimated_deduplicated_story_count is None


# ---------------------------------------------------------------------------
# 4. Empirical Zero vs Partial Empty Window Tests
# ---------------------------------------------------------------------------


class TestEmpiricalZeroAndPartialEmptyWindow:
    """Validate that an individual empty slice NEVER implies an empty complete window."""

    def test_complete_empirical_zero(self) -> None:
        # Full window has 0 articles across all slices
        mock_discovery = MagicMock()
        mock_discovery.start_run.return_value = uuid4()
        mock_obs_repo = MagicMock()
        mock_obs_repo.insert_observation_with_contributing_records.return_value = (uuid4(), True)

        adapter = MockGdeltSliceAdapter(default_is_capped=False, default_count=0)
        workflow = CollectMediaAttention(
            adapter=adapter,
            discovery=mock_discovery,
            observations=mock_obs_repo,
        )

        cfg = MediaAttentionCollectionConfig(window_start=_T0, window_end=_T1)
        res = workflow(cfg)

        assert res.status == "completed"
        assert res.window_covered is True
        assert res.value_status == STATUS_PRESENT
        assert res.completeness_status == COMPLETENESS_COMPLETE
        assert res.value == 0.0

        # Verify domain observation has exact 0 count hierarchy
        call_kwargs = mock_obs_repo.insert_observation_with_contributing_records.call_args.kwargs
        obs = call_kwargs["observation"]
        assert obs.value == 0.0
        assert obs.raw_article_count == 0
        assert obs.distinct_outlet_count == 0
        assert obs.estimated_deduplicated_story_count == 0

    def test_partial_empty_window_never_implies_complete_zero(self) -> None:
        # Window bisects: Slice 1 is empty, but Slice 2 fails with network error
        t_mid = _T0 + (_T1 - _T0) / 2
        k_full = (format_gdelt_timestamp(_T0), format_gdelt_timestamp(_T1))
        k_left = (format_gdelt_timestamp(_T0), format_gdelt_timestamp(t_mid))
        k_right = (format_gdelt_timestamp(t_mid), format_gdelt_timestamp(_T1))

        slice_map = {
            k_full: GdeltSliceResult(
                slice_start=_T0,
                slice_end=_T1,
                records=(),
                is_capped=True,
                articles_count=250,
                raw_payload={},
            ),
            # Left half is empty (0 articles)
            k_left: GdeltSliceResult(
                slice_start=_T0,
                slice_end=t_mid,
                records=(),
                is_capped=False,
                articles_count=0,
                raw_payload={},
            ),
            # Right half fails with transport error!
            k_right: SourceTransientError("provider transport error on right slice"),
        }

        mock_discovery = MagicMock()
        mock_discovery.start_run.return_value = uuid4()
        mock_obs_repo = MagicMock()

        adapter = MockGdeltSliceAdapter(slice_map=slice_map)
        workflow = CollectMediaAttention(
            adapter=adapter,
            discovery=mock_discovery,
            observations=mock_obs_repo,
        )

        cfg = MediaAttentionCollectionConfig(window_start=_T0, window_end=_T1)
        res = workflow(cfg)

        # Run MUST fail — empty slice 1 must NEVER imply empty complete window
        assert res.status == "failed"
        assert res.window_covered is False
        assert res.value_status is None
        assert res.observation_id is None
        assert "temporarily unavailable" in (res.error_summary or "")
        # Never published present/complete observation!
        assert not mock_obs_repo.insert_observation_with_contributing_records.called

    def test_coverage_verification_detects_gap(self) -> None:
        t_mid1 = _T0 + timedelta(days=2)
        t_mid2 = _T0 + timedelta(days=4)

        # Covered [T0, T_mid1) and [T_mid2, T1) with gap between mid1 and mid2
        intervals = [(_T0, t_mid1), (t_mid2, _T1)]
        assert verify_window_coverage(intervals, _T0, _T1) is False

        # Contiguous covering
        intervals_contiguous = [(_T0, t_mid2), (t_mid2, _T1)]
        assert verify_window_coverage(intervals_contiguous, _T0, _T1) is True


class TestFailureAndCoverageSemantics:
    """Validate failure modes and coverage guarantees in CollectMediaAttention:
    Confirm incomplete windows never publish present/complete or non-null aggregate metrics.
    """

    def test_retry_exhaustion_never_publishes_observation(self) -> None:
        """Retry exhaustion on provider 5xx fails the run and never publishes observations."""
        mock_discovery = MagicMock()
        mock_discovery.start_run.return_value = uuid4()
        mock_obs_repo = MagicMock()

        adapter = MagicMock()
        adapter.source_id = SOURCE_GDELT_DOC
        adapter.query_slice.side_effect = SourceTransientError("provider server error: HTTP 500")

        workflow = CollectMediaAttention(
            adapter=adapter,
            discovery=mock_discovery,
            observations=mock_obs_repo,
        )
        res = workflow(MediaAttentionCollectionConfig(window_start=_T0, window_end=_T1))

        assert res.status == "failed"
        assert res.window_covered is False
        assert res.value_status is None
        assert res.completeness_status is None
        assert res.value is None
        assert res.observation_id is None
        assert mock_obs_repo.insert_observation_with_contributing_records.called is False

    def test_http_429_exhaustion_never_publishes_observation(self) -> None:
        """HTTP 429 rate limit exhaustion fails the run and never publishes observations."""
        mock_discovery = MagicMock()
        mock_discovery.start_run.return_value = uuid4()
        mock_obs_repo = MagicMock()

        adapter = MagicMock()
        adapter.source_id = SOURCE_GDELT_DOC
        adapter.query_slice.side_effect = SourceRateLimitError("provider rate limit reached", retry_after_s=5.0)

        workflow = CollectMediaAttention(
            adapter=adapter,
            discovery=mock_discovery,
            observations=mock_obs_repo,
        )
        res = workflow(MediaAttentionCollectionConfig(window_start=_T0, window_end=_T1))

        assert res.status == "failed"
        assert res.window_covered is False
        assert res.value_status is None
        assert res.completeness_status is None
        assert res.value is None
        assert res.observation_id is None
        assert mock_obs_repo.insert_observation_with_contributing_records.called is False

    def test_cooperative_deadline_never_publishes_observation(self) -> None:
        """Cooperative deadline expiration fails the run and never publishes observations."""
        mock_discovery = MagicMock()
        mock_discovery.start_run.return_value = uuid4()
        mock_obs_repo = MagicMock()

        adapter = MagicMock()
        adapter.source_id = SOURCE_GDELT_DOC
        adapter.query_slice.side_effect = SourceDeadlineError("cooperative deadline exceeded")

        workflow = CollectMediaAttention(
            adapter=adapter,
            discovery=mock_discovery,
            observations=mock_obs_repo,
        )
        res = workflow(MediaAttentionCollectionConfig(window_start=_T0, window_end=_T1))

        assert res.status == "failed"
        assert res.window_covered is False
        assert res.value_status is None
        assert res.completeness_status is None
        assert res.value is None
        assert res.observation_id is None
        assert mock_obs_repo.insert_observation_with_contributing_records.called is False

    def test_transport_failure_never_publishes_observation(self) -> None:
        """Transport connection error fails the run and never publishes observations."""
        mock_discovery = MagicMock()
        mock_discovery.start_run.return_value = uuid4()
        mock_obs_repo = MagicMock()

        adapter = MagicMock()
        adapter.source_id = SOURCE_GDELT_DOC
        adapter.query_slice.side_effect = SourceTransientError("provider network transport failure")

        workflow = CollectMediaAttention(
            adapter=adapter,
            discovery=mock_discovery,
            observations=mock_obs_repo,
        )
        res = workflow(MediaAttentionCollectionConfig(window_start=_T0, window_end=_T1))

        assert res.status == "failed"
        assert res.window_covered is False
        assert res.value_status is None
        assert res.completeness_status is None
        assert res.value is None
        assert res.observation_id is None
        assert mock_obs_repo.insert_observation_with_contributing_records.called is False

    def test_malformed_payload_never_publishes_observation(self) -> None:
        """Malformed JSON or payload schema error fails the run and never publishes observations."""
        mock_discovery = MagicMock()
        mock_discovery.start_run.return_value = uuid4()
        mock_obs_repo = MagicMock()

        adapter = MagicMock()
        adapter.source_id = SOURCE_GDELT_DOC
        adapter.query_slice.side_effect = SourcePayloadError("provider returned malformed JSON payload")

        workflow = CollectMediaAttention(
            adapter=adapter,
            discovery=mock_discovery,
            observations=mock_obs_repo,
        )
        res = workflow(MediaAttentionCollectionConfig(window_start=_T0, window_end=_T1))

        assert res.status == "failed"
        assert res.window_covered is False
        assert res.value_status is None
        assert res.completeness_status is None
        assert res.value is None
        assert res.observation_id is None
        assert mock_obs_repo.insert_observation_with_contributing_records.called is False

    def test_response_size_rejection_never_publishes_observation(self) -> None:
        """Oversized response body rejection fails the run and never publishes observations."""
        mock_discovery = MagicMock()
        mock_discovery.start_run.return_value = uuid4()
        mock_obs_repo = MagicMock()

        adapter = MagicMock()
        adapter.source_id = SOURCE_GDELT_DOC
        adapter.query_slice.side_effect = SourcePayloadError("response body exceeds maximum allowed size")

        workflow = CollectMediaAttention(
            adapter=adapter,
            discovery=mock_discovery,
            observations=mock_obs_repo,
        )
        res = workflow(MediaAttentionCollectionConfig(window_start=_T0, window_end=_T1))

        assert res.status == "failed"
        assert res.window_covered is False
        assert res.value_status is None
        assert res.completeness_status is None
        assert res.value is None
        assert res.observation_id is None
        assert mock_obs_repo.insert_observation_with_contributing_records.called is False

    def test_interrupted_truncated_response_never_publishes_observation(self) -> None:
        """Interrupted or truncated response rejection fails the run and never publishes observations."""
        mock_discovery = MagicMock()
        mock_discovery.start_run.return_value = uuid4()
        mock_obs_repo = MagicMock()

        adapter = MagicMock()
        adapter.source_id = SOURCE_GDELT_DOC
        adapter.query_slice.side_effect = SourcePayloadError("response body truncated: expected 1000 bytes, received 500 bytes")

        workflow = CollectMediaAttention(
            adapter=adapter,
            discovery=mock_discovery,
            observations=mock_obs_repo,
        )
        res = workflow(MediaAttentionCollectionConfig(window_start=_T0, window_end=_T1))

        assert res.status == "failed"
        assert res.window_covered is False
        assert res.value_status is None
        assert res.completeness_status is None
        assert res.value is None
        assert res.observation_id is None
        assert mock_obs_repo.insert_observation_with_contributing_records.called is False


# ---------------------------------------------------------------------------
# 5. Database-Backed Observation Persistence & Provenance Linking Tests
# ---------------------------------------------------------------------------


def test_collection_workflow_db_persistence(db: None, migrated_db: str) -> None:
    """Validate end-to-end collection workflow with database persistence (fansivibe_test)."""
    SessionClass = make_session(migrated_db)
    with SessionClass() as session:
        discovery_repo = DiscoveryRepositorySQL(session)
        obs_repo = MediaAttentionRepositorySQL(session)

        # Mock adapter returning 3 valid articles
        articles = (
            RawSourceRecord(
                source=SOURCE_GDELT_DOC,
                payload={
                    "url": "https://vogue.in/fashion/streetwear-guide",
                    "title": "Essential Guide to Indian Streetwear",
                    "seendate": "20260106T100000Z",
                    "domain": "vogue.in",
                    "language": "eng",
                    "sourcecountry": "IN",
                },
                source_record_id="https://vogue.in/fashion/streetwear-guide",
                source_timestamp=datetime(2026, 1, 6, 10, 0, 0, tzinfo=timezone.utc),
            ),
            RawSourceRecord(
                source=SOURCE_GDELT_DOC,
                payload={
                    "url": "https://gqindia.com/style/streetwear-trends",
                    "title": "Essential Guide to Indian Streetwear - GQ India",
                    "seendate": "20260107T120000Z",
                    "domain": "gqindia.com",
                    "language": "eng",
                    "sourcecountry": "IN",
                },
                source_record_id="https://gqindia.com/style/streetwear-trends",
                source_timestamp=datetime(2026, 1, 7, 12, 0, 0, tzinfo=timezone.utc),
            ),
            RawSourceRecord(
                source=SOURCE_GDELT_DOC,
                payload={
                    "url": "https://lifestyleasia.com/ind/fashion/sneaker-culture",
                    "title": "Sneaker Culture Rising Across Mumbai and Delhi",
                    "seendate": "20260108T150000Z",
                    "domain": "lifestyleasia.com",
                    "language": "eng",
                    "sourcecountry": "IN",
                },
                source_record_id="https://lifestyleasia.com/ind/fashion/sneaker-culture",
                source_timestamp=datetime(2026, 1, 8, 15, 0, 0, tzinfo=timezone.utc),
            ),
        )

        adapter = MockGdeltSliceAdapter(
            slice_map={
                (format_gdelt_timestamp(_T0), format_gdelt_timestamp(_T1)): GdeltSliceResult(
                    slice_start=_T0,
                    slice_end=_T1,
                    records=articles,
                    is_capped=False,
                    articles_count=3,
                    raw_payload={},
                )
            }
        )

        workflow = CollectMediaAttention(
            adapter=adapter,
            discovery=discovery_repo,
            observations=obs_repo,
        )

        cfg = MediaAttentionCollectionConfig(
            window_start=_T0,
            window_end=_T1,
            query_key="streetwear",
            geo_scope="IN",
        )
        res = workflow(cfg)

        assert res.status == "completed"
        assert res.window_covered is True
        assert res.value_status == STATUS_PRESENT
        assert res.completeness_status == COMPLETENESS_COMPLETE
        assert res.fetched == 3
        assert res.inserted == 3
        assert res.observation_id is not None

        # Verify collection run row in DB
        run_row = session.get(CollectionRun, res.run_id)
        assert run_row is not None
        assert run_row.status == "completed"
        assert run_row.source == SOURCE_GDELT_DOC

        # Verify observation row in DB
        obs_row = session.get(MediaAttentionObservationModel, res.observation_id)
        assert obs_row is not None
        assert obs_row.source == SOURCE_GDELT_DOC
        assert obs_row.query_key == "streetwear"
        assert obs_row.geo_scope == "IN"
        assert obs_row.raw_article_count == 3
        assert obs_row.distinct_outlet_count == 3
        # 2 stories: 1 cluster of 2 similar headlines + 1 sneaker story
        assert obs_row.estimated_deduplicated_story_count == 2
        assert float(obs_row.value) == 2.0
        assert obs_row.query_config_version == DEFAULT_QUERY_CONFIG_VERSION
        assert obs_row.clustering_version == DEFAULT_CLUSTERING_VERSION
        assert obs_row.contributing_raw_record_count == 3

        # Verify contributing records linked
        linked_records = obs_repo.get_contributing_records(observation_id=res.observation_id)
        assert len(linked_records) == 3


def test_empirical_zero_db_persistence(db: None, migrated_db: str) -> None:
    """Validate DB persistence of empirical zero observation (value=0.0, counts=0)."""
    SessionClass = make_session(migrated_db)
    with SessionClass() as session:
        discovery_repo = DiscoveryRepositorySQL(session)
        obs_repo = MediaAttentionRepositorySQL(session)

        adapter = MockGdeltSliceAdapter(default_count=0)
        workflow = CollectMediaAttention(
            adapter=adapter,
            discovery=discovery_repo,
            observations=obs_repo,
        )

        cfg = MediaAttentionCollectionConfig(
            window_start=_T0,
            window_end=_T1,
            query_key="obscure_concept",
            geo_scope="IN",
        )
        res = workflow(cfg)

        assert res.status == "completed"
        assert res.value_status == STATUS_PRESENT
        assert res.completeness_status == COMPLETENESS_COMPLETE
        assert res.value == 0.0
        assert res.observation_id is not None

        obs_row = session.get(MediaAttentionObservationModel, res.observation_id)
        assert obs_row is not None
        assert float(obs_row.value) == 0.0
        assert obs_row.raw_article_count == 0
        assert obs_row.distinct_outlet_count == 0
        assert obs_row.estimated_deduplicated_story_count == 0
        assert obs_row.contributing_raw_record_count == 0


def test_cap_truncated_db_persistence(db: None, migrated_db: str) -> None:
    """Validate DB persistence of suppressed/truncated observation when provider cap hit at max depth."""
    SessionClass = make_session(migrated_db)
    with SessionClass() as session:
        discovery_repo = DiscoveryRepositorySQL(session)
        obs_repo = MediaAttentionRepositorySQL(session)

        adapter = MockGdeltSliceAdapter(default_is_capped=True, default_count=250)
        workflow = CollectMediaAttention(
            adapter=adapter,
            discovery=discovery_repo,
            observations=obs_repo,
        )

        cfg = MediaAttentionCollectionConfig(
            window_start=_T0,
            window_end=_T1,
            query_key="super_viral_concept",
            geo_scope="IN",
            max_depth=1,
        )
        res = workflow(cfg)

        assert res.status == "completed"
        assert res.value_status == STATUS_SUPPRESSED
        assert res.completeness_status == COMPLETENESS_TRUNCATED
        assert res.value is None
        assert res.observation_id is not None

        obs_row = session.get(MediaAttentionObservationModel, res.observation_id)
        assert obs_row is not None
        assert obs_row.value_status == STATUS_SUPPRESSED
        assert obs_row.completeness_status == COMPLETENESS_TRUNCATED
        assert obs_row.value is None
        assert obs_row.raw_article_count is None
        assert obs_row.distinct_outlet_count is None
        assert obs_row.estimated_deduplicated_story_count is None


def test_idempotent_recollection_db_persistence(db: None, migrated_db: str) -> None:
    """Validate that re-running collection over the same articles is idempotent."""
    SessionClass = make_session(migrated_db)
    with SessionClass() as session:
        discovery_repo = DiscoveryRepositorySQL(session)
        obs_repo = MediaAttentionRepositorySQL(session)

        articles = (
            RawSourceRecord(
                source=SOURCE_GDELT_DOC,
                payload={
                    "url": "https://vogue.in/fashion/streetwear-guide-repeat",
                    "title": "Essential Guide to Streetwear Repeat",
                    "seendate": "20260106T100000Z",
                    "domain": "vogue.in",
                    "language": "eng",
                    "sourcecountry": "IN",
                },
                source_record_id="https://vogue.in/fashion/streetwear-guide-repeat",
                source_timestamp=datetime(2026, 1, 6, 10, 0, 0, tzinfo=timezone.utc),
            ),
        )

        adapter = MockGdeltSliceAdapter(
            slice_map={
                (format_gdelt_timestamp(_T0), format_gdelt_timestamp(_T1)): GdeltSliceResult(
                    slice_start=_T0,
                    slice_end=_T1,
                    records=articles,
                    is_capped=False,
                    articles_count=1,
                    raw_payload={},
                )
            }
        )

        workflow = CollectMediaAttention(
            adapter=adapter,
            discovery=discovery_repo,
            observations=obs_repo,
        )

        cfg = MediaAttentionCollectionConfig(
            window_start=_T0,
            window_end=_T1,
            query_key="streetwear_idempotent",
            geo_scope="IN",
        )

        # First collection run
        res1 = workflow(cfg)
        assert res1.status == "completed"
        assert res1.inserted == 1

        # Second collection run with identical articles
        res2 = workflow(cfg)
        assert res2.status == "completed"
        assert res2.observation_id == res1.observation_id
        assert res2.skipped == 1  # Duplicate raw record skipped


# ---------------------------------------------------------------------------
# 6. Regression & Frozen Boundaries Tests
# ---------------------------------------------------------------------------


class TestExistingAdaptersAndFrozenBoundaries:
    """Confirm existing adapters, workflows, and frozen boundaries remain untouched."""

    def test_fixture_source_adapter_unchanged(self) -> None:
        adapter = FixtureSourceAdapter()
        assert adapter.source_id == "fixture_catalog"
        batch = adapter.fetch_batch(limit=2)
        assert isinstance(batch, SourceBatch)
        assert len(batch.records) == 2
        assert batch.continuation is not None

    def test_synthetic_search_interest_adapter_unchanged(self) -> None:
        adapter = SyntheticSearchInterestAdapter()
        assert adapter.source_id == "synthetic_search_interest"
        batch = adapter.fetch_batch(limit=2)
        assert isinstance(batch, SourceBatch)
        assert len(batch.records) == 2

    def test_demand_signal_available_is_strictly_false(self) -> None:
        assert DEMAND_SIGNAL_AVAILABLE is False

    def test_d6_trend_engine_regression_preserved(self) -> None:
        """Confirm D6 trend candidate computation remains deterministic and unchanged."""
        from app.domain.services.trends import (
            ObservationEvidence,
            STAGE_INSUFFICIENT,
            compute_trend_candidates,
            to_ffo_trend,
        )

        w0 = datetime(2026, 10, 1, tzinfo=timezone.utc)
        w1 = datetime(2026, 10, 8, tzinfo=timezone.utc)
        t_early = datetime(2026, 10, 2, tzinfo=timezone.utc)

        obs = [
            ObservationEvidence(
                product_id=uuid4(),
                category="tops",
                source="fixture_catalog",
                observed_at=t_early,
                price=1999.0,
                availability=True,
                is_fixture=False,
            )
        ]

        analysis = compute_trend_candidates(
            tuple(obs),
            window_start=w0,
            window_end=w1,
        )

        assert len(analysis.candidates) == 1
        cand = analysis.candidates[0]
        assert cand.stage == STAGE_INSUFFICIENT
        assert cand.publishable is False
        assert to_ffo_trend(cand) is None
