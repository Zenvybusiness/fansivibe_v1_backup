// Discover DTOs for the M14 Discover surface (endpoints #43–44, UC-31).
//
// Wire shapes follow the frozen backend contract exactly (camelCase):
// `LookFeed {items: LookSummary[], next_cursor, has_more}` (cursor
// envelope — no `total`) and bare `LookDetail`. Both carry verbatim
// catalog content only: the rows have no occasion/style/fit attributes,
// no image, no ensemble, and no wardrobe linkage (DEC-014 P-3), so none
// of `imageUrl`/`occasion`/`styleTags`/`fitTags`/`wardrobeMatchCount`/
// `matchScoreDetails`/`isTrending`/`isOwned` appear here — callers treat
// those absences as normal, never as failures.
//
// `id` values are backend catalog codes (PR-3 stable strings such as
// `textured_quiff`) passed through verbatim — never translated, never
// resolved against local IDs. Unlike wardrobe/saved-look IDs these are
// NOT UUIDs; the detail read addresses them verbatim.
//
// Parsing is strict — wrong types throw into the client's failure path
// rather than posing garbage as look data. Nothing here derives scores,
// reorders the feed, filters locally by occasion/style/fit, logs wears,
// or writes learning signals: the backend is the sole source of truth.

/// One ranked feed row (#43 list item).
class LookSummary {
  const LookSummary({
    required this.id,
    required this.title,
    required this.description,
    required this.matchScore,
    required this.reasons,
  });

  /// Backend catalog code, verbatim (not a UUID).
  final String id;

  /// Catalog title, verbatim.
  final String title;

  /// Catalog description, verbatim.
  final String description;

  /// Catalog scoreSeed rescaled to the 0–100 derived-look scale, verbatim.
  final int matchScore;

  /// Grounded catalog reasons, verbatim.
  final List<String> reasons;

  factory LookSummary.fromJson(Map<String, dynamic> json) => LookSummary(
    id: json['id'] as String,
    title: json['title'] as String,
    description: json['description'] as String,
    matchScore: json['matchScore'] as int,
    reasons: (json['reasons'] as List).map((e) => e as String).toList(),
  );

  Map<String, dynamic> toJson() => {
    'id': id,
    'title': title,
    'description': description,
    'matchScore': matchScore,
    'reasons': reasons,
  };
}

/// One catalog look with full grounded content (#44 detail read).
class LookDetail {
  const LookDetail({
    required this.id,
    required this.title,
    required this.description,
    required this.matchScore,
    required this.reasons,
    required this.stylingTips,
    required this.maintenance,
    required this.bestFor,
  });

  /// Backend catalog code, verbatim (not a UUID).
  final String id;

  /// Catalog title, verbatim.
  final String title;

  /// Catalog description, verbatim.
  final String description;

  /// Catalog scoreSeed rescaled to 0–100, verbatim.
  final int matchScore;

  /// Grounded catalog reasons, verbatim.
  final List<String> reasons;

  /// Catalog styling tips, verbatim.
  final String stylingTips;

  /// Catalog maintenance, verbatim.
  final String maintenance;

  /// Catalog best-for, verbatim.
  final String bestFor;

  factory LookDetail.fromJson(Map<String, dynamic> json) => LookDetail(
    id: json['id'] as String,
    title: json['title'] as String,
    description: json['description'] as String,
    matchScore: json['matchScore'] as int,
    reasons: (json['reasons'] as List).map((e) => e as String).toList(),
    stylingTips: json['stylingTips'] as String,
    maintenance: json['maintenance'] as String,
    bestFor: json['bestFor'] as String,
  );

  Map<String, dynamic> toJson() => {
    'id': id,
    'title': title,
    'description': description,
    'matchScore': matchScore,
    'reasons': reasons,
    'stylingTips': stylingTips,
    'maintenance': maintenance,
    'bestFor': bestFor,
  };
}

/// One cursor page of the ranked feed (#43 envelope, no `total`).
class LookFeedPage {
  const LookFeedPage({
    required this.items,
    required this.nextCursor,
    required this.hasMore,
  });

  /// Ranked rows for this page, server order (never re-sorted locally).
  final List<LookSummary> items;

  /// Opaque cursor for the next page; null when the feed is exhausted.
  final String? nextCursor;

  /// Whether another page exists ("load more" UX).
  final bool hasMore;

  factory LookFeedPage.fromJson(Map<String, dynamic> json) => LookFeedPage(
    items: (json['items'] as List)
        .map((e) => LookSummary.fromJson(e as Map<String, dynamic>))
        .toList(),
    nextCursor: json['next_cursor'] as String?,
    hasMore: json['has_more'] as bool,
  );

  Map<String, dynamic> toJson() => {
    'items': items.map((e) => e.toJson()).toList(),
    'next_cursor': nextCursor,
    'has_more': hasMore,
  };
}

/// One cursor page of the For You feed (M12 P1 envelope + backend flag).
class ForYouFeedPage extends LookFeedPage {
  const ForYouFeedPage({
    required super.items,
    required super.nextCursor,
    required super.hasMore,
    required this.personalized,
  });

  /// Backend `personalized` verbatim — never inferred locally. False is
  /// the honest cold start (catalog order, not posed as personal).
  final bool personalized;

