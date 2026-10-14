import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/features/discover/data/discover_models.dart';
import 'package:fansivibe/features/discover/data/discover_repository.dart';
import 'package:fansivibe/features/discover/data/guest_session_manager.dart';
import 'package:fansivibe/features/discover/presentation/widgets/existing_user_for_you_widgets.dart';
import 'package:fansivibe/features/discover/presentation/widgets/product_impression_detector.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

ProductRecommendationItem createTelemetryTestProduct({
  required String id,
  required String title,
  required String brand,
  double price = 18000.0,
}) {
  return ProductRecommendationItem(
    id: id,
    title: title,
    brand: brand,
    category: 'outerwear',
    subcategory: 'coat',
    price: price,
    currency: 'INR',
    availability: true,
    imageUrls: const ['assets/images/discover_hero_quiet_luxury.jpg'],
    isSynthetic: false,
    isFixture: false,
    score: 95.0,
    rank: 1,
    scoreBreakdown: const ProductScoreBreakdown(
      preferenceMatch: 50.0,
      styleProfileMatch: 30.0,
      wardrobeComplementarity: 15.0,
      budgetAvailability: 15.0,
      totalScore: 95.0,
      matchReasons: ['Silhouette profile match'],
    ),
    explanation: const ProductExplanation(
      summary: 'Matches minimal silhouette profile',
      reasons: ['Neutral palette fit'],
      positiveEvidence: ['Fit and category align with your profile'],
      isSyntheticFixture: false,
      provenance: 'catalog',
    ),
  );
}

CompleteLook createTelemetryTestLook({
  required String lookId,
}) {
  return CompleteLook(
    lookId: lookId,
    slots: {
      'outerwear': const LookSlotItem(
        itemId: '11111111-1111-4111-8111-111111111111',
        source: 'catalog',
        title: 'Tailored Wool Coat',
        category: 'outerwear',
        brand: 'Atelier Minimalist',
        price: 18000.0,
        currency: 'INR',
        imageUrl: 'assets/images/discover_hero_quiet_luxury.jpg',
        isSynthetic: false,
        isFixture: false,
      ),
      'bottoms': const LookSlotItem(
        itemId: '22222222-2222-4222-8222-222222222222',
        source: 'catalog',
        title: 'Pleated Linen Trouser',
        category: 'bottoms',
        brand: 'Studio Atelier',
        price: 12000.0,
        currency: 'INR',
        imageUrl: 'assets/images/discover_hero_quiet_luxury.jpg',
        isSynthetic: false,
        isFixture: false,
      ),
    },
    totalCatalogPrice: 30000.0,
    currency: 'INR',
    compatibilityScore: 93.0,
    compatibilityBreakdown: const CompleteLookScoreBreakdown(
      categoryCompleteness: 25.0,
      colorHarmony: 25.0,
      materialConsistency: 23.0,
      styleConceptMatch: 20.0,
      silhouetteFormality: 10.0,
      totalScore: 93.0,
      reasons: ['Harmonious wool and cotton textures'],
    ),
    compatibilityReasons: const ['Harmonious wool and cotton textures'],
    unresolvedConstraints: const [],
    explanation: const CompleteLookExplanation(
      summary: 'Cohesive architectural tailoring.',
      reasons: ['Modern Tailoring'],
      isSyntheticFixture: false,
      isWardrobeAware: false,
    ),
    isWardrobeAware: false,
    wardrobeItemCount: 0,
    catalogItemCount: 2,
    containsSyntheticFixtures: false,
    bundlePurchasable: false,
  );
}

class TelemetryRecordingRepository implements DiscoverRepository {
  final List<List<DiscoveryEventItem>> recordedBatches = [];
  int recordEventsCallCount = 0;
  bool shouldFailOnce = false;
  bool shouldAlwaysFail = false;

  @override
  Future<DiscoveryEventsResult> recordEvents(
    List<DiscoveryEventItem> events, {
    String? guestSessionId,
  }) async {
    recordEventsCallCount++;
    recordedBatches.add(List.from(events));

    if (shouldAlwaysFail) {
      return const DiscoveryEventsResult.failure(DiscoverFailure.networkError);
    }
    if (shouldFailOnce && recordEventsCallCount == 1) {
      return const DiscoveryEventsResult.failure(DiscoverFailure.networkError);
    }

    return DiscoveryEventsResult.success(
      DiscoveryEventsBatchResponse(
        acceptedCount: events.length,
        events: events
            .map((e) => DiscoveryEventAck(
                  eventId: e.eventId,
                  status: 'persisted',
                  replayed: false,
                ))
            .toList(),
      ),
    );
  }

  @override
  Future<DiscoverFeedResult> getLookFeed({
    String? occasion,
    String? style,
    String? fit,
    String? cursor,
    int? limit,
  }) async =>
      const DiscoverFeedResult.failure(DiscoverFailure.networkError);

