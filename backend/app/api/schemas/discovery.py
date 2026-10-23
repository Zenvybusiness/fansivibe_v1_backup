"""Wire schemas for Fansivibe Unified Discovery API (TASK DISCOVERY-05).

Defines typed request and response DTOs for:
- `GET /v1/discovery/for-you` (Personalized catalog recommendations)
- `GET /v1/discovery/looks/complete` (Multi-category complete looks)
- `GET /v1/discovery/trending` (Supported catalog trend intelligence)

Invariants:
- All keys follow camelCase JSON serialization (API-19).
- Explicit response models for all endpoints.
- Stable identifiers (UUIDs for products/items, deterministic strings for looks).
- Transparent representation of score breakdowns, grounded explanations,
  neutral dimensions, synthetic fixtures, and unavailable consumer demand.
- Catalog spending is strictly separated from already-owned wardrobe items.
- No direct exposure of internal database models or credentials.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.schemas.trend_analysis import TrendSignalSchema


# ---------------------------------------------------------------------------
# 1. For You Personalization Schemas
# ---------------------------------------------------------------------------


class ProductScoreBreakdownSchema(BaseModel):
    """Transparent breakdown of how candidate relevance score was computed."""

    preferenceMatch: float = Field(
        ge=0.0, le=40.0, description="Explicit preference match points (0–40)"
    )
    styleProfileMatch: float = Field(
        ge=0.0, le=25.0, description="Style profile & aesthetic points (0–25)"
    )
    wardrobeComplementarity: float = Field(
        ge=0.0, le=20.0, description="Wardrobe palette and gap-filling points (0–20)"
    )
    budgetAvailability: float = Field(
        ge=0.0, le=15.0, description="Pricing & in-stock availability points (0–15)"
    )
    totalScore: float = Field(
        ge=0.0, le=100.0, description="Total personalization relevance score (0–100)"
    )
    matchReasons: list[str] = Field(
        default_factory=list, description="Specific matched attribute reasons"
    )
    neutralDimensions: list[str] = Field(
        default_factory=list,
        description="Dimensions without user preferences or unmapped data",
    )


class ProductExplanationSchema(BaseModel):
    """Grounded explanation for a personalized product recommendation."""

    summary: str = Field(description="Deterministic grounded explanation summary")
    reasons: list[str] = Field(
        default_factory=list, description="Auditable match reasons"
    )
    positiveEvidence: list[str] = Field(
        default_factory=list, description="Verified positive match evidence"
    )
    neutralDimensions: list[str] = Field(
        default_factory=list,
        description="Neutral unprovided dimensions without penalty",
    )
    isSyntheticFixture: bool = Field(
        description="True if item originates from synthetic test catalog"
    )
    provenance: str = Field(
        description="Source inventory provenance classification"
    )


class ProductRecommendationItemSchema(BaseModel):
    """One ranked personalized product recommendation."""

    id: UUID = Field(description="Stable product UUID")
    title: str = Field(description="Product title")
    brand: Optional[str] = Field(default=None, description="Product brand name")
    category: Optional[str] = Field(default=None, description="Canonical category")
    subcategory: Optional[str] = Field(
        default=None, description="Detailed subcategory"
    )
    price: Optional[float] = Field(default=None, description="Current price in INR")
    currency: Optional[str] = Field(default="INR", description="Currency code")
    availability: Optional[bool] = Field(
        default=None, description="Stock availability status"
    )
    imageUrls: list[str] = Field(
        default_factory=list, description="Product image URLs"
    )
    attributes: dict[str, Any] = Field(
        default_factory=dict, description="Verified raw product attributes"
    )
    ffoConcepts: list[str] = Field(
        default_factory=list, description="Verified FFO concept canonical IDs"
    )
    isSynthetic: bool = Field(default=False, description="True if marked synthetic")
    isFixture: bool = Field(default=False, description="True if marked fixture")
    score: float = Field(description="Personalization relevance score (0–100)")
    rank: int = Field(ge=1, description="Deterministic 1-indexed rank")
    scoreBreakdown: ProductScoreBreakdownSchema
    explanation: ProductExplanationSchema


class UserPersonalizationContextSummarySchema(BaseModel):
    """Summary of user personalization context applied to recommendation query."""

    isGuest: bool = Field(
        description="Whether this query ran in unauthenticated guest mode"
    )
    userId: Optional[UUID] = Field(
        default=None, description="Authenticated user ID, if authenticated"
    )
    displayName: Optional[str] = Field(
        default=None, description="User display name if authenticated"
    )
    hasWardrobe: bool = Field(
        default=False, description="Whether user has owned wardrobe items"
    )
    styleType: Optional[str] = Field(
        default=None, description="Style profile style type if configured"
    )


class ForYouDiscoveryResponse(BaseModel):
    """Paginated response envelope for personalized product recommendations."""

    items: list[ProductRecommendationItemSchema] = Field(
        default_factory=list, description="Ranked personalized products"
    )
    totalCount: int = Field(ge=0, description="Total eligible matching products")
    page: int = Field(ge=1, description="Current 1-indexed page")
    pageSize: int = Field(ge=1, description="Items per page")
    totalPages: int = Field(ge=0, description="Total pages available")
    hasNext: bool = Field(description="Whether a next page exists")
    hasPrev: bool = Field(description="Whether a previous page exists")
    isPersonalized: bool = Field(
        description="True if ranked with authenticated user profile/wardrobe signals"
    )
    appliedContext: UserPersonalizationContextSummarySchema


# ---------------------------------------------------------------------------
# 2. Complete Looks Schemas
# ---------------------------------------------------------------------------


class LookSlotItemSchema(BaseModel):
    """An item participating in an outfit slot (catalog product or wardrobe item)."""

    itemId: UUID = Field(
        description="Item UUID (product ID or wardrobe item ID)"
    )
    source: str = Field(description="'catalog' or 'wardrobe'")
    title: str = Field(description="Item title or wardrobe item name")
    category: str = Field(
        description="Slot category (tops, bottoms, footwear, etc.)"
    )
    brand: Optional[str] = Field(
        default=None, description="Brand name if catalog product"
    )
    subcategory: Optional[str] = Field(default=None, description="Subcategory")
    color: Optional[str] = Field(default=None, description="Item color")
    material: Optional[str] = Field(default=None, description="Item material")
    fit: Optional[str] = Field(default=None, description="Item fit")
    silhouette: Optional[str] = Field(default=None, description="Item silhouette")
    price: Optional[float] = Field(
        default=None,
        description="Catalog price in INR (0.0 for owned wardrobe items)",
    )
    currency: Optional[str] = Field(default="INR", description="Currency code")
    imageUrl: Optional[str] = Field(
        default=None, description="Product image URL if available"
    )
    isSynthetic: bool = Field(
        default=False, description="True if marked synthetic"
    )
    isFixture: bool = Field(default=False, description="True if marked fixture")
    ffoConcepts: list[str] = Field(
        default_factory=list, description="Mapped FFO concept canonical IDs"
    )


class CompleteLookScoreBreakdownSchema(BaseModel):
    """Transparent scoring breakdown for complete look compatibility."""

    categoryCompleteness: float = Field(
        ge=0.0, le=25.0, description="Core category & slot coverage points (0–25)"
    )
    colorHarmony: float = Field(
        ge=0.0, le=25.0, description="Palette coherence and neutral gate points (0–25)"
    )
    materialConsistency: float = Field(
        ge=0.0,
        le=20.0,
        description="Natural fiber synergy & seasonal intersection points (0–20)",
    )
    styleConceptMatch: float = Field(
        ge=0.0, le=15.0, description="Shared aesthetic / FFO concept points (0–15)"
    )
    silhouetteFormality: float = Field(
        ge=0.0,
        le=15.0,
        description="Formality consistency & volume balance points (0–15)",
    )
    totalScore: float = Field(
        ge=0.0, le=100.0, description="Total outfit compatibility score (0–100)"
    )
    reasons: list[str] = Field(
        default_factory=list, description="Verified compatibility reasons"
    )
    warnings: list[str] = Field(
        default_factory=list, description="Unresolved constraints or warnings"
    )


class CompleteLookExplanationSchema(BaseModel):
    """Grounded explanation for an assembled complete look."""

    summary: str = Field(
        description="Deterministic grounded look explanation summary"
    )
    reasons: list[str] = Field(
        default_factory=list, description="Compatibility reasons"
    )
    positiveEvidence: list[str] = Field(
        default_factory=list,
        description="Verified positive compatibility evidence",
    )
    neutralDimensions: list[str] = Field(
        default_factory=list, description="Neutral unprovided attribute dimensions"
    )
    warnings: list[str] = Field(
        default_factory=list, description="Unresolved outfit constraints"
    )
    isSyntheticFixture: bool = Field(
        description="True if outfit contains synthetic fixture items"
    )
    isWardrobeAware: bool = Field(
        description="True if outfit integrates owned wardrobe items"
    )


class CompleteLookSchema(BaseModel):
    """A fully assembled, compatible multi-category look."""

    lookId: str = Field(
        description="Deterministic look identifier (e.g. look_0123456789abcdef)"
    )
    slots: dict[str, LookSlotItemSchema] = Field(
        description="Slot assignments (e.g. top, bottom, footwear)"
    )
    totalCatalogPrice: float = Field(
        ge=0.0,
        description="Total price of catalog items in INR (excludes owned wardrobe items)",
    )
    currency: str = Field(default="INR", description="Currency code")
    compatibilityScore: float = Field(
        ge=0.0, le=100.0, description="Outfit compatibility score (0–100)"
    )
    compatibilityBreakdown: CompleteLookScoreBreakdownSchema
    compatibilityReasons: list[str] = Field(
        default_factory=list, description="Auditable compatibility reasons"
    )
    unresolvedConstraints: list[str] = Field(
        default_factory=list, description="Auditable unresolved constraints"
    )
    explanation: CompleteLookExplanationSchema
    isWardrobeAware: bool = Field(
        description="Whether look includes owned wardrobe items"
    )
    wardrobeItemCount: int = Field(
        ge=0, description="Count of owned wardrobe items in look"
    )
    catalogItemCount: int = Field(
        ge=0, description="Count of catalog items in look"
    )
    containsSyntheticFixtures: bool = Field(
        description="Whether any item is a synthetic fixture"
    )
    bundlePurchasable: bool = Field(
        default=False,
        description="Purchasable as complete bundle (False until verified bundle support exists)",
    )


class CompleteLooksDiscoveryResponse(BaseModel):
    """Response envelope for complete looks discovery."""

    looks: list[CompleteLookSchema] = Field(
        default_factory=list, description="Assembled complete looks"
    )
    totalLooks: int = Field(ge=0, description="Total complete looks assembled")
    targetOccasion: Optional[str] = Field(
        default=None, description="Requested target occasion"
    )
    targetAesthetic: Optional[str] = Field(
        default=None, description="Requested target aesthetic"
    )
    maxBudget: Optional[float] = Field(
        default=None, description="Maximum budget applied for catalog items"
    )
    isWardrobeAware: bool = Field(
        description="True if any look contains owned wardrobe items"
    )
    containsSyntheticFixtures: bool = Field(
        description="True if any look contains synthetic fixtures"
    )


# ---------------------------------------------------------------------------
# 3. Trending Intelligence Schemas
# ---------------------------------------------------------------------------


class DiscoveryTrendItemExplanationSchema(BaseModel):
    """Grounded explanation of catalog trend observation."""

    summary: str = Field(
        description="Grounded explanation of catalog trend observation"
    )
    evidenceType: str = Field(
        description="Evidence classification (catalog_activity)"
    )
    demandSignalAvailable: bool = Field(
        default=False, description="Consumer demand signal availability"
    )
    reasons: list[str] = Field(
        default_factory=list, description="Auditable evidence reasons"
    )


class MatchedProductSummarySchema(BaseModel):
    """Summary of a genuine catalog product matched to a trend concept."""

    productId: str = Field(description="Product UUID or external identifier")
    title: str = Field(description="Canonical product title")
    brand: Optional[str] = Field(default=None, description="Product brand")
    category: str = Field(description="Product category")
    price: Optional[float] = Field(default=None, description="Current price in INR")
    currency: Optional[str] = Field(default="INR", description="Currency code")
    availability: Optional[bool] = Field(default=None, description="In-stock availability")
    productUrl: Optional[str] = Field(default=None, description="Verified destination product URL")
    imageUrl: Optional[str] = Field(default=None, description="Product image URL")
    retailer: Optional[str] = Field(default=None, description="Retailer display name")
    matchScore: float = Field(ge=0.0, le=1.0, description="Product-to-concept match confidence")
    matchReasons: list[str] = Field(default_factory=list, description="Reasons for match")


class DiscoveryTrendItemSchema(BaseModel):
    """One concept's observation evidence for the discovery trending feed."""

    concept: str = Field(description="Normalized concept identifier")
    canonicalName: str = Field(description="Human-readable concept name")
    category: str = Field(description="Taxonomy category")
    evidenceType: str = Field(
        default="catalog_activity",
        description="Evidence type (catalog_activity)",
    )
    catalogActivityStatus: str = Field(
        description="Catalog observation stage (rising, plateau, declining, insufficient_evidence)"
    )
    observationCount: int = Field(
        ge=0, description="Total observations in window"
    )
    distinctProducts: int = Field(ge=0, description="Distinct products observed")
    distinctSources: int = Field(
        ge=0, description="Distinct sources observing concept"
    )
    firstObservedAt: str = Field(
        description="Earliest observation timestamp (ISO-8601)"
    )
    lastObservedAt: str = Field(
        description="Latest observation timestamp (ISO-8601)"
    )
    catalogGrowth: Optional[float] = Field(
        default=None,
        description="Product growth ratio across window halves (null if baseline=0)",
    )
    priceChangeRatio: Optional[float] = Field(
        default=None,
        description="Mean price change ratio (null if insufficient prices)",
    )
    inStockRatio: Optional[float] = Field(
        default=None, description="Mean in-stock ratio (null if unstated)"
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Data-quality confidence heuristic (0–1)"
    )
    strength: Optional[float] = Field(
        default=None, description="Signal strength magnitude"
    )
    fixtureDerived: bool = Field(
        description="True if observations derive from fixture/synthetic data"
    )
    publishable: bool = Field(
        description="True if eligible for published trend feed"
    )
    reasons: list[str] = Field(
        default_factory=list,
        description="Documented qualification or exclusion reasons",
    )
    signals: list[TrendSignalSchema] = Field(
        default_factory=list, description="Audited signal components"
    )
    directDemandAvailable: bool = Field(
        default=False,
        description="Direct consumer demand signal availability (always False)",
    )
    explanation: DiscoveryTrendItemExplanationSchema
    matchedProducts: list[MatchedProductSummarySchema] = Field(
        default_factory=list,
        description="Genuine catalog products matched to this trend concept (fixtures excluded)",
    )


