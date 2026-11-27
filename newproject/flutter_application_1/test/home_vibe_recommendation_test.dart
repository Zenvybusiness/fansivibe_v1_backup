import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:fansivibe/app/router/app_router.dart';
import 'package:fansivibe/features/discover/data/discover_models.dart';
import 'package:fansivibe/features/discover/data/discover_repository.dart';
import 'package:fansivibe/features/home/data/home_recommendation_models.dart';
import 'package:fansivibe/features/home/data/home_vibe_mapping.dart';
import 'package:fansivibe/features/home/data/today_look_models.dart';
import 'package:fansivibe/features/home/data/today_look_repository.dart';
import 'package:fansivibe/features/home/presentation/first_time_home_screen.dart';
import 'package:fansivibe/features/home/presentation/home_screen.dart';
import 'package:fansivibe/features/home/presentation/widgets/existing_user_home_widgets.dart';
import 'package:fansivibe/features/home/presentation/widgets/first_time_home_widgets.dart';
import 'package:fansivibe/features/learning/learning_summary.dart';
import 'package:fansivibe/features/profile/data/saved_looks_models.dart';
import 'package:fansivibe/features/profile/data/saved_looks_repository.dart';
import 'package:fansivibe/features/trending/data/trending_models.dart';
import 'package:fansivibe/features/trending/data/trending_repository.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/theme/fansivibe_theme.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

class _EstablishedSummaryRepo implements LearningSummaryRepository {
  @override
  Future<LearningSummary?> getSummary() async => const LearningSummary(
    styleScore: 78,
    breakdown: LearningSummaryBreakdown(
      base: 60,
      wardrobePoints: 10,
      savedPoints: 8,
      total: 78,
    ),
    streak: 3,
    recentSignals: ['sig-1'],
  );
}

class _CountingTodayLookRepo implements TodayLookRepository {
  _CountingTodayLookRepo(this.builder);
  final TodayLookResult Function(int callCount) builder;
  int calls = 0;

  @override
  Future<TodayLookResult> getTodayLook({
    String? city,
    double? latitude,
    double? longitude,
  }) async {
    calls++;
    return builder(calls);
  }

  @override
  Future<TodayLookResult> regenerateTodayLook({
    String? seed,
    String? city,
    double? latitude,
    double? longitude,
  }) async => builder(calls);

  @override
  Future<SavedTodayLook?> saveTodayLook({
    String? lookId,
    required String title,
    required Map<String, dynamic> snapshot,
    required String idempotencyKey,
  }) async => null;
}

class _EmptyWardrobeRepo implements WardrobeRepository {
  @override
  Future<WardrobeInsightData?> getInsight() async => null;

  @override
  Future<List<WardrobeItemData>> listItems({
    String? category,
    String? color,
    String? sortBy,
    String? order,
    int page = 1,
    int pageSize = 20,
  }) async => const [];

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _EmptySavedLooksRepo implements SavedLooksRepository {
  @override
  Future<SavedLookListPage?> listSavedLooks({
    int page = 1,
    int pageSize = 20,
  }) async =>
      const SavedLookListPage(items: [], total: 0, page: 1, pageSize: 20);

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _FakeDiscoverRepo implements DiscoverRepository {
  _FakeDiscoverRepo(this.result);
  final ForYouDiscoveryResult result;

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
  }) async => result;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _FakeTrendingRepo implements TrendingRepository {
  _FakeTrendingRepo(this.result);
  final TrendingFeedResult result;

  @override
  Future<TrendingFeedResult> getTrendingFeed({
    String? region,
    int? limit,
  }) async => result;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

TodayLook _sampleTodayLook({String? vibe, String? imageUrl}) {
  return TodayLook.fromJson({
    'title': 'Tailored Neutral Edit',
    'occasion': 'office',
    'description': 'Clean layers matched to your wardrobe.',
    'matchScore': 88,
    'styleScore': 88,
    'components': [
      {
        'id': '11111111-1111-1111-1111-111111111111',
        'name': 'Charcoal Blazer',
        'category': 'outerwear',
        'color': 'charcoal',
      },
    ],
    'reasons': ['Picked for an office occasion'],
    'wardrobeContext': {'totalItems': 3, 'matchingItems': 1},
    'alternatives': <Map<String, dynamic>>[],
    'selectedItemIds': ['11111111-1111-1111-1111-111111111111'],
    'recommendationId': 'today-abc123',
    'sourceType': 'wardrobe_derived',
    if (vibe != null) 'selectedVibe': vibe,
    'isPersonalized': true,
    if (imageUrl != null) 'imageUrl': imageUrl,
  });
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    LocalStorage.init(prefs: await SharedPreferences.getInstance());
    await AuthSession.saveSession('test-token');
  });

