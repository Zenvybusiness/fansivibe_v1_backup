import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_client.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/presentation/wardrobe_screen.dart';
import 'package:fansivibe/features/wardrobe/presentation/widgets/wardrobe_widgets.dart';

const _insightJson = {
  'title': 'Wardrobe Gaps',
  'insight':
      'You have 3 items across 2 of 5 categories (bottoms, tops), '
      'with 1 marked as favorite. Missing: accessories, footwear, outerwear.',
  'action': null,
  'route': null,
};

const _savedLookInsightText =
    'You have 4 items across 3 of 5 categories (bottoms, footwear, tops), '
    'with 0 marked as favorites. Missing: accessories, outerwear. '
    'Saved looks include items from 1 of your 3 covered categories (tops). '
    'Not represented in saved looks: bottoms, footwear.';

void main() {
  group('WardrobeInsight model', () {
    test('fromJson decodes title/insight with null action/route', () {
      final insight = WardrobeInsight.fromJson(_insightJson);

      expect(insight.title, 'Wardrobe Gaps');
      expect(insight.insight, contains('Missing:'));
      expect(insight.action, isNull);
      expect(insight.route, isNull);
    });

    test('fromJson keeps a future action/route payload compatible', () {
      final insight = WardrobeInsight.fromJson({
        'title': 'Wardrobe Gaps',
        'insight': 'Missing: accessories.',
        'action': 'View Gaps',
        'route': '/wardrobe/gaps',
      });

      expect(insight.action, 'View Gaps');
      expect(insight.route, '/wardrobe/gaps');
    });

    test('toJson roundtrip preserves all fields', () {
      const original = WardrobeInsight(
        title: 'Wardrobe Health',
        insight: 'Covering all categories.',
      );

      final roundtrip = WardrobeInsight.fromJson(original.toJson());

      expect(roundtrip.title, original.title);
      expect(roundtrip.insight, original.insight);
      expect(roundtrip.action, isNull);
      expect(roundtrip.route, isNull);
    });
  });

  group('WardrobeClient.getInsight', () {
    test('returns WardrobeInsight on 200 with auth header', () async {
      final client = WardrobeClient(
        client: MockClient((request) async {
          expect(request.url.path, '/v1/wardrobe/insight');
          expect(request.headers['Authorization'], 'Bearer dev');
          return http.Response(jsonEncode(_insightJson), 200);
        }),
      );

      final insight = await client.getInsight();

      expect(insight, isNotNull);
      expect(insight!.title, 'Wardrobe Gaps');
      expect(insight.insight, contains('Missing:'));
      expect(insight.action, isNull);
      expect(insight.route, isNull);
    });

    test('returns null on 204 without treating it as an error', () async {
      var handlerRan = false;
      final client = WardrobeClient(
        client: MockClient((request) async {
          handlerRan = true;
          expect(request.url.path, '/v1/wardrobe/insight');
          return http.Response('', 204);
        }),
      );

      final insight = await client.getInsight();

      expect(handlerRan, isTrue);
      expect(insight, isNull);
    });

    test('returns null on 500', () async {
      final client = WardrobeClient(
        client: MockClient((request) async => http.Response('oops', 500)),
      );

      expect(await client.getInsight(), isNull);
    });

    test('returns null on 401', () async {
      final client = WardrobeClient(
        client: MockClient(
          (request) async => http.Response('{"error":{}}', 401),
        ),
      );

      expect(await client.getInsight(), isNull);
    });

    test('returns null on network failure', () async {
      final client = WardrobeClient(
        client: MockClient(
          (request) async => throw http.ClientException('connection refused'),
        ),
      );

      expect(await client.getInsight(), isNull);
    });

    test('returns null on 200 with a malformed body instead of throwing',
        () async {
      // Non-JSON body: jsonDecode throws inside the client and must be
      // contained — a malformed 200 hides the card, never crashes.
      final nonJson = WardrobeClient(
        client: MockClient((request) async => http.Response('not-json{{{', 200)),
      );
      expect(await nonJson.getInsight(), isNull);

      // Wrong-typed fields: `as String` throws inside fromJson and must be
      // contained the same way (e.g. a future backend shape we do not know).
      final wrongTypes = WardrobeClient(
        client: MockClient(
          (request) async => http.Response(
            jsonEncode({'title': 123, 'insight': null, 'route': 456}),
            200,
          ),
        ),
      );
      expect(await wrongTypes.getInsight(), isNull);
    });
  });

  group('WardrobeRepository.getInsight', () {
    test('API success maps backend title/insight verbatim', () async {
      final repo = WardrobeRepositoryImpl(
        client: WardrobeClient(
          client: MockClient(
            (request) async =>
                http.Response(jsonEncode(_insightJson), 200),
          ),
        ),
      );

      final result = await repo.getInsight();

      expect(result, isNotNull);
      expect(result!.title, 'Wardrobe Gaps');
      expect(
        result.insight,
        'You have 3 items across 2 of 5 categories (bottoms, tops), '
        'with 1 marked as favorite. Missing: accessories, footwear, outerwear.',
      );
      expect(result.actionLabel, isNull);
    });

    test('saved-look-aware text passes through unchanged', () async {
      final repo = WardrobeRepositoryImpl(
        client: WardrobeClient(
          client: MockClient(
            (request) async => http.Response(
              jsonEncode({
                'title': 'Wardrobe Gaps',
                'insight': _savedLookInsightText,
                'action': null,
                'route': null,
              }),
              200,
            ),
          ),
        ),
      );

      final result = await repo.getInsight();

      expect(result, isNotNull);
      expect(result!.insight, _savedLookInsightText);
    });

    test('204 yields null — never the mock fallback', () async {
      final repo = WardrobeRepositoryImpl(
        client: WardrobeClient(
          client: MockClient((request) async => http.Response('', 204)),
        ),
      );

      expect(await repo.getInsight(), isNull);
    });

    test('backend error yields null — no fabricated insight', () async {
      final repo = WardrobeRepositoryImpl(
        client: WardrobeClient(
          client: MockClient((request) async => http.Response('{}', 500)),
        ),
      );

      final result = await repo.getInsight();

      expect(result, isNull);
      // The mock text must never leak in as a substitute.
      expect(WardrobeInsightData.mock.insight, contains('8+ combinations'));
    });

    test('action+route present pass through without inventing navigation',
        () async {
      final repo = WardrobeRepositoryImpl(
        client: WardrobeClient(
          client: MockClient(
            (request) async => http.Response(
              jsonEncode({
                'title': 'Wardrobe Gaps',
                'insight': 'Missing: accessories.',
                'action': 'View Gaps',
                'route': '/wardrobe/gaps',
              }),
              200,
            ),
          ),
        ),
      );

      final result = await repo.getInsight();

      // The label passes through verbatim; the UI model carries no route,
      // so there is nothing to navigate to — no route semantics invented.
      expect(result, isNotNull);
      expect(result!.title, 'Wardrobe Gaps');
      expect(result.insight, 'Missing: accessories.');
      expect(result.actionLabel, 'View Gaps');
    });
  });

  group('WardrobeInsightCard with live data', () {
    testWidgets('renders backend title/insight with no CTA', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: const Scaffold(
            body: WardrobeInsightCard(
              data: WardrobeInsightData(
                title: 'Wardrobe Gaps',
                insight: _savedLookInsightText,
                iconName: 'lightbulb_outline_rounded',
                accentColor: 0xFFC5A059,
              ),
            ),
          ),
        ),
      );

      expect(find.text('Wardrobe Gaps'), findsOneWidget);
      expect(find.text('AI Insight'), findsOneWidget);
      expect(find.text(_savedLookInsightText), findsOneWidget);
      // No action supplied → no call-to-action rendered.
      expect(find.byType(TextButton), findsNothing);
    });

    testWidgets('action label without handler still renders no CTA', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: const Scaffold(
            body: WardrobeInsightCard(
              data: WardrobeInsightData(
                title: 'Wardrobe Gaps',
                insight: 'Missing: accessories.',
                iconName: 'lightbulb_outline_rounded',
                accentColor: 0xFFC5A059,
                actionLabel: 'View Gaps',
              ),
            ),
          ),
        ),
      );

      expect(find.text('Missing: accessories.'), findsOneWidget);
      expect(find.text('View Gaps'), findsNothing);
    });
  });

  group('WardrobeScreen live insight wiring', () {
    testWidgets('shows live insight verbatim, list stays intact', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: WardrobeScreen(
              insightRepository: _FakeInsightRepository(
                const WardrobeInsightData(
                  title: 'Wardrobe Gaps',
                  insight: _savedLookInsightText,
                  iconName: 'lightbulb_outline_rounded',
                  accentColor: 0xFFC5A059,
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Wardrobe Gaps'), findsOneWidget);
      expect(find.text(_savedLookInsightText), findsOneWidget);
      // Item list, filters, and header render independently of insight.
      expect(find.text('My Wardrobe'), findsOneWidget);
      expect(find.text('Merino Crew Neck'), findsOneWidget);
      expect(find.byType(CategoryTile), findsWidgets);
    });

    testWidgets('null insight hides card, list remains usable', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: WardrobeScreen(
              insightRepository: _FakeInsightRepository(null),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('AI Insight'), findsNothing);
      expect(
        find.textContaining('Your wardrobe is balanced across seasons'),
        findsNothing,
      );
      expect(find.text('My Wardrobe'), findsOneWidget);
      expect(find.text('Merino Crew Neck'), findsOneWidget);
    });

    testWidgets('insight loading never blocks the item list', (
      WidgetTester tester,
    ) async {
      final gate = Completer<WardrobeInsightData?>();
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: WardrobeScreen(
              insightRepository: _FutureInsightRepository(gate.future),
            ),
          ),
        ),
      );
      await tester.pump();

      expect(find.text('My Wardrobe'), findsOneWidget);
      expect(find.text('Merino Crew Neck'), findsOneWidget);
      expect(find.text('AI Insight'), findsNothing);

      gate.complete(null);
      await tester.pumpAndSettle();
      expect(find.text('AI Insight'), findsNothing);
    });

    testWidgets('action-bearing insight renders text with no dead CTA', (
      WidgetTester tester,
    ) async {
      // Backend sent action+route: the screen renders the text via the card
      // with no handler wired, so FansiInsightCard shows no CTA — tapping
      // nothing can attempt unsupported `/wardrobe/gaps` navigation.
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: WardrobeScreen(
              insightRepository: _FakeInsightRepository(
                const WardrobeInsightData(
                  title: 'Wardrobe Gaps',
                  insight: 'Missing: accessories.',
                  iconName: 'lightbulb_outline_rounded',
                  accentColor: 0xFFC5A059,
                  actionLabel: 'View Gaps',
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Wardrobe Gaps'), findsOneWidget);
      expect(find.text('Missing: accessories.'), findsOneWidget);
      expect(find.text('View Gaps'), findsNothing);
      expect(find.byType(TextButton), findsNothing);
      // List stays independently usable.
      expect(find.text('My Wardrobe'), findsOneWidget);
      expect(find.text('Merino Crew Neck'), findsOneWidget);
    });
  });
}

