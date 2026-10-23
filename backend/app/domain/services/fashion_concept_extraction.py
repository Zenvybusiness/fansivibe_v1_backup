"""Deterministic fashion-concept extraction service (TRENDING-02).

A pure domain service that extracts normalized fashion concepts from video titles,
descriptions, and tags, adhering to a configuration-driven vocabulary.

Invariants & Principles:
- Deterministic: Pure string normalization and regex pattern matching. Equal input
  produces equal output with zero random state, network calls, or clock calls.
- Word-boundary enforcement: Uses strict `\\b` word boundaries to avoid matching
  concepts solely through unrelated substrings (e.g. "condemning" does not match
  "denim", "rampant" does not match "pant", "precargo" does not match "cargo").
- Negative pattern gating: Suppresses false matches from non-garment contexts
  (e.g. "table linen", "bed linen", "linen tablecloth" do not match "linen shirts").
- Category & attribute compatibility: Mapped concepts specify their canonical
  category (tops, bottoms, outerwear, footwear, accessories) and compatibility criteria.
- Provenance preservation: Extracted video concepts retain original source identifiers,
  channel metadata, timestamps, URLs, thumbnails, and engagement statistics.
- Strict evidence threshold: When evidence is insufficient or general, returns an
  empty tuple `()`. NEVER uses an LLM to invent trend labels, categories, or metrics.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from app.domain.ports.source_adapter import RawSourceRecord


@dataclass(frozen=True)
class ConceptDefinition:
    """Configuration-driven vocabulary entry for a fashion concept."""

    concept_id: str
    canonical_name: str
    category: str
    compatible_subcategories: tuple[str, ...]
    attribute_criteria: dict[str, Any]
    patterns: tuple[re.Pattern, ...]
    negative_patterns: tuple[re.Pattern, ...] = ()
    description: str = ""


@dataclass(frozen=True)
class ExtractedFashionConcept:
    """One normalized fashion concept extracted from video content."""

    concept_id: str
    canonical_name: str
    category: str
    attributes: dict[str, Any]
    confidence: float
    matched_text: str
    matched_field: str  # "title", "description", "tags"


@dataclass(frozen=True)
class ExtractedVideoConcept:
    """One concept observation grounded in an authentic video source record."""

    concept_id: str
    canonical_name: str
    category: str
    attributes: dict[str, Any]
    confidence: float
    matched_text: str
    matched_field: str
    video_id: str
    channel_id: Optional[str]
    channel_title: str
    published_at: datetime
    video_url: str
    thumbnails: dict[str, str] = field(default_factory=dict)
    raw_source_record_id: Optional[UUID] = None
    source: str = "youtube_in"
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    comment_count: Optional[int] = None


def normalize_text(text: str) -> str:
    """NFC-normalize, lowercase, and collapse whitespace."""
    if not text:
        return ""
    norm = unicodedata.normalize("NFC", text)
    # Remove control characters
    cleaned = "".join(ch for ch in norm if unicodedata.category(ch) != "Cc")
    return " ".join(cleaned.lower().split())


# ---------------------------------------------------------------------------
# Configuration-Driven Vocabulary Definitions
# ---------------------------------------------------------------------------

VOCABULARY: tuple[ConceptDefinition, ...] = (
    ConceptDefinition(
        concept_id="oversized_shirts",
        canonical_name="Oversized Shirts",
        category="tops",
        compatible_subcategories=("shirt", "shirts", "button-down", "tee", "t-shirt", "tshirt", "t-shirts", "overshirt"),
        attribute_criteria={"fit": "oversized", "silhouette": "relaxed"},
        patterns=(
            re.compile(r"\b(oversized|baggy|loose|relaxed)\s+(shirt|shirts|button[\s-]down|tee|tees|t[\s-]shirt|t[\s-]shirts|overshirt|overshirts)\b", re.IGNORECASE),
            re.compile(r"\boversized\s+t-?shirt\b", re.IGNORECASE),
            re.compile(r"\bbaggy\s+tee\b", re.IGNORECASE),
        ),
        negative_patterns=(
            re.compile(r"\b(tight|slim[\s-]fit|skinny)\b", re.IGNORECASE),
        ),
        description="Relaxed or exaggerated volume shirts, button-downs, and tees",
    ),
    ConceptDefinition(
        concept_id="wide_leg_trousers",
        canonical_name="Wide-leg Trousers",
        category="bottoms",
        compatible_subcategories=("trousers", "pants", "bottoms", "slacks", "chinos"),
        attribute_criteria={"fit": "wide-leg", "silhouette": "wide"},
        patterns=(
            re.compile(r"\b(wide[\s-]leg|baggy|relaxed[\s-]fit|flared|wide[\s-]cut)\s+(trousers|pants|pant|bottoms|slacks|chinos)\b", re.IGNORECASE),
            re.compile(r"\bwide[\s-]leg\s+(denim|jeans)\b", re.IGNORECASE),
            re.compile(r"\bwide[\s-]leg\b", re.IGNORECASE),
        ),
        negative_patterns=(
            re.compile(r"\b(skinny|slim[\s-]fit|tapered|leggings)\b", re.IGNORECASE),
        ),
        description="Relaxed and wide-silhouette trousers and casual pants",
    ),
    ConceptDefinition(
        concept_id="cargo_trousers",
        canonical_name="Cargo Trousers",
        category="bottoms",
        compatible_subcategories=("cargo", "cargoes", "cargos", "trousers", "pants", "bottoms"),
        attribute_criteria={"style_tags": ("cargo", "utility")},
        patterns=(
            re.compile(r"\b(cargo|combat|utility|parachute)\s+(trousers|pants|pant|bottoms)\b", re.IGNORECASE),
            re.compile(r"\b(cargos|cargoes|cargo\s+pants|cargo\s+trousers)\b", re.IGNORECASE),
            re.compile(r"\bparachute\s+pants\b", re.IGNORECASE),
        ),
        negative_patterns=(),
        description="Utility cargo and multi-pocket combat trousers",
    ),
    ConceptDefinition(
        concept_id="linen_shirts",
        canonical_name="Linen Shirts",
        category="tops",
        compatible_subcategories=("shirt", "shirts", "button-down", "top", "tops", "kurta"),
        attribute_criteria={"material": "linen"},
        patterns=(
            re.compile(r"\b(pure\s+linen|100%\s+linen|organic\s+linen|linen)\s+(shirt|shirts|button[\s-]down|overshirt|top|tops|kurta)\b", re.IGNORECASE),
            re.compile(r"\blinen\s+cuban\s+collar\b", re.IGNORECASE),
        ),
        negative_patterns=(
            re.compile(r"\b(table\s+linen|bed\s+linen|linen\s+tablecloth|linen\s+curtains|linen\s+sheets)\b", re.IGNORECASE),
        ),
        description="Breathable pure and blended linen shirts and resort tops",
    ),
    ConceptDefinition(
        concept_id="denim_jackets",
        canonical_name="Denim Jackets",
        category="outerwear",
        compatible_subcategories=("jacket", "jackets", "outerwear", "trucker", "shacket"),
        attribute_criteria={"material": "denim"},
        patterns=(
            re.compile(r"\b(denim|jean)\s+(jacket|jackets|outerwear|trucker|shacket)\b", re.IGNORECASE),
            re.compile(r"\btrucker\s+jacket\b", re.IGNORECASE),
            re.compile(r"\bjean\s+jacket\b", re.IGNORECASE),
        ),
        negative_patterns=(),
        description="Classic, trucker, and oversized denim jackets and outerwear",
    ),
    ConceptDefinition(
        concept_id="minimalist_sneakers",
        canonical_name="Minimalist Sneakers",
        category="footwear",
        compatible_subcategories=("sneakers", "shoes", "trainers", "kicks", "footwear"),
        attribute_criteria={"style_tags": ("minimalist", "clean")},
        patterns=(
            re.compile(r"\b(minimalist|clean|low[\s-]profile|minimal)\s+(sneakers|sneaker|shoes|kicks|trainers)\b", re.IGNORECASE),
            re.compile(r"\bwhite\s+(sneakers|sneaker|trainers)\b", re.IGNORECASE),
            re.compile(r"\bclassic\s+leather\s+sneakers\b", re.IGNORECASE),
        ),
        negative_patterns=(
            re.compile(r"\b(hiking\s+boots|chunky\s+dad\s+shoes)\b", re.IGNORECASE),
        ),
        description="Clean, low-profile and understated leather or canvas sneakers",
    ),
)


class FashionConceptExtractor:
    """Pure domain service for extracting normalized fashion concepts."""

    def __init__(self, vocabulary: Sequence[ConceptDefinition] = VOCABULARY) -> None:
        self._vocabulary = tuple(vocabulary)

    def extract_from_text(
        self,
        *,
        title: str,
        description: Optional[str] = None,
        tags: Sequence[str] = (),
    ) -> tuple[ExtractedFashionConcept, ...]:
        """Extract concepts deterministically across title, tags, and description.

        Hierarchy & Weights:
        - Title match: 1.0 confidence (primary creative intent).
        - Tag match: 0.85 confidence (explicit creator metadata).
        - Description match: 0.70 confidence (body copy context).
        """
        norm_title = normalize_text(title)
        norm_desc = normalize_text(description or "")
        norm_tags = [normalize_text(t) for t in tags if t]

        extracted: dict[str, ExtractedFashionConcept] = {}

        for defn in self._vocabulary:
            # Check negative patterns first against all text
            has_negative = False
            for neg_pat in defn.negative_patterns:
                if neg_pat.search(norm_title) or neg_pat.search(norm_desc):
                    has_negative = True
                    break
            if has_negative:
                continue

            matched_in_title = False
            matched_term = ""
            for pat in defn.patterns:
                m = pat.search(norm_title)
                if m:
                    matched_in_title = True
                    matched_term = m.group(0)
                    break

            if matched_in_title:
                extracted[defn.concept_id] = ExtractedFashionConcept(
                    concept_id=defn.concept_id,
                    canonical_name=defn.canonical_name,
                    category=defn.category,
                    attributes=defn.attribute_criteria,
                    confidence=1.0,
                    matched_text=matched_term,
                    matched_field="title",
                )
                continue

            # Check tags
            matched_in_tags = False
            for tag in norm_tags:
                for pat in defn.patterns:
                    m = pat.search(tag)
                    if m:
                        matched_in_tags = True
                        matched_term = m.group(0)
                        break
                if matched_in_tags:
                    break

            if matched_in_tags:
                extracted[defn.concept_id] = ExtractedFashionConcept(
                    concept_id=defn.concept_id,
                    canonical_name=defn.canonical_name,
                    category=defn.category,
                    attributes=defn.attribute_criteria,
                    confidence=0.85,
                    matched_text=matched_term,
                    matched_field="tags",
                )
                continue

            # Check description
            if norm_desc:
                matched_in_desc = False
                for pat in defn.patterns:
                    m = pat.search(norm_desc)
                    if m:
                        matched_in_desc = True
                        matched_term = m.group(0)
                        break

                if matched_in_desc:
                    extracted[defn.concept_id] = ExtractedFashionConcept(
                        concept_id=defn.concept_id,
                        canonical_name=defn.canonical_name,
                        category=defn.category,
                        attributes=defn.attribute_criteria,
                        confidence=0.70,
                        matched_text=matched_term,
                        matched_field="description",
                    )

        # Return sorted deterministically by concept_id
        return tuple(extracted[k] for k in sorted(extracted))

    def extract_from_raw_record(
        self, record: RawSourceRecord, raw_id: Optional[UUID] = None
    ) -> tuple[ExtractedVideoConcept, ...]:
        """Extract concepts from a YouTube raw source record, preserving provenance."""
        payload = record.payload if isinstance(record.payload, dict) else {}
        title = str(payload.get("title") or "")
        description = str(payload.get("description") or "")
        tags = payload.get("tags") or ()
        if isinstance(tags, str):
            tags = [tags]

        extracted = self.extract_from_text(title=title, description=description, tags=tags)
        if not extracted:
            return ()

        video_id = str(payload.get("videoId") or record.source_record_id or "").strip()
        channel_id = payload.get("channelId")
        channel_title = str(payload.get("channelTitle") or "")
        published_at = record.source_timestamp
        if not published_at:
            # If source_timestamp not set on record, attempt to parse publishedAt
            pub_str = payload.get("publishedAt")
            if pub_str and isinstance(pub_str, str):
                from app.infrastructure.external.youtube_source import parse_youtube_timestamp
                published_at = parse_youtube_timestamp(pub_str)

        if not published_at:
            # Without an authentic publication timestamp, we cannot establish a time window
            return ()

        video_url = str(payload.get("videoUrl") or f"https://www.youtube.com/watch?v={video_id}")
        thumbnails = payload.get("thumbnails") or {}
        if not isinstance(thumbnails, dict):
            thumbnails = {}

        # Extract statistics if present
        view_count: Optional[int] = None
        like_count: Optional[int] = None
        comment_count: Optional[int] = None
        stats = payload.get("statistics")
        if isinstance(stats, dict):
            if "viewCount" in stats and stats["viewCount"] is not None:
                try:
                    view_count = int(stats["viewCount"])
                except (ValueError, TypeError):
                    view_count = None
            if "likeCount" in stats and stats["likeCount"] is not None:
                try:
                    like_count = int(stats["likeCount"])
                except (ValueError, TypeError):
                    like_count = None
            if "commentCount" in stats and stats["commentCount"] is not None:
                try:
                    comment_count = int(stats["commentCount"])
                except (ValueError, TypeError):
                    comment_count = None

        return tuple(
            ExtractedVideoConcept(
                concept_id=c.concept_id,
                canonical_name=c.canonical_name,
                category=c.category,
                attributes=c.attributes,
                confidence=c.confidence,
                matched_text=c.matched_text,
                matched_field=c.matched_field,
                video_id=video_id,
                channel_id=channel_id,
                channel_title=channel_title,
                published_at=published_at,
                video_url=video_url,
                thumbnails=thumbnails,
                raw_source_record_id=raw_id,
                source=record.source,
                view_count=view_count,
                like_count=like_count,
                comment_count=comment_count,
            )
            for c in extracted
        )
