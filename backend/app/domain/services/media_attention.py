"""Pure media-attention normalization and story-clustering boundary (D9B).

Provider-neutral and fully offline: this module validates media-attention
domain entities, performs deterministic article normalization and deduplication,
and executes 48-hour inception-anchored Jaccard story clustering.

It never executes network I/O, never accesses databases, and never assumes
an unverified provider payload shape.

Semantics preserved here
------------------------
- Exact approved status matrix pairs:
    ('present', 'complete'), ('suppressed', 'truncated'),
    ('missing', 'unavailable'), ('invalid', 'unavailable').
- Empirical zero vs positive branch:
    raw=0 => distinct_outlets=0, stories=0, value=0.0.
    raw>=1 => 1 <= distinct_outlets <= raw, 1 <= stories <= raw, value == float(stories) >= 1.0.
- Rejection of negative counts, negative values, and non-finite numbers (NaN, +/-Inf).
- Rejection of signed negative zero (-0.0).
- Pure article deduplication (URL / canonical identity).
- Deterministic 48-hour inception-anchored Jaccard clustering with chaining prevention.
- Explicit immutable versions for query configuration and clustering algorithms.
"""

from __future__ import annotations

import html
import math
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import NAMESPACE_URL, UUID, uuid5

from app.domain.ports.source_adapter import RawSourceRecord

# The primary metric this boundary records. Never "demand", never "sales".
METRIC_MEDIA_ATTENTION = "media_attention"
SIGNAL_KIND = METRIC_MEDIA_ATTENTION

SOURCE_GDELT_DOC = "gdelt_doc"
SOURCE_SYNTHETIC_MEDIA_ATTENTION = "synthetic_media_attention"

QUERY_KIND_CONCEPT = "concept"
QUERY_KIND_SEARCH_TERM = "search_term"
QUERY_KIND_TOPIC = "topic"
_QUERY_KINDS = (QUERY_KIND_CONCEPT, QUERY_KIND_SEARCH_TERM, QUERY_KIND_TOPIC)

GEO_TYPE_COUNTRY = "country"
GEO_TYPE_REGION = "region"
GEO_TYPE_WORLDWIDE = "worldwide"
_GEO_TYPES = (GEO_TYPE_COUNTRY, GEO_TYPE_REGION, GEO_TYPE_WORLDWIDE)

AGGREGATION_INTERVALS = ("daily", "weekly", "monthly", "rolling_7d")

STATUS_PRESENT = "present"
STATUS_MISSING = "missing"
STATUS_SUPPRESSED = "suppressed"
STATUS_INVALID = "invalid"
_VALUE_STATUSES = (STATUS_PRESENT, STATUS_MISSING, STATUS_SUPPRESSED, STATUS_INVALID)

COMPLETENESS_COMPLETE = "complete"
COMPLETENESS_TRUNCATED = "truncated"
COMPLETENESS_UNAVAILABLE = "unavailable"
_COMPLETENESS_STATUSES = (COMPLETENESS_COMPLETE, COMPLETENESS_TRUNCATED, COMPLETENESS_UNAVAILABLE)

# Closed and null-proof status matrix: exactly four approved pairs
ALLOWED_STATUS_PAIRS = frozenset({
    (STATUS_PRESENT, COMPLETENESS_COMPLETE),
    (STATUS_SUPPRESSED, COMPLETENESS_TRUNCATED),
    (STATUS_MISSING, COMPLETENESS_UNAVAILABLE),
    (STATUS_INVALID, COMPLETENESS_UNAVAILABLE),
})

DEFAULT_VALUE_SCALE = "estimated_deduplicated_stories_v1"
DEFAULT_QUERY_CONFIG_VERSION = "gdelt_india_fashion_v1"
DEFAULT_CLUSTERING_VERSION = "cluster_48h_jaccard_v1"

_TEXT_MAX = 200
_SCALE_MAX = 120
_VERSION_MAX = 60

JACCARD_SIMILARITY_THRESHOLD = 0.70
CLUSTER_INCEPTION_WINDOW = timedelta(hours=48)

_PUBLISHER_SUFFIX_RE = re.compile(
    r"\s*[-–—|:]\s*(pti|ani|ians|reuters|afp|times of india|hindustan times|vogue india|indian express|news18|ndtv|lifestyle asia|femina|gq india|latest news|breaking news)\b.*$",
    re.IGNORECASE,
)

_TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "ref", "ref_src", "source", "ocid",
})

_ENGLISH_STOP_WORDS = frozenset({
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "cannot", "could", "couldn",
    "did", "didn", "do", "does", "doesn", "doing", "don", "down", "during", "each",
    "few", "for", "from", "further", "had", "hadn", "has", "hasn", "have", "haven",
    "having", "he", "her", "here", "hers", "herself", "him", "himself", "his",
    "how", "i", "if", "in", "into", "is", "isn", "it", "its", "itself", "just",
    "ll", "m", "ma", "me", "mightn", "more", "most", "mustn", "my", "myself",
    "no", "nor", "not", "now", "o", "of", "off", "on", "once", "only", "or",
    "other", "our", "ours", "ourselves", "out", "over", "own", "re", "s", "same",
    "shan", "she", "should", "shouldn", "so", "some", "such", "t", "than", "that",
    "the", "their", "theirs", "them", "themselves", "then", "there", "these",
    "they", "this", "those", "through", "to", "too", "under", "until", "up",
    "ve", "very", "was", "wasn", "we", "were", "weren", "what", "when", "where",
    "which", "while", "who", "whom", "why", "will", "with", "won", "wouldn", "y",
    "you", "your", "yours", "yourself", "yourselves",
})


@dataclass(frozen=True)
class MediaAttentionObservation:
    """One normalized, concept-level media-attention observation (D9).

    Represents an aggregated editorial press signal over a geography and period.
    Never direct demand, never search interest, never catalog inventory.

    Provenance & Count Semantics:
    - ``raw_article_count``, ``distinct_outlet_count``, ``estimated_deduplicated_story_count``,
      and ``value``: Immutable historical aggregate metrics of the observation; these
      metrics reflect the state at observation collection/generation time and are NEVER
      altered by downstream operational raw record pruning.
    - ``contributing_raw_record_count``: Count of raw record join records currently
      retained in the ``media_attention_contributing_records`` provenance table for this
      observation. It reflects retained links (decreases on pruning, increases on relinking).
    - ``provenance_pruned``: Boolean flag indicating that historical contributing raw records
      have been pruned by operational retention cleanup (cleared to False upon safe relinking).
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
    value_status: str
    completeness_status: str
    value: Optional[float]
    value_scale: str
    raw_article_count: Optional[int]
    distinct_outlet_count: Optional[int]
    estimated_deduplicated_story_count: Optional[int]
    query_config_version: str
    clustering_version: str
    contributing_raw_record_count: int = 0
    provenance_pruned: bool = False
    source_timestamp: Optional[datetime] = None
    is_relative: bool = False
    synthetic: bool = False

    def __post_init__(self) -> None:
        # 1. Enforce exact approved status tuples
        status_tuple = (self.value_status, self.completeness_status)
        if status_tuple not in ALLOWED_STATUS_PAIRS:
            raise ValueError(f"Invalid status pair: {status_tuple}")

        # 2. Metric identity
        if self.metric != METRIC_MEDIA_ATTENTION:
            raise ValueError(f"metric must be {METRIC_MEDIA_ATTENTION!r}")

        # 3. Period validation (ordered, timezone-aware UTC)
        if not isinstance(self.period_start, datetime) or not isinstance(self.period_end, datetime):
            raise TypeError("period_start and period_end must be datetime instances")
        if self.period_start.tzinfo is None or self.period_start.utcoffset() is None:
            raise ValueError("period_start must be timezone-aware UTC datetime")
        if self.period_end.tzinfo is None or self.period_end.utcoffset() is None:
            raise ValueError("period_end must be timezone-aware UTC datetime")
        if self.period_end <= self.period_start:
            raise ValueError("period_end must be strictly after period_start")

        # 4. Version and string length validation
        if not isinstance(self.query_config_version, str) or not (1 <= len(self.query_config_version) <= _VERSION_MAX):
            raise ValueError(f"query_config_version length must be between 1 and {_VERSION_MAX}")
        if not isinstance(self.clustering_version, str) or not (1 <= len(self.clustering_version) <= _VERSION_MAX):
            raise ValueError(f"clustering_version length must be between 1 and {_VERSION_MAX}")
        if not isinstance(self.query_key, str) or not (1 <= len(self.query_key) <= _TEXT_MAX):
            raise ValueError(f"query_key length must be between 1 and {_TEXT_MAX}")
        if not isinstance(self.value_scale, str) or not (1 <= len(self.value_scale) <= _SCALE_MAX):
            raise ValueError(f"value_scale length must be between 1 and {_SCALE_MAX}")

        if self.query_kind not in _QUERY_KINDS:
            raise ValueError(f"query_kind must be one of {_QUERY_KINDS}")
        if self.geo_scope_type not in _GEO_TYPES:
            raise ValueError(f"geo_scope_type must be one of {_GEO_TYPES}")
        if self.aggregation_interval not in AGGREGATION_INTERVALS:
            raise ValueError(f"aggregation_interval must be one of {AGGREGATION_INTERVALS}")

        # 5. Status-driven numeric and count validation
        if self.value_status == STATUS_PRESENT:
            # Completeness status must be complete
            if self.completeness_status != COMPLETENESS_COMPLETE:
                raise ValueError("completeness_status must be 'complete' when value_status is 'present'")

            # Nullability checks
            if self.value is None:
                raise ValueError("Value cannot be None when value_status is 'present'")
            if self.raw_article_count is None:
                raise ValueError("raw_article_count cannot be None when value_status is 'present'")
            if self.distinct_outlet_count is None:
                raise ValueError("distinct_outlet_count cannot be None when value_status is 'present'")
            if self.estimated_deduplicated_story_count is None:
                raise ValueError("estimated_deduplicated_story_count cannot be None when value_status is 'present'")

            # Non-finite and boolean rejection
            if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
                raise TypeError(f"Value must be a float or int, got {type(self.value).__name__}")
            if math.isnan(self.value):
                raise ValueError("Metric value cannot be NaN")
            if math.isinf(self.value):
                raise ValueError("Metric value cannot be infinite (+inf / -inf)")
            if not math.isfinite(self.value):
                raise ValueError("Metric value must be finite")

            # Non-negative value rejection (reject negative and signed negative zero -0.0)
            if self.value < 0.0:
                raise ValueError(f"Metric value cannot be negative: {self.value}")
            if self.value == 0.0 and math.copysign(1.0, self.value) < 0.0:
                raise ValueError("Metric value cannot be signed negative zero (-0.0)")

            # Non-negative count checks
            for count_name, count_val in [
                ("raw_article_count", self.raw_article_count),
                ("distinct_outlet_count", self.distinct_outlet_count),
                ("estimated_deduplicated_story_count", self.estimated_deduplicated_story_count),
            ]:
                if isinstance(count_val, bool) or not isinstance(count_val, int):
                    raise TypeError(f"{count_name} must be an integer, got {type(count_val).__name__}")
                if count_val < 0:
                    raise ValueError(f"{count_name} cannot be negative: {count_val}")

            # Exact relationship: value == float(estimated_deduplicated_story_count)
            if float(self.value) != float(self.estimated_deduplicated_story_count):
                raise ValueError(
                    f"Value ({self.value}) must exactly equal float(estimated_deduplicated_story_count) "
                    f"({float(self.estimated_deduplicated_story_count)})"
                )

            # Hierarchy integrity: zero vs positive branches
            if self.raw_article_count == 0:
                if self.distinct_outlet_count != 0:
                    raise ValueError("distinct_outlet_count must be 0 when raw_article_count is 0")
                if self.estimated_deduplicated_story_count != 0:
                    raise ValueError("estimated_deduplicated_story_count must be 0 when raw_article_count is 0")
                if self.value != 0.0:
                    raise ValueError("value must be 0.0 when raw_article_count is 0")
            else:
                if self.distinct_outlet_count < 1:
                    raise ValueError("distinct_outlet_count must be >= 1 when raw_article_count >= 1")
                if self.distinct_outlet_count > self.raw_article_count:
                    raise ValueError(
                        f"distinct_outlet_count ({self.distinct_outlet_count}) cannot exceed "
                        f"raw_article_count ({self.raw_article_count})"
                    )
                if self.estimated_deduplicated_story_count < 1:
                    raise ValueError("estimated_deduplicated_story_count must be >= 1 when raw_article_count >= 1")
                if self.estimated_deduplicated_story_count > self.raw_article_count:
                    raise ValueError(
                        f"estimated_deduplicated_story_count ({self.estimated_deduplicated_story_count}) cannot exceed "
                        f"raw_article_count ({self.raw_article_count})"
                    )
                if self.value < 1.0:
                    raise ValueError("value must be >= 1.0 when raw_article_count >= 1")

        else:
            # value_status in ('suppressed', 'missing', 'invalid')
            if self.value is not None:
                raise ValueError(f"Value must be None when value_status is '{self.value_status}'")
            if self.raw_article_count is not None:
                raise ValueError(f"raw_article_count must be None when value_status is '{self.value_status}'")
            if self.distinct_outlet_count is not None:
                raise ValueError(f"distinct_outlet_count must be None when value_status is '{self.value_status}'")
            if self.estimated_deduplicated_story_count is not None:
                raise ValueError(
                    f"estimated_deduplicated_story_count must be None when value_status is '{self.value_status}'"
                )


@dataclass(frozen=True)
class MediaArticle:
    """One normalized media article before or during clustering."""

    url: str
    normalized_url: str
    outlet_domain: str
    title: str
    canonical_tokens: frozenset[str]
    published_at: datetime
    raw_source_record_id: Optional[UUID] = None
    language: str = "eng"
    source_country: Optional[str] = None


@dataclass(frozen=True)
class StoryCluster:
    """A cluster of related news articles representing an estimated unique story."""

    cluster_id: UUID
    anchor_timestamp: datetime
    tokens: frozenset[str]
    articles: tuple[MediaArticle, ...]
    domains: frozenset[str]


@dataclass(frozen=True)
class ContributingRecordAssignment:
    """Linkage between an observation, contributing raw record, and similarity cluster."""

    raw_source_record_id: UUID
    similarity_cluster_id: UUID
    is_canonical: bool
    outlet_domain: str


@dataclass(frozen=True)
class MediaAttentionEvidence:
    """Read representation of a media attention observation for downstream consumers."""

    observation_id: UUID
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
    completeness_status: str
    raw_article_count: Optional[int]
    distinct_outlet_count: Optional[int]
    estimated_deduplicated_story_count: Optional[int]
    query_config_version: str
    clustering_version: str
    contributing_raw_record_count: int
    provenance_pruned: bool
    observed_at: datetime
    source_timestamp: Optional[datetime] = None
    synthetic: bool = False


@dataclass(frozen=True)
class MediaAttentionResult:
    """Outcome of normalizing, deduplicating, and clustering media attention."""

    observation: Optional[MediaAttentionObservation]
    clusters: tuple[StoryCluster, ...] = ()
    contributing_records: tuple[ContributingRecordAssignment, ...] = ()
    errors: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.observation is not None and not self.errors

    @property
    def status(self) -> str:
        if not self.ok:
            return "rejected"
        return "accepted_with_missing_optional" if self.missing else "accepted"


def extract_outlet_domain(url: str, fallback_domain: Optional[str] = None) -> str:
    """Extract and normalize publisher domain from an article URL.

    Strips protocol, port, and common prefixes ('www.', 'm.', 'amp.', 'amp-').
    Falls back to `fallback_domain` if URL netloc cannot be resolved.
    """
    hostname = None
    if url and isinstance(url, str):
        url_clean = url.strip()
        if url_clean:
            if not (url_clean.startswith("http://") or url_clean.startswith("https://")):
                url_clean = "https://" + url_clean
            try:
                parts = urlsplit(url_clean)
                hostname = parts.hostname
            except Exception:
                hostname = None

    if not hostname and fallback_domain and isinstance(fallback_domain, str):
        fb = fallback_domain.strip().lower()
        if fb.startswith("http://") or fb.startswith("https://"):
            try:
                hostname = urlsplit(fb).hostname
            except Exception:
                hostname = fb
        else:
            hostname = fb

    if not hostname:
        raise ValueError(f"Unable to extract valid outlet domain from url={url!r}, fallback={fallback_domain!r}")

    domain = hostname.lower().strip()
    if ":" in domain:
        domain = domain.split(":")[0]

    prefixes = ("www.", "m.", "amp.", "amp-")
    changed = True
    while changed:
        changed = False
        for prefix in prefixes:
            if domain.startswith(prefix):
                domain = domain[len(prefix):]
                changed = True

    domain = domain.strip(".")
    if not domain:
        raise ValueError(f"Outlet domain resolved to empty string from url={url!r}")
    return domain


def normalize_article_url(url: str) -> str:
    """Normalize an article URL for deterministic exact deduplication."""
    if not url or not isinstance(url, str):
        return ""
    clean = url.strip()
    if not (clean.startswith("http://") or clean.startswith("https://")):
        clean = "https://" + clean
    parts = urlsplit(clean)
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    elif netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]

    path = parts.path.rstrip("/")

    filtered_queries = [
        (k, v) for k, v in parse_qsl(parts.query)
        if k.lower() not in _TRACKING_PARAMS
    ]
    filtered_queries.sort()
    query = urlencode(filtered_queries) if filtered_queries else ""

    return urlunsplit((scheme, netloc, path, query, ""))


def parse_media_timestamp(value: object) -> tuple[Optional[datetime], Optional[str]]:
    """Parse a timestamp into a timezone-aware UTC datetime.

    Accepts:
    - datetime instance (must be timezone-aware or error)
    - ISO 8601 strings (e.g. '2026-01-05T12:00:00Z', '2026-01-05T12:00:00+00:00')
    - GDELT format strings (e.g. '20260105T120000Z', '20260105120000')

    Returns (parsed_dt, None) on success or (None, reason) on failure.
    Reasons: 'missing', 'invalid', 'naive'.
    """
    if value is None:
        return None, "missing"
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            return None, "naive"
        return value.astimezone(timezone.utc), None
    if not isinstance(value, str):
        return None, "invalid"

    s = value.strip()
    if not s:
        return None, "missing"

    # Try standard ISO format
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None or dt.utcoffset() is None:
            return None, "naive"
        return dt.astimezone(timezone.utc), None
    except ValueError:
        pass

    # Try GDELT compact format: YYYYMMDDTHHMMSSZ or YYYYMMDDHHMMSS
    gdelt_cleaned = s.rstrip("Z").replace("T", "")
    if len(gdelt_cleaned) == 14 and gdelt_cleaned.isdigit():
        try:
            dt = datetime.strptime(gdelt_cleaned, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
            return dt, None
        except ValueError:
            return None, "invalid"

    return None, "invalid"


def canonicalize_headline_tokens(title: str) -> frozenset[str]:
    """Tokenize and canonicalize an article headline for story clustering.

    1. Unescape HTML entities (&amp;, &#39;, etc.)
    2. NFKC unicode normalize and lowercase
    3. Strip publisher & wire suffixes (e.g. - PTI, | Reuters, - Times of India)
    4. Strip non-alphanumeric characters (replace with spaces)
    5. Filter out English stop words and single-character tokens
    6. Return an immutable frozenset of canonical tokens
    """
    if not title or not isinstance(title, str):
        return frozenset()

    text = html.unescape(title)
    text = unicodedata.normalize("NFKC", text).lower()
    text = _PUBLISHER_SUFFIX_RE.sub("", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)

    tokens = {
        token
        for token in text.split()
        if len(token) >= 2 and token not in _ENGLISH_STOP_WORDS
    }
    return frozenset(tokens)


def jaccard_similarity(tokens_a: frozenset[str], tokens_b: frozenset[str]) -> float:
    """Compute Jaccard token similarity between two token sets."""
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    return intersection / union


def parse_media_article(
    raw: RawSourceRecord | dict,
    default_language: str = "eng",
    default_country: Optional[str] = "IN",
) -> tuple[Optional[MediaArticle], Optional[str]]:
    """Parse one raw article payload into a normalized MediaArticle."""
    raw_id: Optional[UUID] = None
    if isinstance(raw, RawSourceRecord):
        payload = raw.payload
        if hasattr(raw, "source_record_id") and raw.source_record_id:
            try:
                raw_id = UUID(raw.source_record_id)
            except ValueError:
                pass
    elif isinstance(raw, dict):
        payload = raw
    else:
        return None, "article payload must be a mapping or RawSourceRecord"

    if not isinstance(payload, dict):
        return None, "article payload must be a mapping"

    raw_url = payload.get("url") or payload.get("link")
    if not raw_url or not isinstance(raw_url, str) or not raw_url.strip():
        return None, "article url is required"
    clean_url = raw_url.strip()

    raw_title = payload.get("title") or payload.get("headline")
    if not raw_title or not isinstance(raw_title, str) or not raw_title.strip():
        return None, "article title is required"
    title = raw_title.strip()

    raw_domain = payload.get("domain") or payload.get("outlet")
    try:
        outlet_domain = extract_outlet_domain(clean_url, fallback_domain=raw_domain)
    except ValueError as exc:
        return None, str(exc)

    norm_url = normalize_article_url(clean_url)

    raw_ts = (
        payload.get("seendate")
        or payload.get("published_at")
        or payload.get("source_timestamp")
        or (raw.source_timestamp if isinstance(raw, RawSourceRecord) else None)
    )
    published_at, ts_err = parse_media_timestamp(raw_ts)
    if ts_err is not None:
        return None, f"article timestamp {ts_err}: {raw_ts!r}"

    tokens = canonicalize_headline_tokens(title)
    language = payload.get("language") or default_language
    country = payload.get("sourcecountry") or payload.get("country") or default_country

    article = MediaArticle(
        url=clean_url,
        normalized_url=norm_url,
        outlet_domain=outlet_domain,
        title=title,
        canonical_tokens=tokens,
        published_at=published_at,  # type: ignore[arg-type]
        raw_source_record_id=raw_id,
        language=str(language).lower() if language else "eng",
        source_country=str(country).upper() if country else None,
    )
    return article, None


def cluster_stories(
    articles: Sequence[MediaArticle],
    clustering_version: str = DEFAULT_CLUSTERING_VERSION,
    similarity_threshold: float = JACCARD_SIMILARITY_THRESHOLD,
    inception_window: timedelta = CLUSTER_INCEPTION_WINDOW,
) -> tuple[tuple[StoryCluster, ...], tuple[ContributingRecordAssignment, ...]]:
    """Execute deterministic 48-hour inception-anchored Jaccard story clustering.

    1. Sort articles deterministically: (published_at ASC, outlet_domain ASC, normalized_url ASC)
    2. Maintain active clusters list.
    3. For each article A:
       Find matching existing cluster C where:
         - 0 <= (A.published_at - C.anchor_timestamp) <= inception_window (48 hours)
         - jaccard(A.tokens, C.tokens) >= similarity_threshold OR A.tokens == C.tokens
       If matched:
         Pick best cluster (highest Jaccard, tie-breaker: earliest anchor_timestamp, lowest cluster_id)
         Merge A into C: C.tokens |= A.tokens, C.domains |= {A.outlet_domain}, C.articles += (A,)
       If no match:
         Create new cluster with anchor_timestamp = A.published_at, tokens = A.tokens.
    4. Emit clusters and ContributingRecordAssignment for each article.
    """
    sorted_articles = sorted(
        articles,
        key=lambda a: (a.published_at, a.outlet_domain, a.normalized_url),
    )

    class _MutableCluster:
        def __init__(self, cluster_id: UUID, anchor_timestamp: datetime, first_article: MediaArticle):
            self.cluster_id = cluster_id
            self.anchor_timestamp = anchor_timestamp
            self.tokens = set(first_article.canonical_tokens)
            self.articles = [first_article]
            self.domains = {first_article.outlet_domain}

    clusters: list[_MutableCluster] = []

    for article in sorted_articles:
        best_cluster: Optional[_MutableCluster] = None
        best_sim = -1.0

        for cand in clusters:
            delta = article.published_at - cand.anchor_timestamp
            if delta < timedelta(0) or delta > inception_window:
                continue

            # Similarity check
            cand_frozen = frozenset(cand.tokens)
            sim = jaccard_similarity(article.canonical_tokens, cand_frozen)
            is_match = (sim >= similarity_threshold) or (
                article.canonical_tokens and article.canonical_tokens == cand_frozen
            )

            if is_match:
                if sim > best_sim:
                    best_sim = sim
                    best_cluster = cand
                elif sim == best_sim and best_cluster is not None:
                    # Deterministic tie-breaker
                    if (cand.anchor_timestamp, str(cand.cluster_id)) < (
                        best_cluster.anchor_timestamp,
                        str(best_cluster.cluster_id),
                    ):
                        best_cluster = cand

        if best_cluster is not None:
            best_cluster.tokens.update(article.canonical_tokens)
            best_cluster.domains.add(article.outlet_domain)
            best_cluster.articles.append(article)
        else:
            cid = uuid5(
                NAMESPACE_URL,
                f"cluster:{clustering_version}:{article.normalized_url}:{article.published_at.isoformat()}",
            )
            clusters.append(_MutableCluster(cid, article.published_at, article))

    frozen_clusters: list[StoryCluster] = []
    assignments: list[ContributingRecordAssignment] = []

    for c in clusters:
        story_cluster = StoryCluster(
            cluster_id=c.cluster_id,
            anchor_timestamp=c.anchor_timestamp,
            tokens=frozenset(c.tokens),
            articles=tuple(c.articles),
            domains=frozenset(c.domains),
        )
        frozen_clusters.append(story_cluster)

        for idx, art in enumerate(c.articles):
            if art.raw_source_record_id is not None:
                assignments.append(
                    ContributingRecordAssignment(
                        raw_source_record_id=art.raw_source_record_id,
                        similarity_cluster_id=c.cluster_id,
                        is_canonical=(idx == 0),
                        outlet_domain=art.outlet_domain,
                    )
                )

    return tuple(frozen_clusters), tuple(assignments)


def normalize_media_attention(
    *,
    records: Sequence[RawSourceRecord | dict | MediaArticle] = (),
    period_start: datetime,
    period_end: datetime,
    query_key: str,
    query_display: Optional[str] = None,
    geo_scope: str = "IN",
    geo_scope_type: str = GEO_TYPE_COUNTRY,
    aggregation_interval: str = "rolling_7d",
    value_status: str = STATUS_PRESENT,
    completeness_status: str = COMPLETENESS_COMPLETE,
    query_config_version: str = DEFAULT_QUERY_CONFIG_VERSION,
    clustering_version: str = DEFAULT_CLUSTERING_VERSION,
    source: str = SOURCE_GDELT_DOC,
    value_scale: str = DEFAULT_VALUE_SCALE,
    synthetic: bool = False,
    source_timestamp: Optional[datetime] = None,
) -> MediaAttentionResult:
    """Normalize, deduplicate, and cluster a set of articles for a query-period window."""
    errors: list[str] = []
    missing: list[str] = []

    display = query_display or query_key

    # Validate status pair
    status_tuple = (value_status, completeness_status)
    if status_tuple not in ALLOWED_STATUS_PAIRS:
        return MediaAttentionResult(
            observation=None,
            errors=(f"Invalid status pair: {status_tuple}",),
        )

    # Validate period ordering and timezone awareness
    if not isinstance(period_start, datetime) or not isinstance(period_end, datetime):
        return MediaAttentionResult(
            observation=None,
            errors=("period_start and period_end must be datetime instances",),
        )
    if period_start.tzinfo is None or period_start.utcoffset() is None:
        return MediaAttentionResult(
            observation=None,
            errors=("period_start must be a timezone-aware ISO 8601 UTC timestamp",),
        )
    if period_end.tzinfo is None or period_end.utcoffset() is None:
        return MediaAttentionResult(
            observation=None,
            errors=("period_end must be a timezone-aware ISO 8601 UTC timestamp",),
        )
    if period_end <= period_start:
        return MediaAttentionResult(
            observation=None,
            errors=("period.end must be after period.start",),
        )

    # Non-present status: suppressed / missing / invalid
    if value_status != STATUS_PRESENT:
        try:
            obs = MediaAttentionObservation(
                source=source,
                metric=METRIC_MEDIA_ATTENTION,
                query_kind=QUERY_KIND_CONCEPT,
                query_key=query_key,
                query_display=display,
                geo_scope=geo_scope,
                geo_scope_type=geo_scope_type,
                aggregation_interval=aggregation_interval,
                period_start=period_start,
                period_end=period_end,
                value_status=value_status,
                completeness_status=completeness_status,
                value=None,
                value_scale=value_scale,
                raw_article_count=None,
                distinct_outlet_count=None,
                estimated_deduplicated_story_count=None,
                query_config_version=query_config_version,
                clustering_version=clustering_version,
                contributing_raw_record_count=0,
                provenance_pruned=False,
                source_timestamp=source_timestamp,
                is_relative=False,
                synthetic=synthetic,
            )
            return MediaAttentionResult(observation=obs)
        except (ValueError, TypeError) as exc:
            return MediaAttentionResult(observation=None, errors=(str(exc),))

    # Present status: process records
    # Check empirical zero case
    if not records:
        try:
            obs = MediaAttentionObservation(
                source=source,
                metric=METRIC_MEDIA_ATTENTION,
                query_kind=QUERY_KIND_CONCEPT,
                query_key=query_key,
                query_display=display,
                geo_scope=geo_scope,
                geo_scope_type=geo_scope_type,
                aggregation_interval=aggregation_interval,
                period_start=period_start,
                period_end=period_end,
                value_status=STATUS_PRESENT,
                completeness_status=COMPLETENESS_COMPLETE,
                value=0.0,
                value_scale=value_scale,
                raw_article_count=0,
                distinct_outlet_count=0,
                estimated_deduplicated_story_count=0,
                query_config_version=query_config_version,
                clustering_version=clustering_version,
                contributing_raw_record_count=0,
                provenance_pruned=False,
                source_timestamp=source_timestamp,
                is_relative=False,
                synthetic=synthetic,
            )
            return MediaAttentionResult(observation=obs)
        except (ValueError, TypeError) as exc:
            return MediaAttentionResult(observation=None, errors=(str(exc),))

    # Parse and validate incoming articles
    parsed_articles: list[MediaArticle] = []
    seen_urls: set[str] = set()

    for idx, item in enumerate(records):
        if isinstance(item, MediaArticle):
            article = item
        else:
            article, parse_err = parse_media_article(item)
            if parse_err is not None:
                errors.append(f"record[{idx}]: {parse_err}")
                continue

        # Exact duplicate elimination on normalized URL
        if article.normalized_url in seen_urls:
            continue
        seen_urls.add(article.normalized_url)
        parsed_articles.append(article)

    if not parsed_articles:
        if errors:
            return MediaAttentionResult(observation=None, errors=tuple(errors))
        # All were duplicate URLs or filtered: treat as empirical zero
        return MediaAttentionResult(
            observation=MediaAttentionObservation(
                source=source,
                metric=METRIC_MEDIA_ATTENTION,
                query_kind=QUERY_KIND_CONCEPT,
                query_key=query_key,
                query_display=display,
                geo_scope=geo_scope,
                geo_scope_type=geo_scope_type,
                aggregation_interval=aggregation_interval,
                period_start=period_start,
                period_end=period_end,
                value_status=STATUS_PRESENT,
                completeness_status=COMPLETENESS_COMPLETE,
                value=0.0,
                value_scale=value_scale,
                raw_article_count=0,
                distinct_outlet_count=0,
                estimated_deduplicated_story_count=0,
                query_config_version=query_config_version,
                clustering_version=clustering_version,
                contributing_raw_record_count=0,
                provenance_pruned=False,
                source_timestamp=source_timestamp,
                is_relative=False,
                synthetic=synthetic,
            )
        )

    # Perform clustering
    clusters, assignments = cluster_stories(
        parsed_articles,
        clustering_version=clustering_version,
    )

    raw_count = len(parsed_articles)
    distinct_outlets = len({a.outlet_domain for a in parsed_articles})
    story_count = len(clusters)
    metric_value = float(story_count)

    try:
        obs = MediaAttentionObservation(
            source=source,
            metric=METRIC_MEDIA_ATTENTION,
            query_kind=QUERY_KIND_CONCEPT,
            query_key=query_key,
            query_display=display,
            geo_scope=geo_scope,
            geo_scope_type=geo_scope_type,
            aggregation_interval=aggregation_interval,
            period_start=period_start,
            period_end=period_end,
            value_status=STATUS_PRESENT,
            completeness_status=COMPLETENESS_COMPLETE,
            value=metric_value,
            value_scale=value_scale,
            raw_article_count=raw_count,
            distinct_outlet_count=distinct_outlets,
            estimated_deduplicated_story_count=story_count,
            query_config_version=query_config_version,
            clustering_version=clustering_version,
            contributing_raw_record_count=len(assignments),
            provenance_pruned=False,
            source_timestamp=source_timestamp,
            is_relative=False,
            synthetic=synthetic,
        )
        return MediaAttentionResult(
            observation=obs,
            clusters=clusters,
            contributing_records=assignments,
            errors=tuple(errors),
            missing=tuple(missing),
        )
    except (ValueError, TypeError) as exc:
        return MediaAttentionResult(observation=None, errors=(str(exc),))