  factory ForYouFeedPage.fromJson(Map<String, dynamic> json) =>
      ForYouFeedPage(
        items: (json['items'] as List)
            .map((e) => LookSummary.fromJson(e as Map<String, dynamic>))
            .toList(),
        nextCursor: json['next_cursor'] as String?,
        hasMore: json['has_more'] as bool,
        personalized: json['personalized'] as bool,
      );

  @override
  Map<String, dynamic> toJson() => {
    ...super.toJson(),
    'personalized': personalized,
  };
}

/// Typed failures for the Discover surface.
enum DiscoverFailure {
  /// Missing/invalid auth (401).
  unauthorized,

  /// Rejected filter/pagination input (422) — e.g. a filter the current
  /// catalog cannot honor, or a malformed cursor/limit.
  invalidInput,

  /// Rate limited (429).
  rateLimited,

  /// Transport unreachable or malformed 200 body.
  networkError,

  /// Any other unexpected status.
  unknown,
}

/// Result of a feed fetch (#43): a page (possibly empty — empty is not
/// an error) or a typed failure (safe to retry, rows kept).
class DiscoverFeedResult {
  const DiscoverFeedResult.page(this.page) : failure = null;
  const DiscoverFeedResult.failure(this.failure) : page = null;

  final LookFeedPage? page;
  final DiscoverFailure? failure;

  bool get isPage => page != null;
}

/// Result of a For You fetch (M12 P1): a page carrying the backend
/// `personalized` flag, or a typed failure (safe to retry, rows kept).
/// Failures never fall back to `/v1/looks` or mock content.
class ForYouFeedResult {
  const ForYouFeedResult.page(this.page) : failure = null;
  const ForYouFeedResult.failure(this.failure) : page = null;

  final ForYouFeedPage? page;
  final DiscoverFailure? failure;

  bool get isPage => page != null;
}

/// Result of a detail fetch (#44): the look, a truthful not-found, or a
/// typed failure (safe to retry).
class LookDetailResult {
  const LookDetailResult.available(this.detail)
    : notFound = false,
      failure = null;
  const LookDetailResult.notFound()
    : detail = null,
      notFound = true,
      failure = null;
  const LookDetailResult.failure(this.failure)
    : detail = null,
      notFound = false;

  final LookDetail? detail;
  final bool notFound;
  final DiscoverFailure? failure;

  bool get isAvailable => detail != null;
}

// =========================================================================
// Unified Discovery API Models (TASK DISCOVERY-05 / DISCOVERY-06)
// =========================================================================

/// Transparent scoring breakdown for a personalized product recommendation.
class ProductScoreBreakdown {
  const ProductScoreBreakdown({
    required this.preferenceMatch,
    required this.styleProfileMatch,
    required this.wardrobeComplementarity,
    required this.budgetAvailability,
    required this.totalScore,
    this.matchReasons = const [],
    this.neutralDimensions = const [],
  });

  final double preferenceMatch;
  final double styleProfileMatch;
  final double wardrobeComplementarity;
  final double budgetAvailability;
  final double totalScore;
  final List<String> matchReasons;
  final List<String> neutralDimensions;

  factory ProductScoreBreakdown.fromJson(Map<String, dynamic> json) =>
      ProductScoreBreakdown(
        preferenceMatch: (json['preferenceMatch'] as num?)?.toDouble() ?? 0.0,
        styleProfileMatch:
            (json['styleProfileMatch'] as num?)?.toDouble() ?? 0.0,
        wardrobeComplementarity:
            (json['wardrobeComplementarity'] as num?)?.toDouble() ?? 0.0,
        budgetAvailability:
            (json['budgetAvailability'] as num?)?.toDouble() ?? 0.0,
        totalScore: (json['totalScore'] as num?)?.toDouble() ?? 0.0,
        matchReasons: (json['matchReasons'] as List?)
                ?.map((e) => e.toString())
                .toList() ??
            const [],
        neutralDimensions: (json['neutralDimensions'] as List?)
                ?.map((e) => e.toString())
                .toList() ??
            const [],
      );

  Map<String, dynamic> toJson() => {
        'preferenceMatch': preferenceMatch,
        'styleProfileMatch': styleProfileMatch,
        'wardrobeComplementarity': wardrobeComplementarity,
        'budgetAvailability': budgetAvailability,
        'totalScore': totalScore,
        'matchReasons': matchReasons,
        'neutralDimensions': neutralDimensions,
      };
}

/// Grounded explanation for a personalized product recommendation.
class ProductExplanation {
  const ProductExplanation({
    required this.summary,
    this.reasons = const [],
    this.positiveEvidence = const [],
    this.neutralDimensions = const [],
    required this.isSyntheticFixture,
    required this.provenance,
  });

  final String summary;
  final List<String> reasons;
  final List<String> positiveEvidence;
  final List<String> neutralDimensions;
  final bool isSyntheticFixture;
  final String provenance;

  factory ProductExplanation.fromJson(Map<String, dynamic> json) =>
      ProductExplanation(
        summary: json['summary'] as String? ?? '',
        reasons: (json['reasons'] as List?)
                ?.map((e) => e.toString())
                .toList() ??
            const [],
        positiveEvidence: (json['positiveEvidence'] as List?)
                ?.map((e) => e.toString())
                .toList() ??
            const [],
        neutralDimensions: (json['neutralDimensions'] as List?)
                ?.map((e) => e.toString())
                .toList() ??
            const [],
        isSyntheticFixture: json['isSyntheticFixture'] as bool? ?? false,
        provenance: json['provenance'] as String? ?? 'unknown',
      );

