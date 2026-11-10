import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:fansivibe/features/outfit_builder/data/outfit_models.dart';
import 'package:fansivibe/features/outfit_builder/data/outfit_repository.dart';
import 'package:fansivibe/features/outfit_builder/presentation/outfit_recommendation_screen.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/auth/secure_token_storage.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

const String _topId = '11111111-1111-4111-8111-111111111111';
const String _bottomId = '22222222-2222-4222-8222-222222222222';
const String _replacementBottomId = '33333333-3333-4333-8333-333333333333';

Map<String, dynamic> _baseOutfitWire() => {
  'title': 'Smart Casual Look',
  'matchScore': 0.82,
  'components': [
    {
      'id': _topId,
      'name': 'White Oxford Shirt',
      'category': 'tops',
      'color': 'white',
      'material': 'cotton',
      'reason': 'Chosen tops piece',
    },
    {
      'id': _bottomId,
      'name': 'Dark Navy Chinos',
      'category': 'bottoms',
      'color': 'navy',
      'material': 'cotton',
      'reason': 'Chosen bottoms piece',
    },
  ],
  'reasons': ['Clean contrast between white top and navy bottoms'],
  'colorHarmony': 'Balanced monochrome/navy palette',
  'bodyFit': 'Tailored silhouette',
  'occasionMatch': 'Smart casual',
  'styleScoreImpact': '82% match from 2 pieces',
  'improvementSuggestion': 'Consider accessories',
  'selectedOccasion': 'work',
  'selectedMood': 'sharp',
  'selectedColorPalette': 'neutral',
};

const OutfitGenerateRequest _dummyRequest = OutfitGenerateRequest(
  occasion: 'work',
  mood: 'sharp',
  fit: 'tailored',
  colorPalette: 'neutral',
);

class _TestOutfitRepository implements OutfitBuilderRepository {
  List<OutfitCandidateItem> candidateResults = [];
  OutfitSlotSwapResponse? swapResult;
  bool throwOnCandidates = false;
  bool throwOnSwap = false;
  int candidateCalls = 0;
  int swapCalls = 0;
  OutfitSlotSwapRequest? lastSwapRequest;

  @override
  Future<OutfitResult> generateOutfit({
    required String occasion,
    required String mood,
    required String fit,
    required String colorPalette,
    String? seed,
    List<String>? preferredItemIds,
  }) async => const OutfitResult.noneAvailable();

  @override
  Future<SavedOutfit?> saveOutfit({
    String? lookId,
    required String title,
    required Map<String, dynamic> snapshot,
    required String idempotencyKey,
  }) async => null;

  @override
  Future<List<OutfitCandidateItem>> getCandidates({
    required String slot,
    List<String>? currentGarmentIds,
    int limit = 20,
  }) async {
    candidateCalls++;
    if (throwOnCandidates) {
      throw Exception('Network unreachable');
    }
    return candidateResults;
  }

  @override
  Future<OutfitSlotSwapResponse?> swapSlot({
    required OutfitSlotSwapRequest request,
  }) async {
    swapCalls++;
    lastSwapRequest = request;
    if (throwOnSwap) {
      throw Exception('Swap failed');
    }
    return swapResult;
  }
}

class _TestWardrobeRepository implements WardrobeRepository {
  List<WardrobeItemData> items = [];
  int listCalls = 0;

