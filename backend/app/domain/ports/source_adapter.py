"""Discovery source adapter port — the seam every authorized data source
implements (D2).

Only authorized sources implement this contract. Provider-specific HTTP,
authentication, quoting and pagination stay entirely inside the adapter;
this port fixes the shape the ingestion pipeline consumes and the typed
failures it must surface. No real provider connector is implemented in
this phase and no credential belongs in source code or this module.

The adapter emits an **explicit raw-record representation** (``RawSourceRecord``)
rather than a normalized product: normalization is a separate deterministic
boundary (see ``app.domain.services.normalization``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol


class SourceError(Exception):
    """Base class for typed source failures.

    Adapters translate every provider/transport failure into one of these
    subclasses so shared domain logic never depends on a provider SDK,
    HTTP status code, or raw exception.
    """


class SourceAuthError(SourceError):
    """Credentials are missing, invalid or unauthorized.

    Retrying without new access is futile; the caller must stop and report.
    """


class SourceRateLimitError(SourceError):
    """The provider throttled the request.

    ``retry_after_s`` carries the provider's requested delay when it supplies
    one; ``None`` means the caller picks its own backoff.
    """

    def __init__(
        self,
        message: str = "source rate limit reached",
        *,
        retry_after_s: Optional[float] = None,
    ) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


class SourceTransientError(SourceError):
    """A network, timeout or 5xx failure — safe to retry with backoff."""


class SourcePayloadError(SourceError):
    """The provider returned a structurally invalid or unusable payload."""


@dataclass(frozen=True)
class RawSourceRecord:
    """One raw source observation, before any normalization.

    ``payload`` is the original structured provider payload (validated only
    for shape by the adapter, never transformed); ``source_record_id`` is the
    provider's own stable identifier when it has one (``None`` otherwise);
    ``source_timestamp`` is the provider's own timestamp when present.
    """

    source: str
    payload: dict
    source_record_id: Optional[str] = None
    source_timestamp: Optional[datetime] = None


@dataclass(frozen=True)
class SourceBatch:
    """A bounded page of raw records plus an opaque continuation cursor.

    ``continuation`` is provider-defined and must be passed back verbatim to
    fetch the next page; ``None`` means the batch is the last one.
    """

    source: str
    records: tuple[RawSourceRecord, ...]
    continuation: Optional[str] = None


class SourceAdapter(Protocol):
    """The contract every authorized discovery source implements.

    ``source_id`` is the stable identifier persisted on collection runs and
    raw records. ``fetch_batch`` returns a bounded :class:`SourceBatch` or
    raises a typed :class:`SourceError`; it must never fabricate records to
    mask a failure and must never return the whole corpus in one call.
    """

    source_id: str

    def fetch_batch(
        self,
        *,
        continuation: Optional[str] = None,
        limit: int = 50,
    ) -> SourceBatch: ...
