import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'package:fansivibe/core/config/app_config.dart';
import 'package:fansivibe/features/discover/data/discover_models.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';

/// HTTP client for the M14 Discover surface.
///
/// Endpoints: #43 `GET /v1/looks` (`?occasion=&style=&fit=&cursor=&limit=`,
/// cursor envelope) and #44 `GET /v1/looks/{look_id}` (bare detail).
///
/// Override the endpoint with `--dart-define=ASSISTANT_BASE_URL=...`.
/// Fetches never throw: 200 parses into the typed result, 404 on detail
/// into [LookDetailResult.notFound] (truthful empty state), 422 into
/// [DiscoverFailure.invalidInput] (e.g. a filter the current catalog
/// cannot honor, or a bad cursor/limit), and every other status or
/// transport error into a typed failure so the caller renders its honest
/// loading/error states — the flow never fabricates a look when the
/// server is unreachable and never shows fake content offline.
///
/// Look IDs are backend catalog codes (PR-3 strings, not UUIDs) passed
/// through verbatim; local mock IDs (`fy_*`/`tr_*`) are never submitted.
/// Nothing here derives scores, reorders the feed, logs wears, or writes
/// learning signals — the backend response is the source of truth.
class DiscoverClient {
  /// Creates a [DiscoverClient] with an optional client for testing.
  DiscoverClient({http.Client? client}) : _client = client ?? http.Client();

  /// Backend base URL.
  /// Canonical base URL — single source of truth is [AppConfig.apiBaseUrl].
  static const String baseUrl = AppConfig.apiBaseUrl;

  static const String _devTokenDefault = String.fromEnvironment(
    'FANSIVIBE_DEV_TOKEN',
    defaultValue: 'dev',
  );

  /// Session-first Bearer token (D-AUTH-1): the persisted session wins;
  /// the dart-define default covers logged-out/test behavior.
  static String get _devToken => AuthSession.effectiveToken(_devTokenDefault);

  final http.Client _client;
  static const Duration _timeout = Duration(seconds: 12);

  Map<String, String> get _headers => {'Authorization': 'Bearer $_devToken'};

  /// Fetches one cursor page of the ranked feed (#43 `GET /v1/looks`).
  ///
  /// Null filters are omitted (the screen passes null for its `all`
  /// selections); non-null filters travel verbatim and the backend
  /// truthfully 422s values the current catalog cannot honor. [cursor]
  /// is the opaque token from the previous page (null for the first
  /// page); [limit] is the page size when set. Never throws.
  Future<DiscoverFeedResult> getLookFeed({
    String? occasion,
    String? style,
    String? fit,
    String? cursor,
    int? limit,
  }) async {
    try {
      final query = <String, String>{
        if (occasion != null) 'occasion': occasion,
        if (style != null) 'style': style,
        if (fit != null) 'fit': fit,
        if (cursor != null) 'cursor': cursor,
        if (limit != null) 'limit': '$limit',
      };
      final uri = Uri.parse(
        '$baseUrl/v1/looks',
      ).replace(queryParameters: query.isEmpty ? null : query);
      final response = await _client
          .get(uri, headers: _headers)
          .timeout(_timeout);
      if (response.statusCode == 200) {
        try {
          final decoded = jsonDecode(response.body) as Map<String, dynamic>;
          return DiscoverFeedResult.page(LookFeedPage.fromJson(decoded));
        } catch (error) {
          debugPrint('Discover feed: malformed 200 body: $error');
          return const DiscoverFeedResult.failure(DiscoverFailure.networkError);
        }
      }
      final failure = _failureFor(response.statusCode);
      debugPrint(
        'Discover feed responded ${response.statusCode}: ${response.body}',
      );
      return DiscoverFeedResult.failure(failure);
    } catch (error) {
      debugPrint('Discover backend unreachable during feed fetch: $error');
      return const DiscoverFeedResult.failure(DiscoverFailure.networkError);
    }
  }