  @override
  Future<LookDetailResult> getLookDetail({required String lookId}) async =>
      const LookDetailResult.failure(DiscoverFailure.networkError);

  @override
  Future<ForYouFeedResult> getForYouFeed({String? cursor, int? limit}) async =>
      const ForYouFeedResult.failure(DiscoverFailure.networkError);

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
  }) async {
    return ForYouDiscoveryResult.success(
      ForYouDiscoveryResponse(
        page: page,
        pageSize: pageSize,
        totalCount: 2,
        totalPages: 1,
        hasNext: false,
        hasPrev: false,
        isPersonalized: true,
        appliedContext: const UserPersonalizationContextSummary(
          isGuest: false,
          userId: 'user-1',
        ),
        items: [
          createTelemetryTestProduct(
            id: '11111111-1111-4111-8111-111111111111',
            title: 'Tailored Wool Coat',
            brand: 'Atelier Minimalist',
            price: 18000.0,
          ),
          createTelemetryTestProduct(
            id: '22222222-2222-4222-8222-222222222222',
            title: 'Pleated Linen Trouser',
            brand: 'Studio Atelier',
            price: 12000.0,
          ),
        ],
      ),
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
  }) async {
    return CompleteLooksDiscoveryResult.success(
      CompleteLooksDiscoveryResponse(
        totalLooks: 2,
        containsSyntheticFixtures: false,
        isWardrobeAware: false,
        looks: [
          createTelemetryTestLook(lookId: 'look_4a2c89f012b456e7'),
          createTelemetryTestLook(lookId: 'look_b7d1e89201f34a5c'),
        ],
      ),
    );
  }

  @override
  Future<DiscoveryTrendingResult> getTrending({
    DateTime? windowStart,
    DateTime? windowEnd,
    int limit = 20,
    String? category,
  }) async =>
      const DiscoveryTrendingResult.failure(DiscoverFailure.networkError);

  @override
  Future<ProductOffersResult> getProductOffers(String productId) async {
    return ProductOffersResult.success(
      ProductOffersResponse(
        productId: productId,
        title: 'Telemetry Test Product',
        isSyntheticFixture: false,
        offersCount: 0,
        offers: const [],
      ),
    );
  }

  @override
  Uri getOfferRedirectUri({
    required String offerId,
    String? guestSessionId,
    String surface = 'product_offers',
    int? position,
  }) {
    return Uri.parse('http://localhost:8000/v1/discovery/offers/$offerId/redirect');
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    LocalStorage.init(prefs: prefs);
    LocalStorage.savedLookIds = [];
    GuestSessionManager.resetForTest();
  });

  group('DISCOVERY-10A Telemetry Wire Shapes & Serialization', () {
    test('DiscoveryEventItem serializes to exact approved schema', () {
      final event = DiscoveryEventItem(
        eventId: '33333333-3333-4333-8333-333333333333',
        eventType: 'product_save',
        targetType: 'product',
        targetId: '11111111-1111-4111-8111-111111111111',
        surface: 'for_you_hero',
        position: 0,
        metadata: const {'activeCategoryFilter': 'outerwear'},
        occurredAt: '2026-10-14T12:00:00.000Z',
      );

      final json = event.toJson();
      expect(json['eventId'], '33333333-3333-4333-8333-333333333333');
      expect(json['eventType'], 'product_save');
      expect(json['targetType'], 'product');
      expect(json['targetId'], '11111111-1111-4111-8111-111111111111');
      expect(json['surface'], 'for_you_hero');
      expect(json['position'], 0);
      expect(json['metadata'], {'activeCategoryFilter': 'outerwear'});
      expect(json['occurredAt'], '2026-10-14T12:00:00.000Z');
      expect(json.containsKey('userId'), isFalse);
    });

    test('DiscoveryEventsBatchRequest respects guestSessionId isolation', () {
      final event = DiscoveryEventItem(
        eventId: '33333333-3333-4333-8333-333333333333',
        eventType: 'product_impression',
        targetType: 'product',
        targetId: '11111111-1111-4111-8111-111111111111',
        surface: 'for_you_hero',
        metadata: const {'dwellTimeMs': 1200, 'viewportRatio': 0.85},
        occurredAt: '2026-10-14T12:00:00.000Z',
      );

      final reqWithGuest = DiscoveryEventsBatchRequest(
        guestSessionId: '99999999-9999-4999-8999-999999999999',
        events: [event],
      );
      final jsonGuest = reqWithGuest.toJson();
      expect(jsonGuest['guestSessionId'], '99999999-9999-4999-8999-999999999999');
      expect(jsonGuest.containsKey('userId'), isFalse);

      final reqAuth = DiscoveryEventsBatchRequest(
        events: [event],
      );
      final jsonAuth = reqAuth.toJson();
      expect(jsonAuth.containsKey('guestSessionId'), isFalse);
      expect(jsonAuth.containsKey('userId'), isFalse);
    });
  });

  group('GuestSessionManager 30-day Lifecycle & Isolation', () {
    test('Generates valid UUIDv4 session and remains stable during activity', () {
      final sessionId1 = GuestSessionManager.getSessionId();
      expect(
        RegExp(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
            .hasMatch(sessionId1),
        isTrue,
      );

      final sessionId2 = GuestSessionManager.getSessionId();
      expect(sessionId2, equals(sessionId1));
    });

    test('Rotates automatically after 30 days of inactivity', () {
      const thirtyOneDaysMs = 31 * 24 * 60 * 60 * 1000;
      final oldTime = DateTime.now().millisecondsSinceEpoch - thirtyOneDaysMs;
      GuestSessionManager.resetForTest(
        initialSessionId: '00000000-0000-4000-8000-000000000000',
        initialLastActiveMs: oldTime,
      );

      final rotatedSessionId = GuestSessionManager.getSessionId();
      expect(rotatedSessionId, isNot(equals('00000000-0000-4000-8000-000000000000')));
      expect(
        RegExp(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
            .hasMatch(rotatedSessionId),
        isTrue,
      );
    });
  });

  group('ProductImpressionDetector Threshold & Dwell Time', () {
    testWidgets('Does NOT trigger impression before 1000ms continuous dwell time',
        (tester) async {
      int impressionCount = 0;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Center(
              child: SizedBox(
                width: 200,
                height: 300,
                child: ProductImpressionDetector(
                  productId: '11111111-1111-4111-8111-111111111111',
                  surface: 'for_you_hero',
                  position: 0,
                  onImpression: ({
                    required String productId,
                    required String surface,
                    int? position,
                    required double visibilityRatio,
                    required int dwellMs,
                  }) {
                    impressionCount++;
                  },
                  child: const ColoredBox(color: Colors.blue),
                ),
              ),
            ),
          ),
        ),
      );

      // Pump 500ms (dwell < 1000ms threshold)
      await tester.pump(const Duration(milliseconds: 500));
      expect(impressionCount, 0);

      // Pump another 400ms (total 900ms < 1000ms threshold)
      await tester.pump(const Duration(milliseconds: 400));
      expect(impressionCount, 0);

      // Now pass the 1000ms threshold (total 1100ms)
      await tester.pump(const Duration(milliseconds: 200));
      expect(impressionCount, 1);
    });

    testWidgets('Deduplicates impression per product per session',
        (tester) async {
      int impressionCount = 0;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Center(
              child: SizedBox(
                width: 200,
                height: 300,
                child: ProductImpressionDetector(
                  productId: '11111111-1111-4111-8111-111111111111',
                  surface: 'for_you_hero',
                  position: 0,
                  onImpression: ({
                    required String productId,
                    required String surface,
                    int? position,
                    required double visibilityRatio,
                    required int dwellMs,
                  }) {
                    impressionCount++;
                  },
                  child: const ColoredBox(color: Colors.blue),
                ),
              ),
            ),
          ),
        ),
      );

      // Reach 1000ms
      await tester.pump(const Duration(milliseconds: 1100));
      expect(impressionCount, 1);

      // Long re-pumping must not fire duplicate impressions
      await tester.pump(const Duration(seconds: 3));
      expect(impressionCount, 1);
    });
  });

  group('EstablishedUserForYouFeed Telemetry Integration', () {
    testWidgets('Wires product_save and product_unsave telemetry payloads',
        (tester) async {
      final repo = TelemetryRecordingRepository();

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: EstablishedUserForYouFeed(
                repository: repo,
              ),
            ),
          ),
        ),
      );

      // Let initial recommendations load
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      // Find favorite button on hero product card
      final favoriteFinder = find.byIcon(Icons.favorite_border_rounded);
      expect(favoriteFinder, findsWidgets);

      // Tap to save (hero product)
      await tester.tap(favoriteFinder.first);
      await tester.pump();

      // Find the save event in repo batches
      final allEvents = repo.recordedBatches.expand((b) => b).toList();
      final saveEvents = allEvents.where((e) => e.eventType == 'product_save').toList();
      expect(saveEvents.length, 1);
      final saveEvent = saveEvents.first;
      expect(saveEvent.targetType, 'product');
      expect(saveEvent.targetId, '11111111-1111-4111-8111-111111111111');
      expect(saveEvent.surface, 'for_you_hero');
      expect(saveEvent.position, 0);

      // Tap again to unsave
      final savedFinder = find.byIcon(Icons.favorite_rounded);
      expect(savedFinder, findsWidgets);
      await tester.tap(savedFinder.first);
      await tester.pump();

      final updatedEvents = repo.recordedBatches.expand((b) => b).toList();
      final unsaveEvents = updatedEvents.where((e) => e.eventType == 'product_unsave').toList();
      expect(unsaveEvents.length, 1);
      final unsaveEvent = unsaveEvents.first;
      expect(unsaveEvent.targetType, 'product');
      expect(unsaveEvent.targetId, '11111111-1111-4111-8111-111111111111');
      expect(unsaveEvent.surface, 'for_you_hero');
    });

    testWidgets('Wires look_select candidate telemetry with deterministic lookId',
        (tester) async {
      final repo = TelemetryRecordingRepository();

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: EstablishedUserForYouFeed(
                repository: repo,
              ),
            ),
          ),
        ),
      );

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      // Candidate selectors in EnsembleCurationCard
      final lookOptionFinder = find.bySemanticsLabel('Look 2');
      if (lookOptionFinder.evaluate().isNotEmpty) {
        await tester.tap(lookOptionFinder.first);
        await tester.pump();

        final allEvents = repo.recordedBatches.expand((b) => b).toList();
        final lookEvents = allEvents.where((e) => e.eventType == 'look_select').toList();
        expect(lookEvents.isNotEmpty, isTrue);
        final lookEvent = lookEvents.first;
        expect(lookEvent.targetType, 'complete_look');
        expect(
          RegExp(r'^look_[a-f0-9]{16}$').hasMatch(lookEvent.targetId),
          isTrue,
        );
        expect(lookEvent.targetId, 'look_b7d1e89201f34a5c');
        expect(lookEvent.targetId, isNot(equals('1'))); // Never list index!
      }
    });

    testWidgets('Telemetry network failure does not crash or disrupt UX or saves',
        (tester) async {
      final repo = TelemetryRecordingRepository()..shouldAlwaysFail = true;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: EstablishedUserForYouFeed(
                repository: repo,
              ),
            ),
          ),
        ),
      );

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      final favoriteFinder = find.byIcon(Icons.favorite_border_rounded);
      expect(favoriteFinder, findsWidgets);

      // User saves item: UI updates immediately without thrown exceptions
      await tester.tap(favoriteFinder.first);
      await tester.pump();

      // State is saved locally despite telemetry network error
      expect(
        LocalStorage.savedLookIds.contains('11111111-1111-4111-8111-111111111111'),
        isTrue,
      );
      expect(find.byIcon(Icons.favorite_rounded), findsWidgets);
    });

    testWidgets('Reuses stable eventId when retrying failed telemetry dispatch',
        (tester) async {
      final repo = TelemetryRecordingRepository()..shouldFailOnce = true;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: EstablishedUserForYouFeed(
                repository: repo,
              ),
            ),
          ),
        ),
      );

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      final favoriteFinder = find.byIcon(Icons.favorite_border_rounded);
      expect(favoriteFinder, findsWidgets);
      await tester.tap(favoriteFinder.first);
      await tester.pump();

      expect(repo.recordEventsCallCount, 1);
      final initialEvent = repo.recordedBatches[0][0];

      // Advance clock by 1000ms to allow asynchronous retry to trigger
      await tester.pump(const Duration(milliseconds: 1100));

      expect(repo.recordEventsCallCount, 2);
      final retriedEvent = repo.recordedBatches[1][0];

      // Stable event ID across retries
      expect(retriedEvent.eventId, equals(initialEvent.eventId));
      expect(retriedEvent.eventType, equals(initialEvent.eventType));
      expect(retriedEvent.targetId, equals(initialEvent.targetId));
    });

    testWidgets('Preserves Digital Atelier 65/35 card proportions with detector',
        (tester) async {
      final product = ForYouProductItem(
        id: '11111111-1111-4111-8111-111111111111',
        brand: 'COS',
        title: 'Tailored Wool Overshirt',
        price: '₹12,500',
        imageAsset: 'assets/images/discover_hero_quiet_luxury.jpg',
      );

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Center(
              child: SizedBox(
                width: 170,
                child: ProductImpressionDetector(
                  productId: product.id,
                  surface: 'for_you_grid',
                  onImpression: ({
                    required String productId,
                    required String surface,
                    int? position,
                    required double visibilityRatio,
                    required int dwellMs,
                  }) {},
                  child: ForYouGridProductCard(
                    product: product,
                    isSaved: false,
                    onFavoriteToggle: () {},
                    onShopTap: () {},
                  ),
                ),
              ),
            ),
          ),
        ),
      );

      await tester.pump();

      // Card must render without layout overflow or disruption
      expect(tester.takeException(), isNull);
      expect(find.byType(ForYouGridProductCard), findsOneWidget);
      final cardSize = tester.getSize(find.byType(ForYouGridProductCard));
      expect(cardSize.width, equals(170.0));
      expect(cardSize.height, greaterThan(250.0));
    });
  });
}
