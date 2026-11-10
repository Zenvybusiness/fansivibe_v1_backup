"""Domain ports — the seams the decision engine depends on.

The engine depends on these abstractions only (BA-3, BA-8); concrete adapters
live in `app/infrastructure`.
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from app.domain.value_objects import HairstyleRecommendation, WeatherContext


class KnowledgeError(ValueError):
    """Raised when knowledge is missing or fails validation on read.

    Subclasses :class:`ValueError` so existing callers that treat a failed
    knowledge read as a value problem keep working unchanged. Knowledge
    failures are truthful signals about system-owned content — they never
    carry user data (KN-9).
    """


class KnowledgeSource(Protocol):
    """Reads the hairstyle knowledge catalog (K9.1, KN-10).

    Two access paths per `KNOWLEDGE_ARCHITECTURE.md` §3.5/§3.6:

    - ``lookup`` — exact, keyed reads for reference and validation (e.g. the
      save slice validates a client look id against the known catalog).
    - ``retrieve`` — filtered/derived reads for the Decision Engine's
      candidate generation (deprecated entries never served, KN-3).

    ``knowledge_version`` is the curated content version (KN-1 §5.1),
    distinct from the rules-code ``engine_version``.

    Implementation: `CatalogKnowledgeSource` (in-code catalog, offline-safe,
    the approved knowledge seed). A DB-backed adapter may implement the same
    contract later behind this unmoved port.
    """

    knowledge_version: str

    def lookup_hairstyle_look(self, code: str) -> Optional[HairstyleRecommendation]: ...

    def retrieve_hairstyle_looks(self) -> list[HairstyleRecommendation]: ...


# --- Weather Provider Port & Exceptions (Stage 2 P1-3) ---


class WeatherError(Exception):
    """Base exception for weather retrieval, transport, and response parsing failures.

    Adapters translate all vendor/HTTP exceptions into WeatherError subclasses so
    domain and application code remain vendor-neutral (DEC-017-G).
    """

    def __init__(self, message: str, *, cause: Optional[Exception] = None) -> None:
        super().__init__(message)
        self.message = message
        self.cause = cause

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.message!r})"


class WeatherTransientError(WeatherError):
    """Transient network error, timeout, or upstream 5xx failure (safe to retry or fail open)."""


class WeatherLocationError(WeatherError):
    """Invalid, out-of-range, or unsupported geographic coordinates."""


class WeatherResponseError(WeatherError):
    """Upstream payload was malformed, missing required fields, or unparseable."""


@runtime_checkable
class WeatherProvider(Protocol):
    """Application-owned abstraction for external weather forecasting services.

    Application use cases depend strictly on this port, isolating Fansivibe
    from concrete weather vendors (Open-Meteo, NOAA, Tomorrow.io, etc.).
    """

    async def get_weather(
        self,
        *,
        latitude: float,
        longitude: float,
        city: Optional[str] = None,
        country: Optional[str] = None,
    ) -> Optional[WeatherContext]:
        """Retrieve and normalize current weather for the specified coarse coordinates.

        Args:
            latitude: Geographic latitude in decimal degrees (-90.0 to 90.0).
            longitude: Geographic longitude in decimal degrees (-180.0 to 180.0).
            city: Optional human-readable city name for presentation context.
            country: Optional country name or code for presentation context.

        Returns:
            A validated WeatherContext instance, or None if weather is unavailable.

        Raises:
            WeatherError: On transport, response, or coordinate failure (callers
            may catch WeatherError to implement graceful degradation).
        """
        ...

    async def close(self) -> None:
        """Release underlying HTTP client connections or resources."""
        ...
