"""GDELT DOC 2.0 API source adapter (D9B/D9C).

Conforms to ``SourceAdapter`` and provides slice-based article collection
from the GDELT DOC 2.0 API (or injected HTTP mock clients).

Features & Rate-Limit Compliance (D9C.1):
- Request pacing: enforces a minimum 5.5s delay between outbound requests,
  based on GDELT's observed requirement of at most one request every 5 seconds
  plus a 0.5s safety buffer. Pacing is strictly enforced across all outbound
  requests, including initial queries, adaptive recursive slices, and retries.
- Exponential backoff: base delay of 5.0s, yielding nominal delays of 5s, 10s,
  and 20s for retry attempts 0, 1, and 2 before any applicable pacing requirement.
- Retry-After honoring: parses valid numeric Retry-After response headers. If
  absent or invalid, falls back to the configured exponential backoff.
- Cooperative deadline enforcement: checked prior to requests, during request
  pacing, and during retry backoff to ensure bounded collection.
- Shared-IP limitation: per-instance pacing in memory cannot coordinate across
  multiple collection processes or workers sharing a public egress IP. Multiple
  concurrent workers sharing an IP will contend for upstream quotas.
- Bounded retry exhaustion: retries stop strictly after max_retries attempts,
  raising SourceRateLimitError to ensure fail-closed termination.
- Non-guarantee disclaimer: these client-side configurations reflect observed
  provider behaviors and do not guarantee exemption from provider-side rate limits.
- Bounded HTTP response body size handling (2 MB ceiling).
- Provider-cap truncation detection on slices.
- Typed error classification: SourceDeadlineError, SourceRateLimitError,
  SourceTransientError, SourcePayloadError, SourceAuthError.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from app.domain.ports.source_adapter import (
    RawSourceRecord,
    SourceAdapter,
    SourceAuthError,
    SourceBatch,
    SourceDeadlineError,
    SourceError,
    SourcePayloadError,
    SourceRateLimitError,
    SourceTransientError,
)
from app.domain.services.media_attention import (
    DEFAULT_CLUSTERING_VERSION,
    DEFAULT_QUERY_CONFIG_VERSION,
    SOURCE_GDELT_DOC,
    parse_media_timestamp,
)

DEFAULT_GDELT_BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
DEFAULT_MAX_RECORDS = 250
DEFAULT_MAX_RESPONSE_BYTES = 2 * 1024 * 1024  # 2 MB ceiling
DEFAULT_PACE_INTERVAL_S = 5.5  # 5.5s minimum pacing interval (5.0s observed GDELT requirement + 0.5s safety buffer)
DEFAULT_REQUEST_TIMEOUT_S = 10.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE_S = 5.0  # 5.0s exponential base yielding nominal delays of 5s, 10s, 20s
DEFAULT_MAX_BACKOFF_S = 60.0


@dataclass(frozen=True)
class GdeltSliceResult:
    """Result of querying a single GDELT time slice."""

    slice_start: datetime
    slice_end: datetime
    records: tuple[RawSourceRecord, ...]
    is_capped: bool
    articles_count: int
    raw_payload: dict


def format_gdelt_timestamp(dt: datetime) -> str:
    """Format a timezone-aware UTC datetime into GDELT compact format YYYYMMDDHHMMSS."""
    utc_dt = dt.astimezone(timezone.utc)
    return utc_dt.strftime("%Y%m%d%H%M%S")


class GdeltSourceAdapter:
    """GDELT DOC 2.0 API adapter conforming to ``SourceAdapter``."""

    source_id = SOURCE_GDELT_DOC

    def __init__(
        self,
        *,
        http_client: Optional[httpx.Client] = None,
        base_url: str = DEFAULT_GDELT_BASE_URL,
        max_records_per_request: int = DEFAULT_MAX_RECORDS,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        request_timeout_s: float = DEFAULT_REQUEST_TIMEOUT_S,
        pace_interval_s: float = DEFAULT_PACE_INTERVAL_S,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_base_s: float = DEFAULT_BACKOFF_BASE_S,
        max_backoff_s: float = DEFAULT_MAX_BACKOFF_S,
        query_config_version: str = DEFAULT_QUERY_CONFIG_VERSION,
        clustering_version: str = DEFAULT_CLUSTERING_VERSION,
        records: Optional[Sequence[RawSourceRecord]] = None,
    ) -> None:
        self._client = http_client or httpx.Client(timeout=request_timeout_s)
        self._owns_client = http_client is None
        self._base_url = base_url
        self._max_records_per_request = max(1, max_records_per_request)
        self._max_response_bytes = max(1024, max_response_bytes)
        self._request_timeout_s = max(0.1, request_timeout_s)
        self._pace_interval_s = max(0.0, pace_interval_s)
        self._max_retries = max(0, max_retries)
        self._backoff_base_s = max(0.01, backoff_base_s)
        self._max_backoff_s = max(self._backoff_base_s, max_backoff_s)
        self.query_config_version = query_config_version
        self.clustering_version = clustering_version
        self._records = tuple(records) if records is not None else None
        self._last_request_monotonic: float = 0.0

    def close(self) -> None:
        """Close client if owned."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> GdeltSourceAdapter:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def fetch_batch(
        self,
        *,
        continuation: Optional[str] = None,
        limit: int = 50,
    ) -> SourceBatch:
        """Fetch a batch of raw records (SourceAdapter protocol conformance).

        If initialized with seeded records, pages through them sequentially.
        """
        if self._records is not None:
            start = int(continuation) if continuation is not None else 0
            chunk = self._records[start : start + limit]
            next_start = start + len(chunk)
            nxt = str(next_start) if next_start < len(self._records) else None
            return SourceBatch(source=self.source_id, records=chunk, continuation=nxt)

        # Default empty batch when not seeded
        return SourceBatch(source=self.source_id, records=(), continuation=None)

    def query_slice(
        self,
        *,
        query: str,
        start_datetime: datetime,
        end_datetime: datetime,
        deadline: Optional[datetime] = None,
    ) -> GdeltSliceResult:
        """Query GDELT DOC 2.0 API for a specific query and time interval.

        Enforces:
        - Cooperative deadline check before request and during backoff.
        - Request pacing delay.
        - Bounded retries on transient errors and HTTP 429.
        - Response size ceiling.
        - Payload validation and parsing into RawSourceRecord items.
        - Provider cap truncation detection (is_capped).
        """
        if not query or not query.strip():
            raise ValueError("query string must be non-empty")

        if start_datetime.tzinfo is None or end_datetime.tzinfo is None:
            raise ValueError("start_datetime and end_datetime must be timezone-aware UTC")

        if end_datetime <= start_datetime:
            raise ValueError("end_datetime must be strictly after start_datetime")

        params = {
            "query": query.strip(),
            "mode": "ArtList",
            "format": "json",
            "maxrecords": str(self._max_records_per_request),
            "startdatetime": format_gdelt_timestamp(start_datetime),
            "enddatetime": format_gdelt_timestamp(end_datetime),
        }

        # Check deadline before execution
        self._check_deadline(deadline)

        # Bounded retries (pacing enforced before each outbound request attempt)
        response_bytes = self._execute_with_retry(params=params, deadline=deadline)

        # Parse and validate JSON
        data = self._parse_json(response_bytes)

        # Validate structure and extract records
        records = self._extract_records(data)

        articles_count = len(records)
        is_capped = articles_count >= self._max_records_per_request

        return GdeltSliceResult(
            slice_start=start_datetime,
            slice_end=end_datetime,
            records=records,
            is_capped=is_capped,
            articles_count=articles_count,
            raw_payload=data,
        )

    def _check_deadline(self, deadline: Optional[datetime]) -> None:
        """Raise SourceDeadlineError if cooperative deadline has passed."""
        if deadline is not None and datetime.now(timezone.utc) >= deadline:
            raise SourceDeadlineError("cooperative deadline exceeded")

    def _enforce_pacing(self, deadline: Optional[datetime]) -> None:
        """Enforce minimum spacing between HTTP requests."""
        if self._pace_interval_s <= 0.0:
            return

        now_m = time.monotonic()
        elapsed = now_m - self._last_request_monotonic
        if elapsed < self._pace_interval_s:
            sleep_duration = self._pace_interval_s - elapsed
            if deadline is not None:
                remaining_s = (deadline - datetime.now(timezone.utc)).total_seconds()
                if sleep_duration >= remaining_s:
                    raise SourceDeadlineError("cooperative deadline exceeded during request pacing")
            time.sleep(sleep_duration)

        self._last_request_monotonic = time.monotonic()

    def _execute_with_retry(
        self,
        *,
        params: dict[str, str],
        deadline: Optional[datetime],
    ) -> bytes:
        """Execute GET request with bounded retries and exponential backoff."""
        attempt = 0
        last_error: Optional[Exception] = None

        while attempt <= self._max_retries:
            self._check_deadline(deadline)

            # Enforce pacing between all outbound requests (including adaptive slices and retries)
            self._enforce_pacing(deadline)

            # Compute effective timeout bounded by deadline
            if deadline is not None:
                remaining_s = (deadline - datetime.now(timezone.utc)).total_seconds()
                if remaining_s <= 0.0:
                    raise SourceDeadlineError("cooperative deadline exceeded")
                req_timeout = min(self._request_timeout_s, remaining_s)
            else:
                req_timeout = self._request_timeout_s

            try:
                response = self._client.get(
                    self._base_url,
                    params=params,
                    timeout=req_timeout,
                )

                # HTTP 429: Rate limited
                if response.status_code == 429:
                    retry_after_hdr = response.headers.get("retry-after")
                    retry_after_s: Optional[float] = None
                    if retry_after_hdr is not None:
                        try:
                            parsed_retry_after = float(retry_after_hdr.strip())
                            if math.isfinite(parsed_retry_after) and parsed_retry_after >= 0.0:
                                retry_after_s = parsed_retry_after
                        except (ValueError, TypeError):
                            retry_after_s = None

                    if attempt < self._max_retries:
                        backoff = (
                            retry_after_s
                            if retry_after_s is not None
                            else (self._backoff_base_s * (2**attempt))
                        )
                        backoff = min(backoff, self._max_backoff_s)
                        self._sleep_with_deadline_check(backoff, deadline)
                        attempt += 1
                        continue
                    raise SourceRateLimitError(
                        "provider rate limit reached",
                        retry_after_s=retry_after_s,
                    )

                # HTTP 401 / 403: Auth failure
                if response.status_code in (401, 403):
                    raise SourceAuthError(f"provider authentication failed: HTTP {response.status_code}")

                # Other HTTP 4xx
                if 400 <= response.status_code < 500:
                    raise SourcePayloadError(f"provider rejected request: HTTP {response.status_code}")

                # HTTP 5xx: Transient provider failure
                if response.status_code >= 500:
                    if attempt < self._max_retries:
                        backoff = min(self._backoff_base_s * (2**attempt), self._max_backoff_s)
                        self._sleep_with_deadline_check(backoff, deadline)
                        attempt += 1
                        continue
                    raise SourceTransientError(f"provider server error: HTTP {response.status_code}")

                # Check Content-Length header if present
                cl_hdr = response.headers.get("content-length")
                if cl_hdr and cl_hdr.isdigit() and int(cl_hdr) > self._max_response_bytes:
                    raise SourcePayloadError(
                        f"response body exceeds maximum allowed size ({cl_hdr} > {self._max_response_bytes})"
                    )

                content = response.content
                if len(content) > self._max_response_bytes:
                    raise SourcePayloadError(
                        f"response body exceeds maximum allowed size ({len(content)} > {self._max_response_bytes})"
                    )

                # Ensure truncated / interrupted response is rejected
                if cl_hdr and cl_hdr.isdigit() and len(content) < int(cl_hdr):
                    raise SourcePayloadError(
                        f"response body truncated: expected {cl_hdr} bytes, received {len(content)} bytes"
                    )

                return content

            except httpx.TimeoutException as exc:
                last_error = exc
                if attempt < self._max_retries:
                    backoff = min(self._backoff_base_s * (2**attempt), self._max_backoff_s)
                    self._sleep_with_deadline_check(backoff, deadline)
                    attempt += 1
                    continue
                raise SourceTransientError("provider request timed out") from exc

            except (httpx.NetworkError, httpx.ConnectError, httpx.TransportError) as exc:
                last_error = exc
                if attempt < self._max_retries:
                    backoff = min(self._backoff_base_s * (2**attempt), self._max_backoff_s)
                    self._sleep_with_deadline_check(backoff, deadline)
                    attempt += 1
                    continue
                raise SourceTransientError("provider network transport failure") from exc

        if last_error:
            raise SourceTransientError("provider request failed after retries") from last_error
        raise SourceTransientError("provider request failed after retries")

    def _sleep_with_deadline_check(self, seconds: float, deadline: Optional[datetime]) -> None:
        """Sleep with deadline check to prevent blocking past deadline."""
        if deadline is not None:
            remaining_s = (deadline - datetime.now(timezone.utc)).total_seconds()
            if seconds >= remaining_s:
                raise SourceDeadlineError("cooperative deadline exceeded during retry backoff")
        time.sleep(seconds)

    def _parse_json(self, raw_bytes: bytes) -> dict:
        """Decode and parse JSON body, raising SourcePayloadError on malformed data."""
        if not raw_bytes or not raw_bytes.strip():
            # Empty body treated as empty mapping
            return {}

        try:
            parsed = json.loads(raw_bytes.decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            raise SourcePayloadError("provider returned malformed JSON payload") from exc

        if not isinstance(parsed, dict):
            raise SourcePayloadError("provider response payload must be a JSON object")

        return parsed

    def _extract_records(self, data: dict) -> tuple[RawSourceRecord, ...]:
        """Extract RawSourceRecord items from parsed payload."""
        if "articles" not in data:
            # GDELT returns empty mapping or omits articles key on 0 matches
            return ()

        raw_articles = data["articles"]
        if raw_articles is None:
            return ()

        if not isinstance(raw_articles, list):
            raise SourcePayloadError("articles field must be a list")

        records: list[RawSourceRecord] = []
        for item in raw_articles:
            if not isinstance(item, dict):
                raise SourcePayloadError("article item in payload must be a mapping")

            url = item.get("url") or item.get("link")
            if not url or not isinstance(url, str) or not url.strip():
                raise SourcePayloadError("article item missing required url")

            title = item.get("title") or item.get("headline")
            if not title or not isinstance(title, str) or not title.strip():
                raise SourcePayloadError("article item missing required title")

            ts, _ = parse_media_timestamp(item.get("seendate") or item.get("published_at"))

            records.append(
                RawSourceRecord(
                    source=self.source_id,
                    payload=item,
                    source_record_id=url.strip(),
                    source_timestamp=ts,
                )
            )

        return tuple(records)
