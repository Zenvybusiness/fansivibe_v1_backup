import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:fansivibe/features/home/data/today_look_models.dart';
import 'package:fansivibe/features/home/data/today_look_repository.dart';
import 'package:fansivibe/features/home/presentation/daily_outfit_screen.dart';
import 'package:fansivibe/features/outfit_builder/data/outfit_models.dart';
import 'package:fansivibe/features/outfit_builder/presentation/outfit_recommendation_screen.dart';
import 'package:fansivibe/features/wardrobe/data/local_wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_client.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/presentation/ensemble_wear_confirmation_sheet.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:go_router/go_router.dart';

const _itemA = '11111111-1111-4111-8111-111111111111';
const _itemB = '22222222-2222-4222-8222-222222222222';
const _groupA = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const _wearA = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const _wearB = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc';

Map<String, dynamic> _wearResponseJson({
  bool created = true,
  List<String> items = const [_itemA, _itemB],
}) =>
    {
      'wearGroupId': _groupA,
      'wornAt': '2026-10-31T20:00:00.000Z',
      'created': created,
      'wears': items
          .map(
            (id) => {
              'id': id == _itemA ? _wearA : _wearB,
              'wardrobeItemId': id,
              'wornAt': '2026-10-31T20:00:00.000Z',
              'wearGroupId': _groupA,
              'createdAt': '2026-10-31T20:00:00.000Z',
            },
          )
          .toList(),
    };

class _MockScriptedWardrobeRepository implements WardrobeRepository {
  List<String>? lastLoggedIds;
  String? lastIdempotencyKey;
  int logCallCount = 0;
  int wearSummaryCallCount = 0;
  WearEventLogResponse? nextResponse;
  bool shouldThrow = false;

  @override
  Future<WearEventLogResponse?> logEnsembleWear({
    required List<String> itemIds,
    DateTime? wornAt,
    String? idempotencyKey,
  }) async {
    logCallCount++;
    lastLoggedIds = itemIds;
    lastIdempotencyKey = idempotencyKey;
    if (shouldThrow) throw Exception('Simulated network failure');
    return nextResponse;
  }

  @override
  Future<WearSummary?> getWearSummary() async {
    wearSummaryCallCount++;
    return null;
  }

