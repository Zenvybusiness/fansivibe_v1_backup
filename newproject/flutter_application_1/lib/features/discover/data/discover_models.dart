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