  /// Fetches one cursor page of the For You feed (M12 P1
  /// `GET /v1/looks/for-you`).
  ///
  /// [cursor] is the opaque token from the previous page (null for the
  /// first page); [limit] is the page size when set (backend bounds
  /// 1..50). The backend `personalized` flag travels verbatim —
  /// never inferred here. Never throws; failures carry no mock
  /// fallback and never substitute the `/v1/looks` feed.
  Future<ForYouFeedResult> getForYouFeed({String? cursor, int? limit}) async {
    try {
      final query = <String, String>{
        if (cursor != null) 'cursor': cursor,
        if (limit != null) 'limit': '$limit',
      };
      final uri = Uri.parse(
        '$baseUrl/v1/looks/for-you',
      ).replace(queryParameters: query.isEmpty ? null : query);
      final response = await _client
          .get(uri, headers: _headers)
          .timeout(_timeout);
      if (response.statusCode == 200) {
        try {
          final decoded = jsonDecode(response.body) as Map<String, dynamic>;
          return ForYouFeedResult.page(ForYouFeedPage.fromJson(decoded));
        } catch (error) {
          debugPrint('For You feed: malformed 200 body: $error');
          return const ForYouFeedResult.failure(DiscoverFailure.networkError);
        }
      }
      final failure = _failureFor(response.statusCode);
      debugPrint(
        'For You feed responded ${response.statusCode}: ${response.body}',
      );
      return ForYouFeedResult.failure(failure);
    } catch (error) {
      debugPrint('Discover backend unreachable during for-you fetch: $error');
      return const ForYouFeedResult.failure(DiscoverFailure.networkError);
    }
  }

  /// Fetches one catalog look by its backend code (#44).
  ///
  /// [lookId] travels verbatim as the path segment (never translated to
  /// a local ID). Unknown codes 404 into [LookDetailResult.notFound].
  /// Never throws.
  Future<LookDetailResult> getLookDetail({required String lookId}) async {
    try {
      // Path-segment construction (never string interpolation): the
      // backend code travels verbatim and is never treated as a route.
      final base = Uri.parse(baseUrl);
      final uri = base.replace(
        pathSegments: [...base.pathSegments, 'v1', 'looks', lookId],
      );
      final response = await _client
          .get(uri, headers: _headers)
          .timeout(_timeout);
      if (response.statusCode == 200) {
        try {
          final decoded = jsonDecode(response.body) as Map<String, dynamic>;
          return LookDetailResult.available(LookDetail.fromJson(decoded));
        } catch (error) {
          debugPrint('Discover detail: malformed 200 body: $error');
          return const LookDetailResult.failure(DiscoverFailure.networkError);
        }
      }
      if (response.statusCode == 404) {
        return const LookDetailResult.notFound();
      }
      final failure = _failureFor(response.statusCode);
      debugPrint(
        'Discover detail responded ${response.statusCode}: ${response.body}',
      );
      return LookDetailResult.failure(failure);
    } catch (error) {
      debugPrint('Discover backend unreachable during detail fetch: $error');
      return const LookDetailResult.failure(DiscoverFailure.networkError);
    }
  }

  Map<String, String> _headersFor({
    bool isGuest = false,
    bool requireAuth = false,
  }) {
    if (isGuest) return const {};
    if (AuthSession.isAuthenticated) {
      final t = AuthSession.token;
      if (t != null && t.isNotEmpty) {
        return {'Authorization': 'Bearer $t'};
      }
    }
    if (requireAuth) {
      return {'Authorization': 'Bearer $_devToken'};
    }
    return const {};
  }