  @override
  Future<List<WardrobeItemData>> listItems({
    String? category,
    String? color,
    String? sortBy,
    String? order,
    int page = 1,
    int pageSize = 20,
  }) async {
    listCalls++;
    return items
        .where((it) => category == null || it.category == category)
        .toList();
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

  @override
  Future<WearEventLogResponse?> logEnsembleWear({
    required List<String> itemIds,
    DateTime? wornAt,
    String? idempotencyKey,
  }) async => null;
}

Widget _buildTestHarness({
  required OutfitRecommendation recommendation,
  required OutfitBuilderRepository outfitRepository,
  WardrobeRepository? wardrobeRepository,
}) {
  return MaterialApp(
    home: Scaffold(
      body: OutfitRecommendationScreen(
        recommendation: recommendation,
        request: _dummyRequest,
        outfitRepository: outfitRepository,
        wardrobeRepository: wardrobeRepository ?? _TestWardrobeRepository(),
      ),
    ),
  );
}

void _setViewport(WidgetTester tester) {
  tester.view.physicalSize = const Size(800, 2400);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

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

  group('P1-1 Interactive Outfit Component Swapping (Authenticated)', () {
    testWidgets('Tapping Replace opens swap sheet and displays candidates', (
      WidgetTester tester,
    ) async {
      _setViewport(tester);
      final repo = _TestOutfitRepository()
        ..candidateResults = [
          const OutfitCandidateItem(
            id: _replacementBottomId,
            name: 'Grey Wool Trousers',
            category: 'bottoms',
            color: 'grey',
            material: 'wool',
          ),
        ];

      final rec = OutfitRecommendation.fromJson(_baseOutfitWire());
      await tester.pumpWidget(
        _buildTestHarness(recommendation: rec, outfitRepository: repo),
      );
      await tester.pumpAndSettle();

      final replaceButtons = find.text('Replace');
      expect(replaceButtons, findsNWidgets(2));

      // Tap Replace for bottoms
      await tester.tap(replaceButtons.at(1));
      await tester.pumpAndSettle();

      expect(find.text('Replace Dark Navy Chinos'), findsOneWidget);
      expect(find.text('Grey Wool Trousers'), findsOneWidget);
      expect(repo.candidateCalls, 1);
    });

    testWidgets('Empty candidate state displays truthful message', (
      WidgetTester tester,
    ) async {
      _setViewport(tester);
      final repo = _TestOutfitRepository()..candidateResults = [];

      final rec = OutfitRecommendation.fromJson(_baseOutfitWire());
      await tester.pumpWidget(
        _buildTestHarness(recommendation: rec, outfitRepository: repo),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Replace').at(0));
      await tester.pumpAndSettle();

      expect(find.text('No alternative tops found'), findsOneWidget);
      expect(
        find.textContaining(
          'You don\'t have other tops pieces in your wardrobe',
        ),
        findsOneWidget,
      );
    });

    testWidgets('Error state on candidate fetch displays retry button', (
      WidgetTester tester,
    ) async {
      _setViewport(tester);
      final repo = _TestOutfitRepository()..throwOnCandidates = true;

      final rec = OutfitRecommendation.fromJson(_baseOutfitWire());
      await tester.pumpWidget(
        _buildTestHarness(recommendation: rec, outfitRepository: repo),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Replace').at(0));
      await tester.pumpAndSettle();

      expect(
        find.textContaining('Unable to load wardrobe alternatives'),
        findsOneWidget,
      );
      expect(find.text('Retry'), findsOneWidget);

      repo.throwOnCandidates = false;
      repo.candidateResults = [
        const OutfitCandidateItem(
          id: 'alt-top-1',
          name: 'Blue Linen Shirt',
          category: 'tops',
          color: 'blue',
        ),
      ];

      await tester.tap(find.text('Retry'));
      await tester.pumpAndSettle();

      expect(find.text('Blue Linen Shirt'), findsOneWidget);
      expect(repo.candidateCalls, 2);
    });

    testWidgets(
      'Selecting candidate previews updated compatibility before confirmation',
      (WidgetTester tester) async {
        _setViewport(tester);
        final updatedWire = _baseOutfitWire();
        updatedWire['matchScore'] = 0.91;
        updatedWire['styleScoreImpact'] = '91% ensemble match from 2 pieces';
        (updatedWire['components'] as List)[1] = {
          'id': _replacementBottomId,
          'name': 'Grey Wool Trousers',
          'category': 'bottoms',
          'color': 'grey',
          'material': 'wool',
          'reason': 'Replacement piece for tailored fit',
        };

        final repo = _TestOutfitRepository()
          ..candidateResults = [
            const OutfitCandidateItem(
              id: _replacementBottomId,
              name: 'Grey Wool Trousers',
              category: 'bottoms',
              color: 'grey',
              material: 'wool',
            ),
          ]
          ..swapResult = OutfitSlotSwapResponse(
            outfit: OutfitRecommendation.fromJson(updatedWire),
            replacedSlot: 'bottoms',
            previousGarmentId: _bottomId,
            replacementGarmentId: _replacementBottomId,
            compatibilityScore: 0.91,
            reasons: const ['Calculated using canonical compatibility engine'],
          );

        final rec = OutfitRecommendation.fromJson(_baseOutfitWire());
        await tester.pumpWidget(
          _buildTestHarness(recommendation: rec, outfitRepository: repo),
        );
        await tester.pumpAndSettle();

        await tester.tap(find.text('Replace').at(1));
        await tester.pumpAndSettle();

        await tester.tap(find.text('Grey Wool Trousers'));
        await tester.pumpAndSettle();

        expect(find.text('Preview Component Swap'), findsOneWidget);
        expect(find.text('Confirm Replacement'), findsOneWidget);
        expect(find.text('91%'), findsOneWidget);
        expect(repo.swapCalls, 1);
        expect(repo.lastSwapRequest?.slot, 'bottoms');
        expect(
          repo.lastSwapRequest?.replacementGarmentId,
          _replacementBottomId,
        );
      },
    );

    testWidgets('Confirming swap refreshes outfit on screen', (
      WidgetTester tester,
    ) async {
      _setViewport(tester);
      final updatedWire = _baseOutfitWire();
      updatedWire['matchScore'] = 0.91;
      (updatedWire['components'] as List)[1] = {
        'id': _replacementBottomId,
        'name': 'Grey Wool Trousers',
        'category': 'bottoms',
        'color': 'grey',
        'material': 'wool',
        'reason': 'Replacement piece for tailored fit',
      };

      final repo = _TestOutfitRepository()
        ..candidateResults = [
          const OutfitCandidateItem(
            id: _replacementBottomId,
            name: 'Grey Wool Trousers',
            category: 'bottoms',
            color: 'grey',
          ),
        ]
        ..swapResult = OutfitSlotSwapResponse(
          outfit: OutfitRecommendation.fromJson(updatedWire),
          replacedSlot: 'bottoms',
          previousGarmentId: _bottomId,
          replacementGarmentId: _replacementBottomId,
          compatibilityScore: 0.91,
          reasons: const ['Recalculated with canonical rules'],
        );

      final rec = OutfitRecommendation.fromJson(_baseOutfitWire());
      await tester.pumpWidget(
        _buildTestHarness(recommendation: rec, outfitRepository: repo),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Replace').at(1));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Grey Wool Trousers'));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Confirm Replacement'));
      await tester.pumpAndSettle();

      expect(find.text('Replace Dark Navy Chinos'), findsNothing);
      expect(find.text('Grey Wool Trousers'), findsOneWidget);
      expect(find.text('Dark Navy Chinos'), findsNothing);
      expect(find.text('White Oxford Shirt'), findsOneWidget);
    });

    testWidgets('Cancelling swap keeps original outfit unchanged', (
      WidgetTester tester,
    ) async {
      _setViewport(tester);
      final repo = _TestOutfitRepository()
        ..candidateResults = [
          const OutfitCandidateItem(
            id: _replacementBottomId,
            name: 'Grey Wool Trousers',
            category: 'bottoms',
            color: 'grey',
          ),
        ];

      final rec = OutfitRecommendation.fromJson(_baseOutfitWire());
      await tester.pumpWidget(
        _buildTestHarness(recommendation: rec, outfitRepository: repo),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Replace').at(1));
      await tester.pumpAndSettle();

      await tester.tap(find.byIcon(Icons.close_rounded));
      await tester.pumpAndSettle();

      expect(find.text('Dark Navy Chinos'), findsOneWidget);
      expect(find.text('Grey Wool Trousers'), findsNothing);
    });

    testWidgets(
      'Pinning garment prevents replacing it and protects it during swaps',
      (WidgetTester tester) async {
        _setViewport(tester);
        final updatedWire = _baseOutfitWire();
        final repo = _TestOutfitRepository()
          ..candidateResults = [
            const OutfitCandidateItem(
              id: _replacementBottomId,
              name: 'Grey Wool Trousers',
              category: 'bottoms',
              color: 'grey',
            ),
          ]
          ..swapResult = OutfitSlotSwapResponse(
            outfit: OutfitRecommendation.fromJson(updatedWire),
            replacedSlot: 'bottoms',
            previousGarmentId: _bottomId,
            replacementGarmentId: _replacementBottomId,
            compatibilityScore: 0.88,
            reasons: const ['Updated with pinned piece preserved'],
          );

        final rec = OutfitRecommendation.fromJson(_baseOutfitWire());
        await tester.pumpWidget(
          _buildTestHarness(recommendation: rec, outfitRepository: repo),
        );
        await tester.pumpAndSettle();

        // Tap pin on top piece
        final pinButtons = find.byIcon(Icons.push_pin_outlined);
        expect(pinButtons, findsNWidgets(2));
        await tester.tap(pinButtons.first);
        await tester.pumpAndSettle();

        // Top piece now shows pinned badge & filled pin icon
        expect(find.byIcon(Icons.push_pin_rounded), findsNWidgets(2));
        // Top piece Replace button transformed into disabled 'Pinned' button
        expect(find.text('Pinned'), findsOneWidget);
        expect(
          find.text('Replace'),
          findsOneWidget,
        ); // Only bottom piece has Replace

        // Open replace on the remaining unpinned slot (bottoms)
        await tester.tap(find.text('Replace'));
        await tester.pumpAndSettle();

        expect(find.text('Replace Dark Navy Chinos'), findsOneWidget);

        // Select candidate
        await tester.tap(find.text('Grey Wool Trousers'));
        await tester.pumpAndSettle();

        // Confirm swap was called with top garment in pinnedGarmentIds
        expect(repo.swapCalls, 1);
        expect(repo.lastSwapRequest?.pinnedGarmentIds, contains(_topId));
      },
    );
  });

  group('P1-1 Guest Mode Isolation (D10 Option A)', () {
    setUp(() async {
      AuthSession.resetForTest();
      LocalStorage.authToken = null;
    });

    testWidgets(
      'Guest mode loads alternatives from local wardrobe without backend request',
      (WidgetTester tester) async {
        _setViewport(tester);
        final repo = _TestOutfitRepository();
        final wardrobe = _TestWardrobeRepository()
          ..items = [
            const WardrobeItemData(
              id: 'local-pants-1',
              name: 'Guest Khaki Chinos',
              category: 'bottoms',
              color: 'khaki',
            ),
          ];

        final rec = OutfitRecommendation.fromJson(_baseOutfitWire());

        await tester.pumpWidget(
          _buildTestHarness(
            recommendation: rec,
            outfitRepository: repo,
            wardrobeRepository: wardrobe,
          ),
        );
        await tester.pumpAndSettle();

        await tester.tap(find.text('Replace').at(1));
        await tester.pumpAndSettle();

        // Zero backend calls
        expect(repo.candidateCalls, 0);
        expect(wardrobe.listCalls, 1);

        // Local candidate displayed
        expect(find.text('Guest Khaki Chinos'), findsOneWidget);
      },
    );

    testWidgets(
      'Guest mode swap recalculates locally without backend request',
      (WidgetTester tester) async {
        _setViewport(tester);
        final repo = _TestOutfitRepository();
        final wardrobe = _TestWardrobeRepository()
          ..items = [
            const WardrobeItemData(
              id: 'local-pants-1',
              name: 'Guest Khaki Chinos',
              category: 'bottoms',
              color: 'khaki',
            ),
          ];

        final rec = OutfitRecommendation.fromJson(_baseOutfitWire());

        await tester.pumpWidget(
          _buildTestHarness(
            recommendation: rec,
            outfitRepository: repo,
            wardrobeRepository: wardrobe,
          ),
        );
        await tester.pumpAndSettle();

        await tester.tap(find.text('Replace').at(1));
        await tester.pumpAndSettle();

        await tester.tap(find.text('Guest Khaki Chinos'));
        await tester.pumpAndSettle();

        // Zero backend calls
        expect(repo.swapCalls, 0);

        await tester.tap(find.text('Confirm Replacement'));
        await tester.pumpAndSettle();

        // Replaced piece rendered on screen
        expect(find.text('Guest Khaki Chinos'), findsOneWidget);
        expect(find.text('Dark Navy Chinos'), findsNothing);
      },
    );
  });
}