  Map<String, dynamic> toJson() => {
        'summary': summary,
        'reasons': reasons,
        'positiveEvidence': positiveEvidence,
        'neutralDimensions': neutralDimensions,
        'isSyntheticFixture': isSyntheticFixture,
        'provenance': provenance,
      };
}

/// One ranked personalized product recommendation item.
class ProductRecommendationItem {
  const ProductRecommendationItem({
    required this.id,
    required this.title,
    this.brand,
    this.category,
    this.subcategory,
    this.price,
    this.currency = 'INR',
    this.availability,
    this.imageUrls = const [],
    this.attributes = const {},
    this.ffoConcepts = const [],
    this.isSynthetic = false,
    this.isFixture = false,
    required this.score,
    required this.rank,
    required this.scoreBreakdown,
    required this.explanation,
  });

  final String id;
  final String title;
  final String? brand;
  final String? category;
  final String? subcategory;
  final double? price;
  final String currency;
  final bool? availability;
  final List<String> imageUrls;
  final Map<String, dynamic> attributes;
  final List<String> ffoConcepts;
  final bool isSynthetic;
  final bool isFixture;
  final double score;
  final int rank;
  final ProductScoreBreakdown scoreBreakdown;
  final ProductExplanation explanation;

  bool get isSyntheticFixture =>
      isSynthetic || isFixture || explanation.isSyntheticFixture;

  factory ProductRecommendationItem.fromJson(Map<String, dynamic> json) =>
      ProductRecommendationItem(
        id: json['id'] as String,
        title: json['title'] as String,
        brand: json['brand'] as String?,
        category: json['category'] as String?,
        subcategory: json['subcategory'] as String?,
        price: (json['price'] as num?)?.toDouble(),
        currency: json['currency'] as String? ?? 'INR',
        availability: json['availability'] as bool?,
        imageUrls: (json['imageUrls'] as List?)
                ?.map((e) => e.toString())
                .toList() ??
            const [],
        attributes: json['attributes'] as Map<String, dynamic>? ?? const {},
        ffoConcepts: (json['ffoConcepts'] as List?)
                ?.map((e) => e.toString())
                .toList() ??
            const [],
        isSynthetic: json['isSynthetic'] as bool? ?? false,
        isFixture: json['isFixture'] as bool? ?? false,
        score: (json['score'] as num?)?.toDouble() ?? 0.0,
        rank: (json['rank'] as num?)?.toInt() ?? 1,
        scoreBreakdown: ProductScoreBreakdown.fromJson(
          json['scoreBreakdown'] != null
              ? Map<String, dynamic>.from(json['scoreBreakdown'] as Map)
              : const {},
        ),
        explanation: ProductExplanation.fromJson(
          json['explanation'] != null
              ? Map<String, dynamic>.from(json['explanation'] as Map)
              : const {},
        ),
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'title': title,
        'brand': brand,
        'category': category,
        'subcategory': subcategory,
        'price': price,
        'currency': currency,
        'availability': availability,
        'imageUrls': imageUrls,
        'attributes': attributes,
        'ffoConcepts': ffoConcepts,
        'isSynthetic': isSynthetic,
        'isFixture': isFixture,
        'score': score,
        'rank': rank,
        'scoreBreakdown': scoreBreakdown.toJson(),
        'explanation': explanation.toJson(),
      };
}

/// Summary of user personalization context applied to recommendation query.
class UserPersonalizationContextSummary {
  const UserPersonalizationContextSummary({
    required this.isGuest,
    this.userId,
    this.displayName,
    this.hasWardrobe = false,
    this.styleType,
  });

  final bool isGuest;
  final String? userId;
  final String? displayName;
  final bool hasWardrobe;
  final String? styleType;

  factory UserPersonalizationContextSummary.fromJson(
          Map<String, dynamic> json) =>
      UserPersonalizationContextSummary(
        isGuest: json['isGuest'] as bool? ?? (json['userId'] == null),
        userId: json['userId'] as String?,
        displayName: json['displayName'] as String?,
        hasWardrobe: json['hasWardrobe'] as bool? ?? false,
        styleType: json['styleType'] as String?,
      );

  Map<String, dynamic> toJson() => {
        'isGuest': isGuest,
        'userId': userId,
        'displayName': displayName,
        'hasWardrobe': hasWardrobe,
        'styleType': styleType,
      };
}

/// Paginated response envelope for personalized product recommendations.
class ForYouDiscoveryResponse {
  const ForYouDiscoveryResponse({
    required this.items,
    required this.totalCount,
    required this.page,
    required this.pageSize,
    required this.totalPages,
    required this.hasNext,
    required this.hasPrev,
    required this.isPersonalized,
    required this.appliedContext,
  });

  final List<ProductRecommendationItem> items;
  final int totalCount;
  final int page;
  final int pageSize;
  final int totalPages;
  final bool hasNext;
  final bool hasPrev;
  final bool isPersonalized;
  final UserPersonalizationContextSummary appliedContext;