  /// Fetches personalized catalog recommendations (GET /v1/discovery/for-you).
  ///
  /// Safe for both authenticated users and guests. Guest requests never attach
  /// another user's Bearer token and enforce [isGuest] = true.
  Future<ForYouDiscoveryResult> getForYouRecommendations({
    int page = 1,
    int pageSize = 20,
    String? q,
    List<String>? categories,
    List<String>? excludeCategories,
    List<String>? brands,
    List<String>? excludeBrands,
    double? minPrice,
    double? maxPrice,
    String? currency,
    List<String>? colors,
    List<String>? materials,
    List<String>? fits,
    List<String>? silhouettes,
    bool? inStockOnly,
    bool includeSynthetic = true,
    bool isGuest = false,
  }) async {
    try {
      final effectiveGuest = isGuest || !AuthSession.isAuthenticated;
      final cleanQ = q?.trim();
      final query = <String, dynamic>{
        'page': '$page',
        'page_size': '$pageSize',
        'include_synthetic': '$includeSynthetic',
        if (cleanQ != null && cleanQ.isNotEmpty) 'q': cleanQ,
        if (effectiveGuest) 'is_guest': 'true',
        if (categories != null && categories.isNotEmpty) 'categories': categories,
        if (excludeCategories != null && excludeCategories.isNotEmpty)
          'exclude_categories': excludeCategories,
        if (brands != null && brands.isNotEmpty) 'brands': brands,
        if (excludeBrands != null && excludeBrands.isNotEmpty)
          'exclude_brands': excludeBrands,
        if (minPrice != null) 'min_price': '$minPrice',
        if (maxPrice != null) 'max_price': '$maxPrice',
        if (currency != null) 'currency': currency,
        if (colors != null && colors.isNotEmpty) 'colors': colors,
        if (materials != null && materials.isNotEmpty) 'materials': materials,
        if (fits != null && fits.isNotEmpty) 'fits': fits,
        if (silhouettes != null && silhouettes.isNotEmpty)
          'silhouettes': silhouettes,
        if (inStockOnly != null) 'in_stock_only': '$inStockOnly',
      };

      final base = Uri.parse(baseUrl);
      final uri = base.replace(
        pathSegments: [
          ...base.pathSegments.where((s) => s.isNotEmpty),
          'v1',
          'discovery',
          'for-you',
        ],
        queryParameters: query,
      );

      final headers = _headersFor(isGuest: effectiveGuest);
      final response = await _client.get(uri, headers: headers).timeout(_timeout);

      if (response.statusCode == 200) {
        try {
          final decoded = jsonDecode(response.body) as Map<String, dynamic>;
          return ForYouDiscoveryResult.success(
            ForYouDiscoveryResponse.fromJson(decoded),
          );
        } catch (error) {
          debugPrint('For You discovery: malformed 200 body: $error');
          return const ForYouDiscoveryResult.failure(
            DiscoverFailure.networkError,
          );
        }
      }

      final failure = _failureFor(response.statusCode);
      debugPrint(
        'For You discovery responded ${response.statusCode}: ${response.body}',
      );
      return ForYouDiscoveryResult.failure(failure);
    } catch (error) {
      debugPrint('Discover backend unreachable during for-you discovery: $error');
      return const ForYouDiscoveryResult.failure(DiscoverFailure.networkError);
    }
  }

  /// Fetches complete outfit combinations (GET /v1/discovery/looks/complete).
  Future<CompleteLooksDiscoveryResult> getCompleteLooks({
    int limit = 10,
    double? maxBudget,
    String? targetOccasion,
    String? targetAesthetic,
    String? anchorProductId,
    String? anchorWardrobeItemId,
    bool allowWardrobe = true,
    bool includeSynthetic = true,
  }) async {
    try {
      final isAuth = AuthSession.isAuthenticated;
      final query = <String, dynamic>{
        'limit': '$limit',
        'allow_wardrobe': '$allowWardrobe',
        'include_synthetic': '$includeSynthetic',
        if (maxBudget != null) 'max_budget': '$maxBudget',
        if (targetOccasion != null) 'target_occasion': targetOccasion,
        if (targetAesthetic != null) 'target_aesthetic': targetAesthetic,
        if (anchorProductId != null) 'anchor_product_id': anchorProductId,
        if (anchorWardrobeItemId != null)
          'anchor_wardrobe_item_id': anchorWardrobeItemId,
      };

      final base = Uri.parse(baseUrl);
      final uri = base.replace(
        pathSegments: [
          ...base.pathSegments.where((s) => s.isNotEmpty),
          'v1',
          'discovery',
          'looks',
          'complete',
        ],
        queryParameters: query,
      );

      final headers = _headersFor(isGuest: !isAuth);
      final response = await _client.get(uri, headers: headers).timeout(_timeout);

      if (response.statusCode == 200) {
        try {
          final decoded = jsonDecode(response.body) as Map<String, dynamic>;
          return CompleteLooksDiscoveryResult.success(
            CompleteLooksDiscoveryResponse.fromJson(decoded),
          );
        } catch (error) {
          debugPrint('Complete looks: malformed 200 body: $error');
          return const CompleteLooksDiscoveryResult.failure(
            DiscoverFailure.networkError,
          );
        }
      }

      final failure = _failureFor(response.statusCode);
      debugPrint(
        'Complete looks responded ${response.statusCode}: ${response.body}',
      );
      return CompleteLooksDiscoveryResult.failure(failure);
    } catch (error) {
      debugPrint('Discover backend unreachable during complete looks: $error');
      return const CompleteLooksDiscoveryResult.failure(
        DiscoverFailure.networkError,
      );
    }
  }

