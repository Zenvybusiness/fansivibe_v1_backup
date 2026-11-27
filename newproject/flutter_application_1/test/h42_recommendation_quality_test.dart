import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:fansivibe/app/router/app_router.dart';
import 'package:fansivibe/features/discover/data/discover_models.dart';
import 'package:fansivibe/features/discover/data/discover_repository.dart';
import 'package:fansivibe/features/home/data/home_vibe_mapping.dart';
import 'package:fansivibe/features/home/data/today_look_models.dart';
import 'package:fansivibe/features/home/data/today_look_repository.dart';
import 'package:fansivibe/features/home/presentation/home_screen.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/learning/learning_summary.dart';
import 'package:fansivibe/features/onboarding/data/onboarding_data.dart';
import 'package:fansivibe/features/profile/data/saved_looks_models.dart';
import 'package:fansivibe/features/profile/data/saved_looks_repository.dart';
import 'package:fansivibe/features/profile/data/user_profile_models.dart';
import 'package:fansivibe/features/profile/data/user_profile_repository.dart';
import 'package:fansivibe/features/profile/presentation/preferences_screen.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/theme/fansivibe_theme.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:fansivibe/shared/utils/user_session.dart';

class _EstablishedSummaryRepo implements LearningSummaryRepository {
  @override
  Future<LearningSummary?> getSummary() async => const LearningSummary(
    styleScore: 80,
    breakdown: LearningSummaryBreakdown(
      base: 60,
      wardrobePoints: 12,
      savedPoints: 8,
      total: 80,
    ),
    streak: 4,
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

class _FakeUserProfileRepo implements UserProfileRepository {
  _FakeUserProfileRepo(this.profile);
  UserProfile profile;

  @override
  UserProfile? get cachedProfile => profile;

  @override
  Future<UserProfile?> fetchProfile({bool forceRefresh = false}) async =>
      profile;

  @override
  Future<UserProfile?> updateStyleType(String styleType) async {
    profile = UserProfile(
      displayName: profile.displayName,
      styleProfile: UserStyleProfile(styleType: styleType),
      version: profile.version + 1,
    );
    return profile;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

TodayLook _personalizedLook({String? vibe, String? imageUrl}) {
  return TodayLook.fromJson({
    'title': 'Minimalist Office Look',
    'occasion': 'office',
    'description': 'Clean tailored layers.',
    'matchScore': 91,
    'styleScore': 91,
    'components': [
      {
        'id': '11111111-1111-1111-1111-111111111111',
        'name': 'Black Slim Tee',
        'category': 'tops',
        'color': 'black',
      },
    ],
    'reasons': ['Picked for an office occasion'],
    'wardrobeContext': {'totalItems': 2, 'matchingItems': 1},
    'alternatives': <Map<String, dynamic>>[],
    'selectedItemIds': ['11111111-1111-1111-1111-111111111111'],
    'recommendationId': 'today-h42',
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

  group('H4.2 Recommendation quality & image association', () {
    test('every onboarding StyleVibe resolves cleanly in HomeVibeMapping', () {
      for (final vibe in StyleVibe.values) {
        final profile = HomeVibeMapping.resolve(vibe.name);
        expect(profile, isNotNull, reason: 'Missing mapping for ${vibe.name}');
        expect(profile!.canonicalId, vibe.name);
      }
    });

    testWidgets(
      'PreferencesScreen preserves Trendy/Natural/Edgy without corrupting to Bold',
      (tester) async {
        final repo = _FakeUserProfileRepo(
          const UserProfile(
            displayName: 'Test',
            styleProfile: UserStyleProfile(styleType: 'trendy'),
            version: 1,
          ),
        );

        await tester.pumpWidget(
          MaterialApp(
            theme: FansivibeTheme.darkTheme,
            home: PreferencesScreen(userProfileRepository: repo),
          ),
        );
        await tester.pumpAndSettle();

        expect(find.text('Trendy'), findsOneWidget);
        expect(find.text('Natural'), findsOneWidget);
        expect(find.text('Edgy'), findsOneWidget);

        await tester.ensureVisible(find.text('Natural'));
        await tester.tap(find.text('Natural'));
        await tester.pumpAndSettle();
        expect(repo.profile.styleProfile.styleType, 'Natural');
        expect(LocalStorage.vibe, 'Natural');
      },
    );

    testWidgets(
      'Personalized TodayLook without image shows truthful placeholder, not stock photo',
      (tester) async {
        LocalStorage.vibe = 'minimalist';
        final todayRepo = _CountingTodayLookRepo(
          (_) => TodayLookResult.available(
            _personalizedLook(vibe: 'minimalist', imageUrl: null),
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

        expect(find.text('No garment photo yet'), findsOneWidget);
      },
    );

    testWidgets(
      'Personalized ForYou item without imageUrls uses placeholder, not generic vibe image',
      (tester) async {
        final discoverRepo = _FakeDiscoverRepo(
          ForYouDiscoveryResult.success(
            const ForYouDiscoveryResponse(
              items: [
                ProductRecommendationItem(
                  id: 'prod-no-img',
                  title: 'Tailored Wool Trouser',
                  brand: 'Atelier',
                  category: 'bottoms',
                  currency: 'INR',
                  imageUrls: [],
                  attributes: {},
                  ffoConcepts: [],
                  isSynthetic: false,
                  isFixture: false,
                  score: 88.0,
                  rank: 1,
                  scoreBreakdown: ProductScoreBreakdown(
                    preferenceMatch: 25,
                    styleProfileMatch: 25,
                    wardrobeComplementarity: 20,
                    budgetAvailability: 18,
                    totalScore: 88,
                  ),
                  explanation: ProductExplanation(
                    summary: 'Matches your Minimalist vibe',
                    reasons: ['Matches Minimalist'],
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

        final todayRepo = _CountingTodayLookRepo(
          (_) => TodayLookResult.available(
            _personalizedLook(vibe: 'minimalist', imageUrl: null),
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
                    discoverRepository: discoverRepo,
                  ),
                ),
                ...appRoutes,
              ],
            ),
          ),
        );
        await tester.pumpAndSettle();

        expect(find.text('Tailored Wool Trouser'), findsOneWidget);
        expect(find.byIcon(Icons.checkroom_rounded), findsAtLeastNWidgets(1));
      },
    );

    testWidgets(
      'Wardrobe item change or occasion change refreshes HomeScreen TodayLook',
      (tester) async {
        final todayRepo = _CountingTodayLookRepo(
          (_) => TodayLookResult.available(_personalizedLook(vibe: 'classic')),
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
        final initialCalls = todayRepo.calls;

        LearningService.instance.addPreferredOccasion('Formal');
        await tester.pumpAndSettle();
        expect(todayRepo.calls, greaterThan(initialCalls));

        final afterOccasion = todayRepo.calls;
        UserSession.hasSavedWardrobeItem = true;
        await tester.pumpAndSettle();
        expect(todayRepo.calls, greaterThan(afterOccasion));
      },
    );
  });
}
