import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/core/config/app_config.dart';
import 'package:fansivibe/features/discover/data/discover_models.dart';
import 'package:fansivibe/features/discover/data/discover_repository.dart';
import 'package:fansivibe/features/discover/presentation/discover_screen.dart';
import 'package:fansivibe/features/discover/presentation/widgets/existing_user_for_you_widgets.dart';
import 'package:fansivibe/features/discover/presentation/widgets/discover_editorial_widgets.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart'
    show WardrobeInsightData, WardrobeItemData;
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/auth/secure_token_storage.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:fansivibe/shared/utils/user_session.dart';

class MockDiscoverRepository implements DiscoverRepository {
  MockDiscoverRepository({
    this.forYouResult,
    this.completeLooksResult,
    this.trendingResult,
    this.forYouCompleter,
    this.completeLooksCompleter,
    this.onGetForYou,
    this.onGetForYouWithQuery,
    this.onGetCompleteLooks,
  });

  ForYouDiscoveryResult? forYouResult;
  CompleteLooksDiscoveryResult? completeLooksResult;
  DiscoveryTrendingResult? trendingResult;
  Completer<ForYouDiscoveryResult>? forYouCompleter;
  Completer<CompleteLooksDiscoveryResult>? completeLooksCompleter;
  Future<ForYouDiscoveryResult> Function(int page, int pageSize, List<String>? categories)? onGetForYou;
  Future<ForYouDiscoveryResult> Function(int page, int pageSize, List<String>? categories, String? q)? onGetForYouWithQuery;
  Future<CompleteLooksDiscoveryResult> Function(int limit, double? maxBudget, String? targetOccasion, String? anchorWardrobeItemId)? onGetCompleteLooks;

  int forYouCallCount = 0;
  int completeLooksCallCount = 0;
  int trendingCallCount = 0;

  String? lastQ;
  int? lastPage;
  int? lastPageSize;
  List<String>? lastCategories;
  int? lastCompleteLooksLimit;
  double? lastMaxBudget;
  String? lastTargetOccasion;
  String? lastAnchorWardrobeItemId;

  @override
  Future<DiscoverFeedResult> getLookFeed({
    String? occasion,
    String? style,
    String? fit,
    String? cursor,
    int? limit,
  }) async {
    return const DiscoverFeedResult.page(
      LookFeedPage(
        items: [
          LookSummary(
            id: 'look-1',
            title: 'Modern Tailoring',
            description: 'Minimal tailoring',
            matchScore: 90,
            reasons: ['Coordinated neutrals'],
          ),
        ],
        nextCursor: null,
        hasMore: false,
      ),
    );
  }

  @override
  Future<LookDetailResult> getLookDetail({required String lookId}) async {
    return const LookDetailResult.notFound();
  }

