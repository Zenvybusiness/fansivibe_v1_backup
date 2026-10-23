"""YouTube Data API v3 source adapter for fashion video content trends.

Conforms to ``SourceAdapter`` and provides structured fashion video ingestion
for creator and content trend intelligence in India (Category 26: Howto & Style).

Features & Invariants:
- Fail-closed credential boundary: If credentials are not configured in environment
  or passed directly, ``fetch_batch`` cleanly fails closed with ``SourceAuthError``.
- Zero unauthorized live network calls: Never executes live HTTP requests without
  configured credentials.
- Pacing & bounded retry with exponential backoff on transient errors and throttling.
- Error taxonomy: Maps HTTP 400 to SourcePayloadError, 401/403 (invalid key) to
  SourceAuthError, 403 (quota/rate limit exceeded) or 429 to SourceRateLimitError,
  5xx/timeouts to SourceTransientError.
- Response parsing: Extracts video ID, publication timestamp, channel metadata,
  title, description, tags, and direct CDN thumbnail links (hotlinks only; zero local
  binary image hosting).
- Compliance with YouTube API Services Developer Policies:
  * Section III.E: Cache/storage retention ≤ 30 calendar days.
  * Direct video linking (`https://www.youtube.com/watch?v={id}`) and channel attribution.
  * Metrics policy: Video view count, like count, comment count, and upload velocity
    are strictly video creator engagement metrics; they NEVER represent sales or
    consumer purchase demand.
- Idempotency & deduplication: Structured payload hashing and stable record IDs
  prevent duplicate observations.
"""

from __future__ import annotations

import json
import logging
import math
import time
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.config.settings import get_settings
from app.domain.ports.source_adapter import (
    RawSourceRecord,
    SourceAdapter,
    SourceAuthError,
    SourceBatch,
    SourceError,
    SourcePayloadError,
    SourceRateLimitError,
    SourceTransientError,
)

logger = logging.getLogger(__name__)

SOURCE_YOUTUBE_IN = "youtube_in"
DEFAULT_YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
DEFAULT_YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
DEFAULT_REGION_CODE = "IN"
DEFAULT_VIDEO_CATEGORY_ID = "26"  # Howto & Style
DEFAULT_QUERY = "fashion style trends"
DEFAULT_PACE_INTERVAL_S = 0.5
DEFAULT_TIMEOUT_S = 10.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_BACKOFF_BASE_S = 0.5
DEFAULT_MAX_BACKOFF_S = 10.0