  tearDown(() async {
    await AuthSession.clearSession();
  });

  group('H4.1 Vibe-to-image mapping & provenance', () {
    test(
      'all supported vibes resolve to distinct profiles and valid assets',
      () {
        const supported = [
          'minimalist',
          'classic',
          'bold',
          'trendy',
          'streetwear',
          'natural',
          'bohemian',
          'edgy',
          'athleisure',
        ];
        for (final vibe in supported) {
          final profile = HomeVibeMapping.resolve(vibe);
          expect(profile, isNotNull, reason: 'Expected profile for $vibe');
          expect(profile!.heroImageAsset, startsWith('assets/images/'));
          expect(profile.curatedLooks, isNotEmpty);
        }
        expect(HomeVibeMapping.resolve('sporty')?.canonicalId, 'athleisure');
        expect(HomeVibeMapping.resolve('Minimal')?.canonicalId, 'minimalist');
        expect(HomeVibeMapping.resolve('unknown_xyz'), isNull);
      },
    );

    testWidgets(
      'FirstTimeHomeScreen displays vibe-matched image, not streetwear for minimalist',
      (tester) async {
        LocalStorage.vibe = 'minimalist';
        await tester.pumpWidget(
          MaterialApp.router(
            theme: FansivibeTheme.darkTheme,
            routerConfig: GoRouter(
              initialLocation: '/first',
              routes: [
                GoRoute(
                  path: '/first',
                  builder: (_, _) => const FirstTimeHomeScreen(),
                ),
                ...appRoutes,
              ],
            ),
          ),
        );
        await tester.pumpAndSettle();

        final img = tester.widget<Image>(
          find.descendant(
            of: find.byType(EditorialOutfitVisual),
            matching: find.byType(Image),
          ),
        );
        final asset = img.image as AssetImage;
        expect(
          asset.assetName,
          'assets/images/discover_look_urban_minimal.jpg',
        );
        expect(
          getCuratedLookForVibe('minimalist').provenance.sourceType,
          HomeRecommendationSourceType.demoFixture,
        );
        expect(
          getCuratedLookForVibe('minimalist').provenance.isPersonalized,
          isFalse,
        );
      },
    );

    testWidgets(
      'HomeScreen TodayLook displays truthful provenance badge and vibe image',
      (tester) async {
        LocalStorage.vibe = 'classic';
        final todayRepo = _CountingTodayLookRepo(
          (_) => TodayLookResult.available(_sampleTodayLook(vibe: 'classic')),
        );
        await tester.pumpWidget(
          MaterialApp.router(
            theme: FansivibeTheme.darkTheme,
            routerConfig: GoRouter(
              initialLocation: '/home',
              routes: [
                GoRoute(
                  path: '/home',
                  builder: (_, _) => HomeScreen(
                    summaryRepository: _EstablishedSummaryRepo(),
                    todayLookRepository: todayRepo,
                    wardrobeRepository: _EmptyWardrobeRepo(),
                    savedLooksRepository: _EmptySavedLooksRepo(),
                  ),
                ),
                ...appRoutes,
              ],
            ),
          ),
        );
        await tester.pumpAndSettle();

        expect(find.text('PERSONALIZED • CLASSIC'), findsOneWidget);
        expect(find.text('CURATED #140'), findsNothing);
      },
    );

    testWidgets('Empty wardrobe shows truthful empty state, never fake look', (
      tester,
    ) async {
      final todayRepo = _CountingTodayLookRepo(
        (_) => const TodayLookResult.noneAvailable(),
      );
      await tester.pumpWidget(
        MaterialApp.router(
          theme: FansivibeTheme.darkTheme,
          routerConfig: GoRouter(
            initialLocation: '/home',
            routes: [
              GoRoute(
                path: '/home',
                builder: (_, _) => HomeScreen(
                  summaryRepository: _EstablishedSummaryRepo(),
                  todayLookRepository: todayRepo,
                  wardrobeRepository: _EmptyWardrobeRepo(),
                  savedLooksRepository: _EmptySavedLooksRepo(),
                ),
              ),
              ...appRoutes,
            ],
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.textContaining('No today\'s look available right now.'),
        findsOneWidget,
      );
    });

    testWidgets(
      'Personalized vs generic fallback in Curated Looks & Trending stale state',
      (tester) async {
        final discoverRepo = _FakeDiscoverRepo(
          ForYouDiscoveryResult.success(
            ForYouDiscoveryResponse(
              items: const [
                ProductRecommendationItem(
                  id: 'prod-1',
                  title: 'Minimalist Wool Coat',
                  brand: 'Atelier',
                  category: 'outerwear',
                  currency: 'INR',
                  imageUrls: ['assets/images/discover_item_wool_coat.jpg'],
                  attributes: {},
                  ffoConcepts: [],
                  isSynthetic: false,
                  isFixture: false,
                  score: 92.0,
                  rank: 1,
                  scoreBreakdown: ProductScoreBreakdown(
                    preferenceMatch: 30,
                    styleProfileMatch: 25,
                    wardrobeComplementarity: 20,
                    budgetAvailability: 17,
                    totalScore: 92,
                  ),
                  explanation: ProductExplanation(
                    summary: 'Matches your Minimalist vibe',
                    reasons: ['Matches Minimalist aesthetic'],
                    isSyntheticFixture: false,
                    provenance: 'catalog',
                  ),
                ),
              ],
              totalCount: 1,
              page: 1,
              pageSize: 4,
              totalPages: 1,
              hasNext: false,
              hasPrev: false,
              isPersonalized: true,
              appliedContext: UserPersonalizationContextSummary(
                isGuest: false,
                hasWardrobe: true,
                styleType: 'minimalist',
              ),
            ),
          ),
        );

        final trendingRepo = _FakeTrendingRepo(
          TrendingFeedResult.page(
            const TrendingFeed(
              region: 'IN',
              generatedAt: '2026-11-27T00:00:00Z',
              isStale: true,
              items: [
                TrendingItem(
                  trendId: 'trend-1',
                  displayName: 'Structured Blazers',
                  category: 'outerwear',
                  region: 'IN',
                  velocity: 0.8,
                  confidence: 0.85,
                  supportingSignals: 2,
                  sources: ['youtube_in'],
                  provenance: [],
                  matchedProducts: [],
                ),
              ],
            ),
          ),
        );

        final todayRepo = _CountingTodayLookRepo(
          (_) =>
              TodayLookResult.available(_sampleTodayLook(vibe: 'minimalist')),
        );

        await tester.pumpWidget(
          MaterialApp.router(
            theme: FansivibeTheme.darkTheme,
            routerConfig: GoRouter(
              initialLocation: '/home',
              routes: [
                GoRoute(
                  path: '/home',
                  builder: (_, _) => HomeScreen(
                    summaryRepository: _EstablishedSummaryRepo(),
                    todayLookRepository: todayRepo,
                    wardrobeRepository: _EmptyWardrobeRepo(),
                    savedLooksRepository: _EmptySavedLooksRepo(),
                    discoverRepository: discoverRepo,
                    trendingRepository: trendingRepo,
                  ),
                ),
                ...appRoutes,
              ],
            ),
          ),
        );
        await tester.pumpAndSettle();

        await tester.scrollUntilVisible(
          find.text('Minimalist Wool Coat'),
          400.0,
        );
        expect(find.text('PERSONALIZED SELECTION'), findsOneWidget);

        await tester.scrollUntilVisible(find.text('Structured Blazers'), 400.0);
        expect(find.text('CACHED TRENDS'), findsOneWidget);
        expect(find.text('Cached • IN'), findsOneWidget);
      },
    );

    testWidgets(
      'Vibe change in LocalStorage triggers HomeScreen TodayLook refresh',
      (tester) async {
        LocalStorage.vibe = 'minimalist';
        final todayRepo = _CountingTodayLookRepo(
          (n) => TodayLookResult.available(
            _sampleTodayLook(vibe: n == 1 ? 'minimalist' : 'bold'),
          ),
        );

        await tester.pumpWidget(
          MaterialApp.router(
            theme: FansivibeTheme.darkTheme,
            routerConfig: GoRouter(
              initialLocation: '/home',
              routes: [
                GoRoute(
                  path: '/home',
                  builder: (_, _) => HomeScreen(
                    summaryRepository: _EstablishedSummaryRepo(),
                    todayLookRepository: todayRepo,
                    wardrobeRepository: _EmptyWardrobeRepo(),
                    savedLooksRepository: _EmptySavedLooksRepo(),
                  ),
                ),
                ...appRoutes,
              ],
            ),
          ),
        );
        await tester.pumpAndSettle();
        expect(todayRepo.calls, 1);
        expect(find.text('PERSONALIZED • MINIMALIST'), findsOneWidget);

        LocalStorage.vibe = 'bold';
        await tester.pumpAndSettle();
        expect(todayRepo.calls, 2);
        expect(find.text('PERSONALIZED • BOLD'), findsOneWidget);
      },
    );

    testWidgets('Empty curated and trending lists show honest empty states', (
      tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: FansivibeTheme.darkTheme,
          home: const Scaffold(
            body: SingleChildScrollView(
              child: Column(
                children: [
                  ExistingUserCuratedForYou(items: []),
                  ExistingUserTrending(items: []),
                ],
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.text('No curated looks available right now.'),
        findsOneWidget,
      );
      expect(
        find.text('No trending data available right now.'),
        findsOneWidget,
      );
    });
  });
}
