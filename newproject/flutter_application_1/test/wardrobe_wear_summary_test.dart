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

const _itemA = '11111111-1111-4111-8111-111111111111';
const _itemB = '22222222-2222-4222-8222-222222222222';
const _itemC = '33333333-3333-4333-8333-333333333333';

Map<String, dynamic> _summaryJson() => {
      'totalWears': 5,
      'wearCounts': {_itemA: 3, _itemB: 2},
      'lastWorn': {
        _itemA: '2024-08-10T12:00:00Z',
        _itemB: '2024-08-05T12:00:00Z',
      },
      'mostWornItemIds': [_itemA],
      'leastWornItemIds': [_itemB],
      'unwornItemIds': const <String>[],
      'recentlyWornItemIds': [_itemA],
      'wearsByCategory': {'bottoms': 2, 'tops': 3},
    };

Map<String, dynamic> _zeroJson() => {
      'totalWears': 0,
      'wearCounts': {_itemA: 0, _itemB: 0},
      'lastWorn': {_itemA: null, _itemB: null},
      'mostWornItemIds': const <String>[],
      'leastWornItemIds': [_itemA, _itemB],
      'unwornItemIds': [_itemA, _itemB],
      'recentlyWornItemIds': const <String>[],
      'wearsByCategory': {'bottoms': 0, 'tops': 0},
    };