def parse_youtube_timestamp(ts_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO-8601 UTC timestamp from YouTube API (e.g. '2026-10-15T08:30:00Z')."""
    if not ts_str or not isinstance(ts_str, str):
        return None
    cleaned = ts_str.strip()
    if not cleaned:
        return None
    try:
        if cleaned.endswith("Z"):
            cleaned = cleaned[:-1] + "+00:00"
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


class YouTubeSourceAdapter:
    """YouTube Data API v3 source adapter conforming to ``SourceAdapter``."""

    source_id = SOURCE_YOUTUBE_IN

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        http_client: Optional[httpx.Client] = None,
        search_url: str = DEFAULT_YOUTUBE_SEARCH_URL,
        videos_url: str = DEFAULT_YOUTUBE_VIDEOS_URL,
        region_code: str = DEFAULT_REGION_CODE,
        video_category_id: str = DEFAULT_VIDEO_CATEGORY_ID,
        default_query: str = DEFAULT_QUERY,
        pace_interval_s: float = DEFAULT_PACE_INTERVAL_S,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_base_s: float = DEFAULT_BACKOFF_BASE_S,
        max_backoff_s: float = DEFAULT_MAX_BACKOFF_S,
        records: Optional[Sequence[RawSourceRecord]] = None,
    ) -> None:
        settings = get_settings()
        self._api_key = (api_key or settings.youtube_data_api_key or "").strip() or None
        self._client = http_client or httpx.Client(timeout=timeout_s)
        self._owns_client = http_client is None
        self._search_url = search_url
        self._videos_url = videos_url
        self._region_code = region_code
        self._video_category_id = video_category_id
        self._default_query = default_query
        self._pace_interval_s = max(0.0, pace_interval_s)
        self._timeout_s = max(0.1, timeout_s)
        self._max_retries = max(0, max_retries)
        self._backoff_base_s = max(0.01, backoff_base_s)
        self._max_backoff_s = max(self._backoff_base_s, max_backoff_s)
        self._records = tuple(records) if records is not None else None
        self._last_request_monotonic: float = 0.0

    @property
    def is_configured(self) -> bool:
        """True if an API key is available or seeded offline records are present."""
        return self._records is not None or self._api_key is not None

    def close(self) -> None:
        """Close HTTP client if owned."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> YouTubeSourceAdapter:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def fetch_batch(
        self,
        *,
        continuation: Optional[str] = None,
        limit: int = 50,
    ) -> SourceBatch:
        """Fetch a page of fashion video raw records (SourceAdapter protocol conformance).

        If initialized with seeded records, pages through them sequentially.
        If credentials are not configured, fails closed with SourceAuthError.
        """
        # 1. Offline seeded test mode
        if self._records is not None:
            start = int(continuation) if continuation is not None and continuation.isdigit() else 0
            chunk = self._records[start : start + limit]
            next_start = start + len(chunk)
            nxt = str(next_start) if next_start < len(self._records) else None
            return SourceBatch(source=self.source_id, records=chunk, continuation=nxt)

        # 2. Safety boundary: fail closed when credentials are unset
        if not self._api_key:
            raise SourceAuthError(
                "YouTube Data API credentials not configured (YOUTUBE_DATA_API_KEY). "
                "Live collection requires a valid GCP API key with YouTube Data API v3 enabled."
            )

        # 3. Execute bounded live/mocked search
        return self._fetch_search_batch(continuation=continuation, limit=limit)

    def _fetch_search_batch(
        self,
        *,
        continuation: Optional[str],
        limit: int,
    ) -> SourceBatch:
        """Execute search.list request against YouTube Data API v3."""
        params: dict[str, str] = {
            "part": "snippet",
            "type": "video",
            "videoCategoryId": self._video_category_id,
            "regionCode": self._region_code,
            "q": self._default_query,
            "maxResults": str(max(1, min(limit, 50))),
            "key": self._api_key or "",
        }
        if continuation:
            params["pageToken"] = continuation

        response_bytes = self._execute_request(self._search_url, params=params)
        data = self._parse_json(response_bytes)

        if not isinstance(data, dict):
            raise SourcePayloadError("provider response must be a JSON object")

        items = data.get("items")
        if items is None or not isinstance(items, list):
            raise SourcePayloadError("provider response missing 'items' array")

        records: list[RawSourceRecord] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            record = self._extract_search_record(item)
            if record is not None:
                records.append(record)

        next_page_token = data.get("nextPageToken")
        nxt = str(next_page_token) if next_page_token and isinstance(next_page_token, str) else None

        return SourceBatch(
            source=self.source_id,
            records=tuple(records),
            continuation=nxt,
        )

    def _extract_search_record(self, item: dict[str, Any]) -> Optional[RawSourceRecord]:
        """Extract RawSourceRecord from a YouTube search result item."""
        item_id = item.get("id")
        video_id: Optional[str] = None
        if isinstance(item_id, dict):
            video_id = item_id.get("videoId")
        elif isinstance(item_id, str):
            video_id = item_id

        if not video_id or not isinstance(video_id, str) or not video_id.strip():
            return None

        video_id = video_id.strip()
        snippet = item.get("snippet") or {}
        if not isinstance(snippet, dict):
            snippet = {}

        title = (snippet.get("title") or "").strip()
        description = (snippet.get("description") or "").strip()
        published_at_str = snippet.get("publishedAt")
        source_ts = parse_youtube_timestamp(published_at_str)
        channel_id = snippet.get("channelId")
        channel_title = (snippet.get("channelTitle") or "").strip()

        thumbnails_raw = snippet.get("thumbnails") or {}
        thumbnail_urls: dict[str, str] = {}
        if isinstance(thumbnails_raw, dict):
            for quality, thumb_info in thumbnails_raw.items():
                if isinstance(thumb_info, dict) and "url" in thumb_info:
                    thumbnail_urls[quality] = str(thumb_info["url"])

        # Construct clean, structured payload preserving YouTube provenance
        payload: dict[str, Any] = {
            "videoId": video_id,
            "title": title,
            "description": description,
            "publishedAt": published_at_str,
            "channelId": channel_id,
            "channelTitle": channel_title,
            "videoCategoryId": self._video_category_id,
            "regionCode": self._region_code,
            "videoUrl": f"https://www.youtube.com/watch?v={video_id}",
            "thumbnails": thumbnail_urls,
            "provenance": {
                "source": self.source_id,
                "region": self._region_code,
                "category_id": self._video_category_id,
                "retention_policy_days": 30,
                "signal_type": "video_content_velocity",
            },
        }

        # If statistics are present (e.g. from enriched video detail), preserve them
        if "statistics" in item and isinstance(item["statistics"], dict):
            stats = item["statistics"]
            payload["statistics"] = {
                "viewCount": int(stats["viewCount"]) if "viewCount" in stats and stats["viewCount"] is not None else None,
                "likeCount": int(stats["likeCount"]) if "likeCount" in stats and stats["likeCount"] is not None else None,
                "commentCount": int(stats["commentCount"]) if "commentCount" in stats and stats["commentCount"] is not None else None,
            }

        return RawSourceRecord(
            source=self.source_id,
            payload=payload,
            source_record_id=video_id,
            source_timestamp=source_ts,
        )

    def _enforce_pacing(self) -> None:
        """Enforce request spacing between outbound calls."""
        if self._pace_interval_s <= 0.0:
            return
        now_m = time.monotonic()
        elapsed = now_m - self._last_request_monotonic
        if elapsed < self._pace_interval_s:
            time.sleep(self._pace_interval_s - elapsed)
        self._last_request_monotonic = time.monotonic()

    def _execute_request(self, url: str, params: dict[str, str]) -> bytes:
        """Execute HTTP GET with bounded retries and typed error translation."""
        attempt = 0
        last_error: Optional[Exception] = None

        while attempt <= self._max_retries:
            self._enforce_pacing()

            try:
                response = self._client.get(url, params=params)

                # HTTP 200: Success
                if response.status_code == 200:
                    return response.content

                # HTTP 400: Malformed request / parameter error
                if response.status_code == 400:
                    raise SourcePayloadError(f"YouTube API rejected request (HTTP 400): {response.text[:200]}")

                # HTTP 401 / 403: Auth or permission error
                if response.status_code in (401, 403):
                    # Check if error is quota exhaustion vs invalid key
                    body_text = response.text.lower()
                    if "quotaexceeded" in body_text or "ratelimitexceeded" in body_text:
                        raise SourceRateLimitError("YouTube Data API quota exceeded or rate limited")
                    raise SourceAuthError(f"YouTube Data API authentication failed (HTTP {response.status_code})")

                # HTTP 429: Throttling
                if response.status_code == 429:
                    retry_after_hdr = response.headers.get("retry-after")
                    retry_after_s: Optional[float] = None
                    if retry_after_hdr:
                        try:
                            retry_after_s = float(retry_after_hdr)
                        except (ValueError, TypeError):
                            retry_after_s = None
                    if attempt < self._max_retries:
                        backoff = retry_after_s or min(self._backoff_base_s * (2**attempt), self._max_backoff_s)
                        time.sleep(backoff)
                        attempt += 1
                        continue
                    raise SourceRateLimitError("YouTube Data API throttled request", retry_after_s=retry_after_s)

                # HTTP 5xx: Transient server failure
                if response.status_code >= 500:
                    if attempt < self._max_retries:
                        backoff = min(self._backoff_base_s * (2**attempt), self._max_backoff_s)
                        time.sleep(backoff)
                        attempt += 1
                        continue
                    raise SourceTransientError(f"YouTube server error (HTTP {response.status_code})")

                # Other HTTP 4xx
                raise SourcePayloadError(f"YouTube API returned HTTP {response.status_code}: {response.text[:200]}")

            except (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError) as exc:
                last_error = exc
                if attempt < self._max_retries:
                    backoff = min(self._backoff_base_s * (2**attempt), self._max_backoff_s)
                    time.sleep(backoff)
                    attempt += 1
                    continue
                raise SourceTransientError("YouTube request failed due to transport/timeout error") from exc

        if last_error:
            raise SourceTransientError("YouTube request failed after retries") from last_error
        raise SourceTransientError("YouTube request failed after retries")

    def _parse_json(self, raw_bytes: bytes) -> dict:
        """Decode and parse JSON response payload."""
        if not raw_bytes or not raw_bytes.strip():
            return {}
        try:
            parsed = json.loads(raw_bytes.decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            raise SourcePayloadError("provider returned malformed JSON payload") from exc
        if not isinstance(parsed, dict):
            raise SourcePayloadError("provider response must be a JSON object")
        return parsed
