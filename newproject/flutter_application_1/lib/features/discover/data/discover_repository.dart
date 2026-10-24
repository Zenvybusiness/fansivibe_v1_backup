import 'package:fansivibe/features/discover/data/discover_client.dart';
import 'package:fansivibe/features/discover/data/discover_models.dart';
import 'package:fansivibe/features/discover/data/guest_session_manager.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';

/// Abstract contract for M14 Discover data operations.
///
/// The [DiscoverRepository] is the single source consumed by the
/// Discover / Look Details surfaces: the backend `/v1/looks` collection
/// is authoritative. There is deliberately no local-service merge and no
/// mock fallback — a fabricated look would corrupt the code-addressed
/// detail surface. Failures travel as typed results; the caller keeps
/// its rows and allows a retry.
abstract class DiscoverRepository {
  /// Returns one cursor page of the ranked feed (#43 `GET /v1/looks`).
  ///
  /// Null filters are omitted (`all` selections); [cursor] is the opaque
  /// token from the previous page (null for the first page). Server
  /// order is never re-sorted in this layer.
  Future<DiscoverFeedResult> getLookFeed({
    String? occasion,
    String? style,
    String? fit,
    String? cursor,
    int? limit,
  });

  /// Returns one catalog look by its backend code (#44).
  ///
  /// [lookId] is the backend code verbatim — never a local mock ID.
  Future<LookDetailResult> getLookDetail({required String lookId});

  /// Returns one cursor page of the For You feed (M12 P1).
  ///
  /// Server order and the `personalized` flag travel verbatim.
  Future<ForYouFeedResult> getForYouFeed({String? cursor, int? limit});

  /// Returns personalized catalog recommendations (GET /v1/discovery/for-you).
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
  });

  /// Returns compatible complete looks (GET /v1/discovery/looks/complete).
  Future<CompleteLooksDiscoveryResult> getCompleteLooks({
    int limit = 10,
    double? maxBudget,
    String? targetOccasion,
    String? targetAesthetic,
    String? anchorProductId,
    String? anchorWardrobeItemId,
    bool allowWardrobe = true,
    bool includeSynthetic = true,
  });

  /// Returns catalog trend intelligence (GET /v1/discovery/trending).
  Future<DiscoveryTrendingResult> getTrending({
    DateTime? windowStart,
    DateTime? windowEnd,
    int limit = 20,
    String? category,
  });

  /// Dispatches a batch of interaction events for persistence (POST /v1/discovery/events).
  ///
  /// Non-blocking telemetry ingress. Safe for both authenticated users and guests.
  Future<DiscoveryEventsResult> recordEvents(
    List<DiscoveryEventItem> events, {
    String? guestSessionId,
  });

  /// Returns verified retailer offers for a product (GET /v1/discovery/products/{product_id}/offers).
  Future<ProductOffersResult> getProductOffers(String productId);

  /// Returns the authorized server redirect URI for an offer.
  Uri getOfferRedirectUri({
    required String offerId,
    String? guestSessionId,
    String surface = 'product_offers',
    int? position,
  });
}

/// Backend implementation of [DiscoverRepository].
class DiscoverRepositoryImpl implements DiscoverRepository {
  /// Creates a [DiscoverRepositoryImpl] with an optional client for
  /// testing. Without a client, uses the default [DiscoverClient].
  DiscoverRepositoryImpl({DiscoverClient? client})
    : _client = client ?? DiscoverClient();

  final DiscoverClient _client;

  @override
  Future<DiscoverFeedResult> getLookFeed({
    String? occasion,
    String? style,
    String? fit,
    String? cursor,
    int? limit,
  }) {
    // Verbatim passthrough: ranking, cursor windows, and envelope
    // semantics stay server-authoritative. Failures travel typed.
    return _client.getLookFeed(
      occasion: occasion,
      style: style,
      fit: fit,
      cursor: cursor,
      limit: limit,
    );
  }

  @override
  Future<LookDetailResult> getLookDetail({required String lookId}) {
    // Verbatim passthrough of the backend code: no ID translation, no
    // local mock IDs, no fabrication on failure.
    return _client.getLookDetail(lookId: lookId);
  }

  @override
  Future<ForYouFeedResult> getForYouFeed({String? cursor, int? limit}) {
    // Verbatim passthrough: personalization stays server-authoritative.
    // Failures travel typed — never the /v1/looks feed, never mocks.
    return _client.getForYouFeed(cursor: cursor, limit: limit);
  }

  @override
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
  }) {
    return _client.getForYouRecommendations(
      page: page,
      pageSize: pageSize,
      q: q,
      categories: categories,
      excludeCategories: excludeCategories,
      brands: brands,
      excludeBrands: excludeBrands,
      minPrice: minPrice,
      maxPrice: maxPrice,
      currency: currency,
      colors: colors,
      materials: materials,
      fits: fits,
      silhouettes: silhouettes,
      inStockOnly: inStockOnly,
      includeSynthetic: includeSynthetic,
      isGuest: isGuest,
    );
  }

  @override
  Future<CompleteLooksDiscoveryResult> getCompleteLooks({
    int limit = 10,
    double? maxBudget,
    String? targetOccasion,
    String? targetAesthetic,
    String? anchorProductId,
    String? anchorWardrobeItemId,
    bool allowWardrobe = true,
    bool includeSynthetic = true,
  }) {
    return _client.getCompleteLooks(
      limit: limit,
      maxBudget: maxBudget,
      targetOccasion: targetOccasion,
      targetAesthetic: targetAesthetic,
      anchorProductId: anchorProductId,
      anchorWardrobeItemId: anchorWardrobeItemId,
      allowWardrobe: allowWardrobe,
      includeSynthetic: includeSynthetic,
    );
  }

  @override
  Future<DiscoveryTrendingResult> getTrending({
    DateTime? windowStart,
    DateTime? windowEnd,
    int limit = 20,
    String? category,
  }) {
    return _client.getTrending(
      windowStart: windowStart,
      windowEnd: windowEnd,
      limit: limit,
      category: category,
    );
  }

  @override
  Future<DiscoveryEventsResult> recordEvents(
    List<DiscoveryEventItem> events, {
    String? guestSessionId,
  }) {
    final isAuth = AuthSession.isAuthenticated;
    final effectiveGuestSessionId =
        isAuth ? null : (guestSessionId ?? GuestSessionManager.getSessionId());
    return _client.postEvents(
      DiscoveryEventsBatchRequest(
        guestSessionId: effectiveGuestSessionId,
        events: events,
      ),
      isGuest: !isAuth,
    );
  }

  @override
  Future<ProductOffersResult> getProductOffers(String productId) {
    return _client.getProductOffers(productId: productId);
  }

  @override
  Uri getOfferRedirectUri({
    required String offerId,
    String? guestSessionId,
    String surface = 'product_offers',
    int? position,
  }) {
    final effectiveGuestSessionId = AuthSession.isAuthenticated
        ? null
        : (guestSessionId ?? GuestSessionManager.getSessionId());
    return _client.getOfferRedirectUri(
      offerId: offerId,
      guestSessionId: effectiveGuestSessionId,
      surface: surface,
      position: position,
    );
  }
}
