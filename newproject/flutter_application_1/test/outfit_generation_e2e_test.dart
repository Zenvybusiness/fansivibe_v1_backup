import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/outfit_builder/data/outfit_models.dart';
import 'package:fansivibe/features/outfit_builder/data/outfit_repository.dart';
import 'package:fansivibe/features/outfit_builder/presentation/build_outfit_screen.dart';
import 'package:fansivibe/features/outfit_builder/presentation/outfit_generation_screen.dart';
import 'package:fansivibe/features/outfit_builder/presentation/outfit_recommendation_screen.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/auth/secure_token_storage.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

// ---------------------------------------------------------------------------
// Test Doubles & Fixtures
// ---------------------------------------------------------------------------

const _topId = '11111111-1111-4111-8111-111111111111';
const _botId = '22222222-2222-4222-8222-222222222222';
const _shoeId = '33333333-3333-4333-8333-333333333333';
const _topAltId = '44444444-4444-4444-8444-444444444444';

OutfitCandidate _buildCandidate({
  required String id,
  required String title,
  required double score,
  String topName = 'White Linen Shirt',
  String topId = _topId,
}) {
  return OutfitCandidate(
    id: id,
    title: title,
    occasion: 'casual',
    styleDescription: 'Relaxed casual coordination with balanced contrast',
    matchScore: score,
    components: [
      OutfitComponent(
        id: topId,
        name: topName,
        category: 'tops',
        color: 'white',
        material: 'linen',
        role: 'top',
        reason: 'Selected top piece for casual styling',
      ),
      const OutfitComponent(
        id: _botId,
        name: 'Beige Chinos',
        category: 'bottoms',
        color: 'beige',
        material: 'cotton',
        role: 'bottom',
        reason: 'Selected bottom piece for casual styling',
      ),
      const OutfitComponent(
        id: _shoeId,
        name: 'White Sneakers',
        category: 'footwear',
        color: 'white',
        material: 'leather',
        role: 'footwear',
        reason: 'Selected footwear piece for casual styling',
      ),
    ],
    reasons: const [
      'Grounded light neutral color palette',
      'Relaxed silhouette fit across all layers',
    ],
    stylingRationale: 'A balanced, breathable summer combination suitable for casual outings.',
    stylingTips: const [
      'Cuff the chinos slightly above the sneakers for an effortless look.',
      'Leave the top linen button open for relaxed breathability.',
    ],
    missingPieces: const [
      MissingPieceSuggestion(
        role: 'accessory',
        category: 'accessories',
        suggestion: 'Consider adding a braided leather belt in brown to tie the neutrals together.',
      ),
    ],
    colorHarmony: 'Monochromatic light neutrals with high comfort balance',
    scoreBreakdown: const ScoreBreakdown(
      totalScore: 0.88,
      occasionMatch: 0.35,
      paletteMatch: 0.25,
      fitMatch: 0.18,
      preferenceBonus: 0.10,
      calculation: 'Total compatibility 88% based on occasion and palette harmony.',
    ),
    selectedOccasion: 'casual',
    selectedMood: 'relaxed',
    selectedColorPalette: 'neutral',
    snapshot: {
      'title': title,
      'matchScore': score,
      'components': [
        {
          'id': topId,
          'name': topName,
          'category': 'tops',
          'color': 'white',
          'material': 'linen',
          'role': 'top',
          'reason': 'Selected top piece',
        },
        {
          'id': _botId,
          'name': 'Beige Chinos',
          'category': 'bottoms',
          'color': 'beige',
          'material': 'cotton',
          'role': 'bottom',
          'reason': 'Selected bottom piece',
        },
      ],
      'reasons': ['Grounded light neutral color palette'],
      'colorHarmony': 'Monochromatic light neutrals',
      'bodyFit': 'Relaxed fit',
      'occasionMatch': 'Casual weekend match',
      'styleScoreImpact': 'High ensemble compatibility (+88% match)',
      'improvementSuggestion': 'Add an accessory piece to ground the neutrals.',
      'selectedOccasion': 'casual',
      'selectedMood': 'relaxed',
      'selectedColorPalette': 'neutral',
    },
  );
}

