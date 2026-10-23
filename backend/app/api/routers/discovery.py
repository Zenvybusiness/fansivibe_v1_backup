"""Fansivibe Unified Discovery API — `/v1/discovery` (TASK DISCOVERY-05).

Provides stable, documented endpoints for:
- `GET /v1/discovery/for-you` (Personalized catalog recommendations)
- `GET /v1/discovery/looks/complete` (Multi-category complete looks)
- `GET /v1/discovery/trending` (Supported catalog trend intelligence)

Invariants:
- Grounded, deterministic explanations for all recommendations and looks.
- Strict owner-scoping: unauthenticated / guest contexts cannot query another user's
  profile, preferences, or wardrobe items.
- DEMAND_SIGNAL_AVAILABLE = False preserved: no fake popularity, bestselling, or viral signals.
- Missing attributes are honestly treated as neutral and never fabricated.
- Synthetic fixtures are explicitly labeled.
- Catalog spending is strictly separated from owned wardrobe item values.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import SQLAlchemyError

from app.config.settings import get_settings

from app.api.deps import (
    get_candidate_repository,
    get_current_user_id,
    get_discovery_event_repository,
    get_optional_user_id,
    get_trend_repository,
    get_user_state_repository,
    get_wardrobe_repository,
)
from app.api.errors import (
    ApiError,
    authentication_error,
    database_failure,
    not_found,
    validation,
)
from app.api.routers.trend_analysis import (
    _CONFIDENCE_INTERPRETATION,
    _LIMITATIONS,
    EVIDENCE_TYPE_CATALOG,
    _resolve_window,
)
from app.api.schemas.discovery import (
    CompleteLookExplanationSchema,
    CompleteLookSchema,
    CompleteLookScoreBreakdownSchema,
    CompleteLooksDiscoveryResponse,
    DiscoveryEventsBatchRequest,
    DiscoveryEventsIngestResponse,
    DiscoveryTrendItemExplanationSchema,
    DiscoveryTrendItemSchema,
    DiscoveryTrendingResponse,
    ForYouDiscoveryResponse,
    LookSlotItemSchema,
    MatchedProductSummarySchema,
    ProductExplanationSchema,
    ProductOfferItemSchema,
    ProductOffersResponse,
    ProductRecommendationItemSchema,
    ProductScoreBreakdownSchema,
    ProductVariantSummarySchema,
    RetailerSummarySchema,
    UserPersonalizationContextSummarySchema,
)
from app.api.schemas.trend_analysis import TrendSignalSchema
from app.application.candidate_retrieval import RetrieveProductCandidates
from app.application.complete_looks import AssembleCompleteLooks
from app.application.discovery_events import (
    IngestDiscoveryEvents,
    compute_payload_hash,
)
from app.application.for_you import PersonalizeForYou
from app.domain.ports.repositories import DiscoveryEventRepository
from app.application.trends import AnalyzeTrends, TrendConfig
from app.domain.ports.repositories import ProductFilterCriteria
from app.domain.services.candidate_filters import validate_criteria, validate_pagination
from app.domain.services.grounded_explanations import (
    format_complete_look_explanation,
    format_product_recommendation_explanation,
    format_trend_candidate_explanation,
)
from app.domain.services.personalization import PersonalizationPreferences
from app.domain.services.trends import DEMAND_SIGNAL_AVAILABLE

logger = logging.getLogger("fansivibe.discovery")

router = APIRouter(prefix="/v1/discovery", tags=["discovery"])


# ---------------------------------------------------------------------------
# Helper: Routable Image URL Resolution
# ---------------------------------------------------------------------------


def _resolve_image_urls(
    image_urls: list[str] | tuple[str, ...],
    request: Optional[Request] = None,
) -> list[str]:
    """Resolve image URLs to fully qualified, routable URLs without hardcoding localhost."""
    settings = get_settings()
    base = settings.static_asset_base_url
    if not base and request:
        base = str(request.base_url).rstrip("/")
    if not base:
        base = ""
    resolved: list[str] = []
    for u in image_urls:
        if isinstance(u, str) and u.startswith("/"):
            resolved.append(f"{base}{u}")
        else:
            resolved.append(u)
    return resolved


def _resolve_single_image_url(
    image_url: Optional[str],
    request: Optional[Request] = None,
) -> Optional[str]:
    """Resolve a single image URL or return None."""
    if not image_url:
        return None
    return _resolve_image_urls([image_url], request)[0]


# ---------------------------------------------------------------------------
# A. GET /v1/discovery/for-you
# ---------------------------------------------------------------------------


@router.get(
    "/for-you",
    response_model=ForYouDiscoveryResponse,
    summary="Personalized Catalog Recommendations",
    description=(
        "Returns personalized catalog recommendations ranked deterministically by relevance "
        "to the authenticated user's verified preferences, style profile, and wardrobe context. "
        "Supports safe guest access with catalog-only fallback."
    ),
)
def get_for_you_recommendations(
    page: int = Query(default=1, ge=1, description="1-indexed page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    categories: Optional[list[str]] = Query(
        default=None, description="Hard category filter (e.g. tops, bottoms)"
    ),
    exclude_categories: Optional[list[str]] = Query(
        default=None, description="Categories to exclude"
    ),
    brands: Optional[list[str]] = Query(
        default=None, description="Hard brand filter"
    ),
    exclude_brands: Optional[list[str]] = Query(
        default=None, description="Brands to exclude"
    ),
    min_price: Optional[float] = Query(
        default=None, ge=0, description="Minimum price in INR"
    ),
    max_price: Optional[float] = Query(
        default=None, ge=0, description="Maximum price in INR"
    ),
    currency: Optional[str] = Query(default="INR", description="Currency code"),
    colors: Optional[list[str]] = Query(default=None, description="Color filters"),
    materials: Optional[list[str]] = Query(
        default=None, description="Material filters"
    ),
    fits: Optional[list[str]] = Query(default=None, description="Fit filters"),
    silhouettes: Optional[list[str]] = Query(
        default=None, description="Silhouette filters"
    ),
    in_stock_only: Optional[bool] = Query(
        default=None, description="Filter for in-stock products only"
    ),
    include_synthetic: bool = Query(
        default=True, description="Include synthetic test fixture products"
    ),
    is_guest: bool = Query(
        default=False, description="Force unauthenticated guest access"
    ),
    q: Optional[str] = Query(
        default=None,
        max_length=200,
        description="Optional text search query to filter candidates across title, brand, category, subcategory",
    ),
    user_id: Optional[UUID] = Depends(get_optional_user_id),
    candidate_repo=Depends(get_candidate_repository),
    user_state_repo=Depends(get_user_state_repository),
    wardrobe_repo=Depends(get_wardrobe_repository),
    request: Request = None,  # type: ignore[assignment]
) -> ForYouDiscoveryResponse:
    """Retrieve and rank personalized product candidates."""
    try:
        validate_pagination(page, page_size)
    except ValueError as exc:
        raise validation([{"field": "pagination", "error": str(exc)}])

    clean_q = q.strip() if q and q.strip() else None
    criteria = ProductFilterCriteria(
        categories=tuple(categories) if categories else None,
        exclude_categories=tuple(exclude_categories) if exclude_categories else None,
        brands=tuple(brands) if brands else None,
        exclude_brands=tuple(exclude_brands) if exclude_brands else None,
        min_price=min_price,
        max_price=max_price,
        currency=currency,
        colors=tuple(colors) if colors else None,
        materials=tuple(materials) if materials else None,
        fits=tuple(fits) if fits else None,
        silhouettes=tuple(silhouettes) if silhouettes else None,
        in_stock_only=in_stock_only,
        include_synthetic=include_synthetic,
        q=clean_q,
    )
    try:
        validate_criteria(criteria)
    except ValueError as exc:
        raise validation([{"field": "criteria", "error": str(exc)}])

    effective_is_guest = is_guest or (user_id is None)
    effective_user_id = None if effective_is_guest else user_id

    retrieval = RetrieveProductCandidates(candidate_repo)
    use_case = PersonalizeForYou(
        candidate_retrieval=retrieval,
        user_state_repo=user_state_repo,
        wardrobe_repo=wardrobe_repo,
    )

    result = use_case(
        user_id=effective_user_id,
        criteria=criteria,
        page=page,
        page_size=page_size,
        is_guest=effective_is_guest,
    )

    items: list[ProductRecommendationItemSchema] = []
    for cand in result.items:
        prod = cand.product
        breakdown = cand.breakdown
        explanation = format_product_recommendation_explanation(
            cand, result.applied_context
        )

        score_breakdown_schema = ProductScoreBreakdownSchema(
            preferenceMatch=breakdown.preference_match,
            styleProfileMatch=breakdown.style_profile_match,
            wardrobeComplementarity=breakdown.wardrobe_complementarity,
            budgetAvailability=breakdown.budget_availability,
            totalScore=breakdown.total_score,
            matchReasons=list(breakdown.match_reasons),
            neutralDimensions=list(breakdown.neutral_dimensions),
        )

        explanation_schema = ProductExplanationSchema(
            summary=explanation.summary,
            reasons=list(explanation.reasons),
            positiveEvidence=list(explanation.positive_evidence),
            neutralDimensions=list(explanation.neutral_dimensions),
            isSyntheticFixture=explanation.is_synthetic_fixture,
            provenance=explanation.provenance,
        )

        raw_attrs = dict(prod.attributes or {})
        ffo_concepts = list(sorted(cand.ffo_bridge.canonical_ids))

        items.append(
            ProductRecommendationItemSchema(
                id=prod.id,
                title=prod.title,
                brand=prod.brand,
                category=prod.category,
                subcategory=prod.subcategory,
                price=prod.price,
                currency=prod.currency or "INR",
                availability=prod.availability,
                imageUrls=_resolve_image_urls(prod.image_urls, request),
                attributes=raw_attrs,
                ffoConcepts=ffo_concepts,
                isSynthetic=prod.is_synthetic,
                isFixture=prod.is_fixture,
                score=cand.score,
                rank=cand.rank,
                scoreBreakdown=score_breakdown_schema,
                explanation=explanation_schema,
            )
        )

    context_summary = UserPersonalizationContextSummarySchema(
        isGuest=result.applied_context.is_guest,
        userId=result.applied_context.user_id,
        displayName=result.applied_context.display_name,
        hasWardrobe=result.applied_context.wardrobe_context.has_wardrobe,
        styleType=result.applied_context.style_profile.get("style_type"),
    )

    return ForYouDiscoveryResponse(
        items=items,
        totalCount=result.total_count,
        page=result.page,
        pageSize=result.page_size,
        totalPages=result.total_pages,
        hasNext=result.has_next,
        hasPrev=result.has_prev,
        isPersonalized=not result.applied_context.is_guest,
        appliedContext=context_summary,
    )


# ---------------------------------------------------------------------------
# B. GET /v1/discovery/looks/complete
# ---------------------------------------------------------------------------


@router.get(
    "/looks/complete",
    response_model=CompleteLooksDiscoveryResponse,
    summary="Complete Outfit Combinations",
    description=(
        "Returns compatible, multi-category outfit combinations assembled from catalog products "
        "and, when authorized and enabled, owned wardrobe items. Catalog spending is strictly "
        "enforced against the budget constraint while owned wardrobe items cost ₹0 towards catalog spend."
    ),
)
def get_complete_looks(
    limit: int = Query(
        default=10, ge=1, le=50, description="Max complete looks to return"
    ),
    max_budget: Optional[float] = Query(
        default=None,
        ge=0,
        description="Maximum total price for catalog items in INR",
    ),
    target_occasion: Optional[str] = Query(
        default=None,
        max_length=100,
        description="Target occasion (e.g. casual, formal, business-casual)",
    ),
    target_aesthetic: Optional[str] = Query(
        default=None,
        max_length=100,
        description="Target aesthetic (e.g. minimalist, streetwear, classic)",
    ),
    anchor_product_id: Optional[UUID] = Query(
        default=None, description="Anchor outfit generation to a specific catalog product"
    ),
    anchor_wardrobe_item_id: Optional[UUID] = Query(
        default=None,
        description="Anchor outfit generation to an owned wardrobe item (requires authentication)",
    ),
    allow_wardrobe: bool = Query(
        default=True,
        description="Whether to incorporate owned wardrobe items when available",
    ),
    include_synthetic: bool = Query(
        default=True, description="Include synthetic test fixture products"
    ),
    user_id: Optional[UUID] = Depends(get_optional_user_id),
    candidate_repo=Depends(get_candidate_repository),
    wardrobe_repo=Depends(get_wardrobe_repository),
    request: Request = None,  # type: ignore[assignment]
) -> CompleteLooksDiscoveryResponse:
    """Assemble compatible complete looks."""
    # Guard: anchoring to a wardrobe item requires an authenticated user
    if anchor_wardrobe_item_id is not None and user_id is None:
        raise authentication_error()

    if anchor_product_id is not None and anchor_wardrobe_item_id is not None:
        raise validation(
            [
                {
                    "field": "anchor",
                    "error": "Provide either anchor_product_id or anchor_wardrobe_item_id, not both",
                }
            ]
        )

    retrieval = RetrieveProductCandidates(candidate_repo)
    use_case = AssembleCompleteLooks(
        candidate_retrieval=retrieval,
        wardrobe_repo=wardrobe_repo,
    )

    try:
        result = use_case(
            user_id=user_id,
            anchor_wardrobe_item_id=anchor_wardrobe_item_id,
            anchor_product_id=anchor_product_id,
            target_occasion=target_occasion,
            target_aesthetic=target_aesthetic,
            max_budget=max_budget,
            limit=limit,
            allow_wardrobe=allow_wardrobe,
            include_synthetic=include_synthetic,
        )
    except ValueError as exc:
        err_msg = str(exc)
        if (
            "not found in user's wardrobe" in err_msg
            or ("Catalog product" in err_msg and "not found" in err_msg)
        ):
            raise not_found()
        raise validation([{"field": "looks", "error": err_msg}])

    looks_schemas: list[CompleteLookSchema] = []
    for look in result.looks:
        explanation = format_complete_look_explanation(look)

        slots_schemas: dict[str, LookSlotItemSchema] = {}
        for slot_name, item in look.slots.items():
            slots_schemas[slot_name] = LookSlotItemSchema(
                itemId=item.item_id,
                source=item.source,
                title=item.title,
                category=item.category,
                brand=item.brand,
                subcategory=item.subcategory,
                color=item.color,
                material=item.material,
                fit=item.fit,
                silhouette=item.silhouette,
                price=item.price,
                currency=item.currency or "INR",
                imageUrl=_resolve_single_image_url(item.image_url, request),
                isSynthetic=item.is_synthetic,
                isFixture=item.is_fixture,
                ffoConcepts=list(item.ffo_concepts),
            )

        bd = look.compatibility_breakdown
        breakdown_schema = CompleteLookScoreBreakdownSchema(
            categoryCompleteness=bd.category_completeness,
            colorHarmony=bd.color_harmony,
            materialConsistency=bd.material_consistency,
            styleConceptMatch=bd.style_concept_match,
            silhouetteFormality=bd.silhouette_formality,
            totalScore=bd.total_score,
            reasons=list(bd.reasons),
            warnings=list(bd.warnings),
        )

        explanation_schema = CompleteLookExplanationSchema(
            summary=explanation.summary,
            reasons=list(explanation.reasons),
            positiveEvidence=list(explanation.positive_evidence),
            neutralDimensions=list(explanation.neutral_dimensions),
            warnings=list(explanation.warnings),
            isSyntheticFixture=explanation.is_synthetic_fixture,
            isWardrobeAware=explanation.is_wardrobe_aware,
        )

        looks_schemas.append(
            CompleteLookSchema(
                lookId=look.look_id,
                slots=slots_schemas,
                totalCatalogPrice=look.total_catalog_price,
                currency=look.currency,
                compatibilityScore=look.compatibility_score,
                compatibilityBreakdown=breakdown_schema,
                compatibilityReasons=list(look.compatibility_reasons),
                unresolvedConstraints=list(look.unresolved_constraints),
                explanation=explanation_schema,
                isWardrobeAware=look.is_wardrobe_aware,
                wardrobeItemCount=look.wardrobe_item_count,
                catalogItemCount=look.catalog_item_count,
                containsSyntheticFixtures=look.contains_synthetic_fixtures,
                bundlePurchasable=False,
            )
        )

    return CompleteLooksDiscoveryResponse(
        looks=looks_schemas,
        totalLooks=result.total_looks,
        targetOccasion=result.target_occasion,
        targetAesthetic=result.target_aesthetic,
        maxBudget=result.max_budget,
        isWardrobeAware=result.is_wardrobe_aware,
        containsSyntheticFixtures=any(
            l.contains_synthetic_fixtures for l in result.looks
        ),
    )


# ---------------------------------------------------------------------------
# C. GET /v1/discovery/trending
# ---------------------------------------------------------------------------


@router.get(
    "/trending",
    response_model=DiscoveryTrendingResponse,
    summary="Discovery Trending Intelligence",
    description=(
        "Exposes supported catalog observation intelligence from the D6/D7 trend engine. "
        "Catalog activity and source coverage are reported honestly as catalog facts. "
        "Consumer demand trends remain unavailable (DEMAND_SIGNAL_AVAILABLE = False) "
        "and missing metrics remain null."
    ),
)
def get_discovery_trending(
    window_start: Optional[datetime] = Query(
        default=None,
        description="Observation window start (ISO-8601 with timezone)",
    ),
    window_end: Optional[datetime] = Query(
        default=None,
        description="Observation window end (ISO-8601 with timezone)",
    ),
    limit: int = Query(
        default=20, ge=1, le=50, description="Max trending candidates to return"
    ),
    category: Optional[str] = Query(
        default=None, description="Optional category filter (e.g. outerwear, tops)"
    ),
    user_id: UUID = Depends(get_current_user_id),
    repository=Depends(get_trend_repository),
) -> DiscoveryTrendingResponse:
    """Analyze catalog observation history for trend candidates."""
    del user_id  # Authentication required; trend intelligence is system-wide
    now = datetime.now(timezone.utc)
    start, end = _resolve_window(window_start, window_end, now=now)

    try:
        analysis = AnalyzeTrends(repository=repository)(
            TrendConfig(window_start=start, window_end=end)
        )
    except SQLAlchemyError:
        raise database_failure()

    candidates = list(analysis.candidates)
    if category:
        wanted_cat = category.strip().lower()
        candidates = [c for c in candidates if c.category.strip().lower() == wanted_cat]

    items: list[DiscoveryTrendItemSchema] = []
    for cand in candidates[:limit]:
        explanation = format_trend_candidate_explanation(cand)

        explanation_schema = DiscoveryTrendItemExplanationSchema(
            summary=explanation.summary,
            evidenceType=explanation.evidence_type,
            demandSignalAvailable=explanation.demand_signal_available,
            reasons=list(explanation.reasons),
        )

        signal_schemas = [
            TrendSignalSchema(
                metric=s.name,
                kind=s.kind,
                available=s.available,
                value=s.value,
                unit=s.unit,
                detail=s.detail,
            )
            for s in cand.signals
        ]

        items.append(
            DiscoveryTrendItemSchema(
                concept=cand.concept,
                canonicalName=cand.canonical_name,
                category=cand.category,
                evidenceType=EVIDENCE_TYPE_CATALOG,
                catalogActivityStatus=cand.stage,
                observationCount=cand.observation_count,
                distinctProducts=cand.distinct_products,
                distinctSources=cand.distinct_sources,
                firstObservedAt=cand.first_observed_at.isoformat(),
                lastObservedAt=cand.last_observed_at.isoformat(),
                catalogGrowth=cand.catalog_growth,
                priceChangeRatio=cand.price_change_ratio,
                inStockRatio=cand.in_stock_ratio,
                confidence=cand.confidence,
                strength=cand.strength,
                fixtureDerived=cand.is_fixture,
                publishable=cand.publishable,
                reasons=list(cand.reasons),
                signals=signal_schemas,
                directDemandAvailable=DEMAND_SIGNAL_AVAILABLE,
                explanation=explanation_schema,
            )
        )

    return DiscoveryTrendingResponse(
        windowStart=start.isoformat(),
        windowEnd=end.isoformat(),
        generatedAt=now.isoformat(),
        demandTrendStatus=analysis.demand_trend_status,
        evidenceType=EVIDENCE_TYPE_CATALOG,
        catalogActivityStatus="observed" if items else "no_observations",
        directDemandAvailable=DEMAND_SIGNAL_AVAILABLE,
        sourceCoverage=analysis.source_coverage,
        observationCount=analysis.observation_count,
        insufficientEvidenceReason=analysis.demand_insufficient_reason,
        confidenceInterpretation=_CONFIDENCE_INTERPRETATION,
        limitations=list(_LIMITATIONS),
        items=items,
    )


@router.post(
    "/events",
    status_code=202,
    response_model=DiscoveryEventsIngestResponse,
    summary="Ingest discovery interaction events batch",
    description=(
        "Accepts a batch of 1 to 50 interaction events from authenticated users "
        "or guest sessions. Returns HTTP 202 with explicit per-event acknowledgement."
    ),
)
def ingest_discovery_events(
    request: DiscoveryEventsBatchRequest,
    user_id: Optional[UUID] = Depends(get_optional_user_id),
    event_repo: DiscoveryEventRepository = Depends(
        get_discovery_event_repository
    ),
) -> DiscoveryEventsIngestResponse:
    use_case = IngestDiscoveryEvents(event_repo)
    return use_case(request=request, user_id=user_id)


# ---------------------------------------------------------------------------
# D. Multi-Retailer Product Offers & Outbound Redirect (DISCOVERY-10B-3)
# ---------------------------------------------------------------------------


@router.get(
    "/products/{product_id}/offers",
    response_model=ProductOffersResponse,
    summary="Get verified retailer offers for a product",
    description=(
        "Returns active, verified retailer offers for a canonical product with pricing, "
        "currency, availability, variants, and freshness metadata. If the product is a "
        "synthetic fixture or has no commercial listings, an honest empty response is returned."
    ),
)
def get_product_offers(
    product_id: UUID = Path(..., description="Canonical product UUID"),
    candidate_repo=Depends(get_candidate_repository),
) -> ProductOffersResponse:
    """Retrieve verified retailer offers for a canonical product."""
    product = candidate_repo.get_by_id(product_id)
    if product is None:
        raise not_found()

    is_fixture = bool(product.is_fixture or product.is_synthetic)
    if is_fixture:
        # Development fixtures have no real commercial retailer inventory
        return ProductOffersResponse(
            productId=product.id,
            title=product.title,
            brand=product.brand,
            isSyntheticFixture=True,
            offersCount=0,
            offers=[],
        )

    offers = candidate_repo.get_product_offers(product_id)
    now = datetime.now(timezone.utc)
    max_price_age = timedelta(hours=24)

    offer_schemas: list[ProductOfferItemSchema] = []
    for o in offers:
        is_fresh = False
        freshness_status = "unverified"
        last_checked_iso = None

        if o.last_checked_at is not None:
            last_checked_dt = (
                o.last_checked_at
                if o.last_checked_at.tzinfo is not None
                else o.last_checked_at.replace(tzinfo=timezone.utc)
            )
            last_checked_iso = last_checked_dt.isoformat()
            if (now - last_checked_dt) <= max_price_age:
                is_fresh = True
                freshness_status = "fresh"
            else:
                is_fresh = False
                freshness_status = "stale"

        variant_schema = None
        if o.variant:
            variant_schema = ProductVariantSummarySchema(
                id=o.variant.id,
                sku=o.variant.sku,
                gtin=o.variant.gtin,
                size=o.variant.size,
                color=o.variant.color,
                attributes=dict(o.variant.attributes or {}),
            )

        retailer_schema = RetailerSummarySchema(
            id=o.retailer_id,
            name=o.retailer_name,
            slug=o.retailer_slug,
            domain=o.retailer_domain,
        )

        offer_schemas.append(
            ProductOfferItemSchema(
                id=o.id,
                retailer=retailer_schema,
                price=o.price,
                originalPrice=o.original_price,
                currency=o.currency,
                availability=o.availability,
                inStock=o.in_stock,
                productUrl=o.product_url,
                redirectUrl=f"/v1/discovery/offers/{o.id}/redirect",
                variant=variant_schema,
                lastCheckedAt=last_checked_iso,
                isPriceFresh=is_fresh,
                freshnessStatus=freshness_status,
            )
        )

    return ProductOffersResponse(
        productId=product.id,
        title=product.title,
        brand=product.brand,
        isSyntheticFixture=False,
        offersCount=len(offer_schemas),
        offers=offer_schemas,
    )


@router.get(
    "/offers/{offer_id}/redirect",
    status_code=307,
    summary="Outbound retailer purchase redirect with attribution",
    description=(
        "Validates destination against authorized retailer domain, records a minimal "
        "offer_click attribution event, and redirects (HTTP 307) to the authorized merchant page."
    ),
)
def redirect_to_offer(
    offer_id: UUID = Path(..., description="Offer UUID"),
    guest_session_id: Optional[UUID] = Query(
        default=None,
        description="Guest session identifier if unauthenticated",
    ),
    surface: str = Query(
        default="product_offers",
        description="Discovery surface where the click originated",
    ),
    position: Optional[int] = Query(
        default=None,
        ge=0,
        le=1000,
        description="Feed position if clicked from a feed surface",
    ),
    user_id: Optional[UUID] = Depends(get_optional_user_id),
    candidate_repo=Depends(get_candidate_repository),
    event_repo: DiscoveryEventRepository = Depends(get_discovery_event_repository),
) -> RedirectResponse:
    """Validate offer destination, record minimal attribution event, and redirect to merchant."""
    # 1. Lookup offer
    offer = candidate_repo.get_offer_by_id(offer_id)
    if offer is None:
        raise not_found()

    # 2. Check active state (inactive/expired offer handling)
    if not offer.is_active:
        raise ApiError(
            status_code=410,
            code="OFFER_INACTIVE",
            message="This commercial offer is no longer active.",
        )

    # 3. Lookup destination URL
    destination = offer.affiliate_url or offer.product_url
    if not destination or not destination.strip():
        raise ApiError(
            status_code=404,
            code="DESTINATION_NOT_FOUND",
            message="No destination URL is configured for this offer.",
        )

    destination_url = destination.strip()

    # 4. Validate authorized retailer destination domain (prevent open redirect / SSRF)
    parsed = urlparse(destination_url)
    if parsed.scheme not in {"http", "https"}:
        raise ApiError(
            status_code=400,
            code="INVALID_URL_SCHEME",
            message="Destination URL must use HTTP or HTTPS.",
        )

    dest_host = (parsed.hostname or "").lower()
    authorized_domain = (offer.retailer_domain or "").lower().strip()
    if not authorized_domain or not (
        dest_host == authorized_domain or dest_host.endswith(f".{authorized_domain}")
    ):
        raise ApiError(
            status_code=403,
            code="UNAUTHORIZED_DESTINATION",
            message=f"Destination '{dest_host}' is not an authorized domain for retailer '{offer.retailer_name}'.",
        )

    # 5. Record minimal offer-click attribution event
    now = datetime.now(timezone.utc)
    target_id = str(offer.product_id) if offer.product_id else str(offer.id)
    metadata = {
        "offerId": str(offer.id),
        "retailer": offer.retailer_name,
        "retailerSlug": offer.retailer_slug,
    }

    # Validate surface against allowed surfaces
    valid_surface = (
        surface
        if surface
        in {
            "for_you_hero",
            "for_you_grid",
            "because_you_like",
            "complete_looks",
            "product_offers",
            "product_offer_sheet",
        }
        else "product_offers"
    )

    payload_hash = compute_payload_hash(
        event_type="offer_click",
        target_type="product",
        target_id=target_id,
        surface=valid_surface,
        position=position,
        metadata=metadata,
    )

    client_event_id = uuid4()
    effective_user_id = user_id
    effective_guest_id = None if user_id is not None else (guest_session_id or uuid4())

    event_payload = {
        "client_event_id": client_event_id,
        "event_type": "offer_click",
        "target_type": "product",
        "target_id": target_id,
        "product_id": offer.product_id,
        "surface": valid_surface,
        "position": position,
        "payload_hash": payload_hash,
        "metadata": metadata,
        "client_occurred_at": now,
    }

    try:
        event_repo.persist_events_batch(
            events=[event_payload],
            user_id=effective_user_id,
            guest_session_id=effective_guest_id,
        )
    except Exception as exc:
        logger.warning(
            "Failed to record offer_click attribution event: %s",
            exc,
            exc_info=True,
        )

    return RedirectResponse(url=destination_url, status_code=307)