  factory ForYouDiscoveryResponse.fromJson(Map<String, dynamic> json) =>
      ForYouDiscoveryResponse(
        items: (json['items'] as List?)
                ?.map((e) => ProductRecommendationItem.fromJson(
                    e as Map<String, dynamic>))
                .toList() ??
            const [],
        totalCount: (json['totalCount'] as num?)?.toInt() ?? 0,
        page: (json['page'] as num?)?.toInt() ?? 1,
        pageSize: (json['pageSize'] as num?)?.toInt() ?? 20,
        totalPages: (json['totalPages'] as num?)?.toInt() ?? 0,
        hasNext: json['hasNext'] as bool? ?? false,
        hasPrev: json['hasPrev'] as bool? ?? false,
        isPersonalized: json['isPersonalized'] as bool? ?? false,
        appliedContext: UserPersonalizationContextSummary.fromJson(
          json['appliedContext'] as Map<String, dynamic>? ?? const {},
        ),
      );

  Map<String, dynamic> toJson() => {
        'items': items.map((e) => e.toJson()).toList(),
        'totalCount': totalCount,
        'page': page,
        'pageSize': pageSize,
        'totalPages': totalPages,
        'hasNext': hasNext,
        'hasPrev': hasPrev,
        'isPersonalized': isPersonalized,
        'appliedContext': appliedContext.toJson(),
      };
}

/// Result of For You personalized discovery query.
class ForYouDiscoveryResult {
  const ForYouDiscoveryResult.success(this.response) : failure = null;
  const ForYouDiscoveryResult.failure(this.failure) : response = null;

  final ForYouDiscoveryResponse? response;
  final DiscoverFailure? failure;

  bool get isSuccess => response != null;
}

// ---------------------------------------------------------------------------
// Complete Looks Models
// ---------------------------------------------------------------------------

/// An item participating in an outfit slot (catalog product or wardrobe item).
class LookSlotItem {
  const LookSlotItem({
    required this.itemId,
    required this.source,
    required this.title,
    required this.category,
    this.brand,
    this.subcategory,
    this.color,
    this.material,
    this.fit,
    this.silhouette,
    this.price,
    this.currency = 'INR',
    this.imageUrl,
    this.isSynthetic = false,
    this.isFixture = false,
    this.ffoConcepts = const [],
  });

  final String itemId;
  final String source; // 'catalog' or 'wardrobe'
  final String title;
  final String category;
  final String? brand;
  final String? subcategory;
  final String? color;
  final String? material;
  final String? fit;
  final String? silhouette;
  final double? price;
  final String currency;
  final String? imageUrl;
  final bool isSynthetic;
  final bool isFixture;
  final List<String> ffoConcepts;

  bool get isWardrobe => source == 'wardrobe';
  bool get isCatalog => source == 'catalog';
  bool get isSyntheticFixture => isSynthetic || isFixture;

  factory LookSlotItem.fromJson(Map<String, dynamic> json) => LookSlotItem(
        itemId: json['itemId'] as String,
        source: json['source'] as String? ?? 'catalog',
        title: json['title'] as String,
        category: json['category'] as String,
        brand: json['brand'] as String?,
        subcategory: json['subcategory'] as String?,
        color: json['color'] as String?,
        material: json['material'] as String?,
        fit: json['fit'] as String?,
        silhouette: json['silhouette'] as String?,
        price: (json['price'] as num?)?.toDouble(),
        currency: json['currency'] as String? ?? 'INR',
        imageUrl: json['imageUrl'] as String?,
        isSynthetic: json['isSynthetic'] as bool? ?? false,
        isFixture: json['isFixture'] as bool? ?? false,
        ffoConcepts: (json['ffoConcepts'] as List?)
                ?.map((e) => e.toString())
                .toList() ??
            const [],
      );

  Map<String, dynamic> toJson() => {
        'itemId': itemId,
        'source': source,
        'title': title,
        'category': category,
        'brand': brand,
        'subcategory': subcategory,
        'color': color,
        'material': material,
        'fit': fit,
        'silhouette': silhouette,
        'price': price,
        'currency': currency,
        'imageUrl': imageUrl,
        'isSynthetic': isSynthetic,
        'isFixture': isFixture,
        'ffoConcepts': ffoConcepts,
      };
}

/// Scoring breakdown for complete look compatibility.
class CompleteLookScoreBreakdown {
  const CompleteLookScoreBreakdown({
    required this.categoryCompleteness,
    required this.colorHarmony,
    required this.materialConsistency,
    required this.styleConceptMatch,
    required this.silhouetteFormality,
    required this.totalScore,
    this.reasons = const [],
    this.warnings = const [],
  });

  final double categoryCompleteness;
  final double colorHarmony;
  final double materialConsistency;
  final double styleConceptMatch;
  final double silhouetteFormality;
  final double totalScore;
  final List<String> reasons;
  final List<String> warnings;

  factory CompleteLookScoreBreakdown.fromJson(Map<String, dynamic> json) =>
      CompleteLookScoreBreakdown(
        categoryCompleteness:
            (json['categoryCompleteness'] as num?)?.toDouble() ?? 0.0,
        colorHarmony: (json['colorHarmony'] as num?)?.toDouble() ?? 0.0,
        materialConsistency:
            (json['materialConsistency'] as num?)?.toDouble() ?? 0.0,
        styleConceptMatch:
            (json['styleConceptMatch'] as num?)?.toDouble() ?? 0.0,
        silhouetteFormality:
            (json['silhouetteFormality'] as num?)?.toDouble() ?? 0.0,
        totalScore: (json['totalScore'] as num?)?.toDouble() ?? 0.0,
        reasons: (json['reasons'] as List?)
                ?.map((e) => e.toString())
                .toList() ??
            const [],
        warnings: (json['warnings'] as List?)
                ?.map((e) => e.toString())
                .toList() ??
            const [],
      );