  /// Fetches discovery trending intelligence (GET /v1/discovery/trending).
  ///
  /// Requires authentication. Preserves DEMAND_SIGNAL_AVAILABLE = False.
  Future<DiscoveryTrendingResult> getTrending({
    DateTime? windowStart,
    DateTime? windowEnd,
    int limit = 20,
    String? category,
  }) async {
    try {
      final query = <String, dynamic>{
        'limit': '$limit',
        if (category != null && category.isNotEmpty) 'category': category,
        if (windowStart != null)
          'window_start': windowStart.toUtc().toIso8601String(),
        if (windowEnd != null)
          'window_end': windowEnd.toUtc().toIso8601String(),
      };

      final base = Uri.parse(baseUrl);
      final uri = base.replace(
        pathSegments: [
          ...base.pathSegments.where((s) => s.isNotEmpty),
          'v1',
          'discovery',
          'trending',
        ],
        queryParameters: query,
      );

      final headers = _headersFor(requireAuth: true);
      final response = await _client.get(uri, headers: headers).timeout(_timeout);

      if (response.statusCode == 200) {
        try {
          final decoded = jsonDecode(response.body) as Map<String, dynamic>;
          return DiscoveryTrendingResult.success(
            DiscoveryTrendingResponse.fromJson(decoded),
          );
        } catch (error) {
          debugPrint('Trending discovery: malformed 200 body: $error');
          return const DiscoveryTrendingResult.failure(
            DiscoverFailure.networkError,
          );
        }
      }

      final failure = _failureFor(response.statusCode);
      debugPrint(
        'Trending discovery responded ${response.statusCode}: ${response.body}',
      );
      return DiscoveryTrendingResult.failure(failure);
    } catch (error) {
      debugPrint('Discover backend unreachable during trending discovery: $error');
      return const DiscoveryTrendingResult.failure(
        DiscoverFailure.networkError,
      );
    }
  }

  /// Dispatches a batch of interaction events to POST /v1/discovery/events.
  ///
  /// Never throws. Non-blocking: failures return DiscoveryEventsResult.failure.
  Future<DiscoveryEventsResult> postEvents(
    DiscoveryEventsBatchRequest request, {
    bool isGuest = false,
  }) async {
    try {
      final effectiveGuest = isGuest || !AuthSession.isAuthenticated;
      final base = Uri.parse(baseUrl);
      final uri = base.replace(
        pathSegments: [
          ...base.pathSegments.where((s) => s.isNotEmpty),
          'v1',
          'discovery',
          'events',
        ],
      );

      final headers = <String, String>{
        'Content-Type': 'application/json',
        ..._headersFor(isGuest: effectiveGuest),
      };

      final body = jsonEncode(request.toJson());
      final response = await _client
          .post(uri, headers: headers, body: body)
          .timeout(_timeout);

      if (response.statusCode == 202 || response.statusCode == 200) {
        try {
          final decoded = jsonDecode(response.body) as Map<String, dynamic>;
          return DiscoveryEventsResult.success(
            DiscoveryEventsBatchResponse.fromJson(decoded),
          );
        } catch (error) {
          debugPrint('Discovery events: malformed 202 body: $error');
          return const DiscoveryEventsResult.failure(
            DiscoverFailure.networkError,
          );
        }
      }

      final failure = _failureFor(response.statusCode);
      debugPrint(
        'Discovery events responded ${response.statusCode}: ${response.body}',
      );
      return DiscoveryEventsResult.failure(failure);
    } catch (error) {
      debugPrint('Discover backend unreachable during events dispatch: $error');
      return const DiscoveryEventsResult.failure(DiscoverFailure.networkError);
    }
  }