class DiscoveryTrendingResponse(BaseModel):
    """Read-only trend intelligence for discovery feed."""

    windowStart: str = Field(description="Observation window start (ISO-8601)")
    windowEnd: str = Field(description="Observation window end (ISO-8601)")
    generatedAt: str = Field(
        description="Timestamp of trend analysis generation (ISO-8601)"
    )
    demandTrendStatus: str = Field(
        description="Overall consumer demand status (insufficient_evidence)"
    )
    evidenceType: str = Field(
        default="catalog_activity", description="Supported evidence type"
    )
    catalogActivityStatus: str = Field(
        description="Catalog observation state (observed / no_observations)"
    )
    directDemandAvailable: bool = Field(
        default=False,
        description="Always False until authorized demand provider is wired",
    )
    sourceCoverage: int = Field(
        ge=0, description="Number of distinct sources in observation history"
    )
    observationCount: int = Field(
        ge=0, description="Total observations analyzed"
    )
    insufficientEvidenceReason: Optional[str] = Field(
        default=None, description="Reason consumer demand trends are withheld"
    )
    confidenceInterpretation: str = Field(
        description="Interpretation of data-quality confidence metric"
    )
    limitations: list[str] = Field(
        default_factory=list,
        description="Truthful limitations of current trend intelligence",
    )
    items: list[DiscoveryTrendItemSchema] = Field(
        default_factory=list, description="Audited trend candidates"
    )