  Map<String, dynamic> toJson() => {
        'categoryCompleteness': categoryCompleteness,
        'colorHarmony': colorHarmony,
        'materialConsistency': materialConsistency,
        'styleConceptMatch': styleConceptMatch,
        'silhouetteFormality': silhouetteFormality,
        'totalScore': totalScore,
        'reasons': reasons,
        'warnings': warnings,
      };
}

/// Grounded explanation for complete look.
class CompleteLookExplanation {
  const CompleteLookExplanation({
    required this.summary,
    this.reasons = const [],
    this.positiveEvidence = const [],
    this.neutralDimensions = const [],
    this.warnings = const [],
    required this.isSyntheticFixture,
    required this.isWardrobeAware,
  });

  final String summary;
  final List<String> reasons;
  final List<String> positiveEvidence;
  final List<String> neutralDimensions;
  final List<String> warnings;
  final bool isSyntheticFixture;
  final bool isWardrobeAware;

  factory CompleteLookExplanation.fromJson(Map<String, dynamic> json) =>
      CompleteLookExplanation(
        summary: json['summary'] as String? ?? '',
        reasons: (json['reasons'] as List?)
                ?.map((e) => e.toString())
                .toList() ??
            const [],
        positiveEvidence: (json['positiveEvidence'] as List?)
                ?.map((e) => e.toString())
                .toList() ??
            const [],
        neutralDimensions: (json['neutralDimensions'] as List?)
                ?.map((e) => e.toString())
                .toList() ??
            const [],
        warnings: (json['warnings'] as List?)
                ?.map((e) => e.toString())
                .toList() ??
            const [],
        isSyntheticFixture: json['isSyntheticFixture'] as bool? ?? false,
        isWardrobeAware: json['isWardrobeAware'] as bool? ?? false,
      );

  Map<String, dynamic> toJson() => {
        'summary': summary,
        'reasons': reasons,
        'positiveEvidence': positiveEvidence,
        'neutralDimensions': neutralDimensions,
        'warnings': warnings,
        'isSyntheticFixture': isSyntheticFixture,
        'isWardrobeAware': isWardrobeAware,
      };
}

/// A complete assembled look.
class CompleteLook {
  const CompleteLook({
    required this.lookId,
    required this.slots,
    required this.totalCatalogPrice,
    this.currency = 'INR',
    required this.compatibilityScore,
    required this.compatibilityBreakdown,
    this.compatibilityReasons = const [],
    this.unresolvedConstraints = const [],
    required this.explanation,
    required this.isWardrobeAware,
    this.wardrobeItemCount = 0,
    this.catalogItemCount = 0,
    this.containsSyntheticFixtures = false,
    this.bundlePurchasable = false,
  });

  final String lookId;
  final Map<String, LookSlotItem> slots;
  final double totalCatalogPrice;
  final String currency;
  final double compatibilityScore;
  final CompleteLookScoreBreakdown compatibilityBreakdown;
  final List<String> compatibilityReasons;
  final List<String> unresolvedConstraints;
  final CompleteLookExplanation explanation;
  final bool isWardrobeAware;
  final int wardrobeItemCount;
  final int catalogItemCount;
  final bool containsSyntheticFixtures;
  final bool bundlePurchasable;

  factory CompleteLook.fromJson(Map<String, dynamic> json) {
    final rawSlots = (json['slots'] as Map?) ?? const {};
    final parsedSlots = <String, LookSlotItem>{};
    for (final entry in rawSlots.entries) {
      if (entry.value is Map) {
        parsedSlots[entry.key.toString()] =
            LookSlotItem.fromJson(Map<String, dynamic>.from(entry.value as Map));
      }
    }
    return CompleteLook(
      lookId: json['lookId'] as String,
      slots: parsedSlots,
      totalCatalogPrice:
          (json['totalCatalogPrice'] as num?)?.toDouble() ?? 0.0,
      currency: json['currency'] as String? ?? 'INR',
      compatibilityScore:
          (json['compatibilityScore'] as num?)?.toDouble() ?? 0.0,
      compatibilityBreakdown: CompleteLookScoreBreakdown.fromJson(
        json['compatibilityBreakdown'] != null
            ? Map<String, dynamic>.from(json['compatibilityBreakdown'] as Map)
            : const {},
      ),
      compatibilityReasons: (json['compatibilityReasons'] as List?)
              ?.map((e) => e.toString())
              .toList() ??
          const [],
      unresolvedConstraints: (json['unresolvedConstraints'] as List?)
              ?.map((e) => e.toString())
              .toList() ??
          const [],
      explanation: CompleteLookExplanation.fromJson(
        json['explanation'] != null
            ? Map<String, dynamic>.from(json['explanation'] as Map)
            : const {},
      ),
      isWardrobeAware: json['isWardrobeAware'] as bool? ?? false,
      wardrobeItemCount: (json['wardrobeItemCount'] as num?)?.toInt() ?? 0,
      catalogItemCount: (json['catalogItemCount'] as num?)?.toInt() ?? 0,
      containsSyntheticFixtures:
          json['containsSyntheticFixtures'] as bool? ?? false,
      bundlePurchasable: json['bundlePurchasable'] as bool? ?? false,
    );
  }