class _E2EOutfitRepository implements OutfitBuilderRepository {
  OutfitCompositionResult composeResult = OutfitCompositionResult.available(
    OutfitCompositionResponse(
      candidates: [
        _buildCandidate(id: 'cand-1', title: 'Look 1: Linen Elegance', score: 0.88),
        _buildCandidate(id: 'cand-2', title: 'Look 2: Casual Modern', score: 0.82),
      ],
      totalCandidates: 2,
      occasion: 'casual',
      mood: 'relaxed',
      fit: 'regular',
      colorPalette: 'neutral',
    ),
  );

  OutfitResult generateResult = OutfitResult.noneAvailable();
  SavedOutfit? saveResult = SavedOutfit(
    id: 'saved-1',
    lookId: 'saved-look-1',
    title: 'Saved Look',
    snapshot: const {'title': 'Saved Look'},
    createdAt: DateTime(2026, 1, 1),
  );

  int composeCalls = 0;
  int saveCalls = 0;
  List<OutfitCandidateItem> candidateItems = [
    const OutfitCandidateItem(
      id: _topAltId,
      name: 'Navy Cotton T-Shirt',
      category: 'tops',
      color: 'navy',
      material: 'cotton',
      isFavorite: true,
      fit: 'regular',
    ),
  ];

  @override
  Future<OutfitCompositionResult> composeOutfits({
    String? occasion,
    String? mood,
    String? fit,
    String? colorPalette,
    String? query,
    List<String>? preferredItemIds,
    int limit = 3,
    String? seed,
    String? weatherContext,
  }) async {
    composeCalls++;
    return composeResult;
  }

  @override
  Future<OutfitResult> generateOutfit({
    required String occasion,
    required String mood,
    required String fit,
    required String colorPalette,
    String? seed,
    List<String>? preferredItemIds,
  }) async => generateResult;

  @override
  Future<SavedOutfit?> saveOutfit({
    String? lookId,
    required String title,
    required Map<String, dynamic> snapshot,
    required String idempotencyKey,
  }) async {
    saveCalls++;
    return saveResult;
  }

  @override
  Future<List<OutfitCandidateItem>> getCandidates({
    required String slot,
    List<String>? currentGarmentIds,
    int limit = 20,
  }) async => candidateItems;

  @override
  Future<OutfitSlotSwapResponse?> swapSlot({
    required OutfitSlotSwapRequest request,
  }) async {
    return OutfitSlotSwapResponse(
      outfit: _buildCandidate(
        id: 'cand-swapped',
        title: 'Look 1: Linen Elegance (Swapped)',
        score: 0.85,
        topName: 'Navy Cotton T-Shirt',
        topId: request.replacementGarmentId,
      ).toRecommendation(),
      replacedSlot: request.slot,
      replacementGarmentId: request.replacementGarmentId,
      compatibilityScore: 0.85,
      reasons: const ['Balanced tones with navy contrast'],
    );
  }
}

class _E2EWardrobeRepository implements WardrobeRepository {
  List<WardrobeItemData> items = [];

  @override
  Future<List<WardrobeItemData>> listItems({
    String? category,
    String? color,
    String? sortBy,
    String? order,
    int page = 1,
    int pageSize = 20,
  }) async => items;

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

  @override
  Future<WearEventLogResponse?> logEnsembleWear({
    required List<String> itemIds,
    DateTime? wornAt,
    String? idempotencyKey,
  }) async => null;
}

Widget _appHarness({
  required Widget child,
  NavigatorObserver? observer,
}) {
  return MaterialApp(
    navigatorObservers: [if (observer != null) observer],
    theme: ThemeData.dark().copyWith(
      scaffoldBackgroundColor: const Color(0xFF121214),
    ),
    home: child,
  );
}