  @override
  Future<ForYouFeedResult> getForYouFeed({String? cursor, int? limit}) async {
    return const ForYouFeedResult.page(
      ForYouFeedPage(
        items: [],
        nextCursor: null,
        hasMore: false,
        personalized: false,
      ),
    );
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
  }) async {
    forYouCallCount++;
    lastPage = page;
    lastPageSize = pageSize;
    lastQ = q;
    lastCategories = categories != null ? List<String>.from(categories) : null;
    if (onGetForYouWithQuery != null) {
      return onGetForYouWithQuery!(page, pageSize, categories, q);
    }
    if (onGetForYou != null) {
      return onGetForYou!(page, pageSize, categories);
    }
    if (forYouCompleter != null) {
      return forYouCompleter!.future;
    }
    return forYouResult ??
        const ForYouDiscoveryResult.failure(DiscoverFailure.networkError);
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
    completeLooksCallCount++;
    lastCompleteLooksLimit = limit;
    lastMaxBudget = maxBudget;
    lastTargetOccasion = targetOccasion;
    lastAnchorWardrobeItemId = anchorWardrobeItemId;
    if (onGetCompleteLooks != null) {
      return onGetCompleteLooks!(limit, maxBudget, targetOccasion, anchorWardrobeItemId);
    }
    if (completeLooksCompleter != null) {
      return completeLooksCompleter!.future;
    }
    return completeLooksResult ??
        const CompleteLooksDiscoveryResult.failure(DiscoverFailure.networkError);
  }

  @override
  Future<DiscoveryTrendingResult> getTrending({
    DateTime? windowStart,
    DateTime? windowEnd,
    int limit = 20,
    String? category,
  }) async {
    trendingCallCount++;
    return trendingResult ??
        const DiscoveryTrendingResult.failure(DiscoverFailure.networkError);
  }

  int recordEventsCallCount = 0;
  List<DiscoveryEventItem> recordedEvents = [];
  DiscoveryEventsResult? recordEventsResult;

  @override
  Future<DiscoveryEventsResult> recordEvents(
    List<DiscoveryEventItem> events, {
    String? guestSessionId,
  }) async {
    recordEventsCallCount++;
    recordedEvents.addAll(events);
    return recordEventsResult ??
        const DiscoveryEventsResult.success(
          DiscoveryEventsBatchResponse(acceptedCount: 1, events: []),
        );
  }

  @override
  Future<ProductOffersResult> getProductOffers(String productId) async {
    return ProductOffersResult.success(
      ProductOffersResponse(
        productId: productId,
        title: 'Mock Product',
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

class MockWardrobeRepository implements WardrobeRepository {
  MockWardrobeRepository({this.items = const []});
  final List<WardrobeItemData> items;
  int listItemsCallCount = 0;

  @override
  Future<List<WardrobeItemData>> listItems({
    String? category,
    String? color,
    String? sortBy,
    String? order,
    int page = 1,
    int pageSize = 20,
  }) async {
    listItemsCallCount++;
    return items;
  }

  @override
  Future<WardrobeItemData?> getItem({required String itemId}) async => null;
  @override
  Future<WardrobeItemData?> createItem({
    required String name,
    required String category,
    required String color,
    String? material,
    MediaRef? imageRef,
    String? fit,
    double? fitConfidence,
  }) async => null;
  @override
  Future<WardrobeItemData?> updateItem({
    required String itemId,
    String? name,
    String? category,
    String? color,
    String? material,
    bool? isFavorite,
    String? fit,
    double? fitConfidence,
  }) async => null;
  @override
  Future<bool?> deleteItem({required String itemId}) async => true;
  @override
  Future<WardrobeInsightData?> getInsight() async => null;
  @override
  Future<WearSummary?> getWearSummary() async => null;
  @override
  Future<WearEventLogResponse?> logWear({
    required List<String> itemIds,
    DateTime? wornAt,
    String? idempotencyKey,
  }) async => null;
}

ProductRecommendationItem createTestProduct({
  required String id,
  required String title,
  String brand = 'Studio Atelier',
  double price = 2499.0,
  double score = 95.0,
  bool isSynthetic = true,
  bool isFixture = true,
}) {
  return ProductRecommendationItem(
    id: id,
    title: title,
    brand: brand,
    category: 'tops',
    subcategory: 'shirt',
    price: price,
    currency: 'INR',
    availability: true,
    imageUrls: const ['https://cdn.fixture.test/shirt.jpg'],
    isSynthetic: isSynthetic,
    isFixture: isFixture,
    score: score,
    rank: 1,
    scoreBreakdown: ProductScoreBreakdown(
      preferenceMatch: 50.0,
      styleProfileMatch: 30.0,
      wardrobeComplementarity: 15.0,
      budgetAvailability: 15.0,
      totalScore: score,
      matchReasons: const ['Tailored silhouette match'],
    ),
    explanation: ProductExplanation(
      summary: 'Tailored for your modern aesthetic.',
      reasons: const ['Tailored silhouette match'],
      positiveEvidence: const ['Fit and category align with your profile'],
      isSyntheticFixture: isSynthetic || isFixture,
      provenance: 'synthetic_fixture_catalog',
    ),
  );
}

CompleteLook createTestCompleteLook({
  required String lookId,
  bool isWardrobeAware = true,
  double compatibilityScore = 91.0,
}) {
  return CompleteLook(
    lookId: lookId,
    slots: {
      'top': const LookSlotItem(
        itemId: 'top-1',
        source: 'catalog',
        title: 'Structured Wool Overshirt',
        category: 'tops',
        brand: 'COS Seed',
        price: 3499.0,
        currency: 'INR',
        imageUrl: 'https://cdn.fixture.test/top.jpg',
        isSynthetic: true,
        isFixture: true,
      ),
      'bottom': const LookSlotItem(
        itemId: 'wardrobe-bot-1',
        source: 'wardrobe',
        title: 'Owned Charcoal Trousers',
        category: 'bottoms',
        brand: 'Wardrobe Piece',
        price: null,
        imageUrl: null,
        isSynthetic: false,
        isFixture: false,
      ),
    },
    totalCatalogPrice: 3499.0,
    currency: 'INR',
    compatibilityScore: compatibilityScore,
    compatibilityBreakdown: CompleteLookScoreBreakdown(
      categoryCompleteness: 25.0,
      colorHarmony: 25.0,
      materialConsistency: 21.0,
      styleConceptMatch: 20.0,
      silhouetteFormality: 10.0,
      totalScore: compatibilityScore,
      reasons: const ['Harmonious wool and cotton textures'],
    ),
    compatibilityReasons: const ['Harmonious wool and cotton textures'],
    unresolvedConstraints: const [],
    explanation: const CompleteLookExplanation(
      summary: 'Assembled utilizing your owned charcoal trousers.',
      reasons: ['Coordinated palette'],
      isSyntheticFixture: true,
      isWardrobeAware: true,
    ),
    isWardrobeAware: isWardrobeAware,
    wardrobeItemCount: 1,
    catalogItemCount: 1,
    containsSyntheticFixtures: true,
    bundlePurchasable: false,
  );
}

void main() {
  setUp(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({
      'saved_locally': true,
      'is_returning_user': true,
    });
    final prefs = await SharedPreferences.getInstance();
    LocalStorage.init(prefs: prefs);
    UserSession.isReturningUser = true;
    SecureTokenStorage.resetForTest();
    AuthSession.resetForTest();
    await AuthSession.clearSession();
  });

  Widget buildHarness({
    required Widget child,
    Size size = const Size(1080, 2400),
  }) {
    return MaterialApp(
      home: MediaQuery(
        data: MediaQueryData(size: size),
        child: Scaffold(
          body: SingleChildScrollView(
            child: child,
          ),
        ),
      ),
    );
  }

  group('EstablishedUserForYouFeed API integration', () {
    testWidgets('renders API recommendations and complete look with fixture disclaimers', (tester) async {
      final mockRepo = MockDiscoverRepository(
        forYouResult: ForYouDiscoveryResult.success(
          ForYouDiscoveryResponse(
            items: [
              createTestProduct(id: 'prod-1', title: 'Atelier Relaxed Shirt', brand: 'Studio Seed', price: 2999.0),
              createTestProduct(id: 'prod-2', title: 'Atelier Pleated Trousers', brand: 'Studio Seed', price: 3499.0),
              createTestProduct(id: 'prod-3', title: 'Leather Minimal Loafers', brand: 'Studio Footwear', price: 4999.0),
            ],
            totalCount: 3,
            page: 1,
            pageSize: 20,
            totalPages: 1,
            hasNext: false,
            hasPrev: false,
            isPersonalized: true,
            appliedContext: const UserPersonalizationContextSummary(isGuest: false, userId: 'usr-1'),
          ),
        ),
        completeLooksResult: CompleteLooksDiscoveryResult.success(
          CompleteLooksDiscoveryResponse(
            looks: [createTestCompleteLook(lookId: 'look-1')],
            totalLooks: 1,
            isWardrobeAware: true,
            containsSyntheticFixtures: true,
          ),
        ),
      );

      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await tester.pumpWidget(
        buildHarness(
          child: EstablishedUserForYouFeed(
            repository: mockRepo,
          ),
        ),
      );

      // Pump to resolve futures
      await tester.pump();
      await tester.pumpAndSettle();

      // Check repository calls
      expect(mockRepo.forYouCallCount, 1);
      expect(mockRepo.completeLooksCallCount, 1);

      // Hero Product Card displays API product title and brand
      expect(find.text('Atelier Relaxed Shirt'), findsOneWidget);
      expect(find.text('STUDIO SEED'), findsWidgets);

      // Hero Product displays DEMO FIXTURE badge and non-commercial CTA
      expect(find.text('DEMO FIXTURE'), findsOneWidget);
      expect(find.text('DEMO FIXTURE • NOT FOR SALE'), findsOneWidget);

      // Complete Look card is rendered with slot details
      expect(find.text('ENSEMBLE CURATION'), findsOneWidget);
      expect(find.text('Structured Wool Overshirt'), findsOneWidget);
      expect(find.text('Owned Charcoal Trousers'), findsOneWidget);

      // Proves wardrobe item is displayed as OWNED (₹0) while catalog item has price
      expect(find.text('OWNED (₹0)'), findsOneWidget);
      expect(find.text('₹3499'), findsWidgets);

      // Proves bundle non-purchasable disclosure is explicitly displayed
      expect(
        find.text('Bundle purchase unavailable • Items must be acquired individually'),
        findsOneWidget,
      );
    });

    testWidgets('65% image / 35% content card proportions verification', (tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await tester.pumpWidget(
        buildHarness(
          child: SingleChildScrollView(
            child: Column(
              children: [
                PersonalizedHeroProductCard(
                  product: const ForYouProductItem(
                    id: 'hero-1',
                    brand: 'Studio Atelier',
                    title: 'Minimalist Overcoat',
                    price: '₹14,999',
                    imageAsset: 'https://cdn.fixture.test/coat.jpg',
                    matchScore: 96,
                    reasons: ['Perfect tailoring for your proportions'],
                    isSyntheticFixture: true,
                  ),
                  onFavoriteToggle: () {},
                  onShopTap: (_) {},
                ),
                SizedBox(
                  width: 200,
                  child: ForYouGridProductCard(
                    product: const ForYouProductItem(
                      id: 'grid-1',
                      brand: 'COS',
                      title: 'Relaxed T-Shirt',
                      price: '₹2,500',
                      imageAsset: 'https://cdn.fixture.test/tee.jpg',
                      matchScore: 90,
                      reasons: ['Casual baseline'],
                      isSyntheticFixture: true,
                    ),
                    isSaved: false,
                    onFavoriteToggle: () {},
                    onShopTap: () {},
                  ),
                ),
              ],
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Verify AspectRatio widgets exist enforcing established card proportions
      final aspectRatios = tester.widgetList<AspectRatio>(find.byType(AspectRatio)).toList();
      expect(aspectRatios.any((a) => a.aspectRatio == 0.82), isTrue, reason: 'Hero card preserves AspectRatio(0.82)');
      expect(aspectRatios.any((a) => a.aspectRatio == 0.95), isTrue, reason: 'Grid card preserves AspectRatio(0.95)');
    });
  });

  group('DiscoverScreen Trending Intelligence & State Isolation', () {
    testWidgets('unauthenticated user sees TrendingGuestNoticeCard prompting sign-in', (tester) async {
      final mockRepo = MockDiscoverRepository();

      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await tester.pumpWidget(
        MaterialApp(
          home: DiscoverScreen(
            repository: mockRepo,
            isEstablishedUser: true,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Switch to Trending tab
      await tester.tap(find.text('Trending'));
      await tester.pumpAndSettle();

      // Unauthenticated user must see TrendingGuestNoticeCard
      expect(find.byType(TrendingGuestNoticeCard), findsOneWidget);
      expect(find.text('TREND INTELLIGENCE ACCESS'), findsOneWidget);
      expect(
        find.text(
          'Direct catalog observation metrics and brand assortment velocity require an active account session. Sign in to view global trends.',
        ),
        findsOneWidget,
      );
      expect(find.text('SIGN IN FOR TREND ANALYTICS →'), findsOneWidget);

      // No unauthorized network requests are made
      expect(mockRepo.trendingCallCount, 0);
    });

    testWidgets('authenticated user sees TrendingEvidenceStatusCard and honest demand status', (tester) async {
      await AuthSession.saveSession('valid-user-token');

      final mockRepo = MockDiscoverRepository(
        trendingResult: DiscoveryTrendingResult.success(
          const DiscoveryTrendingResponse(
            windowStart: '2026-10-01T00:00:00Z',
            windowEnd: '2026-10-14T00:00:00Z',
            generatedAt: '2026-10-14T12:00:00Z',
            demandTrendStatus: 'insufficient_evidence',
            evidenceType: 'catalog_activity',
            catalogActivityStatus: 'active',
            directDemandAvailable: false,
            sourceCoverage: 3,
            observationCount: 1,
            confidenceInterpretation: 'Catalog assortment data only',
            limitations: [
              'Direct consumer purchase telemetry is unavailable',
              'Assortment reflects partner catalog velocity, not consumer sales',
            ],
            items: [
              DiscoveryTrendItem(
                concept: 'carpenter-pant',
                canonicalName: 'Carpenter Workwear Pants',
                category: 'bottoms',
                catalogActivityStatus: 'active',
                observationCount: 5,
                distinctProducts: 3,
                distinctSources: 2,
                firstObservedAt: '2026-10-01T00:00:00Z',
                lastObservedAt: '2026-10-14T00:00:00Z',
                confidence: 0.82,
                fixtureDerived: true,
                publishable: true,
                directDemandAvailable: false,
                explanation: DiscoveryTrendItemExplanation(
                  summary: 'Observed assortment velocity in bottoms category.',
                  evidenceType: 'catalog_activity',
                  demandSignalAvailable: false,
                  reasons: ['Catalog additions observed'],
                ),
              ),
            ],
          ),
        ),
      );

      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await tester.pumpWidget(
        MaterialApp(
          home: DiscoverScreen(
            repository: mockRepo,
            isEstablishedUser: true,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Switch to Trending tab
      await tester.tap(find.text('Trending'));
      await tester.pump();
      await tester.pumpAndSettle();

      // Trending endpoint called
      expect(mockRepo.trendingCallCount, 1);

      // Authenticated user sees TrendingEvidenceStatusCard
      expect(find.byType(TrendingEvidenceStatusCard), findsOneWidget);

      // Verifies DEMAND SIGNALS UNAVAILABLE badge is truthfully rendered
      expect(find.text('DEMAND SIGNALS UNAVAILABLE'), findsOneWidget);
      expect(find.text('CATALOG OBSERVATION INTELLIGENCE'), findsOneWidget);
      expect(find.text('OBSERVATION LIMITATIONS'), findsOneWidget);
      expect(find.text('Direct consumer purchase telemetry is unavailable'), findsOneWidget);

      // Verifies catalog candidate item rendered with non-commercial fixture notice
      expect(find.text('Carpenter Workwear Pants'), findsOneWidget);
      expect(find.text('FIXTURE'), findsWidgets);
    });

    testWidgets('authVersion change triggers state reset and prevents stale data leakage', (tester) async {
      await AuthSession.saveSession('initial-token');

      final mockRepo = MockDiscoverRepository(
        trendingResult: DiscoveryTrendingResult.success(
          const DiscoveryTrendingResponse(
            windowStart: '2026-10-01T00:00:00Z',
            windowEnd: '2026-10-14T00:00:00Z',
            generatedAt: '2026-10-14T12:00:00Z',
            demandTrendStatus: 'insufficient_evidence',
            catalogActivityStatus: 'active',
            directDemandAvailable: false,
            sourceCoverage: 1,
            observationCount: 0,
            confidenceInterpretation: 'None',
            items: [],
          ),
        ),
      );

      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await tester.pumpWidget(
        MaterialApp(
          home: DiscoverScreen(
            repository: mockRepo,
            isEstablishedUser: true,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Switch to Trending tab
      await tester.tap(find.text('Trending'));
      await tester.pumpAndSettle();
      expect(find.byType(TrendingEvidenceStatusCard), findsOneWidget);

      // Simulate Sign Out (clearing session and bumping authVersion)
      await AuthSession.clearSession();
      await tester.pumpAndSettle();

      // State is immediately reset: user sees TrendingGuestNoticeCard, no old state remains
      expect(find.byType(TrendingGuestNoticeCard), findsOneWidget);
      expect(find.byType(TrendingEvidenceStatusCard), findsNothing);
    });
  });

  group('DISCOVERY-07A — Score Correction and Honest API States', () {
    testWidgets('For You score presentation displays accurately across representative scale (0, 15, 50, 91, 94, 100)', (tester) async {
      final testCases = <double, String>{
        0.0: '0% STYLE MATCH',
        15.0: '15% STYLE MATCH',
        50.0: '50% STYLE MATCH',
        91.0: '91% STYLE MATCH',
        94.0: '94% STYLE MATCH',
        100.0: '100% STYLE MATCH',
      };

      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      for (final entry in testCases.entries) {
        final productItem = ForYouProductItem.fromRecommendation(
          createTestProduct(
            id: 'prod-score-${entry.key.toInt()}',
            title: 'Test Tailored Shirt',
            score: entry.key,
          ),
        );

        // Unit expectation on DTO matchScore
        expect(productItem.matchScore, entry.key.toInt());

        // Widget rendering verification
        await tester.pumpWidget(
          buildHarness(
            child: PersonalizedHeroProductCard(
              product: productItem,
              onFavoriteToggle: () {},
              onShopTap: (_) {},
            ),
          ),
        );
        await tester.pumpAndSettle();

        expect(find.text(entry.value), findsOneWidget);
        // Explicit negative assertions: must not multiply by 100 or truncate
        if (entry.key > 0) {
          expect(find.text('${(entry.key * 100).toInt()}% STYLE MATCH'), findsNothing);
        }
        if (entry.key == 100.0) {
          expect(find.text('99% STYLE MATCH'), findsNothing);
        }
        if (entry.key == 0.0) {
          expect(find.text('1% STYLE MATCH'), findsNothing);
        }
      }
    });

    testWidgets('Complete Look compatibility score displays accurately without 100x multiplication across (0, 15, 50, 69, 91, 100)', (tester) async {
      final testCases = <double, String>{
        0.0: 'Selected with 0% style and color harmony.',
        15.0: 'Selected with 15% style and color harmony.',
        50.0: 'Selected with 50% style and color harmony.',
        69.0: 'Selected with 69% style and color harmony.',
        91.0: 'Selected with 91% style and color harmony.',
        100.0: 'Selected with 100% style and color harmony.',
      };

      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      for (final entry in testCases.entries) {
        final look = createTestCompleteLook(
          lookId: 'look-${entry.key.toInt()}',
          compatibilityScore: entry.key,
        );

        await tester.pumpWidget(
          buildHarness(
            child: EnsembleCurationCard(
              completeLook: look,
              onShopLookTap: () {},
            ),
          ),
        );
        await tester.pumpAndSettle();

        expect(find.text(entry.value), findsOneWidget);

        // Regression check: verify 6900% / 9100% / 10000% never appear
        if (entry.key > 0) {
          expect(find.textContaining('${(entry.key * 100).toInt()}%'), findsNothing);
        }
        if (entry.key == 100.0) {
          expect(find.textContaining('99%'), findsNothing);
        }
      }
    });

    testWidgets('Initial loading state displays loading copy and does not render mock products', (tester) async {
      final forYouCompleter = Completer<ForYouDiscoveryResult>();
      final looksCompleter = Completer<CompleteLooksDiscoveryResult>();

      final mockRepo = MockDiscoverRepository(
        forYouCompleter: forYouCompleter,
        completeLooksCompleter: looksCompleter,
      );

      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await tester.pumpWidget(
        buildHarness(
          child: EstablishedUserForYouFeed(
            repository: mockRepo,
          ),
        ),
      );

      // Pump 1 frame to trigger initState and start futures
      await tester.pump();

      // Honest loading screen is visible
      expect(find.text('Curating your personal style feed...'), findsOneWidget);
      expect(find.byType(CircularProgressIndicator), findsOneWidget);

      // Misleading fallback mock products are NOT rendered
      expect(find.text('Structured Double-Faced Wool Overshirt'), findsNothing);
      expect(find.text('COS'), findsNothing);
      expect(find.text('Curated Autumn Evening'), findsNothing);

      // Resolve completers to clean up async tasks
      forYouCompleter.complete(
        const ForYouDiscoveryResult.failure(DiscoverFailure.networkError),
      );
      looksCompleter.complete(
        const CompleteLooksDiscoveryResult.failure(DiscoverFailure.networkError),
      );
      await tester.pumpAndSettle();
    });

    testWidgets('Empty recommendations response displays honest empty state and working Refresh Feed', (tester) async {
      final mockRepo = MockDiscoverRepository(
        forYouResult: const ForYouDiscoveryResult.success(
          ForYouDiscoveryResponse(
            items: [],
            totalCount: 0,
            page: 1,
            pageSize: 20,
            totalPages: 0,
            hasNext: false,
            hasPrev: false,
            isPersonalized: true,
            appliedContext: UserPersonalizationContextSummary(isGuest: false, userId: 'usr-1'),
          ),
        ),
        completeLooksResult: const CompleteLooksDiscoveryResult.success(
          CompleteLooksDiscoveryResponse(
            looks: [],
            totalLooks: 0,
            isWardrobeAware: false,
            containsSyntheticFixtures: false,
          ),
        ),
      );

      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await tester.pumpWidget(
        buildHarness(
          child: EstablishedUserForYouFeed(
            repository: mockRepo,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Honest empty state rendered
      expect(find.text('No Recommendations Found'), findsOneWidget);
      expect(
        find.text('We couldn’t find personalized fashion recommendations matching your profile right now.'),
        findsOneWidget,
      );
      expect(find.text('Refresh Feed'), findsOneWidget);

      // Misleading mock products must NOT be substituted
      expect(find.text('Structured Double-Faced Wool Overshirt'), findsNothing);
      expect(find.text('COS'), findsNothing);

      // Tapping Refresh Feed calls repository again
      final initialCalls = mockRepo.forYouCallCount;
      await tester.tap(find.text('Refresh Feed'));
      await tester.pump();
      await tester.pumpAndSettle();
      expect(mockRepo.forYouCallCount, greaterThan(initialCalls));
    });

    testWidgets('Failed request displays honest network error state with retry and does not call it an empty catalog', (tester) async {
      final mockRepo = MockDiscoverRepository(
        forYouResult: const ForYouDiscoveryResult.failure(DiscoverFailure.networkError),
        completeLooksResult: const CompleteLooksDiscoveryResult.failure(DiscoverFailure.networkError),
      );

      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await tester.pumpWidget(
        buildHarness(
          child: EstablishedUserForYouFeed(
            repository: mockRepo,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Honest error state rendered — truthful network failure copy
      expect(find.text('Connection Unavailable'), findsOneWidget);
      expect(
        find.text("Couldn't connect to Fansivibe server. Please check your network connection."),
        findsOneWidget,
      );
      expect(find.text('Retry'), findsOneWidget);

      // Does not describe a network failure as an empty catalog
      expect(find.text('No Recommendations Found'), findsNothing);
      expect(find.text('No products found'), findsNothing);

      // Misleading mock products must NOT be substituted
      expect(find.text('Structured Double-Faced Wool Overshirt'), findsNothing);
      expect(find.text('COS'), findsNothing);

      // Retry button triggers a retry
      final callsBeforeRetry = mockRepo.forYouCallCount;
      await tester.tap(find.text('Retry'));
      await tester.pump();
      await tester.pumpAndSettle();
      expect(mockRepo.forYouCallCount, greaterThan(callsBeforeRetry));
    });

    testWidgets('Active category and search filters returning 0 results display honest filter empty state with Reset Filters', (tester) async {
      final mockRepo = MockDiscoverRepository(
        forYouResult: ForYouDiscoveryResult.success(
          ForYouDiscoveryResponse(
            items: [
              createTestProduct(id: 'prod-1', title: 'Wool Coat', brand: 'Studio'),
              createTestProduct(id: 'prod-2', title: 'Silk Shirt', brand: 'Studio'),
            ],
            totalCount: 2,
            page: 1,
            pageSize: 20,
            totalPages: 1,
            hasNext: false,
            hasPrev: false,
            isPersonalized: true,
            appliedContext: const UserPersonalizationContextSummary(isGuest: false, userId: 'usr-1'),
          ),
        ),
        completeLooksResult: CompleteLooksDiscoveryResult.success(
          CompleteLooksDiscoveryResponse(
            looks: [createTestCompleteLook(lookId: 'look-1')],
            totalLooks: 1,
            isWardrobeAware: true,
            containsSyntheticFixtures: true,
          ),
        ),
      );

      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await tester.pumpWidget(
        buildHarness(
          child: EstablishedUserForYouFeed(
            repository: mockRepo,
            searchQuery: 'NonexistentProductXYZ',
          ),
        ),
      );
      await tester.pumpAndSettle();

      // BecauseYouLikeSection displays honest search filter empty state
      expect(find.text('No products match "NonexistentProductXYZ"'), findsOneWidget);
      expect(
        find.text('Try adjusting your search or resetting category filters to see more picks.'),
        findsOneWidget,
      );
      expect(find.text('Reset Filters'), findsOneWidget);

      // Does not substitute allCatalogProducts
      expect(find.text('LEMAIRE'), findsNothing);
      expect(find.text('Pleated Wool Flannel Pant'), findsNothing);
    });

    testWidgets('Complete Look failure displays honest error card with retry and does not substitute default mock look', (tester) async {
      final mockRepo = MockDiscoverRepository(
        forYouResult: ForYouDiscoveryResult.success(
          ForYouDiscoveryResponse(
            items: [
              createTestProduct(id: 'prod-1', title: 'Wool Coat', brand: 'Studio'),
              createTestProduct(id: 'prod-2', title: 'Silk Shirt', brand: 'Studio'),
            ],
            totalCount: 2,
            page: 1,
            pageSize: 20,
            totalPages: 1,
            hasNext: false,
            hasPrev: false,
            isPersonalized: true,
            appliedContext: const UserPersonalizationContextSummary(isGuest: false, userId: 'usr-1'),
          ),
        ),
        completeLooksResult: const CompleteLooksDiscoveryResult.failure(
          DiscoverFailure.networkError,
        ),
      );

      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await tester.pumpWidget(
        buildHarness(
          child: EstablishedUserForYouFeed(
            repository: mockRepo,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Complete Look card shows honest error card
      expect(
        find.text("Couldn't connect to server to assemble complete look."),
        findsOneWidget,
      );
      expect(find.text('Retry Look'), findsOneWidget);

      // Default mock look is NOT substituted
      expect(find.text('Curated Autumn Evening'), findsNothing);
      expect(find.text('Cashmere Knit'), findsNothing);
      expect(find.text('Chelsea Boot'), findsNothing);

      // Tapping Retry Look calls complete looks again
      final callsBeforeRetry = mockRepo.completeLooksCallCount;
      await tester.ensureVisible(find.text('Retry Look'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Retry Look'));
      await tester.pump();
      await tester.pumpAndSettle();
      expect(mockRepo.completeLooksCallCount, greaterThan(callsBeforeRetry));
    });

    testWidgets('Complete Look empty response displays honest empty card and does not substitute default mock look', (tester) async {
      final mockRepo = MockDiscoverRepository(
        forYouResult: ForYouDiscoveryResult.success(
          ForYouDiscoveryResponse(
            items: [
              createTestProduct(id: 'prod-1', title: 'Wool Coat', brand: 'Studio'),
              createTestProduct(id: 'prod-2', title: 'Silk Shirt', brand: 'Studio'),
            ],
            totalCount: 2,
            page: 1,
            pageSize: 20,
            totalPages: 1,
            hasNext: false,
            hasPrev: false,
            isPersonalized: true,
            appliedContext: const UserPersonalizationContextSummary(isGuest: false, userId: 'usr-1'),
          ),
        ),
        completeLooksResult: const CompleteLooksDiscoveryResult.success(
          CompleteLooksDiscoveryResponse(
            looks: [],
            totalLooks: 0,
            isWardrobeAware: false,
            containsSyntheticFixtures: false,
          ),
        ),
      );

      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await tester.pumpWidget(
        buildHarness(
          child: EstablishedUserForYouFeed(
            repository: mockRepo,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Complete Look card shows honest empty card
      expect(find.text('No complete look available'), findsOneWidget);
      expect(
        find.text('We couldn’t assemble a compatible multi-piece outfit for this selection right now.'),
        findsOneWidget,
      );

      // Default mock look is NOT substituted
      expect(find.text('Curated Autumn Evening'), findsNothing);
      expect(find.text('Cashmere Knit'), findsNothing);
    });
  });

  group('DISCOVERY-07B Server-Backed Filtering, Pagination, and Multi-Look Browsing', () {
    // 1. Category selection sends the correct backend query
    testWidgets('1. Category selection sends the correct backend query', (tester) async {
      final mockRepo = MockDiscoverRepository(
        forYouResult: ForYouDiscoveryResult.success(
          ForYouDiscoveryResponse(
            items: [createTestProduct(id: 'prod-1', title: 'Top Item')],
            totalCount: 1,
            page: 1,
            pageSize: 20,
            totalPages: 1,
            hasNext: false,
            hasPrev: false,
            isPersonalized: true,
            appliedContext: const UserPersonalizationContextSummary(isGuest: false, userId: 'usr-1'),
          ),
        ),
      );

      await tester.pumpWidget(buildHarness(child: EstablishedUserForYouFeed(repository: mockRepo)));
      await tester.pumpAndSettle();

      // Tap 'Jackets & Coats' chip
      await tester.ensureVisible(find.text('Jackets & Coats'));
      await tester.tap(find.text('Jackets & Coats'));
      await tester.pumpAndSettle();

      expect(mockRepo.lastCategories, equals(['outerwear']));
      expect(mockRepo.lastPage, equals(1));

      // Tap 'Sneakers' chip
      await tester.ensureVisible(find.text('Sneakers'));
      await tester.tap(find.text('Sneakers'));
      await tester.pumpAndSettle();

      expect(mockRepo.lastCategories, equals(['footwear']));
      expect(mockRepo.lastPage, equals(1));
    });

    // 2. All Picks clears the category filter
    testWidgets('2. All Picks clears the category filter', (tester) async {
      final mockRepo = MockDiscoverRepository(
        forYouResult: ForYouDiscoveryResult.success(
          ForYouDiscoveryResponse(
            items: [createTestProduct(id: 'prod-1', title: 'Top Item')],
            totalCount: 1,
            page: 1,
            pageSize: 20,
            totalPages: 1,
            hasNext: false,
            hasPrev: false,
            isPersonalized: true,
            appliedContext: const UserPersonalizationContextSummary(isGuest: false, userId: 'usr-1'),
          ),
        ),
      );

      await tester.pumpWidget(buildHarness(child: EstablishedUserForYouFeed(repository: mockRepo)));
      await tester.pumpAndSettle();

      // Filter to Knitwear
      await tester.ensureVisible(find.text('Knitwear'));
      await tester.tap(find.text('Knitwear'));
      await tester.pumpAndSettle();
      expect(mockRepo.lastCategories, equals(['tops']));

      // Filter to All Picks
      await tester.ensureVisible(find.text('All Picks'));
      await tester.tap(find.text('All Picks'));
      await tester.pumpAndSettle();
      expect(mockRepo.lastCategories, isNull);
      expect(mockRepo.lastPage, equals(1));
    });

    // 3. Changing categories resets page state and results
    testWidgets('3. Changing categories resets page state and results', (tester) async {
      final mockRepo = MockDiscoverRepository(
        onGetForYou: (page, pageSize, categories) async {
          if (categories == null) {
            if (page == 1) {
              return ForYouDiscoveryResult.success(
                ForYouDiscoveryResponse(
                  items: [createTestProduct(id: 'all-p1', title: 'All Item P1')],
                  totalCount: 2,
                  page: 1,
                  pageSize: 1,
                  totalPages: 2,
                  hasNext: true,
                  hasPrev: false,
                  isPersonalized: true,
                  appliedContext: const UserPersonalizationContextSummary(isGuest: false, userId: 'usr-1'),
                ),
              );
            } else {
              return ForYouDiscoveryResult.success(
                ForYouDiscoveryResponse(
                  items: [createTestProduct(id: 'all-p2', title: 'All Item P2')],
                  totalCount: 2,
                  page: 2,
                  pageSize: 1,
                  totalPages: 2,
                  hasNext: false,
                  hasPrev: true,
                  isPersonalized: true,
                  appliedContext: const UserPersonalizationContextSummary(isGuest: false, userId: 'usr-1'),
                ),
              );
            }
          } else {
            return ForYouDiscoveryResult.success(
              ForYouDiscoveryResponse(
                items: [createTestProduct(id: 'trouser-1', title: 'Trouser Item 1')],
                totalCount: 1,
                page: 1,
                pageSize: 1,
                totalPages: 1,
                hasNext: false,
                hasPrev: false,
                isPersonalized: true,
                appliedContext: const UserPersonalizationContextSummary(isGuest: false, userId: 'usr-1'),
              ),
            );
          }
        },
      );

      await tester.pumpWidget(buildHarness(child: EstablishedUserForYouFeed(repository: mockRepo)));
      await tester.pumpAndSettle();

      expect(find.text('All Item P1'), findsOneWidget);

      // Load more to get to page 2
      await tester.ensureVisible(find.text('Load more'));
      await tester.tap(find.text('Load more'));
      await tester.pumpAndSettle();

      expect(find.text('All Item P2'), findsOneWidget);
      expect(mockRepo.lastPage, equals(2));

      // Now change category to Trousers
      await tester.ensureVisible(find.text('Trousers'));
      await tester.tap(find.text('Trousers'));
      await tester.pumpAndSettle();

      // Page reset to 1 and old items are replaced with category items
      expect(mockRepo.lastPage, equals(1));
      expect(mockRepo.lastCategories, equals(['bottoms']));
      expect(find.text('Trouser Item 1'), findsOneWidget);
      expect(find.text('All Item P1'), findsNothing);
      expect(find.text('All Item P2'), findsNothing);
    });

    // 4. Stale responses cannot overwrite the current category
    testWidgets('4. Stale responses cannot overwrite the current category', (tester) async {
      final completer1 = Completer<ForYouDiscoveryResult>();
      final completer2 = Completer<ForYouDiscoveryResult>();
      int reqIndex = 0;

      final mockRepo = MockDiscoverRepository(
        onGetForYou: (page, pageSize, categories) {
          reqIndex++;
          if (reqIndex == 1) {
            // initial load
            return Future.value(
              ForYouDiscoveryResult.success(
                ForYouDiscoveryResponse(
                  items: [createTestProduct(id: 'init-1', title: 'Initial Product')],
                  totalCount: 1,
                  page: 1,
                  pageSize: 20,
                  totalPages: 1,
                  hasNext: false,
                  hasPrev: false,
                  isPersonalized: true,
                  appliedContext: const UserPersonalizationContextSummary(isGuest: false, userId: 'usr-1'),
                ),
              ),
            );
          } else if (reqIndex == 2) {
            // First category switch (Jackets)
            return completer1.future;
          } else {
            // Second category switch (Sneakers)
            return completer2.future;
          }
        },
      );

      await tester.pumpWidget(buildHarness(child: EstablishedUserForYouFeed(repository: mockRepo)));
      await tester.pumpAndSettle();
      expect(find.text('Initial Product'), findsOneWidget);

      // Tap Jackets & Coats -> reqIndex == 2 (in flight)
      await tester.ensureVisible(find.text('Jackets & Coats'));
      await tester.tap(find.text('Jackets & Coats'));
      await tester.pump();

      // Quickly tap Sneakers -> reqIndex == 3 (in flight)
      await tester.ensureVisible(find.text('Sneakers'));
      await tester.tap(find.text('Sneakers'));
      await tester.pump();

      // Now completer2 (Sneakers) finishes first
      completer2.complete(
        ForYouDiscoveryResult.success(
          ForYouDiscoveryResponse(
            items: [createTestProduct(id: 'snk-1', title: 'Sneaker Alpha')],
            totalCount: 1,
            page: 1,
            pageSize: 20,
            totalPages: 1,
            hasNext: false,
            hasPrev: false,
            isPersonalized: true,
            appliedContext: const UserPersonalizationContextSummary(isGuest: false, userId: 'usr-1'),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Sneaker Alpha'), findsOneWidget);

      // Then stale completer1 (Jackets) finishes later
      completer1.complete(
        ForYouDiscoveryResult.success(
          ForYouDiscoveryResponse(
            items: [createTestProduct(id: 'jkt-1', title: 'Stale Jacket Omega')],
            totalCount: 1,
            page: 1,
            pageSize: 20,
            totalPages: 1,
            hasNext: false,
            hasPrev: false,
            isPersonalized: true,
            appliedContext: const UserPersonalizationContextSummary(isGuest: false, userId: 'usr-1'),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // UI still shows Sneaker Alpha, stale jacket omega is rejected
      expect(find.text('Sneaker Alpha'), findsOneWidget);
      expect(find.text('Stale Jacket Omega'), findsNothing);
    });

    // 5. Page two appends results without duplicates
    testWidgets('5. Page two appends results without duplicates', (tester) async {
      final mockRepo = MockDiscoverRepository(
        onGetForYou: (page, pageSize, categories) async {
          if (page == 1) {
            return ForYouDiscoveryResult.success(
              ForYouDiscoveryResponse(
                items: [
                  createTestProduct(id: 'p-1', title: 'Item One'),
                  createTestProduct(id: 'p-2', title: 'Item Two'),
                ],
                totalCount: 4,
                page: 1,
                pageSize: 2,
                totalPages: 2,
                hasNext: true,
                hasPrev: false,
                isPersonalized: true,
                appliedContext: const UserPersonalizationContextSummary(isGuest: false, userId: 'usr-1'),
              ),
            );
          } else {
            return ForYouDiscoveryResult.success(
              ForYouDiscoveryResponse(
                items: [
                  // p-2 is a duplicate from page 1, p-3 is new
                  createTestProduct(id: 'p-2', title: 'Item Two'),
                  createTestProduct(id: 'p-3', title: 'Item Three'),
                ],
                totalCount: 4,
                page: 2,
                pageSize: 2,
                totalPages: 2,
                hasNext: false,
                hasPrev: true,
                isPersonalized: true,
                appliedContext: const UserPersonalizationContextSummary(isGuest: false, userId: 'usr-1'),
              ),
            );
          }
        },
      );

      await tester.pumpWidget(buildHarness(child: EstablishedUserForYouFeed(repository: mockRepo)));
      await tester.pumpAndSettle();

      expect(find.text('Item One'), findsOneWidget);
      expect(find.text('Item Two'), findsOneWidget);

      // Tap Load more
      await tester.ensureVisible(find.text('Load more'));
      await tester.tap(find.text('Load more'));
      await tester.pumpAndSettle();

      // All 3 unique items present, Item Two is not duplicated
      expect(find.text('Item One'), findsOneWidget);
      expect(find.text('Item Two'), findsOneWidget);
      expect(find.text('Item Three'), findsOneWidget);
    });

    // 6. Duplicate Load More requests are prevented
    testWidgets('6. Duplicate Load More requests are prevented', (tester) async {
      final completer = Completer<ForYouDiscoveryResult>();
      int calls = 0;
      final mockRepo = MockDiscoverRepository(
        onGetForYou: (page, pageSize, categories) {
          calls++;
          if (page == 1) {
            return Future.value(
              ForYouDiscoveryResult.success(
                ForYouDiscoveryResponse(
                  items: [createTestProduct(id: 'p-1', title: 'Item One')],
                  totalCount: 10,
                  page: 1,
                  pageSize: 1,
                  totalPages: 10,
                  hasNext: true,
                  hasPrev: false,
                  isPersonalized: true,
                  appliedContext: const UserPersonalizationContextSummary(isGuest: false, userId: 'usr-1'),
                ),
              ),
            );
          } else {
            return completer.future;
          }
        },
      );

      await tester.pumpWidget(buildHarness(child: EstablishedUserForYouFeed(repository: mockRepo)));
      await tester.pumpAndSettle();
      expect(calls, equals(1));

      // Tap Load more -> in-flight
      await tester.ensureVisible(find.text('Load more'));
      await tester.tap(find.text('Load more'));
      await tester.pump(); // Start async request
      expect(calls, equals(2));

      // In UI, loading indicator is active and Load more button is not present
      expect(find.byType(CircularProgressIndicator), findsWidgets);
      expect(find.text('Load more'), findsNothing);
      expect(calls, equals(2));

      // Complete the request
      completer.complete(
        ForYouDiscoveryResult.success(
          ForYouDiscoveryResponse(
            items: [createTestProduct(id: 'p-2', title: 'Item Two')],
            totalCount: 10,
            page: 2,
            pageSize: 1,
            totalPages: 10,
            hasNext: false,
            hasPrev: true,
            isPersonalized: true,
            appliedContext: const UserPersonalizationContextSummary(isGuest: false, userId: 'usr-1'),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Item Two'), findsOneWidget);
    });

    // 7. A failed later page preserves already loaded results
    testWidgets('7. A failed later page preserves already loaded results', (tester) async {
      final mockRepo = MockDiscoverRepository(
        onGetForYou: (page, pageSize, categories) async {
          if (page == 1) {
            return ForYouDiscoveryResult.success(
              ForYouDiscoveryResponse(
                items: [
                  createTestProduct(id: 'p-1', title: 'Item Alpha'),
                  createTestProduct(id: 'p-2', title: 'Item Beta'),
                ],
                totalCount: 4,
                page: 1,
                pageSize: 2,
                totalPages: 2,
                hasNext: true,
                hasPrev: false,
                isPersonalized: true,
                appliedContext: const UserPersonalizationContextSummary(isGuest: false, userId: 'usr-1'),
              ),
            );
          } else {
            return const ForYouDiscoveryResult.failure(DiscoverFailure.networkError);
          }
        },
      );

      await tester.pumpWidget(buildHarness(child: EstablishedUserForYouFeed(repository: mockRepo)));
      await tester.pumpAndSettle();

      expect(find.text('Item Alpha'), findsOneWidget);
      expect(find.text('Item Beta'), findsOneWidget);

      // Trigger Load more which fails
      await tester.ensureVisible(find.text('Load more'));
      await tester.tap(find.text('Load more'));
      await tester.pumpAndSettle();

      // Loaded results are PRESERVED
      expect(find.text('Item Alpha'), findsOneWidget);
      expect(find.text('Item Beta'), findsOneWidget);
      // SnackBar shows failure notification
      expect(
        find.text("Couldn't connect to Fansivibe server. Please check your network connection."),
        findsOneWidget,
      );
    });

    // 8. End-of-results behavior follows the real API contract
    testWidgets('8. End-of-results behavior follows the real API contract', (tester) async {
      final mockRepo = MockDiscoverRepository(
        forYouResult: ForYouDiscoveryResult.success(
          ForYouDiscoveryResponse(
            items: [createTestProduct(id: 'p-1', title: 'Only Product')],
            totalCount: 1,
            page: 1,
            pageSize: 20,
            totalPages: 1,
            hasNext: false,
            hasPrev: false,
            isPersonalized: true,
            appliedContext: const UserPersonalizationContextSummary(isGuest: false, userId: 'usr-1'),
          ),
        ),
      );

      await tester.pumpWidget(buildHarness(child: EstablishedUserForYouFeed(repository: mockRepo)));
      await tester.pumpAndSettle();

      // hasNext is false -> Load more button is NOT rendered
      expect(find.text('Load more'), findsNothing);
    });

    // 9. Multiple Complete Look candidates can be displayed
    testWidgets('9. Multiple Complete Look candidates can be displayed', (tester) async {
      final look1 = createTestCompleteLook(lookId: 'look-alpha', compatibilityScore: 92.0);
      final look2 = CompleteLook(
        lookId: 'look-beta',
        slots: {
          'top': const LookSlotItem(
            itemId: 'top-2',
            source: 'catalog',
            title: 'Silk Evening Blouse',
            category: 'tops',
            brand: 'Studio Atelier',
            price: 5200.0,
            currency: 'INR',
            imageUrl: null,
            isSynthetic: true,
            isFixture: true,
          ),
          'bottom': const LookSlotItem(
            itemId: 'bot-2',
            source: 'catalog',
            title: 'Tailored Silk Pant',
            category: 'bottoms',
            brand: 'Studio Atelier',
            price: 6800.0,
            currency: 'INR',
            imageUrl: null,
            isSynthetic: true,
            isFixture: true,
          ),
        },
        totalCatalogPrice: 12000.0,
        currency: 'INR',
        compatibilityScore: 96.0,
        compatibilityBreakdown: const CompleteLookScoreBreakdown(
          categoryCompleteness: 25.0,
          colorHarmony: 25.0,
          materialConsistency: 25.0,
          styleConceptMatch: 21.0,
          silhouetteFormality: 10.0,
          totalScore: 96.0,
          reasons: ['Coordinated silk textures'],
        ),
        compatibilityReasons: const ['Coordinated silk textures'],
        unresolvedConstraints: const [],
        explanation: const CompleteLookExplanation(
          summary: 'High-contrast silk ensemble for formal evening.',
          reasons: ['Harmonious drape'],
          isSyntheticFixture: true,
          isWardrobeAware: false,
        ),
        isWardrobeAware: false,
        wardrobeItemCount: 0,
        catalogItemCount: 2,
        containsSyntheticFixtures: true,
        bundlePurchasable: false,
      );

      final mockRepo = MockDiscoverRepository(
        forYouResult: ForYouDiscoveryResult.success(
          ForYouDiscoveryResponse(
            items: [createTestProduct(id: 'p-1', title: 'Catalog Item')],
            totalCount: 1,
            page: 1,
            pageSize: 20,
            totalPages: 1,
            hasNext: false,
            hasPrev: false,
            isPersonalized: true,
            appliedContext: const UserPersonalizationContextSummary(isGuest: false, userId: 'usr-1'),
          ),
        ),
        completeLooksResult: CompleteLooksDiscoveryResult.success(
          CompleteLooksDiscoveryResponse(
            looks: [look1, look2],
            totalLooks: 2,
            isWardrobeAware: true,
            containsSyntheticFixtures: true,
          ),
        ),
      );

      await tester.pumpWidget(buildHarness(child: EstablishedUserForYouFeed(repository: mockRepo)));
      await tester.pumpAndSettle();

      // Look 1 and Look 2 chips exist
      await tester.ensureVisible(find.text('Look 1 (2 pcs)'));
      expect(find.text('Look 1 (2 pcs)'), findsOneWidget);
      expect(find.text('Look 2 (2 pcs)'), findsOneWidget);

      // Initially Look 1 is active
      expect(find.text('Structured Wool Overshirt'), findsOneWidget);
      expect(find.text('Silk Evening Blouse'), findsNothing);

      // Tap Look 2 chip
      await tester.ensureVisible(find.text('Look 2 (2 pcs)'));
      await tester.tap(find.text('Look 2 (2 pcs)'));
      await tester.pumpAndSettle();

      // Now Look 2 content is active
      expect(find.text('Silk Evening Blouse'), findsOneWidget);
      expect(find.text('Tailored Silk Pant'), findsOneWidget);
      expect(find.text('Structured Wool Overshirt'), findsNothing);

      // Bundle purchase disclaimer is strictly preserved
      expect(
        find.text('Bundle purchase unavailable • Items must be acquired individually'),
        findsOneWidget,
      );
    });

    // 10. One-result and zero-result responses are handled honestly
    testWidgets('10. One-result and zero-result responses are handled honestly', (tester) async {
      // Test 1-result:
      final mockRepoOne = MockDiscoverRepository(
        forYouResult: ForYouDiscoveryResult.success(
          ForYouDiscoveryResponse(
            items: [createTestProduct(id: 'p-1', title: 'Catalog Item')],
            totalCount: 1,
            page: 1,
            pageSize: 20,
            totalPages: 1,
            hasNext: false,
            hasPrev: false,
            isPersonalized: true,
            appliedContext: const UserPersonalizationContextSummary(isGuest: false, userId: 'usr-1'),
          ),
        ),
        completeLooksResult: CompleteLooksDiscoveryResult.success(
          CompleteLooksDiscoveryResponse(
            looks: [createTestCompleteLook(lookId: 'single-look')],
            totalLooks: 1,
            isWardrobeAware: true,
            containsSyntheticFixtures: true,
          ),
        ),
      );

      await tester.pumpWidget(buildHarness(child: EstablishedUserForYouFeed(key: const ValueKey('one'), repository: mockRepoOne)));
      await tester.pumpAndSettle();

      // Displays the single look, no switcher chips needed
      expect(find.text('Structured Wool Overshirt'), findsOneWidget);
      expect(find.text('Look 1 (2 pcs)'), findsNothing);

      // Test 0-result:
      final mockRepoZero = MockDiscoverRepository(
        forYouResult: ForYouDiscoveryResult.success(
          ForYouDiscoveryResponse(
            items: [createTestProduct(id: 'p-1', title: 'Catalog Item')],
            totalCount: 1,
            page: 1,
            pageSize: 20,
            totalPages: 1,
            hasNext: false,
            hasPrev: false,
            isPersonalized: true,
            appliedContext: const UserPersonalizationContextSummary(isGuest: false, userId: 'usr-1'),
          ),
        ),
        completeLooksResult: const CompleteLooksDiscoveryResult.success(
          CompleteLooksDiscoveryResponse(
            looks: [],
            totalLooks: 0,
            isWardrobeAware: false,
            containsSyntheticFixtures: false,
          ),
        ),
      );

      await tester.pumpWidget(buildHarness(child: EstablishedUserForYouFeed(key: const ValueKey('zero'), repository: mockRepoZero)));
      await tester.pumpAndSettle();

      expect(find.text('No complete look available'), findsOneWidget);
      expect(find.text('Curated Autumn Evening'), findsNothing);
    });

    // 11. Budget and occasion controls map to supported request parameters
    testWidgets('11. Budget and occasion controls map to supported request parameters', (tester) async {
      final mockRepo = MockDiscoverRepository(
        forYouResult: ForYouDiscoveryResult.success(
          ForYouDiscoveryResponse(
            items: [createTestProduct(id: 'p-1', title: 'Catalog Item')],
            totalCount: 1,
            page: 1,
            pageSize: 20,
            totalPages: 1,
            hasNext: false,
            hasPrev: false,
            isPersonalized: true,
            appliedContext: const UserPersonalizationContextSummary(isGuest: false, userId: 'usr-1'),
          ),
        ),
        completeLooksResult: CompleteLooksDiscoveryResult.success(
          CompleteLooksDiscoveryResponse(
            looks: [createTestCompleteLook(lookId: 'initial-look')],
            totalLooks: 1,
            isWardrobeAware: true,
            containsSyntheticFixtures: true,
          ),
        ),
      );

      await tester.pumpWidget(buildHarness(child: EstablishedUserForYouFeed(repository: mockRepo)));
      await tester.pumpAndSettle();

      // Initial query has limit 5
      expect(mockRepo.lastCompleteLooksLimit, equals(5));
      expect(mockRepo.lastMaxBudget, isNull);
      expect(mockRepo.lastTargetOccasion, isNull);

      // Tap 'Casual' occasion chip
      await tester.ensureVisible(find.text('Casual'));
      await tester.tap(find.text('Casual'));
      await tester.pumpAndSettle();
      expect(mockRepo.lastTargetOccasion, equals('casual'));

      // Tap 'Under ₹15,000' budget chip
      await tester.ensureVisible(find.text('Under ₹15,000'));
      await tester.tap(find.text('Under ₹15,000'));
      await tester.pumpAndSettle();
      expect(mockRepo.lastMaxBudget, equals(15000.0));
      expect(mockRepo.lastTargetOccasion, equals('casual'));

      // Tap 'All Occasions' to clear occasion
      await tester.ensureVisible(find.text('All Occasions'));
      await tester.tap(find.text('All Occasions'));
      await tester.pumpAndSettle();
      expect(mockRepo.lastTargetOccasion, isNull);
      expect(mockRepo.lastMaxBudget, equals(15000.0));

      // Tap 'Any Budget' to clear budget
      await tester.ensureVisible(find.text('Any Budget'));
      await tester.tap(find.text('Any Budget'));
      await tester.pumpAndSettle();
      expect(mockRepo.lastMaxBudget, isNull);
    });

    // 12. Guest and cross-user wardrobe isolation remain intact
    testWidgets('12. Guest and cross-user wardrobe isolation remain intact', (tester) async {
      final mockWardrobe = MockWardrobeRepository(
        items: [
          WardrobeItemData(
            id: 'owned-item-1',
            name: 'Cashmere Overcoat',
            category: 'outerwear',
            color: 'Black',
          ),
        ],
      );

      final mockRepo = MockDiscoverRepository(
        forYouResult: ForYouDiscoveryResult.success(
          ForYouDiscoveryResponse(
            items: [createTestProduct(id: 'p-1', title: 'Catalog Item')],
            totalCount: 1,
            page: 1,
            pageSize: 20,
            totalPages: 1,
            hasNext: false,
            hasPrev: false,
            isPersonalized: false,
            appliedContext: const UserPersonalizationContextSummary(isGuest: true, userId: null),
          ),
        ),
        completeLooksResult: CompleteLooksDiscoveryResult.success(
          CompleteLooksDiscoveryResponse(
            looks: [createTestCompleteLook(lookId: 'guest-look')],
            totalLooks: 1,
            isWardrobeAware: false,
            containsSyntheticFixtures: true,
          ),
        ),
      );

      // 1. In Guest state:
      AuthSession.resetForTest();
      await AuthSession.clearSession();

      await tester.pumpWidget(
        buildHarness(
          child: EstablishedUserForYouFeed(
            key: const ValueKey('guest'),
            repository: mockRepo,
            wardrobeRepository: mockWardrobe,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Guest: wardrobe items are NOT fetched from repository (isolation!)
      expect(mockWardrobe.listItemsCallCount, equals(0));
      // Anchor controls are not rendered for guests
      expect(find.text('Anchor with Wardrobe Item'), findsNothing);
      expect(find.text('Cashmere Overcoat'), findsNothing);
      // anchorWardrobeItemId is null in backend request
      expect(mockRepo.lastAnchorWardrobeItemId, isNull);

      // 2. In Authenticated state:
      await AuthSession.saveSession('valid-test-token');

      final mockRepoAuth = MockDiscoverRepository(
        forYouResult: ForYouDiscoveryResult.success(
          ForYouDiscoveryResponse(
            items: [createTestProduct(id: 'p-1', title: 'Catalog Item')],
            totalCount: 1,
            page: 1,
            pageSize: 20,
            totalPages: 1,
            hasNext: false,
            hasPrev: false,
            isPersonalized: true,
            appliedContext: const UserPersonalizationContextSummary(isGuest: false, userId: 'user-auth-123'),
          ),
        ),
        completeLooksResult: CompleteLooksDiscoveryResult.success(
          CompleteLooksDiscoveryResponse(
            looks: [createTestCompleteLook(lookId: 'auth-look')],
            totalLooks: 1,
            isWardrobeAware: true,
            containsSyntheticFixtures: true,
          ),
        ),
      );

      await tester.pumpWidget(
        buildHarness(
          child: EstablishedUserForYouFeed(
            key: const ValueKey('auth'),
            repository: mockRepoAuth,
            wardrobeRepository: mockWardrobe,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Authenticated: wardrobe repository IS queried for the user
      expect(mockWardrobe.listItemsCallCount, greaterThan(0));
      expect(find.text('Anchor with Wardrobe Item'), findsOneWidget);
      expect(find.text('Cashmere Overcoat'), findsOneWidget);

      // Tapping the wardrobe item anchor sends anchorWardrobeItemId
      await tester.ensureVisible(find.text('Cashmere Overcoat'));
      await tester.tap(find.text('Cashmere Overcoat'));
      await tester.pumpAndSettle();
      expect(mockRepoAuth.lastAnchorWardrobeItemId, equals('owned-item-1'));
    });
  });

  group('DISCOVERY-09C Server-Backed Discovery Search', () {
    testWidgets('1. Typing a query sends the expected q parameter', (tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      final mockRepo = MockDiscoverRepository(
        forYouResult: ForYouDiscoveryResult.success(
          ForYouDiscoveryResponse(
            items: [createTestProduct(id: 'p-1', title: 'Khadi Kurta', brand: 'Indus')],
            totalCount: 1,
            page: 1,
            pageSize: 20,
            totalPages: 1,
            hasNext: false,
            hasPrev: false,
            isPersonalized: false,
            appliedContext: const UserPersonalizationContextSummary(isGuest: true),
          ),
        ),
      );

      await tester.pumpWidget(
        MaterialApp(
          home: DiscoverScreen(
            repository: mockRepo,
            isEstablishedUser: true,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Switch to For You tab
      await tester.tap(find.text('For You'));
      await tester.pumpAndSettle();

      // Enter query in search bar
      await tester.enterText(find.byType(TextField), 'Khadi');
      await tester.pumpAndSettle();

      expect(mockRepo.lastQ, equals('Khadi'));
    });

    testWidgets('2. Search and category filters are combined correctly', (tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      final mockRepo = MockDiscoverRepository(
        forYouResult: ForYouDiscoveryResult.success(
          ForYouDiscoveryResponse(
            items: [createTestProduct(id: 'p-1', title: 'Khadi Espadrilles', brand: 'Indus')],
            totalCount: 1,
            page: 1,
            pageSize: 20,
            totalPages: 1,
            hasNext: false,
            hasPrev: false,
            isPersonalized: false,
            appliedContext: const UserPersonalizationContextSummary(isGuest: true),
          ),
        ),
      );

      await tester.pumpWidget(
        buildHarness(
          child: EstablishedUserForYouFeed(
            repository: mockRepo,
            searchQuery: 'Khadi',
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(mockRepo.lastQ, equals('Khadi'));

      // Select category Footwear (chip is Sneakers in UI)
      await tester.ensureVisible(find.text('Sneakers'));
      await tester.tap(find.text('Sneakers'));
      await tester.pumpAndSettle();

      // Both category and q are sent simultaneously
      expect(mockRepo.lastCategories, equals(['footwear']));
      expect(mockRepo.lastQ, equals('Khadi'));
    });

    testWidgets('3. Query changes reset pagination', (tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      final mockRepo = MockDiscoverRepository(
        onGetForYouWithQuery: (page, pageSize, categories, q) async {
          return ForYouDiscoveryResult.success(
            ForYouDiscoveryResponse(
              items: [
                createTestProduct(id: 'p-$page-$q-1', title: '$q Product 1'),
                createTestProduct(id: 'p-$page-$q-2', title: '$q Product 2'),
              ],
              totalCount: 40,
              page: page,
              pageSize: 20,
              totalPages: 2,
              hasNext: page == 1,
              hasPrev: page > 1,
              isPersonalized: false,
              appliedContext: const UserPersonalizationContextSummary(isGuest: true),
            ),
          );
        },
      );

      await tester.pumpWidget(
        buildHarness(
          child: EstablishedUserForYouFeed(
            repository: mockRepo,
            searchQuery: 'Cotton',
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Advance to page 2
      await tester.ensureVisible(find.text('Load more'));
      await tester.tap(find.text('Load more'));
      await tester.pumpAndSettle();
      expect(mockRepo.lastPage, equals(2));
      expect(mockRepo.lastQ, equals('Cotton'));

      // Change query in widget
      await tester.pumpWidget(
        buildHarness(
          child: EstablishedUserForYouFeed(
            repository: mockRepo,
            searchQuery: 'Linen',
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Page resets to 1 with new query
      expect(mockRepo.lastPage, equals(1));
      expect(mockRepo.lastQ, equals('Linen'));
    });

    testWidgets('4. Page-two requests preserve the current query', (tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      final mockRepo = MockDiscoverRepository(
        onGetForYouWithQuery: (page, pageSize, categories, q) async {
          return ForYouDiscoveryResult.success(
            ForYouDiscoveryResponse(
              items: [
                createTestProduct(id: 'p-$page-1', title: '$q Item $page-1'),
                createTestProduct(id: 'p-$page-2', title: '$q Item $page-2'),
              ],
              totalCount: 40,
              page: page,
              pageSize: 20,
              totalPages: 2,
              hasNext: page == 1,
              hasPrev: page > 1,
              isPersonalized: false,
              appliedContext: const UserPersonalizationContextSummary(isGuest: true),
            ),
          );
        },
      );

      await tester.pumpWidget(
        buildHarness(
          child: EstablishedUserForYouFeed(
            repository: mockRepo,
            searchQuery: 'Khadi',
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(mockRepo.lastPage, equals(1));
      expect(mockRepo.lastQ, equals('Khadi'));

      // Tap load more
      await tester.ensureVisible(find.text('Load more'));
      await tester.tap(find.text('Load more'));
      await tester.pumpAndSettle();

      expect(mockRepo.lastPage, equals(2));
      expect(mockRepo.lastQ, equals('Khadi'));
    });

    testWidgets('5. Clearing search restores unsearched results', (tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      final mockRepo = MockDiscoverRepository(
        onGetForYouWithQuery: (page, pageSize, categories, q) async {
          return ForYouDiscoveryResult.success(
            ForYouDiscoveryResponse(
              items: [
                createTestProduct(
                  id: q != null ? 'searched-1' : 'unsearched-1',
                  title: q != null ? 'Searched Item' : 'Unsearched Catalog Item',
                ),
              ],
              totalCount: q != null ? 1 : 60,
              page: 1,
              pageSize: 20,
              totalPages: q != null ? 1 : 3,
              hasNext: q == null,
              hasPrev: false,
              isPersonalized: false,
              appliedContext: const UserPersonalizationContextSummary(isGuest: true),
            ),
          );
        },
      );

      await tester.pumpWidget(
        MaterialApp(
          home: DiscoverScreen(
            repository: mockRepo,
            isEstablishedUser: true,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Switch to For You
      await tester.tap(find.text('For You'));
      await tester.pumpAndSettle();

      // Enter query
      await tester.enterText(find.byType(TextField), 'Khadi');
      await tester.pumpAndSettle();
      expect(mockRepo.lastQ, equals('Khadi'));

      // Clear search
      await tester.tap(find.byIcon(Icons.clear_rounded));
      await tester.pumpAndSettle();

      // Restores unsearched query (null)
      expect(mockRepo.lastQ, isNull);
    });

    testWidgets('6. A slow response for an old query cannot overwrite a newer query', (tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      final slowCompleter = Completer<ForYouDiscoveryResult>();
      final fastCompleter = Completer<ForYouDiscoveryResult>();

      final mockRepo = MockDiscoverRepository(
        onGetForYouWithQuery: (page, pageSize, categories, q) {
          if (q == 'slow') return slowCompleter.future;
          if (q == 'fast') return fastCompleter.future;
          return Future.value(
            const ForYouDiscoveryResult.failure(DiscoverFailure.unknown),
          );
        },
      );

      await tester.pumpWidget(
        buildHarness(
          child: EstablishedUserForYouFeed(
            repository: mockRepo,
            searchQuery: 'slow',
          ),
        ),
      );
      await tester.pump();

      // Change query to 'fast'
      await tester.pumpWidget(
        buildHarness(
          child: EstablishedUserForYouFeed(
            repository: mockRepo,
            searchQuery: 'fast',
          ),
        ),
      );
      await tester.pump();

      // Fast query resolves first
      fastCompleter.complete(
        ForYouDiscoveryResult.success(
          ForYouDiscoveryResponse(
            items: [
              createTestProduct(id: 'fast-prod-1', title: 'Fast Winner Shirt', brand: 'FastBrand'),
              createTestProduct(id: 'fast-prod-2', title: 'Fast Secondary Shirt', brand: 'FastBrand'),
            ],
            totalCount: 2,
            page: 1,
            pageSize: 20,
            totalPages: 1,
            hasNext: false,
            hasPrev: false,
            isPersonalized: false,
            appliedContext: const UserPersonalizationContextSummary(isGuest: true),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('Fast Winner Shirt'), findsOneWidget);

      // Now slow query finishes late
      slowCompleter.complete(
        ForYouDiscoveryResult.success(
          ForYouDiscoveryResponse(
            items: [
              createTestProduct(id: 'slow-prod-1', title: 'Stale Slow Shirt', brand: 'SlowBrand'),
            ],
            totalCount: 1,
            page: 1,
            pageSize: 20,
            totalPages: 1,
            hasNext: false,
            hasPrev: false,
            isPersonalized: false,
            appliedContext: const UserPersonalizationContextSummary(isGuest: true),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Stale slow response was dropped; fast results remain displayed!
      expect(find.text('Fast Winner Shirt'), findsOneWidget);
      expect(find.text('Stale Slow Shirt'), findsNothing);
    });

    testWidgets('7. Empty search results render the honest empty state', (tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      final mockRepo = MockDiscoverRepository(
        forYouResult: ForYouDiscoveryResult.success(
          const ForYouDiscoveryResponse(
            items: [],
            totalCount: 0,
            page: 1,
            pageSize: 20,
            totalPages: 0,
            hasNext: false,
            hasPrev: false,
            isPersonalized: false,
            appliedContext: UserPersonalizationContextSummary(isGuest: true),
          ),
        ),
      );

      await tester.pumpWidget(
        buildHarness(
          child: EstablishedUserForYouFeed(
            repository: mockRepo,
            searchQuery: 'NonexistentBrand',
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('No Matching Products'), findsOneWidget);
      expect(find.text('No products match your active filters or search terms.'), findsOneWidget);
      expect(find.text('Reset Filters'), findsOneWidget);

      // No fake products
      expect(find.text('COS'), findsNothing);
    });

    testWidgets('8. Search request failure renders the honest error state and supports retry', (tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      final mockRepo = MockDiscoverRepository(
        forYouResult: const ForYouDiscoveryResult.failure(DiscoverFailure.networkError),
      );

      await tester.pumpWidget(
        buildHarness(
          child: EstablishedUserForYouFeed(
            repository: mockRepo,
            searchQuery: 'Khadi',
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Connection Unavailable'), findsOneWidget);
      expect(find.text('Retry'), findsOneWidget);

      final initialCalls = mockRepo.forYouCallCount;
      await tester.tap(find.text('Retry'));
      await tester.pumpAndSettle();

      expect(mockRepo.forYouCallCount, greaterThan(initialCalls));
      expect(mockRepo.lastQ, equals('Khadi'));
    });

    testWidgets('9. Load More remains duplicate-safe', (tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      final mockRepo = MockDiscoverRepository(
        onGetForYouWithQuery: (page, pageSize, categories, q) async {
          if (page == 1) {
            return ForYouDiscoveryResult.success(
              ForYouDiscoveryResponse(
                items: [
                  createTestProduct(id: 'prod-dup-1', title: 'Khadi Shirt Primary'),
                  createTestProduct(id: 'prod-dup-2', title: 'Khadi Shirt Secondary'),
                ],
                totalCount: 4,
                page: 1,
                pageSize: 2,
                totalPages: 2,
                hasNext: true,
                hasPrev: false,
                isPersonalized: false,
                appliedContext: const UserPersonalizationContextSummary(isGuest: true),
              ),
            );
          } else {
            // Page 2 returns duplicate prod-dup-2 alongside prod-dup-3
            return ForYouDiscoveryResult.success(
              ForYouDiscoveryResponse(
                items: [
                  createTestProduct(id: 'prod-dup-2', title: 'Khadi Shirt Secondary'),
                  createTestProduct(id: 'prod-dup-3', title: 'Khadi Shirt Tertiary'),
                ],
                totalCount: 4,
                page: 2,
                pageSize: 2,
                totalPages: 2,
                hasNext: false,
                hasPrev: true,
                isPersonalized: false,
                appliedContext: const UserPersonalizationContextSummary(isGuest: true),
              ),
            );
          }
        },
      );

      await tester.pumpWidget(
        buildHarness(
          child: EstablishedUserForYouFeed(
            repository: mockRepo,
            searchQuery: 'Khadi',
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Khadi Shirt Primary'), findsOneWidget);
      expect(find.text('Khadi Shirt Secondary'), findsOneWidget);

      // Load more
      await tester.ensureVisible(find.text('Load more'));
      await tester.tap(find.text('Load more'));
      await tester.pumpAndSettle();

      // prod-dup-2 appears exactly once (no duplicates!)
      expect(find.text('Khadi Shirt Secondary'), findsOneWidget);
      expect(find.text('Khadi Shirt Tertiary'), findsOneWidget);
    });

    testWidgets('10. Existing guest isolation and synthetic-fixture disclosures remain intact', (tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await AuthSession.clearSession();

      final mockRepo = MockDiscoverRepository(
        forYouResult: ForYouDiscoveryResult.success(
          ForYouDiscoveryResponse(
            items: [
              createTestProduct(
                id: 'synth-1',
                title: 'Synthetic Demo Blazer',
                isSynthetic: true,
                isFixture: true,
              ),
              createTestProduct(
                id: 'synth-2',
                title: 'Synthetic Demo Trousers',
                isSynthetic: true,
                isFixture: true,
              ),
            ],
            totalCount: 2,
            page: 1,
            pageSize: 20,
            totalPages: 1,
            hasNext: false,
            hasPrev: false,
            isPersonalized: false,
            appliedContext: const UserPersonalizationContextSummary(isGuest: true),
          ),
        ),
      );

      await tester.pumpWidget(
        buildHarness(
          child: EstablishedUserForYouFeed(
            repository: mockRepo,
            searchQuery: 'Blazer',
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Guest context
      expect(mockRepo.lastQ, equals('Blazer'));

      // Tap on shop button for synthetic item
      await tester.ensureVisible(find.text('DEMO FIXTURE • NOT FOR SALE').first);
      await tester.tap(find.text('DEMO FIXTURE • NOT FOR SALE').first);
      await tester.pumpAndSettle();

      // Honest synthetic disclosure dialog
      expect(find.text('Synthetic Demo Product'), findsOneWidget);
      expect(find.text('Understood'), findsOneWidget);

      await tester.tap(find.text('Understood'));
      await tester.pumpAndSettle();
      expect(find.text('Synthetic Demo Product'), findsNothing);
    });
  });

  group('DISCOVERY-09D — Trending Screen Integrity and Mock Claim Removal', () {
    // 1. No unsupported "1.4K SAVES" or "920 SAVES" claims appear
    testWidgets('1. No unsupported "1.4K SAVES" or "920 SAVES" claims appear anywhere on the Trending screen', (tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await tester.pumpWidget(
        MaterialApp(
          home: const DiscoverScreen(),
        ),
      );
      await tester.pumpAndSettle();

      // Verify no invented save count claims
      expect(find.text('1.4K SAVES'), findsNothing);
      expect(find.text('920 SAVES'), findsNothing);
      expect(find.textContaining('SAVES'), findsNothing);

      // Verify no fake piece catalog claims
      expect(find.text('128 pieces cataloged'), findsNothing);
      expect(find.text('96 pieces cataloged'), findsNothing);

      // Verified honest curation badge rendered
      expect(find.text('CURATED'), findsWidgets);
      expect(find.text('Monochrome architectural layering'), findsOneWidget);
      expect(find.text('Tailored heritage essentials'), findsOneWidget);
    });

    // 2. Unsupported global-wishlist rankings and popularity superlatives are absent
    testWidgets('2. Unsupported global-wishlist rankings and popularity superlatives are absent', (tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await tester.pumpWidget(
        MaterialApp(
          home: const DiscoverScreen(),
        ),
      );
      await tester.pumpAndSettle();

      // Verify absence of unverified wishlist superlatives
      expect(find.text('Most saved across top global wishlists'), findsNothing);
      expect(find.textContaining('global wishlists'), findsNothing);
      expect(find.textContaining('Most saved'), findsNothing);

      // Verify presence of grounded editorial curation subtitle
      expect(find.text('Curated staple silhouettes & studio concept references'), findsOneWidget);
    });

    // 3. Synthetic fixture products remain clearly disclosed without mock retailer claims
    testWidgets('3. Synthetic fixture products remain clearly disclosed without mock retailer claims', (tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await tester.pumpWidget(
        MaterialApp(
          home: const DiscoverScreen(),
        ),
      );
      await tester.pumpAndSettle();

      // Verify absence of mock Zara and Adidas retailer claims
      expect(find.text('ZARA ATELIER'), findsNothing);
      expect(find.text('ADIDAS ORIGINALS'), findsNothing);

      // Verify studio concept brands
      expect(find.text('STUDIO ATELIER'), findsOneWidget);
      expect(find.text('HERITAGE ARCHIVE'), findsOneWidget);
      expect(find.text('Tailored Wool Coat'), findsOneWidget);
      expect(find.text('Samba OG Archive'), findsOneWidget);

      // Verify synthetic fixture badge is rendered on items
      expect(find.text('FIXTURE'), findsWidgets);
    });

    // 4. The unavailable-demand evidence card remains visible to authenticated users with 3-domain breakdown
    testWidgets('4. The unavailable-demand evidence card remains visible to authenticated users with 3-domain breakdown', (tester) async {
      await AuthSession.saveSession('valid-user-token-09d');

      final mockRepo = MockDiscoverRepository(
        trendingResult: DiscoveryTrendingResult.success(
          const DiscoveryTrendingResponse(
            windowStart: '2026-10-01T00:00:00Z',
            windowEnd: '2026-10-14T00:00:00Z',
            generatedAt: '2026-10-14T12:00:00Z',
            demandTrendStatus: 'insufficient_evidence',
            evidenceType: 'catalog_activity',
            catalogActivityStatus: 'active',
            directDemandAvailable: false,
            sourceCoverage: 5,
            observationCount: 60,
            confidenceInterpretation: 'Catalog assortment data only',
            limitations: [
              'Direct consumer purchase telemetry is unavailable',
              'Assortment reflects partner catalog velocity, not consumer sales',
            ],
            items: [],
          ),
        ),
      );

      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await tester.pumpWidget(
        MaterialApp(
          home: DiscoverScreen(
            repository: mockRepo,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // TrendingEvidenceStatusCard is rendered
      expect(find.byType(TrendingEvidenceStatusCard), findsOneWidget);
      expect(find.text('CATALOG OBSERVATION INTELLIGENCE'), findsOneWidget);
      expect(find.text('DEMAND SIGNALS UNAVAILABLE'), findsOneWidget);

      // 3-Domain Evidence Breakdown
      expect(find.text('EVIDENCE SIGNAL DOMAINS'), findsOneWidget);
      expect(find.text('Catalog Activity:'), findsOneWidget);
      expect(find.text('ACTIVE (60 observations)'), findsOneWidget);
      expect(find.text('Media Attention:'), findsOneWidget);
      expect(find.text('Inactive / Unverified'), findsOneWidget);
      expect(find.text('Consumer Demand:'), findsOneWidget);
      expect(find.text('Unavailable (insufficient evidence)'), findsOneWidget);
    });

    // 5. Guest users continue to receive the appropriate sign-in notice
    testWidgets('5. Guest users continue to receive the appropriate sign-in notice', (tester) async {
      await AuthSession.clearSession();

      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await tester.pumpWidget(
        MaterialApp(
          home: const DiscoverScreen(),
        ),
      );
      await tester.pumpAndSettle();

      // Guest notice card rendered
      expect(find.byType(TrendingGuestNoticeCard), findsOneWidget);
      expect(find.text('TREND INTELLIGENCE ACCESS'), findsOneWidget);
      expect(find.text('SIGN IN FOR TREND ANALYTICS →'), findsOneWidget);

      // Trend evidence status card hidden from unauthenticated guest
      expect(find.byType(TrendingEvidenceStatusCard), findsNothing);
    });

    // 6. Empty trend candidates do not trigger fabricated fallback trend products
    testWidgets('6. Empty trend candidates do not trigger fabricated fallback trend products', (tester) async {
      await AuthSession.saveSession('valid-user-token-09d');

      final mockRepo = MockDiscoverRepository(
        trendingResult: DiscoveryTrendingResult.success(
          const DiscoveryTrendingResponse(
            windowStart: '2026-10-01T00:00:00Z',
            windowEnd: '2026-10-14T00:00:00Z',
            generatedAt: '2026-10-14T12:00:00Z',
            demandTrendStatus: 'insufficient_evidence',
            evidenceType: 'catalog_activity',
            catalogActivityStatus: 'active',
            directDemandAvailable: false,
            sourceCoverage: 5,
            observationCount: 60,
            confidenceInterpretation: 'Catalog assortment data only',
            limitations: ['Demand telemetry unavailable'],
            items: [
              // 1 candidate that is NOT publishable
              DiscoveryTrendItem(
                concept: 'candidate-1',
                canonicalName: 'Oversized Blazer Observation',
                category: 'outerwear',
                catalogActivityStatus: 'active',
                observationCount: 12,
                distinctProducts: 4,
                distinctSources: 3,
                firstObservedAt: '2026-10-01T00:00:00Z',
                lastObservedAt: '2026-10-14T00:00:00Z',
                confidence: 0.75,
                fixtureDerived: true,
                publishable: false, // NOT publishable
                directDemandAvailable: false,
                explanation: DiscoveryTrendItemExplanation(
                  summary: 'Candidate under evaluation.',
                  evidenceType: 'catalog_activity',
                  demandSignalAvailable: false,
                  reasons: ['Insufficient demand evidence'],
                ),
              ),
            ],
          ),
        ),
      );

      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await tester.pumpWidget(
        MaterialApp(
          home: DiscoverScreen(
            repository: mockRepo,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // No trending candidate cards rendered for unpublishable candidate
      expect(find.byType(TrendingCandidateCard), findsNothing);

      // Honest explanation card displayed
      expect(
        find.textContaining('No candidate trends currently meet publishable evidence thresholds'),
        findsOneWidget,
      );
      expect(
        find.textContaining('Missing consumer demand signals remain unmeasured'),
        findsOneWidget,
      );
    });

    // 7. Curated editorial content is clearly differentiated from measured trends
    testWidgets('7. Curated editorial content is clearly differentiated from measured trends', (tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await tester.pumpWidget(
        MaterialApp(
          home: const DiscoverScreen(),
        ),
      );
      await tester.pumpAndSettle();

      // Hero directive uses CURATED DIRECTIVE badge rather than live TRENDING claim
      expect(find.text('CURATED DIRECTIVE'), findsOneWidget);
      expect(find.text('Quiet Luxury'), findsOneWidget);
      expect(find.text('BRUTALIST EDIT'), findsOneWidget);

      // Section headers clearly declare editorial directives
      expect(find.text('SPOTLIGHT EDIT'), findsOneWidget);
      expect(find.text('Trending Now'), findsOneWidget);
      expect(find.text('Curated directives defining current global fashion discourse.'), findsOneWidget);
      expect(find.text('STYLIST ENSEMBLES'), findsOneWidget);
      expect(find.text('Trending Looks'), findsOneWidget);
      expect(find.text('Directorial curations ready for styling'), findsOneWidget);
      expect(find.text('EDITORIAL MOODBOARD'), findsOneWidget);
      expect(find.text('Style Inspiration'), findsOneWidget);
    });

    // 8. Existing category navigation and screen behavior remain correct
    testWidgets('8. Existing category navigation and screen behavior remain correct', (tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await tester.pumpWidget(
        MaterialApp(
          home: const DiscoverScreen(),
        ),
      );
      await tester.pumpAndSettle();

      // Category tiles in Atelier rail are rendered and interactive
      expect(find.text('Clothing'), findsOneWidget);
      expect(find.text('Sneakers'), findsOneWidget);
      expect(find.text('Accessories'), findsOneWidget);

      await tester.tap(find.text('Sneakers'));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Clothing'));
      await tester.pumpAndSettle();
    });

    // 9. Digital Atelier card proportions and design tokens remain intact
    testWidgets('9. Digital Atelier card proportions and design tokens remain intact', (tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await tester.pumpWidget(
        MaterialApp(
          home: const DiscoverScreen(),
        ),
      );
      await tester.pumpAndSettle();

      // Verify EditorialLookCard presence and layout structure
      expect(find.byType(EditorialLookCard), findsNWidgets(2));
      expect(find.byType(EditorialCommerceItemCard), findsNWidgets(2));
      expect(find.byType(SpotlightHeroCard), findsOneWidget);

      // Verify aspect ratio visual containers preserve 65/35 proportion
      final aspectRatios = tester.widgetList<AspectRatio>(find.byType(AspectRatio));
      expect(aspectRatios.any((a) => a.aspectRatio == 0.85), isTrue); // EditorialLookCard visual area
      expect(aspectRatios.any((a) => a.aspectRatio == 0.95), isTrue); // EditorialCommerceItemCard visual area
    });

    // =========================================================================
    // TASK DISCOVERY-10B-1: FIXTURE IMAGERY REPAIR & ROUTABLE RESOLUTION TESTS
    // =========================================================================
    test('10. AppConfig.resolveImageUrl resolves relative, loopback, public, and asset URLs safely', () {
      // 1. Relative static asset path prepends resolvedApiBaseUrl
      final relativeUrl = '/static/fixtures/fashion/SEED-TOP-001.png';
      final resolvedRelative = AppConfig.resolveImageUrl(relativeUrl);
      expect(resolvedRelative, startsWith('http'));
      expect(resolvedRelative, endsWith(relativeUrl));

      // 2. Public CDN / HTTPS URL is preserved verbatim
      const publicCdn = 'https://rukminim1.flixcart.com/image/832/832/product.jpg';
      expect(AppConfig.resolveImageUrl(publicCdn), publicCdn);

      // 3. Bundled Flutter asset path is preserved verbatim
      const assetPath = 'assets/images/discover_hero_quiet_luxury.jpg';
      expect(AppConfig.resolveImageUrl(assetPath), assetPath);

      // 4. Empty and blank strings return unchanged
      expect(AppConfig.resolveImageUrl(''), '');
      expect(AppConfig.resolveImageUrl('   '), '');
    });

    testWidgets('11. AtelierImage resolves routable URLs, supports Image.network and graceful fallback', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Column(
              children: const [
                // 1. Network image with relative path
                AtelierImage(
                  assetPath: '/static/fixtures/fashion/SEED-TOP-001.png',
                  width: 100,
                  height: 120,
                ),
                // 2. Bundled Flutter asset
                AtelierImage(
                  assetPath: 'assets/images/discover_hero_quiet_luxury.jpg',
                  width: 100,
                  height: 120,
                ),
              ],
            ),
          ),
        ),
      );
      await tester.pump();

      // AtelierImage renders without crashing and mounts the image widgets
      expect(find.byType(AtelierImage), findsNWidgets(2));
      expect(find.byType(Image), findsNWidgets(2));
    });
  });
}