void main() {
  group('WearSummary model', () {
    test('fromJson parses the W-9 payload exactly (camelCase)', () {
      final summary = WearSummary.fromJson(_summaryJson());

      expect(summary.totalWears, 5);
      expect(summary.wearCounts, {_itemA: 3, _itemB: 2});
      expect(
        summary.lastWorn[_itemA]?.toUtc(),
        DateTime.utc(2024, 8, 10, 12),
      );
      expect(
        summary.lastWorn[_itemB]?.toUtc(),
        DateTime.utc(2024, 8, 5, 12),
      );
      expect(summary.mostWornItemIds, [_itemA]);
      expect(summary.leastWornItemIds, [_itemB]);
      expect(summary.unwornItemIds, isEmpty);
      expect(summary.recentlyWornItemIds, [_itemA]);
      expect(summary.wearsByCategory, {'bottoms': 2, 'tops': 3});
    });

    test('null lastWorn stays null (never worn)', () {
      final summary = WearSummary.fromJson(_zeroJson());

      expect(summary.totalWears, 0);
      expect(summary.lastWorn[_itemA], isNull);
      expect(summary.lastWorn[_itemB], isNull);
      expect(summary.mostWornItemIds, isEmpty);
    });

    test('UUID keys pass through verbatim, never transformed', () {
      final summary = WearSummary.fromJson(_summaryJson());

      expect(summary.wearCounts.keys, containsAll([_itemA, _itemB]));
      expect(summary.lastWorn.keys, containsAll([_itemA, _itemB]));
      // Even a local-looking key would pass through untouched: the model
      // never validates, translates, or reconciles IDs.
      final local = WearSummary.fromJson({
        ..._zeroJson(),
        'wearCounts': {'1': 0},
        'lastWorn': {'1': null},
      });
      expect(local.wearCounts.keys, ['1']);
    });

    test('wrong-typed fields throw instead of fabricating data', () {
      expect(
        () => WearSummary.fromJson({..._summaryJson(), 'totalWears': 'five'}),
        throwsA(anything),
      );
      expect(
        () => WearSummary.fromJson({
          ..._summaryJson(),
          'wearCounts': {
            _itemA: 'three',
          },
        }),
        throwsA(anything),
      );
      expect(
        () => WearSummary.fromJson({
          ..._summaryJson(),
          'mostWornItemIds': [42],
        }),
        throwsA(anything),
      );
    });

    test('unparseable non-null instant throws (never poses as unworn)', () {
      expect(
        () => WearSummary.fromJson({
          ..._summaryJson(),
          'lastWorn': {_itemA: 'not-a-date'},
        }),
        throwsA(anything),
      );
    });

    test('missing required field throws', () {
      expect(() => WearSummary.fromJson({}), throwsA(anything));
    });

    test('toJson roundtrip preserves shape', () {
      final summary = WearSummary.fromJson(_summaryJson());
      final roundtripped = WearSummary.fromJson(
        jsonDecode(jsonEncode(summary.toJson())) as Map<String, dynamic>,
      );

      expect(roundtripped.totalWears, summary.totalWears);
      expect(roundtripped.wearCounts, summary.wearCounts);
      expect(
        roundtripped.lastWorn[_itemA]?.toUtc(),
        summary.lastWorn[_itemA]?.toUtc(),
      );
      expect(roundtripped.mostWornItemIds, summary.mostWornItemIds);
      expect(roundtripped.wearsByCategory, summary.wearsByCategory);
    });
  });

  group('WardrobeClient.getWearSummary', () {
    test('GETs path with auth and parses 200', () async {
      String? seenMethod;
      String? seenPath;
      String? seenAuth;
      bool? seenQueryEmpty;
      final client = WardrobeClient(
        client: MockClient((request) async {
          seenMethod = request.method;
          seenPath = request.url.path;
          seenAuth = request.headers['Authorization'];
          seenQueryEmpty = request.url.queryParameters.isEmpty;
          return http.Response(jsonEncode(_summaryJson()), 200);
        }),
      );

      final result = await client.getWearSummary();

      // The read sends no IDs at all: local IDs can never leak into it.
      expect(seenMethod, 'GET');
      expect(seenPath, '/v1/wardrobe/wear-summary');
      expect(seenAuth, 'Bearer dev');
      expect(seenQueryEmpty, isTrue);
      expect(result, isNotNull);
      expect(result!.totalWears, 5);
      expect(result.wearCounts[_itemA], 3);
      expect(result.mostWornItemIds, [_itemA]);
      expect(result.wearsByCategory['tops'], 3);
    });

    test('200 with malformed JSON returns null', () async {
      final wrongTypes = WardrobeClient(
        client: MockClient(
          (request) async => http.Response(
            jsonEncode({..._summaryJson(), 'totalWears': 'five'}),
            200,
          ),
        ),
      );
      expect(await wrongTypes.getWearSummary(), isNull);

      final garbageInstant = WardrobeClient(
        client: MockClient(
          (request) async => http.Response(
            jsonEncode({
              ..._summaryJson(),
              'lastWorn': {_itemA: 'not-a-date'},
            }),
            200,
          ),
        ),
      );
      expect(await garbageInstant.getWearSummary(), isNull);

      final nonMap = WardrobeClient(
        client: MockClient(
          (request) async => http.Response('[1, 2, 3]', 200),
        ),
      );
      expect(await nonMap.getWearSummary(), isNull);

      final emptyBody = WardrobeClient(
        client: MockClient(
          (request) async => http.Response('', 200),
        ),
      );
      expect(await emptyBody.getWearSummary(), isNull);
    });

    test('401/429/5xx return null — never a mock fallback', () async {
      for (final status in [401, 429, 500, 502]) {
        final client = WardrobeClient(
          client: MockClient(
            (request) async => http.Response('{}', status),
          ),
        );
        expect(await client.getWearSummary(), isNull);
      }
    });

    test('network failure returns null', () async {
      final client = WardrobeClient(
        client: MockClient((request) async => throw Exception('down')),
      );
      expect(await client.getWearSummary(), isNull);
    });
  });

  group('WardrobeRepository.getWearSummary', () {
    test('passes the client DTO through verbatim', () async {
      final repo = WardrobeRepositoryImpl(
        client: WardrobeClient(
          client: MockClient(
            (request) async =>
                http.Response(jsonEncode(_summaryJson()), 200),
          ),
        ),
      );

      final result = await repo.getWearSummary();

      expect(result, isNotNull);
      expect(result!.totalWears, 5);
      expect(result.wearCounts, {_itemA: 3, _itemB: 2});
      expect(result.lastWorn[_itemA]?.toUtc(), DateTime.utc(2024, 8, 10, 12));
      expect(result.unwornItemIds, isEmpty);
    });

    test('backend error yields null — no fabricated zero object', () async {
      final repo = WardrobeRepositoryImpl(
        client: WardrobeClient(
          client: MockClient((request) async => http.Response('{}', 500)),
        ),
      );

      // Null means unavailable; a zero WearSummary would pose as fact.
      expect(await repo.getWearSummary(), isNull);
    });
  });

  group('mapWearSummaryToUi', () {
    test('zero history maps to null — no wear sentence', () {
      expect(
        mapWearSummaryToUi(WearSummary.fromJson(_zeroJson())),
        isNull,
      );
    });

    test('nonzero summary renders grounded counts-only copy', () {
      final card = mapWearSummaryToUi(WearSummary.fromJson(_summaryJson()));

      expect(card, isNotNull);
      expect(card!.title, 'Wear Summary');
      expect(
        card.insight,
        'Logged 5 wears across 2 items. '
        '1 item worn in the last 30 days. '
        'Most-worn: 1 item at 3 wears. '
        'Least-worn: 1 item at 2 wears. '
        'Most logged category: tops (3 of 5 wears).',
      );
      expect(card.actionLabel, isNull);
    });

    test('ties are named, never hidden', () {
      final card = mapWearSummaryToUi(
        WearSummary.fromJson({
          ..._summaryJson(),
          'totalWears': 6,
          'wearCounts': {_itemA: 3, _itemB: 3},
          'mostWornItemIds': [_itemA, _itemB],
          'wearsByCategory': {'bottoms': 3, 'tops': 3},
        }),
      );

      expect(card, isNotNull);
      expect(card!.insight, contains('Most-worn: 2 items at 3 wears (tied).'));
      expect(
        card.insight,
        contains(
          'Most logged categories (tied): bottoms, tops (3 of 6 wears each).',
        ),
      );
    });

    test('unworn items render as counts, never judgments', () {
      final card = mapWearSummaryToUi(
        WearSummary.fromJson({
          ..._summaryJson(),
          'totalWears': 3,
          'wearCounts': {_itemA: 3, _itemB: 0, _itemC: 0},
          'lastWorn': {
            _itemA: '2024-08-10T12:00:00Z',
            _itemB: null,
            _itemC: null,
          },
          'mostWornItemIds': [_itemA],
          'leastWornItemIds': [_itemB, _itemC],
          'unwornItemIds': [_itemB, _itemC],
          'recentlyWornItemIds': [_itemA],
          'wearsByCategory': {'bottoms': 0, 'tops': 3},
        }),
      );

      expect(card, isNotNull);
      expect(card!.insight, contains('2 items not logged yet.'));
    });

    test('copy never uses banned language or raw UUIDs', () {
      const banned = [
        'never wear',
        'neglected',
        'should',
        'need',
        'balanced',
        'rotation',
        'favorite',
        'always',
      ];
      final bodies = [
        mapWearSummaryToUi(WearSummary.fromJson(_summaryJson()))!.insight,
        mapWearSummaryToUi(
          WearSummary.fromJson({
            ..._summaryJson(),
            'totalWears': 6,
            'wearCounts': {_itemA: 3, _itemB: 3},
            'mostWornItemIds': [_itemA, _itemB],
            'wearsByCategory': {'bottoms': 3, 'tops': 3},
          }),
        )!
            .insight,
      ];
      for (final body in bodies) {
        for (final word in banned) {
          expect(body.toLowerCase(), isNot(contains(word)));
        }
        expect(body, isNot(contains(_itemA)));
        expect(body, isNot(contains(_itemB)));
      }
    });
  });

  group('WardrobeScreen wear-summary slot', () {
    testWidgets('renders grounded summary beside unchanged W-7 insight', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: WardrobeScreen(
              insightRepository: _FakeWardrobeRepository(
                insight: const WardrobeInsightData(
                  title: 'Wardrobe Gaps',
                  insight: 'Missing: accessories.',
                  iconName: 'lightbulb_outline_rounded',
                  accentColor: 0xFFC5A059,
                ),
                summary: WearSummary.fromJson(_summaryJson()),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // W-7 insight renders verbatim, unchanged.
      expect(find.text('Wardrobe Gaps'), findsOneWidget);
      expect(find.text('Missing: accessories.'), findsOneWidget);
      // Summary renders grounded counts-only copy with no CTA.
      expect(find.text('Wear Summary'), findsOneWidget);
      expect(
        find.textContaining('Logged 5 wears across 2 items.'),
        findsOneWidget,
      );
      expect(find.byType(TextButton), findsNothing);
      // List stays independently usable.
      expect(find.text('My Wardrobe'), findsOneWidget);
      expect(find.text('Merino Crew Neck'), findsOneWidget);
    });

    testWidgets('null summary hides card, insight and list intact', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: WardrobeScreen(
              insightRepository: _FakeWardrobeRepository(
                insight: const WardrobeInsightData(
                  title: 'Wardrobe Gaps',
                  insight: 'Missing: accessories.',
                  iconName: 'lightbulb_outline_rounded',
                  accentColor: 0xFFC5A059,
                ),
                summary: null,
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Wear Summary'), findsNothing);
      expect(find.text('Wardrobe Gaps'), findsOneWidget);
      expect(find.text('My Wardrobe'), findsOneWidget);
      expect(find.text('Merino Crew Neck'), findsOneWidget);
    });

    testWidgets('pending summary never blocks the item list', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: WardrobeScreen(
              insightRepository: _FakeWardrobeRepository(
                insight: null,
                summaryFuture: Completer<WearSummary?>().future,
              ),
            ),
          ),
        ),
      );
      await tester.pump();

      expect(find.text('My Wardrobe'), findsOneWidget);
      expect(find.text('Merino Crew Neck'), findsOneWidget);
      expect(find.text('Wear Summary'), findsNothing);
      expect(find.text('AI Insight'), findsNothing);
    });
  });
}

/// Repository stub controlling insight and wear summary; item reads are
/// out of scope (the screen renders items from LearningService).
class _FakeWardrobeRepository implements WardrobeRepository {
  _FakeWardrobeRepository({this.insight, this.summary, this.summaryFuture});

  final WardrobeInsightData? insight;
  final WearSummary? summary;
  final Future<WearSummary?>? summaryFuture;

  @override
  Future<WardrobeInsightData?> getInsight() async => insight;

  @override
  Future<WearSummary?> getWearSummary() =>
      summaryFuture ?? Future.value(summary);

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
}