# ---------------------------------------------------------------------------
# Interaction Event Ingestion Schemas (DISCOVERY-10A)
# ---------------------------------------------------------------------------


class DiscoveryEventIngestItemSchema(BaseModel):
    """One interaction event in an ingress batch (DISCOVERY-10A)."""

    model_config = ConfigDict(extra="forbid")

    eventId: UUID = Field(
        description="Client-generated stable UUIDv4 event identifier"
    )
    eventType: str = Field(description="Event type name")
    targetType: str = Field(
        description="Target entity type ('product' or 'complete_look')"
    )
    targetId: str = Field(description="Target entity identifier")
    surface: str = Field(
        description="Discovery UI surface where interaction occurred"
    )
    position: Optional[int] = Field(
        default=None, description="Zero-indexed feed position (0–1000)"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Bounded event metadata"
    )
    occurredAt: datetime = Field(
        description="Client occurrence timestamp (ISO-8601 UTC)"
    )

    @model_validator(mode="before")
    @classmethod
    def reject_client_user_id(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "userId" in data or "user_id" in data:
                raise ValueError("Client cannot provide or override userId.")
        return data


class DiscoveryEventsBatchRequest(BaseModel):
    """Batch ingestion request for discovery interaction events."""

    model_config = ConfigDict(extra="forbid")

    guestSessionId: Optional[UUID] = Field(
        default=None,
        description="Client-generated UUIDv4 session ID for guest requests",
    )
    events: list[DiscoveryEventIngestItemSchema] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Batch of 1 to 50 interaction events",
    )

    @model_validator(mode="before")
    @classmethod
    def reject_client_user_id(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "userId" in data or "user_id" in data:
                raise ValueError("Client cannot provide or override userId.")
        return data


class DiscoveryEventAckSchema(BaseModel):
    """Per-event acknowledgement in an accepted batch response."""

    eventId: UUID = Field(description="Client event identifier")
    status: str = Field(
        description="Acceptance status: 'accepted' or 'acknowledged'"
    )
    replayed: bool = Field(
        description="True if identical event was previously persisted"
    )


class DiscoveryEventsIngestResponse(BaseModel):
    """Response returned upon successful acceptance of an event batch."""

    acceptedCount: int = Field(
        ge=0, description="Count of accepted/acknowledged events in this batch"
    )
    events: list[DiscoveryEventAckSchema] = Field(
        description="Per-event acknowledgement details"
    )


# ---------------------------------------------------------------------------
# Multi-Retailer Product Offer Schemas (DISCOVERY-10B-3)
# ---------------------------------------------------------------------------


class RetailerSummarySchema(BaseModel):
    """Public summary of a verified retailer/merchant."""

    id: UUID = Field(description="Retailer UUID")
    name: str = Field(description="Display name of retailer")
    slug: str = Field(description="Canonical retailer slug")
    domain: str = Field(description="Verified merchant website domain")


class ProductVariantSummarySchema(BaseModel):
    """Product variant attributes associated with an offer."""

    id: UUID = Field(description="Variant UUID")
    sku: Optional[str] = Field(default=None, description="Merchant SKU")
    gtin: Optional[str] = Field(default=None, description="Global Trade Item Number")
    size: Optional[str] = Field(default=None, description="Variant size")
    color: Optional[str] = Field(default=None, description="Variant color")
    attributes: dict[str, Any] = Field(
        default_factory=dict, description="Additional variant attributes"
    )


class ProductOfferItemSchema(BaseModel):
    """One verified commercial retailer offer for a canonical product."""

    id: UUID = Field(description="Stable offer UUID")
    retailer: RetailerSummarySchema = Field(description="Verified merchant information")
    price: float = Field(ge=0.0, description="Verified commercial price")
    originalPrice: Optional[float] = Field(
        default=None, ge=0.0, description="Original list/strikethrough price"
    )
    currency: str = Field(default="INR", description="Three-letter currency code")
    availability: bool = Field(description="Whether the product is orderable")
    inStock: bool = Field(description="Whether item is currently in-stock")
    productUrl: Optional[str] = Field(
        default=None, description="Direct merchant product URL"
    )
    redirectUrl: str = Field(
        description="Authorized server-mediated redirect endpoint for outbound purchase"
    )
    variant: Optional[ProductVariantSummarySchema] = Field(
        default=None, description="Variant details if known"
    )
    lastCheckedAt: Optional[str] = Field(
        default=None, description="ISO-8601 timestamp of last price verification"
    )
    isPriceFresh: bool = Field(
        default=True,
        description="True if price was verified within max freshness window (24h)",
    )
    freshnessStatus: str = Field(
        default="fresh",
        description="Price freshness classification: 'fresh', 'stale', or 'unverified'",
    )


class ProductOffersResponse(BaseModel):
    """Shopping comparison response containing verified retailer offers."""

    productId: UUID = Field(description="Canonical product UUID")
    title: str = Field(description="Canonical product title")
    brand: Optional[str] = Field(default=None, description="Product brand name")
    isSyntheticFixture: bool = Field(
        default=False,
        description="True if this is a synthetic demonstration fixture catalog item",
    )
    offersCount: int = Field(
        ge=0, description="Count of active verified retailer offers"
    )
    offers: list[ProductOfferItemSchema] = Field(
        default_factory=list, description="List of active verified commercial offers"
    )

