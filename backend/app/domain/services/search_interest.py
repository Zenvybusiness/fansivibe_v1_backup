"""Pure search-interest normalization boundary (D9B).

Provider-neutral and fully offline: this module validates the *canonical
search-interest payload shape* that a search-interest source adapter emits into
a typed :class:`SearchInterestObservation`. It never talks to a provider, never
invents a value, and never assumes Google's response schema, value scale,
authentication, pagination or suppression semantics — those are supplied per
record by the adapter.

Why a separate boundary
-----------------------
A search-interest observation is a **concept-level relative signal**, not a
product listing: it has no canonical product, no price and no availability. It
must not be forced into ``products``, ``product_source_map`` or
``product_observations`` (see ``docs/architecture/D8_GOOGLE_TRENDS_INTEGRATION_READINESS.md``).

Semantics preserved here
------------------------
- ``value`` is a provider-reported **relative** search-interest value; absolute
  search volumes, sales or purchasing intent are never inferred.
- Missing / suppressed / invalid values stay ``NULL`` (``value_status``), never
  ``0``.
- ``period_start``/``period_end`` must be timezone-aware and ordered; the
  observation describes a *period*, not an instant.
- ``source_timestamp`` (provider time) is kept distinct from the collection
  time added by the database.
- A record marked ``synthetic: true`` is fixture/test data and is never real
  provider evidence.

Everything here is pure Python: no database, no network, no clock, and never
Qwen / MediaPipe / an LLM. Equal inputs give equal output. The payload digest is
the shared :func:`app.domain.services.normalization.payload_hash` (no second
hashing scheme).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.domain.ports.source_adapter import RawSourceRecord
from app.trending.domain import normalize_term

# The one metric this foundation records. Never "volume", never "sales".
METRIC_SEARCH_INTEREST = "search_interest"
# A distinct signal kind (not D6's catalog_operational / supporting). D6 adopts
# it only when search-interest evidence is wired and reviewed (D9C/D9D).
SIGNAL_KIND = METRIC_SEARCH_INTEREST

QUERY_KIND_SEARCH_TERM = "search_term"
QUERY_KIND_TOPIC = "topic"
_QUERY_KINDS = (QUERY_KIND_SEARCH_TERM, QUERY_KIND_TOPIC)

GEO_TYPE_COUNTRY = "country"
GEO_TYPE_REGION = "region"
GEO_TYPE_WORLDWIDE = "worldwide"
_GEO_TYPES = (GEO_TYPE_COUNTRY, GEO_TYPE_REGION, GEO_TYPE_WORLDWIDE)

AGGREGATION_INTERVALS = ("daily", "weekly", "monthly", "yearly")

STATUS_PRESENT = "present"
STATUS_MISSING = "missing"
STATUS_SUPPRESSED = "suppressed"
STATUS_INVALID = "invalid"
_VALUE_STATUSES = (STATUS_PRESENT, STATUS_MISSING, STATUS_SUPPRESSED, STATUS_INVALID)

_TEXT_MAX = 200
_SCALE_MAX = 120
_VERSION_MAX = 60


@dataclass(frozen=True)
class SearchInterestObservation:
    """One normalized, concept-level search-interest observation.

    ``value`` is ``None`` for every non-``present`` status — never zero.
    ``is_relative`` is always ``True`` (this signal is a relative index, not an
    absolute quantity). ``synthetic`` marks fixture/test data.
    """

    source: str
    metric: str
    query_kind: str
    query_key: str
    query_display: str
    geo_scope: str
    geo_scope_type: str
    aggregation_interval: str
    period_start: datetime
    period_end: datetime
    value: Optional[float]
    value_scale: str
    value_status: str
    query_config_version: str
    source_timestamp: Optional[datetime] = None
    is_relative: bool = True
    synthetic: bool = False


@dataclass(frozen=True)
class SearchInterestResult:
    """Outcome of normalizing one raw search-interest record.

    Mirrors :class:`app.domain.services.normalization.NormalizationResult`:
    either ``observation`` is populated and ``errors`` is empty, or
    ``observation`` is ``None`` and ``errors`` explains every failure.
    ``missing`` lists accepted-but-absent optional fields.
    """

    observation: Optional[SearchInterestObservation]
    errors: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.observation is not None and not self.errors

    @property
    def status(self) -> str:
        """``accepted`` | ``accepted_with_missing_optional`` | ``rejected``."""
        if not self.ok:
            return "rejected"
        return "accepted_with_missing_optional" if self.missing else "accepted"


def _text(value: object) -> Optional[str]:
    """Trimmed non-empty text, else ``None`` (strings only)."""
    if isinstance(value, str):
        trimmed = value.strip()
        return trimmed or None
    return None


def _parse_ts(value: object) -> tuple[Optional[datetime], Optional[str]]:
    """Parse an ISO 8601 timestamp, requiring timezone awareness.

    Returns ``(datetime, None)`` on success or ``(None, reason)`` where reason
    is ``"missing"`` (``None`` input), ``"invalid"`` (unparseable) or
    ``"naive"`` (no timezone).
    """
    if value is None:
        return None, "missing"
    if not isinstance(value, str):
        return None, "invalid"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None, "invalid"
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None, "naive"
    return parsed, None


def _finite_number(value: object) -> Optional[float]:
    """A finite real number, rejecting bool and non-numeric strings."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def normalize_search_interest(raw: RawSourceRecord) -> SearchInterestResult:
    """Validate one raw record into a typed search-interest observation.

    The adapter is responsible for emitting this canonical payload shape (and,
    later, for translating a real provider response into it); this function
    only validates and maps. On any failure it returns a rejected result with
    deterministic error strings and no observation.
    """
    errors: list[str] = []
    missing: list[str] = []

    payload = raw.payload
    if not isinstance(payload, dict):
        return SearchInterestResult(None, ("payload must be a mapping",))

    source = _text(raw.source)
    if source is None:
        errors.append("source is required")

    metric = payload.get("metric", METRIC_SEARCH_INTEREST)
    if metric != METRIC_SEARCH_INTEREST:
        errors.append(f"metric must be {METRIC_SEARCH_INTEREST!r}")

    # --- query -------------------------------------------------------------
    query_kind: Optional[str] = None
    query_key: Optional[str] = None
    query_display: Optional[str] = None
    query = payload.get("query")
    if not isinstance(query, dict):
        errors.append("query must be a mapping")
    else:
        query_kind = _text(query.get("kind"))
        if query_kind not in _QUERY_KINDS:
            errors.append("query.kind must be 'search_term' or 'topic'")
            query_kind = None
        query_display = _text(query.get("display"))
        if query_display is None:
            errors.append("query.display is required")
        query_key = _text(query.get("key"))
        if query_key is None and query_kind == QUERY_KIND_SEARCH_TERM and query_display:
            query_key = normalize_term(query_display) or None
        if query_key is None:
            errors.append("query.key is required (or derivable for a search_term)")
        elif len(query_key) > _TEXT_MAX:
            errors.append("query.key is too long")

    # --- geography ---------------------------------------------------------
    geo_scope: Optional[str] = None
    geo_scope_type: Optional[str] = None
    geo = payload.get("geo")
    if not isinstance(geo, dict):
        errors.append("geo must be a mapping")
    else:
        geo_scope = _text(geo.get("scope"))
        geo_scope_type = _text(geo.get("scope_type"))
        if geo_scope is None:
            errors.append("geo.scope is required")
        if geo_scope_type not in _GEO_TYPES:
            errors.append("geo.scope_type must be 'country', 'region' or 'worldwide'")
            geo_scope_type = None
        elif geo_scope_type == GEO_TYPE_WORLDWIDE and geo_scope != GEO_TYPE_WORLDWIDE:
            errors.append("geo.scope must be 'worldwide' when scope_type is 'worldwide'")

    # --- interval ----------------------------------------------------------
    aggregation_interval = _text(payload.get("interval"))
    if aggregation_interval not in AGGREGATION_INTERVALS:
        errors.append("interval must be one of daily/weekly/monthly/yearly")

    # --- period ------------------------------------------------------------
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    period = payload.get("period")
    if not isinstance(period, dict):
        errors.append("period must be a mapping")
    else:
        period_start, s_err = _parse_ts(period.get("start"))
        if s_err == "missing":
            errors.append("period.start is required")
        elif s_err is not None:
            errors.append("period.start must be a timezone-aware ISO 8601 timestamp")
        period_end, e_err = _parse_ts(period.get("end"))
        if e_err == "missing":
            errors.append("period.end is required")
        elif e_err is not None:
            errors.append("period.end must be a timezone-aware ISO 8601 timestamp")
        if period_start is not None and period_end is not None and period_end <= period_start:
            errors.append("period.end must be after period.start")

    # --- value (relative; missing/suppressed never become zero) ------------
    value_status = _text(payload.get("value_status"))
    raw_value = payload.get("value")
    value: Optional[float] = None
    if value_status is None:
        value_status = STATUS_PRESENT if raw_value is not None else STATUS_MISSING
    if value_status not in _VALUE_STATUSES:
        errors.append(
            "value_status must be one of present/missing/suppressed/invalid"
        )
    elif value_status == STATUS_PRESENT:
        value = _finite_number(raw_value)
        if value is None:
            errors.append("value must be a finite number when value_status is 'present'")
    else:
        if raw_value is not None:
            errors.append(f"value must be absent when value_status is {value_status!r}")
        value = None  # unknown stays unknown — never 0
        missing.append("value")

    # --- scale / version ---------------------------------------------------
    value_scale = _text(payload.get("value_scale"))
    if value_scale is None:
        errors.append("value_scale is required")
    elif len(value_scale) > _SCALE_MAX:
        errors.append("value_scale is too long")

    query_config_version = _text(payload.get("query_config_version"))
    if query_config_version is None:
        errors.append("query_config_version is required")
    elif len(query_config_version) > _VERSION_MAX:
        errors.append("query_config_version is too long")

    # --- source timestamp (distinct from collection time) ------------------
    source_timestamp: Optional[datetime] = None
    supplied_ts = raw.source_timestamp if raw.source_timestamp is not None else payload.get("source_timestamp")
    if supplied_ts is None:
        missing.append("source_timestamp")
    else:
        source_timestamp, ts_err = _parse_ts(
            supplied_ts.isoformat() if isinstance(supplied_ts, datetime) else supplied_ts
        )
        if ts_err is not None:
            errors.append("source_timestamp must be a timezone-aware ISO 8601 timestamp")

    synthetic = payload.get("synthetic", False)
    if not isinstance(synthetic, bool):
        errors.append("synthetic must be a boolean")
        synthetic = False

    if errors:
        return SearchInterestResult(None, tuple(errors), tuple(missing))

    observation = SearchInterestObservation(
        source=source,  # type: ignore[arg-type]
        metric=METRIC_SEARCH_INTEREST,
        query_kind=query_kind,  # type: ignore[arg-type]
        query_key=query_key,  # type: ignore[arg-type]
        query_display=query_display,  # type: ignore[arg-type]
        geo_scope=geo_scope,  # type: ignore[arg-type]
        geo_scope_type=geo_scope_type,  # type: ignore[arg-type]
        aggregation_interval=aggregation_interval,  # type: ignore[arg-type]
        period_start=period_start,  # type: ignore[arg-type]
        period_end=period_end,  # type: ignore[arg-type]
        value=value,
        value_scale=value_scale,  # type: ignore[arg-type]
        value_status=value_status,
        query_config_version=query_config_version,  # type: ignore[arg-type]
        source_timestamp=source_timestamp,
        is_relative=True,
        synthetic=synthetic,
    )
    return SearchInterestResult(observation, (), tuple(missing))