/// Repository stub controlling only the insight; item reads are out of
/// scope for these tests (the screen renders items from LearningService).
class _FakeInsightRepository implements WardrobeRepository {
  _FakeInsightRepository(this.insight);

  final WardrobeInsightData? insight;

  @override
  Future<WardrobeInsightData?> getInsight() async => insight;

  @override
  Future<List<WardrobeItemData>> listItems({
    String? category,
    String? color,
    String? sortBy,
    String? order,
    int page = 1,
    int pageSize = 20,
  }) async =>
      WardrobeMockData.itemsForCategory(category ?? 'all');

  @override
  Future<WardrobeItemData?> getItem({required String itemId}) =>
      throw UnimplementedError();

  @override
  Future<WardrobeItemData?> createItem({
    required String name,
    required String category,
    required String color,
    String? material,
    MediaRef? imageRef,
  }) =>
      throw UnimplementedError();

  @override
  Future<WardrobeItemData?> updateItem({
    required String itemId,
    String? name,
    String? category,
    String? color,
    String? material,
    bool? isFavorite,
  }) =>
      throw UnimplementedError();

  @override
  Future<bool?> deleteItem({required String itemId}) =>
      throw UnimplementedError();

  @override
  Future<WearEventLogResponse?> logWear({
    required List<String> itemIds,
    DateTime? wornAt,
    String? idempotencyKey,
  }) =>
      throw UnimplementedError();