  DiscoverFailure _failureFor(int statusCode) {
    switch (statusCode) {
      case 401:
        AuthSession.notifyUnauthorized();
        return DiscoverFailure.unauthorized;
      case 422:
        return DiscoverFailure.invalidInput;
      case 429:
        return DiscoverFailure.rateLimited;
      default:
        return DiscoverFailure.unknown;
    }
  }

  /// Fetches verified retailer offers for a canonical product (GET /v1/discovery/products/{product_id}/offers).
  Future<ProductOffersResult> getProductOffers({
    required String productId,
  }) async {
    try {
      final base = Uri.parse(baseUrl);
      final uri = base.replace(
        pathSegments: [
          ...base.pathSegments.where((s) => s.isNotEmpty),
          'v1',
          'discovery',
          'products',
          productId,
          'offers',
        ],
      );

      final response = await _client
          .get(uri, headers: _headersFor())
          .timeout(_timeout);

      if (response.statusCode == 200) {
        try {
          final decoded = jsonDecode(response.body) as Map<String, dynamic>;
          return ProductOffersResult.success(
            ProductOffersResponse.fromJson(decoded),
          );
        } catch (error) {
          debugPrint('Discover offers: malformed 200 body: $error');
          return const ProductOffersResult.failure(
            DiscoverFailure.networkError,
          );
        }
      }

      final failure = _failureFor(response.statusCode);
      debugPrint(
        'Discover offers responded ${response.statusCode}: ${response.body}',
      );
      return ProductOffersResult.failure(failure);
    } catch (error) {
      debugPrint('Discover backend unreachable during offers fetch: $error');
      return const ProductOffersResult.failure(DiscoverFailure.networkError);
    }
  }

  /// Builds the authorized outbound redirect URI for an offer (GET /v1/discovery/offers/{offer_id}/redirect).
  Uri getOfferRedirectUri({
    required String offerId,
    String? guestSessionId,
    String surface = 'product_offers',
    int? position,
  }) {
    final base = Uri.parse(baseUrl);
    return base.replace(
      pathSegments: [
        ...base.pathSegments.where((s) => s.isNotEmpty),
        'v1',
        'discovery',
        'offers',
        offerId,
        'redirect',
      ],
      queryParameters: {
        'surface': surface,
        if (guestSessionId != null && guestSessionId.isNotEmpty)
          'guest_session_id': guestSessionId,
        if (position != null) 'position': '$position',
      },
    );
  }

  /// Closes the underlying HTTP client.
  void dispose() => _client.close();
}

/// Generates a stable RFC 4122 compliant UUIDv4 identifier for telemetry events.
String newDiscoveryEventId() {
  final random = Random.secure();
  final bytes = List<int>.generate(16, (_) => random.nextInt(256));
  bytes[6] = (bytes[6] & 0x0F) | 0x40; // Version 4
  bytes[8] = (bytes[8] & 0x3F) | 0x80; // Variant 1
  String hex(int v) => v.toRadixString(16).padLeft(2, '0');
  final h = bytes.map(hex).join();
  return '${h.substring(0, 8)}-${h.substring(8, 12)}-'
      '${h.substring(12, 16)}-${h.substring(16, 20)}-${h.substring(20)}';
}