  Map<String, dynamic> toJson() => {
        'lookId': lookId,
        'slots': slots.map((k, v) => MapEntry(k, v.toJson())),
        'totalCatalogPrice': totalCatalogPrice,
        'currency': currency,
        'compatibilityScore': compatibilityScore,
        'compatibilityBreakdown': compatibilityBreakdown.toJson(),
        'compatibilityReasons': compatibilityReasons,
        'unresolvedConstraints': unresolvedConstraints,
        'explanation': explanation.toJson(),
        'isWardrobeAware': isWardrobeAware,
        'wardrobeItemCount': wardrobeItemCount,
        'catalogItemCount': catalogItemCount,
        'containsSyntheticFixtures': containsSyntheticFixtures,
        'bundlePurchasable': bundlePurchasable,
      };
}

/// Response envelope for Complete Looks.
class CompleteLooksDiscoveryResponse {
  const CompleteLooksDiscoveryResponse({
    required this.looks,
    required this.totalLooks,
    this.targetOccasion,
    this.targetAesthetic,
    this.maxBudget,
    required this.isWardrobeAware,
    required this.containsSyntheticFixtures,
  });

  final List<CompleteLook> looks;
  final int totalLooks;
  final String? targetOccasion;
  final String? targetAesthetic;
  final double? maxBudget;
  final bool isWardrobeAware;
  final bool containsSyntheticFixtures;

  factory CompleteLooksDiscoveryResponse.fromJson(Map<String, dynamic> json) =>
      CompleteLooksDiscoveryResponse(
        looks: (json['looks'] as List?)
                ?.map((e) => CompleteLook.fromJson(e as Map<String, dynamic>))
                .toList() ??
            const [],
        totalLooks: (json['totalLooks'] as num?)?.toInt() ?? 0,
        targetOccasion: json['targetOccasion'] as String?,
        targetAesthetic: json['targetAesthetic'] as String?,
        maxBudget: (json['maxBudget'] as num?)?.toDouble(),
        isWardrobeAware: json['isWardrobeAware'] as bool? ?? false,
        containsSyntheticFixtures:
            json['containsSyntheticFixtures'] as bool? ?? false,
      );

  Map<String, dynamic> toJson() => {
        'looks': looks.map((e) => e.toJson()).toList(),
        'totalLooks': totalLooks,
        'targetOccasion': targetOccasion,
        'targetAesthetic': targetAesthetic,
        'maxBudget': maxBudget,
        'isWardrobeAware': isWardrobeAware,
        'containsSyntheticFixtures': containsSyntheticFixtures,
      };
}

/// Result of complete looks discovery query.
class CompleteLooksDiscoveryResult {
  const CompleteLooksDiscoveryResult.success(this.response) : failure = null;
  const CompleteLooksDiscoveryResult.failure(this.failure) : response = null;

  final CompleteLooksDiscoveryResponse? response;
  final DiscoverFailure? failure;

  bool get isSuccess => response != null;
}

// ---------------------------------------------------------------------------
// Trending Intelligence Models
// ---------------------------------------------------------------------------

/// Component signal in a trending candidate.
class DiscoveryTrendSignal {
  const DiscoveryTrendSignal({
    required this.metric,
    required this.kind,
    required this.available,
    this.value,
    this.unit,
    this.detail,
  });

  final String metric;
  final String kind;
  final bool available;
  final dynamic value;
  final String? unit;
  final String? detail;

  factory DiscoveryTrendSignal.fromJson(Map<String, dynamic> json) =>
      DiscoveryTrendSignal(
        metric: json['metric'] as String? ?? '',
        kind: json['kind'] as String? ?? '',
        available: json['available'] as bool? ?? false,
        value: json['value'],
        unit: json['unit'] as String?,
        detail: json['detail'] as String?,
      );

  Map<String, dynamic> toJson() => {
        'metric': metric,
        'kind': kind,
        'available': available,
        'value': value,
        'unit': unit,
        'detail': detail,
      };
}

/// Grounded explanation for a trending candidate item.
class DiscoveryTrendItemExplanation {
  const DiscoveryTrendItemExplanation({
    required this.summary,
    required this.evidenceType,
    required this.demandSignalAvailable,
    this.reasons = const [],
  });

  final String summary;
  final String evidenceType;
  final bool demandSignalAvailable;
  final List<String> reasons;

  factory DiscoveryTrendItemExplanation.fromJson(Map<String, dynamic> json) =>
      DiscoveryTrendItemExplanation(
        summary: json['summary'] as String? ?? '',
        evidenceType: json['evidenceType'] as String? ?? 'catalog_activity',
        demandSignalAvailable: json['demandSignalAvailable'] as bool? ?? false,
        reasons: (json['reasons'] as List?)
                ?.map((e) => e.toString())
                .toList() ??
            const [],
      );

  Map<String, dynamic> toJson() => {
        'summary': summary,
        'evidenceType': evidenceType,
        'demandSignalAvailable': demandSignalAvailable,
        'reasons': reasons,
      };
}

/// One concept observation item in the trending response.
class DiscoveryTrendItem {
  const DiscoveryTrendItem({
    required this.concept,
    required this.canonicalName,
    required this.category,
    this.evidenceType = 'catalog_activity',
    required this.catalogActivityStatus,
    required this.observationCount,
    required this.distinctProducts,
    required this.distinctSources,
    required this.firstObservedAt,
    required this.lastObservedAt,
    this.catalogGrowth,
    this.priceChangeRatio,
    this.inStockRatio,
    required this.confidence,
    this.strength,
    required this.fixtureDerived,
    required this.publishable,
    this.reasons = const [],
    this.signals = const [],
    this.directDemandAvailable = false,
    required this.explanation,
  });