  @override
  Future<WearEventLogResponse?> logWear({
    required List<String> itemIds,
    DateTime? wornAt,
    String? idempotencyKey,
  }) =>
      logEnsembleWear(
        itemIds: itemIds,
        wornAt: wornAt,
        idempotencyKey: idempotencyKey,
      );

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _FakeTodayLookRepo implements TodayLookRepository {
  _FakeTodayLookRepo(this.look);
  final TodayLook look;

  @override
  Future<TodayLookResult> getTodayLook() async => TodayLookResult.available(look);

  @override
  Future<TodayLookResult> regenerateTodayLook({String? seed}) async =>
      TodayLookResult.available(look);

  @override
  Future<SavedTodayLook?> saveTodayLook({
    required String title,
    String? lookId,
    required Map<String, dynamic> snapshot,
    required String idempotencyKey,
  }) async =>
      null;
}

TodayLook _buildTestTodayLook({List<TodayLookComponent>? components}) {
  final comps = components ??
      const [
        TodayLookComponent(
          id: _itemA,
          name: 'Navy Merino Knit',
          category: 'tops',
          color: 'navy',
          material: 'merino_wool',
        ),
        TodayLookComponent(
          id: _itemB,
          name: 'Charcoal Trousers',
          category: 'bottoms',
          color: 'charcoal',
          material: 'wool',
        ),
      ];

  return TodayLook(
    title: 'Modern Tailoring',
    description: 'Clean balanced silhouette',
    matchScore: 92,
    styleScore: 90,
    components: comps,
    reasons: const ['Color harmony across neutral tones'],
    wardrobeContext: const TodayLookWardrobeContext(totalItems: 12, matchingItems: 8),
    selectedItemIds: comps.map((c) => c.id).toList(),
    snapshot: const {'title': 'Modern Tailoring'},
  );
}

OutfitRecommendation _buildTestOutfitRec({List<OutfitComponent>? components}) {
  final comps = components ??
      const [
        OutfitComponent(
          id: _itemA,
          name: 'Navy Merino Knit',
          category: 'tops',
          color: 'navy',
          reason: 'Balances undertone',
        ),
        OutfitComponent(
          id: _itemB,
          name: 'Charcoal Trousers',
          category: 'bottoms',
          color: 'charcoal',
          reason: 'Elongates line',
        ),
      ];

  return OutfitRecommendation(
    title: 'Atelier Minimal',
    matchScore: 0.94,
    components: comps,
    reasons: const ['Precision fit and complementary palette'],
    colorHarmony: 'Complementary tones',
    bodyFit: 'Tailored drape',
    occasionMatch: 'Formal / Evening',
    styleScoreImpact: '+8% Ensemble Match',
    improvementSuggestion: 'Pair with minimal silver accessories',
    selectedOccasion: 'Evening',
    selectedMood: 'Polished',
    selectedColorPalette: 'Neutral Tones',
    snapshot: const {'title': 'Atelier Minimal'},
  );
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    LocalStorage.init(prefs: prefs);
    AuthSession.resetForTest();
    await AuthSession.saveSession('test-token');
  });

  group('WardrobeClient.logEnsembleWear', () {
    test('sends POST /v1/wardrobe/wears with correct headers and payload', () async {
      late http.Request captured;
      final mock = MockClient((request) async {
        captured = request;
        return http.Response(
          jsonEncode(_wearResponseJson(created: true)),
          201,
          headers: {'content-type': 'application/json'},
        );
      });

      final client = WardrobeClient(client: mock);
      final resp = await client.logEnsembleWear(
        itemIds: const [_itemA, _itemB],
        idempotencyKey: 'test-idemp-key',
      );

      expect(resp, isNotNull);
      expect(resp!.created, isTrue);
      expect(resp.wearGroupId, _groupA);
      expect(resp.wears.length, 2);

      expect(captured.method, 'POST');
      expect(captured.url.path, '/v1/wardrobe/wears');
      expect(captured.headers['Authorization'], 'Bearer test-token');
      expect(captured.headers['Idempotency-Key'], 'test-idemp-key');

      final body = jsonDecode(captured.body) as Map<String, dynamic>;
      expect(body['itemIds'], [_itemA, _itemB]);
    });

    test('parses idempotent replay with created = false', () async {
      final mock = MockClient((request) async {
        return http.Response(
          jsonEncode(_wearResponseJson(created: false)),
          201,
          headers: {'content-type': 'application/json'},
        );
      });

      final client = WardrobeClient(client: mock);
      final resp = await client.logEnsembleWear(
        itemIds: const [_itemA, _itemB],
      );

      expect(resp, isNotNull);
      expect(resp!.created, isFalse);
    });

    test('returns null on 404/409/422/500 API errors without throwing', () async {
      for (final code in [401, 404, 409, 422, 500]) {
        final mock = MockClient((request) async {
          return http.Response(jsonEncode({'error': 'failed'}), code);
        });
        final client = WardrobeClient(client: mock);
        final resp = await client.logEnsembleWear(itemIds: const [_itemA]);
        expect(resp, isNull);
      }
    });
  });

  group('WardrobeRepositoryImpl.logEnsembleWear', () {
    test('validates UUIDs, deduplicates, and delegates to client', () async {
      late List<String> passedItems;
      final mock = MockClient((request) async {
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        passedItems = (body['itemIds'] as List).cast<String>();
        return http.Response(jsonEncode(_wearResponseJson()), 201);
      });

      final repo = WardrobeRepositoryImpl(client: WardrobeClient(client: mock));
      // Pass duplicates and whitespace
      final resp = await repo.logEnsembleWear(
        itemIds: const [_itemA, '  $_itemB  ', _itemA],
      );

      expect(resp, isNotNull);
      expect(passedItems, [_itemA, _itemB]);
    });

    test('rejects empty list without network call', () async {
      var called = false;
      final mock = MockClient((request) async {
        called = true;
        return http.Response('{}', 200);
      });

      final repo = WardrobeRepositoryImpl(client: WardrobeClient(client: mock));
      final resp = await repo.logEnsembleWear(itemIds: const []);

      expect(resp, isNull);
      expect(called, isFalse);
    });

    test('rejects non-UUID items (zero fabrication) without network call', () async {
      var called = false;
      final mock = MockClient((request) async {
        called = true;
        return http.Response('{}', 200);
      });

      final repo = WardrobeRepositoryImpl(client: WardrobeClient(client: mock));
      final resp = await repo.logEnsembleWear(
        itemIds: const [_itemA, '12', 'fake-item'],
      );

      expect(resp, isNull);
      expect(called, isFalse);
    });

    test('rejects lists exceeding 10 canonical items', () async {
      var called = false;
      final mock = MockClient((request) async {
        called = true;
        return http.Response('{}', 200);
      });

      final repo = WardrobeRepositoryImpl(client: WardrobeClient(client: mock));
      final elevenItems = List.generate(
        11,
        (i) => '11111111-1111-4111-8111-11111111111$i',
      );
      final resp = await repo.logEnsembleWear(itemIds: elevenItems);

      expect(resp, isNull);
      expect(called, isFalse);
    });
  });

  group('LocalWardrobeRepository.logEnsembleWear', () {
    test('returns null without network calls (D10 guest boundary)', () async {
      final repo = LocalWardrobeRepository();
      final resp = await repo.logEnsembleWear(itemIds: const [_itemA, _itemB]);
      expect(resp, isNull);
    });
  });

  group('EnsembleWearConfirmationSheet Widget', () {
    testWidgets('renders preview, garment details, count, and confirms wear', (
      WidgetTester tester,
    ) async {
      final repo = _MockScriptedWardrobeRepository()
        ..nextResponse = WearEventLogResponse.fromJson(_wearResponseJson());

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: EnsembleWearConfirmationSheet(
              outfitTitle: 'Modern Tailoring',
              garments: const [
                EnsembleWearGarment(
                  id: _itemA,
                  name: 'Navy Merino Knit',
                  category: 'tops',
                  color: 'navy',
                  material: 'wool',
                ),
                EnsembleWearGarment(
                  id: _itemB,
                  name: 'Charcoal Trousers',
                  category: 'bottoms',
                  color: 'charcoal',
                  material: 'wool',
                ),
              ],
              wardrobeRepository: repo,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Modern Tailoring'), findsOneWidget);
      expect(find.text('2 of 2 garments selected'), findsOneWidget);
      expect(find.text('Navy Merino Knit'), findsOneWidget);
      expect(find.text('Charcoal Trousers'), findsOneWidget);
      expect(find.text('Confirm Wear (2)'), findsOneWidget);

      // Deselect item B
      await tester.tap(find.byKey(const Key('garment_toggle_$_itemB')));
      await tester.pumpAndSettle();

      expect(find.text('1 of 2 garments selected'), findsOneWidget);
      expect(find.text('Confirm Wear (1)'), findsOneWidget);

      // Tap Confirm
      await tester.tap(find.byKey(const Key('confirm_wear_button')));
      await tester.pumpAndSettle();

      expect(repo.logCallCount, 1);
      expect(repo.lastLoggedIds, [_itemA]);
      expect(find.text('Outfit Recorded!'), findsOneWidget);
      expect(find.byKey(const Key('wear_success_done_button')), findsOneWidget);
    });

    testWidgets('disables confirm button when all items are deselected', (
      WidgetTester tester,
    ) async {
      final repo = _MockScriptedWardrobeRepository();

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: EnsembleWearConfirmationSheet(
              outfitTitle: 'Minimal Look',
              garments: const [
                EnsembleWearGarment(
                  id: _itemA,
                  name: 'White Tee',
                  category: 'tops',
                ),
              ],
              wardrobeRepository: repo,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Confirm Wear (1)'), findsOneWidget);

      // Deselect the only item
      await tester.tap(find.byKey(const Key('garment_toggle_$_itemA')));
      await tester.pumpAndSettle();

      expect(find.text('Select At Least One Item'), findsOneWidget);

      // Tapping disabled button does nothing
      await tester.tap(find.byKey(const Key('confirm_wear_button')));
      await tester.pumpAndSettle();

      expect(repo.logCallCount, 0);
    });

    testWidgets('renders error view with retry on failure, preserving idempotency key', (
      WidgetTester tester,
    ) async {
      final repo = _MockScriptedWardrobeRepository()
        ..nextResponse = null; // failure

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: EnsembleWearConfirmationSheet(
              outfitTitle: 'Tailored Ensemble',
              garments: const [
                EnsembleWearGarment(
                  id: _itemA,
                  name: 'Merino Blazer',
                  category: 'outerwear',
                ),
              ],
              wardrobeRepository: repo,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('confirm_wear_button')));
      await tester.pumpAndSettle();

      expect(repo.logCallCount, 1);
      final firstKey = repo.lastIdempotencyKey;
      expect(find.text("Couldn't Record Wear"), findsOneWidget);

      // Set up success for retry
      repo.nextResponse = WearEventLogResponse.fromJson(_wearResponseJson(items: [_itemA]));

      await tester.tap(find.byKey(const Key('wear_error_retry_button')));
      await tester.pumpAndSettle();

      expect(repo.logCallCount, 2);
      expect(repo.lastIdempotencyKey, firstKey); // Idempotency key preserved across retry
      expect(find.text('Outfit Recorded!'), findsOneWidget);
    });

    testWidgets('enforces guest authentication boundary', (WidgetTester tester) async {
      AuthSession.resetForTest();
      await AuthSession.clearSession();
      LocalStorage.savedLocally = true;
      final repo = _MockScriptedWardrobeRepository();

      final router = GoRouter(
        initialLocation: '/sheet',
        routes: [
          GoRoute(
            path: '/sheet',
            builder: (context, state) => Scaffold(
              body: EnsembleWearConfirmationSheet(
                outfitTitle: 'Guest Outfit',
                garments: const [
                  EnsembleWearGarment(
                    id: _itemA,
                    name: 'Guest Item',
                    category: 'tops',
                  ),
                ],
                wardrobeRepository: repo,
              ),
            ),
          ),
          GoRoute(
            path: '/sign-in',
            name: RouteNames.signIn,
            builder: (context, state) =>
                const Scaffold(body: Text('sign-in-screen')),
          ),
        ],
      );

      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('confirm_wear_button')));
      await tester.pumpAndSettle();

      // Zero backend calls made
      expect(repo.logCallCount, 0);
      // Guest sign-in prompted
      expect(find.text('Sign in to log wears. Browsing stays free.'), findsOneWidget);
    });
  });

  group('DailyOutfitScreen Ensemble Wear Integration', () {
    testWidgets('renders Wear This Look and opens confirmation sheet', (
      WidgetTester tester,
    ) async {
      final look = _buildTestTodayLook();
      final todayRepo = _FakeTodayLookRepo(look);
      final wardrobeRepo = _MockScriptedWardrobeRepository()
        ..nextResponse = WearEventLogResponse.fromJson(_wearResponseJson());

      await tester.pumpWidget(
        MaterialApp(
          home: DailyOutfitScreen(
            todayLookRepository: todayRepo,
            wardrobeRepository: wardrobeRepo,
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Wear This Look'), findsOneWidget);

      // Tap Wear This Look
      await tester.ensureVisible(find.text('Wear This Look'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Wear This Look'));
      await tester.pumpAndSettle();

      // Sheet opens
      expect(find.byKey(const Key('ensemble_wear_sheet')), findsOneWidget);
      expect(find.text('Modern Tailoring'), findsWidgets);

      // Confirm in sheet
      await tester.tap(find.byKey(const Key('confirm_wear_button')));
      await tester.pumpAndSettle();

      expect(wardrobeRepo.logCallCount, 1);
      expect(find.text('Outfit Recorded!'), findsOneWidget);

      // Close sheet
      await tester.tap(find.byKey(const Key('wear_success_done_button')));
      await tester.pumpAndSettle();

      expect(wardrobeRepo.wearSummaryCallCount, 1); // Refreshed wear summary
      // Button updates to Worn Today
      expect(find.text('Worn Today'), findsOneWidget);
    });

    testWidgets('prevents wear logging when guest user', (WidgetTester tester) async {
      AuthSession.resetForTest();
      await AuthSession.clearSession();
      LocalStorage.savedLocally = true;
      final look = _buildTestTodayLook();
      final todayRepo = _FakeTodayLookRepo(look);
      final wardrobeRepo = _MockScriptedWardrobeRepository();

      await tester.pumpWidget(
        MaterialApp(
          home: DailyOutfitScreen(
            todayLookRepository: todayRepo,
            wardrobeRepository: wardrobeRepo,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // DailyOutfitScreen renders guest sign-in card
      expect(find.byType(GuestSignInCard), findsOneWidget);
      expect(find.text('Wear This Look'), findsNothing);
      expect(wardrobeRepo.logCallCount, 0);
    });
  });

  group('OutfitRecommendationScreen Ensemble Wear Integration', () {
    testWidgets('renders Log Wear Today and persists ensemble wear', (
      WidgetTester tester,
    ) async {
      final rec = _buildTestOutfitRec();
      final wardrobeRepo = _MockScriptedWardrobeRepository()
        ..nextResponse = WearEventLogResponse.fromJson(_wearResponseJson());

      await tester.pumpWidget(
        MaterialApp(
          home: OutfitRecommendationScreen(
            recommendation: rec,
            request: const OutfitGenerateRequest(
              occasion: 'Evening',
              mood: 'Polished',
              fit: 'Tailored',
              colorPalette: 'Neutral Tones',
            ),
            wardrobeRepository: wardrobeRepo,
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Log Wear Today'), findsOneWidget);

      await tester.ensureVisible(find.text('Log Wear Today'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Log Wear Today'));
      await tester.pumpAndSettle();

      // Sheet opens
      expect(find.byKey(const Key('ensemble_wear_sheet')), findsOneWidget);
      expect(find.text('Atelier Minimal'), findsWidgets);

      // Confirm in sheet
      await tester.tap(find.byKey(const Key('confirm_wear_button')));
      await tester.pumpAndSettle();

      expect(wardrobeRepo.logCallCount, 1);
      expect(find.text('Outfit Recorded!'), findsOneWidget);

      // Done
      await tester.tap(find.byKey(const Key('wear_success_done_button')));
      await tester.pumpAndSettle();

      // Button updates to Worn Today
      expect(find.text('Worn Today'), findsOneWidget);
    });

    testWidgets('prompts sign in when guest taps Log Wear Today', (WidgetTester tester) async {
      AuthSession.resetForTest();
      await AuthSession.clearSession();
      LocalStorage.savedLocally = true;
      final rec = _buildTestOutfitRec();
      final wardrobeRepo = _MockScriptedWardrobeRepository();

      final router = GoRouter(
        initialLocation: '/rec',
        routes: [
          GoRoute(
            path: '/rec',
            builder: (context, state) => OutfitRecommendationScreen(
              recommendation: rec,
              request: const OutfitGenerateRequest(
                occasion: 'Evening',
                mood: 'Polished',
                fit: 'Tailored',
                colorPalette: 'Neutral Tones',
              ),
              wardrobeRepository: wardrobeRepo,
            ),
          ),
          GoRoute(
            path: '/sign-in',
            name: RouteNames.signIn,
            builder: (context, state) =>
                const Scaffold(body: Text('sign-in-screen')),
          ),
        ],
      );

      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.text('Log Wear Today'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Log Wear Today'));
      await tester.pumpAndSettle();

      expect(wardrobeRepo.logCallCount, 0);
      expect(find.text('Sign in to log wears. Browsing stays free.'), findsOneWidget);
      expect(find.text('sign-in-screen'), findsOneWidget);
    });
  });
}