  @override
  Future<WearSummary?> getWearSummary() => throw UnimplementedError();
}

/// Repository stub exposing a controllable insight future (loading-state tests).
class _FutureInsightRepository implements WardrobeRepository {
  _FutureInsightRepository(this.future);

  final Future<WardrobeInsightData?> future;

  @override
  Future<WardrobeInsightData?> getInsight() => future;

  @override
  Future<List<WardrobeItemData>> listItems({
    String? category,
    String? color,
    String? sortBy,
    String? order,
    int page = 1,
    int pageSize = 20,
  }) =>
      throw UnimplementedError();

  @override
  Future<WardrobeItemData?> getItem({required String itemId}) =>
      throw UnimplementedError();

  @override
  Future<WardrobeItemData?> createItem({
    required String name,
    required String category,
    required String color,
    String? material,
    MediaRef? imageRef,
  }) =>
      throw UnimplementedError();

  @override
  Future<WardrobeItemData?> updateItem({
    required String itemId,
    String? name,
    String? category,
    String? color,
    String? material,
    bool? isFavorite,
  }) =>
      throw UnimplementedError();

  @override
  Future<bool?> deleteItem({required String itemId}) =>
      throw UnimplementedError();

  @override
  Future<WearEventLogResponse?> logWear({
    required List<String> itemIds,
    DateTime? wornAt,
    String? idempotencyKey,
  }) =>
      throw UnimplementedError();

  @override
  Future<WearSummary?> getWearSummary() => throw UnimplementedError();
}