  final String concept;
  final String canonicalName;
  final String category;
  final String evidenceType;
  final String catalogActivityStatus;
  final int observationCount;
  final int distinctProducts;
  final int distinctSources;
  final String firstObservedAt;
  final String lastObservedAt;
  final double? catalogGrowth;
  final double? priceChangeRatio;
  final double? inStockRatio;
  final double confidence;
  final double? strength;
  final bool fixtureDerived;
  final bool publishable;
  final List<String> reasons;
  final List<DiscoveryTrendSignal> signals;
  final bool directDemandAvailable;
  final DiscoveryTrendItemExplanation explanation;

  factory DiscoveryTrendItem.fromJson(Map<String, dynamic> json) =>
      DiscoveryTrendItem(
        concept: json['concept'] as String? ?? '',
        canonicalName: json['canonicalName'] as String? ?? '',
        category: json['category'] as String? ?? '',
        evidenceType: json['evidenceType'] as String? ?? 'catalog_activity',
        catalogActivityStatus: json['catalogActivityStatus'] as String? ?? '',
        observationCount: (json['observationCount'] as num?)?.toInt() ?? 0,
        distinctProducts: (json['distinctProducts'] as num?)?.toInt() ?? 0,
        distinctSources: (json['distinctSources'] as num?)?.toInt() ?? 0,
        firstObservedAt: json['firstObservedAt'] as String? ?? '',
        lastObservedAt: json['lastObservedAt'] as String? ?? '',
        catalogGrowth: (json['catalogGrowth'] as num?)?.toDouble(),
        priceChangeRatio: (json['priceChangeRatio'] as num?)?.toDouble(),
        inStockRatio: (json['inStockRatio'] as num?)?.toDouble(),
        confidence: (json['confidence'] as num?)?.toDouble() ?? 0.0,
        strength: (json['strength'] as num?)?.toDouble(),
        fixtureDerived: json['fixtureDerived'] as bool? ?? false,
        publishable: json['publishable'] as bool? ?? false,
        reasons: (json['reasons'] as List?)
                ?.map((e) => e.toString())
                .toList() ??
            const [],
        signals: (json['signals'] as List?)
                ?.map((e) => DiscoveryTrendSignal.fromJson(
                    e as Map<String, dynamic>))
                .toList() ??
            const [],
        directDemandAvailable:
            json['directDemandAvailable'] as bool? ?? false,
        explanation: DiscoveryTrendItemExplanation.fromJson(
          json['explanation'] as Map<String, dynamic>? ?? const {},
        ),
      );

  Map<String, dynamic> toJson() => {
        'concept': concept,
        'canonicalName': canonicalName,
        'category': category,
        'evidenceType': evidenceType,
        'catalogActivityStatus': catalogActivityStatus,
        'observationCount': observationCount,
        'distinctProducts': distinctProducts,
        'distinctSources': distinctSources,
        'firstObservedAt': firstObservedAt,
        'lastObservedAt': lastObservedAt,
        'catalogGrowth': catalogGrowth,
        'priceChangeRatio': priceChangeRatio,
        'inStockRatio': inStockRatio,
        'confidence': confidence,
        'strength': strength,
        'fixtureDerived': fixtureDerived,
        'publishable': publishable,
        'reasons': reasons,
        'signals': signals.map((e) => e.toJson()).toList(),
        'directDemandAvailable': directDemandAvailable,
        'explanation': explanation.toJson(),
      };
}

/// Read-only trend intelligence for discovery feed.
class DiscoveryTrendingResponse {
  const DiscoveryTrendingResponse({
    required this.windowStart,
    required this.windowEnd,
    required this.generatedAt,
    required this.demandTrendStatus,
    this.evidenceType = 'catalog_activity',
    required this.catalogActivityStatus,
    this.directDemandAvailable = false,
    required this.sourceCoverage,
    required this.observationCount,
    this.insufficientEvidenceReason,
    required this.confidenceInterpretation,
    this.limitations = const [],
    this.items = const [],
  });

  final String windowStart;
  final String windowEnd;
  final String generatedAt;
  final String demandTrendStatus;
  final String evidenceType;
  final String catalogActivityStatus;
  final bool directDemandAvailable;
  final int sourceCoverage;
  final int observationCount;
  final String? insufficientEvidenceReason;
  final String confidenceInterpretation;
  final List<String> limitations;
  final List<DiscoveryTrendItem> items;

  factory DiscoveryTrendingResponse.fromJson(Map<String, dynamic> json) =>
      DiscoveryTrendingResponse(
        windowStart: json['windowStart'] as String? ?? '',
        windowEnd: json['windowEnd'] as String? ?? '',
        generatedAt: json['generatedAt'] as String? ?? '',
        demandTrendStatus: json['demandTrendStatus'] as String? ?? '',
        evidenceType: json['evidenceType'] as String? ?? 'catalog_activity',
        catalogActivityStatus:
            json['catalogActivityStatus'] as String? ?? '',
        directDemandAvailable:
            json['directDemandAvailable'] as bool? ?? false,
        sourceCoverage: (json['sourceCoverage'] as num?)?.toInt() ?? 0,
        observationCount: (json['observationCount'] as num?)?.toInt() ?? 0,
        insufficientEvidenceReason:
            json['insufficientEvidenceReason'] as String?,
        confidenceInterpretation:
            json['confidenceInterpretation'] as String? ?? '',
        limitations: (json['limitations'] as List?)
                ?.map((e) => e.toString())
                .toList() ??
            const [],
        items: (json['items'] as List?)
                ?.map((e) => DiscoveryTrendItem.fromJson(
                    e as Map<String, dynamic>))
                .toList() ??
            const [],
      );