Widget _flowApp(OutfitBuilderRepository repo) {
  return MaterialApp.router(
    theme: ThemeData.dark().copyWith(
      scaffoldBackgroundColor: const Color(0xFF121214),
    ),
    routerConfig: GoRouter(
      initialLocation: '/gen',
      routes: [
        GoRoute(
          path: '/gen',
          builder: (context, state) => OutfitGenerationScreen(
            occasion: 'casual',
            mood: 'relaxed',
            fit: 'regular',
            colorPalette: 'neutral',
            outfitRepository: repo,
          ),
        ),
        GoRoute(
          name: RouteNames.outfitRecommendation,
          path: '/rec',
          builder: (context, state) {
            final extra = state.extra as Map<String, dynamic>;
            return OutfitRecommendationScreen(
              recommendation: OutfitRecommendation.fromJson(
                extra['recommendation'] as Map<String, dynamic>,
              ),
              request: OutfitGenerateRequest.fromJson(
                extra['request'] as Map<String, dynamic>,
              ),
              candidates: (extra['candidates'] as List<dynamic>?)
                  ?.map((c) => OutfitCandidate.fromJson(c as Map<String, dynamic>))
                  .toList(),
              outfitRepository: repo,
            );
          },
        ),
      ],
    ),
  );
}

void _setViewport(WidgetTester tester) {
  tester.view.physicalSize = const Size(800, 2400);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

// ---------------------------------------------------------------------------
// Test Suite
// ---------------------------------------------------------------------------

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({
      'fansivibe_auth_token': 'valid_jwt_token',
    });
    final prefs = await SharedPreferences.getInstance();
    LocalStorage.init(prefs: prefs);
    SecureTokenStorage.resetForTest();
    await SecureTokenStorage.init();
    await AuthSession.saveSession('valid_jwt_token');
  });

  tearDown(() {
    AuthSession.resetForTest();
  });

  group('Phase 3 Outfit Generation E2E Journey', () {
    testWidgets('1. Entry point renders option chips and natural language trigger', (
      WidgetTester tester,
    ) async {
      _setViewport(tester);
      await tester.pumpWidget(_appHarness(child: const BuildOutfitScreen()));
      await tester.pumpAndSettle();

      expect(find.text('Create Your Look'), findsOneWidget);
      expect(find.text('Occasion'), findsOneWidget);
      expect(find.text('Mood'), findsOneWidget);
      expect(find.text('Preferred Fit'), findsOneWidget);
      expect(find.text('Color Palette'), findsOneWidget);
      expect(find.text('Describe what you want in natural language…'), findsOneWidget);
    });

    testWidgets('2. User request submission with natural language prompts enables build', (
      WidgetTester tester,
    ) async {
      _setViewport(tester);
      await tester.pumpWidget(_appHarness(child: const BuildOutfitScreen()));
      await tester.pumpAndSettle();

      // Tap natural language toggle
      await tester.tap(find.byKey(const Key('btn_toggle_natural_language')));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('input_outfit_natural_language')), findsOneWidget);

      // Enter query
      await tester.enterText(
        find.byKey(const Key('input_outfit_natural_language')),
        'Dinner date with casual relaxed vibe',
      );
      await tester.pump();

      // Build outfit button should now be enabled
      final buildButtonFinder = find.ancestor(
        of: find.text('Build Outfit'),
        matching: find.byWidgetPredicate((w) => w is ButtonStyleButton),
      );
      expect(tester.widget<ButtonStyleButton>(buildButtonFinder).onPressed, isNotNull);
    });

    testWidgets('3. Loading and error states with honest retry button', (
      WidgetTester tester,
    ) async {
      _setViewport(tester);
      final repo = _E2EOutfitRepository()
        ..composeResult = const OutfitCompositionResult.failure(OutfitFailure.networkError);

      await tester.pumpWidget(_flowApp(repo));

      // Verify loading indicators
      expect(find.text('Building Outfit'), findsOneWidget);
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
      await tester.pumpAndSettle();

      // Verify honest error state
      expect(find.text('Couldn\'t build your outfit'), findsOneWidget);
      expect(find.text('Try Again'), findsOneWidget);

      // Tap Try Again
      repo.composeResult = OutfitCompositionResult.available(
        OutfitCompositionResponse(
          candidates: [_buildCandidate(id: 'c1', title: 'Look 1', score: 0.85)],
          totalCandidates: 1,
          occasion: 'casual',
          mood: 'relaxed',
          fit: 'regular',
          colorPalette: 'neutral',
        ),
      );
      await tester.tap(find.text('Try Again'));
      await tester.pump();
      expect(repo.composeCalls, 2);
    });

    testWidgets('4. Multiple outfit cards display with look switching tabs', (
      WidgetTester tester,
    ) async {
      _setViewport(tester);
      final cand1 = _buildCandidate(id: 'cand-1', title: 'Look 1: Linen Elegance', score: 0.88);
      final cand2 = _buildCandidate(id: 'cand-2', title: 'Look 2: Casual Modern', score: 0.82);

      await tester.pumpWidget(
        _appHarness(
          child: OutfitRecommendationScreen(
            recommendation: cand1.toRecommendation(),
            request: const OutfitGenerateRequest(
              occasion: 'casual',
              mood: 'relaxed',
              fit: 'regular',
              colorPalette: 'neutral',
            ),
            candidates: [cand1, cand2],
            outfitRepository: _E2EOutfitRepository(),
            wardrobeRepository: _E2EWardrobeRepository(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Verify both candidate tabs
      expect(find.text('Look 1'), findsOneWidget);
      expect(find.text('Look 2'), findsOneWidget);
      expect(find.text('88% match'), findsOneWidget);
      expect(find.text('82% match'), findsOneWidget);
      expect(find.text('Look 1: Linen Elegance'), findsOneWidget);

      // Switch to Look 2
      await tester.tap(find.byKey(const Key('candidate_tab_1')));
      await tester.pumpAndSettle();

      expect(find.text('Look 2: Casual Modern'), findsOneWidget);
    });

    testWidgets('5. Garment display shows roles, fallbacks, and grounded details', (
      WidgetTester tester,
    ) async {
      _setViewport(tester);
      final cand = _buildCandidate(id: 'cand-1', title: 'Look 1: Linen Elegance', score: 0.88);

      await tester.pumpWidget(
        _appHarness(
          child: OutfitRecommendationScreen(
            recommendation: cand.toRecommendation(),
            request: const OutfitGenerateRequest(
              occasion: 'casual',
              mood: 'relaxed',
              fit: 'regular',
              colorPalette: 'neutral',
            ),
            candidates: [cand],
            outfitRepository: _E2EOutfitRepository(),
            wardrobeRepository: _E2EWardrobeRepository(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('White Linen Shirt'), findsOneWidget);
      expect(find.text('Beige Chinos'), findsOneWidget);
      expect(find.text('White Sneakers'), findsOneWidget);
      expect(find.text('TOP'), findsOneWidget);
      expect(find.text('BOTTOM'), findsOneWidget);
      expect(find.text('FOOTWEAR'), findsOneWidget);
    });

    testWidgets('6. Garment replacement invokes slot swap sheet and updates outfit', (
      WidgetTester tester,
    ) async {
      _setViewport(tester);
      final cand = _buildCandidate(id: 'cand-1', title: 'Look 1: Linen Elegance', score: 0.88);
      final repo = _E2EOutfitRepository();

      await tester.pumpWidget(
        _appHarness(
          child: OutfitRecommendationScreen(
            recommendation: cand.toRecommendation(),
            request: const OutfitGenerateRequest(
              occasion: 'casual',
              mood: 'relaxed',
              fit: 'regular',
              colorPalette: 'neutral',
            ),
            candidates: [cand],
            outfitRepository: repo,
            wardrobeRepository: _E2EWardrobeRepository(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Tap Replace on top component
      await tester.scrollUntilVisible(find.text('Replace').first, 300);
      await tester.tap(find.text('Replace').first);
      await tester.pumpAndSettle();

      // Verify bottom sheet candidate appears
      expect(find.text('Navy Cotton T-Shirt'), findsOneWidget);

      // Select replacement piece
      await tester.tap(find.text('Navy Cotton T-Shirt'));
      await tester.pumpAndSettle();

      // Confirm replacement
      await tester.tap(find.text('Confirm Replacement'));
      await tester.pumpAndSettle();

      // Outfit should now display replaced piece
      expect(find.text('Navy Cotton T-Shirt'), findsOneWidget);
    });

    testWidgets('7. Alternative generation button re-derives outfits', (
      WidgetTester tester,
    ) async {
      _setViewport(tester);
      final cand = _buildCandidate(id: 'cand-1', title: 'Look 1: Original', score: 0.88);
      final repo = _E2EOutfitRepository()
        ..composeResult = OutfitCompositionResult.available(
          OutfitCompositionResponse(
            candidates: [_buildCandidate(id: 'cand-alt-1', title: 'Look 1: Regenerated', score: 0.84)],
            totalCandidates: 1,
            occasion: 'casual',
            mood: 'relaxed',
            fit: 'regular',
            colorPalette: 'neutral',
          ),
        );

      await tester.pumpWidget(
        _appHarness(
          child: OutfitRecommendationScreen(
            recommendation: cand.toRecommendation(),
            request: const OutfitGenerateRequest(
              occasion: 'casual',
              mood: 'relaxed',
              fit: 'regular',
              colorPalette: 'neutral',
            ),
            candidates: [cand],
            outfitRepository: repo,
            wardrobeRepository: _E2EWardrobeRepository(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Look 1: Original'), findsOneWidget);

      // Tap Regenerate
      await tester.scrollUntilVisible(find.text('Regenerate'), 300);
      await tester.tap(find.text('Regenerate'));
      await tester.pumpAndSettle();

      expect(repo.composeCalls, 1);
      expect(find.text('Look 1: Regenerated'), findsOneWidget);
    });

    testWidgets('8. Saving an outfit calls repository and updates button state', (
      WidgetTester tester,
    ) async {
      _setViewport(tester);
      final cand = _buildCandidate(id: 'cand-1', title: 'Look 1: To Save', score: 0.88);
      final repo = _E2EOutfitRepository();

      await tester.pumpWidget(
        _appHarness(
          child: OutfitRecommendationScreen(
            recommendation: cand.toRecommendation(),
            request: const OutfitGenerateRequest(
              occasion: 'casual',
              mood: 'relaxed',
              fit: 'regular',
              colorPalette: 'neutral',
            ),
            candidates: [cand],
            outfitRepository: repo,
            wardrobeRepository: _E2EWardrobeRepository(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Save Outfit'), findsOneWidget);

      // Tap Save Outfit
      await tester.scrollUntilVisible(find.text('Save Outfit'), 300);
      await tester.tap(find.text('Save Outfit'));
      await tester.pumpAndSettle();

      expect(repo.saveCalls, 1);
      expect(find.text('Saved'), findsOneWidget);
    });

    testWidgets('9. Retrieving saved outfits navigation action is present', (
      WidgetTester tester,
    ) async {
      _setViewport(tester);
      final cand = _buildCandidate(id: 'cand-1', title: 'Look 1', score: 0.88);

      await tester.pumpWidget(
        _appHarness(
          child: OutfitRecommendationScreen(
            recommendation: cand.toRecommendation(),
            request: const OutfitGenerateRequest(
              occasion: 'casual',
              mood: 'relaxed',
              fit: 'regular',
              colorPalette: 'neutral',
            ),
            candidates: [cand],
            outfitRepository: _E2EOutfitRepository(),
            wardrobeRepository: _E2EWardrobeRepository(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.scrollUntilVisible(find.text('View Saved Outfits'), 300);
      expect(find.text('View Saved Outfits'), findsOneWidget);
      expect(find.byKey(const Key('btn_view_saved_outfits_nav')), findsOneWidget);
    });

    testWidgets('10. Empty wardrobe guidance displays honest copy and wardrobe navigation', (
      WidgetTester tester,
    ) async {
      _setViewport(tester);
      final repo = _E2EOutfitRepository()
        ..composeResult = const OutfitCompositionResult.noneAvailable(emptyReason: 'empty_wardrobe');

      await tester.pumpWidget(
        _appHarness(
          child: OutfitGenerationScreen(
            occasion: 'casual',
            mood: 'relaxed',
            fit: 'regular',
            colorPalette: 'neutral',
            outfitRepository: repo,
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('No matching outfit'), findsOneWidget);
      expect(find.text('Add some wardrobe items to build an outfit.'), findsOneWidget);
      expect(find.text('Add wardrobe items'), findsOneWidget);
    });
  });
}