  Map<String, dynamic> toJson() => {
        'windowStart': windowStart,
        'windowEnd': windowEnd,
        'generatedAt': generatedAt,
        'demandTrendStatus': demandTrendStatus,
        'evidenceType': evidenceType,
        'catalogActivityStatus': catalogActivityStatus,
        'directDemandAvailable': directDemandAvailable,
        'sourceCoverage': sourceCoverage,
        'observationCount': observationCount,
        'insufficientEvidenceReason': insufficientEvidenceReason,
        'confidenceInterpretation': confidenceInterpretation,
        'limitations': limitations,
        'items': items.map((e) => e.toJson()).toList(),
      };
}

/// Result of trending discovery query.
class DiscoveryTrendingResult {
  const DiscoveryTrendingResult.success(this.response) : failure = null;
  const DiscoveryTrendingResult.failure(this.failure) : response = null;

  final DiscoveryTrendingResponse? response;
  final DiscoverFailure? failure;

  bool get isSuccess => response != null;
}

// ---------------------------------------------------------------------------
// Interaction Telemetry Models (DISCOVERY-10A)
// ---------------------------------------------------------------------------

/// One interaction event in an ingress batch.
class DiscoveryEventItem {
  const DiscoveryEventItem({
    required this.eventId,
    required this.eventType,
    required this.targetType,
    required this.targetId,
    required this.surface,
    this.position,
    this.metadata = const {},
    required this.occurredAt,
  });

  final String eventId;
  final String eventType;
  final String targetType;
  final String targetId;
  final String surface;
  final int? position;
  final Map<String, dynamic> metadata;
  final String occurredAt;

  Map<String, dynamic> toJson() => {
        'eventId': eventId,
        'eventType': eventType,
        'targetType': targetType,
        'targetId': targetId,
        'surface': surface,
        if (position != null) 'position': position,
        'metadata': metadata,
        'occurredAt': occurredAt,
      };

  factory DiscoveryEventItem.fromJson(Map<String, dynamic> json) =>
      DiscoveryEventItem(
        eventId: json['eventId'] as String? ?? '',
        eventType: json['eventType'] as String? ?? '',
        targetType: json['targetType'] as String? ?? '',
        targetId: json['targetId'] as String? ?? '',
        surface: json['surface'] as String? ?? '',
        position: (json['position'] as num?)?.toInt(),
        metadata: (json['metadata'] as Map<String, dynamic>?) ?? const {},
        occurredAt: json['occurredAt'] as String? ?? '',
      );
}

/// Batch ingestion request for discovery interaction events.
class DiscoveryEventsBatchRequest {
  const DiscoveryEventsBatchRequest({
    this.guestSessionId,
    required this.events,
  });

  final String? guestSessionId;
  final List<DiscoveryEventItem> events;

  Map<String, dynamic> toJson() => {
        if (guestSessionId != null) 'guestSessionId': guestSessionId,
        'events': events.map((e) => e.toJson()).toList(),
      };
}

/// Per-event acknowledgement returned in an accepted batch response.
class DiscoveryEventAck {
  const DiscoveryEventAck({
    required this.eventId,
    required this.status,
    required this.replayed,
  });

  final String eventId;
  final String status;
  final bool replayed;

  factory DiscoveryEventAck.fromJson(Map<String, dynamic> json) =>
      DiscoveryEventAck(
        eventId: json['eventId'] as String? ?? '',
        status: json['status'] as String? ?? '',
        replayed: json['replayed'] as bool? ?? false,
      );

  Map<String, dynamic> toJson() => {
        'eventId': eventId,
        'status': status,
        'replayed': replayed,
      };
}

/// Ingestion response for POST /v1/discovery/events (HTTP 202 Accepted).
class DiscoveryEventsBatchResponse {
  const DiscoveryEventsBatchResponse({
    required this.acceptedCount,
    required this.events,
  });

  final int acceptedCount;
  final List<DiscoveryEventAck> events;

  factory DiscoveryEventsBatchResponse.fromJson(Map<String, dynamic> json) =>
      DiscoveryEventsBatchResponse(
        acceptedCount: (json['acceptedCount'] as num?)?.toInt() ?? 0,
        events: (json['events'] as List?)
                ?.map((e) =>
                    DiscoveryEventAck.fromJson(e as Map<String, dynamic>))
                .toList() ??
            const [],
      );

  Map<String, dynamic> toJson() => {
        'acceptedCount': acceptedCount,
        'events': events.map((e) => e.toJson()).toList(),
      };
}

/// Result of dispatching discovery telemetry events.
class DiscoveryEventsResult {
  const DiscoveryEventsResult.success(this.response) : failure = null;
  const DiscoveryEventsResult.failure(this.failure) : response = null;

  final DiscoveryEventsBatchResponse? response;
  final DiscoverFailure? failure;

  bool get isSuccess => response != null;
}


