import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/presentation/wardrobe_item_details_screen.dart';

const _uuidItem = '11111111-1111-4111-8111-111111111111';
const _groupId = '33333333-3333-4333-8333-333333333333';

WearEventLogResponse _ok({required bool created}) => WearEventLogResponse(
      wears: const <WearEvent>[],
      wearGroupId: _groupId,
      wornAt: DateTime.utc(2024, 8, 1, 12),
      created: created,
    );

WardrobeItemData _itemWithId(String id) => WardrobeItemData(
      id: id,
      name: 'Merino Crew Neck',
      category: 'tops',
      color: 'Charcoal',
      material: 'Wool',
    );

Widget _wrapScreen(_FakeCaptureRepository repo, String itemId) =>
    MaterialApp(
      theme: ThemeData.dark(),
      home: WardrobeItemDetailsScreen(itemId: itemId, repository: repo),
    );

void main() {
  group('wear capture availability (UUID gate)', () {
    testWidgets('backend UUID item shows the capture action', (
      WidgetTester tester,
    ) async {
      final repo = _FakeCaptureRepository(item: _itemWithId(_uuidItem));
      await tester.pumpWidget(_wrapScreen(repo, _uuidItem));
      await tester.pumpAndSettle();

      expect(find.text('I wore this'), findsOneWidget);
      expect(repo.logCalls, 0);
    });

    testWidgets('local mock ID hides the action and never submits', (
      WidgetTester tester,
    ) async {
      final repo = _FakeCaptureRepository(item: _itemWithId('1'));
      await tester.pumpWidget(_wrapScreen(repo, '1'));
      await tester.pumpAndSettle();

      expect(find.text('I wore this'), findsNothing);
      // Screen still fully usable without capture.
      expect(find.text('Merino Crew Neck'), findsWidgets);
      expect(repo.logCalls, 0);
    });

    testWidgets('non-UUID IDs hide the action and never submit', (
      WidgetTester tester,
    ) async {
      for (final id in ['abc', '', '12345', 'not-a-uuid-at-all']) {
        final repo = _FakeCaptureRepository(item: _itemWithId(id));
        await tester.pumpWidget(_wrapScreen(repo, id));
        await tester.pumpAndSettle();

        expect(find.text('I wore this'), findsNothing);
        expect(repo.logCalls, 0);
      }
    });
  });

  group('wear capture submission', () {
    testWidgets('tap sends exactly one backend UUID', (
      WidgetTester tester,
    ) async {
      final repo = _FakeCaptureRepository(
        item: _itemWithId(_uuidItem),
        logResult: _ok(created: true),
      );
      await tester.pumpWidget(_wrapScreen(repo, _uuidItem));
      await tester.pumpAndSettle();

      await tester.tap(find.text('I wore this'));
      await tester.pumpAndSettle();

      expect(repo.logCalls, 1);
      expect(repo.lastIds, [_uuidItem]);
      expect(find.text('Wear logged'), findsOneWidget);
    });

    testWidgets('pending state prevents duplicate taps', (
      WidgetTester tester,
    ) async {
      final gate = Completer<WearEventLogResponse?>();
      final repo = _FakeCaptureRepository(item: _itemWithId(_uuidItem));
      repo.logHandler = (_, __) => gate.future;
      await tester.pumpWidget(_wrapScreen(repo, _uuidItem));
      await tester.pumpAndSettle();

      await tester.tap(find.text('I wore this'));
      await tester.pump();
      expect(repo.logCalls, 1);
      // Pending: label stays visible with a spinner; the action is disabled.
      expect(find.text('I wore this'), findsOneWidget);
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
      // Second tap while pending is ignored.
      await tester.tap(find.text('I wore this'));
      await tester.pump();
      expect(repo.logCalls, 1);

      gate.complete(_ok(created: true));
      await tester.pumpAndSettle();
      expect(find.text('Wear logged'), findsOneWidget);
      expect(repo.logCalls, 1);
    });

    testWidgets('idempotent replay shows already-logged, not a new log', (
      WidgetTester tester,
    ) async {
      final repo = _FakeCaptureRepository(
        item: _itemWithId(_uuidItem),
        logResult: _ok(created: false),
      );
      await tester.pumpWidget(_wrapScreen(repo, _uuidItem));
      await tester.pumpAndSettle();

      await tester.tap(find.text('I wore this'));
      await tester.pumpAndSettle();

      expect(repo.logCalls, 1);
      expect(find.text('Already logged'), findsOneWidget);
      expect(find.text('Wear logged'), findsNothing);
    });

    testWidgets('failure shows retry message, fabricates nothing', (
      WidgetTester tester,
    ) async {
      final repo = _FakeCaptureRepository(
        item: _itemWithId(_uuidItem),
        logResult: null,
      );
      await tester.pumpWidget(_wrapScreen(repo, _uuidItem));
      await tester.pumpAndSettle();

      await tester.tap(find.text('I wore this'));
      await tester.pumpAndSettle();

      expect(repo.logCalls, 1);
      expect(find.text('Wear logged'), findsNothing);
      expect(find.text('Already logged'), findsNothing);
      expect(
        find.text("Couldn't log wear. Check your connection and try again."),
        findsOneWidget,
      );
      // Rest of the screen is preserved.
      expect(find.text('Merino Crew Neck'), findsWidgets);
      expect(find.text('I wore this'), findsOneWidget);
    });

    testWidgets('explicit retry reuses the key; next action gets a fresh key',
        (
      WidgetTester tester,
    ) async {
      var attempt = 0;
      final repo = _FakeCaptureRepository(item: _itemWithId(_uuidItem));
      repo.logHandler = (_, __) async {
        attempt++;
        return attempt == 1 ? null : _ok(created: true);
      };
      await tester.pumpWidget(_wrapScreen(repo, _uuidItem));
      await tester.pumpAndSettle();

      // First attempt fails; let its snackbar expire so the retry
      // confirmation is observable on its own (SnackBars queue).
      await tester.tap(find.text('I wore this'));
      await tester.pumpAndSettle();
      final firstKey = repo.lastKey;
      expect(firstKey, isNotNull);
      expect(
        find.text("Couldn't log wear. Check your connection and try again."),
        findsOneWidget,
      );
      await tester.pump(const Duration(seconds: 5));
      await tester.pumpAndSettle();
      await tester.tap(find.text('I wore this'));
      await tester.pumpAndSettle();
      expect(repo.logCalls, 2);
      expect(repo.lastKey, firstKey);
      expect(find.text('Wear logged'), findsOneWidget);

      // Success clears the action: the next tap is a new logical action.
      await tester.tap(find.text('I wore this'));
      await tester.pumpAndSettle();
      expect(repo.logCalls, 3);
      expect(repo.lastKey, isNotNull);
      expect(repo.lastKey, isNot(firstKey));
    });
  });

  group('capture safety (no auto-logging, no navigation)', () {
    testWidgets('opening the screen never logs', (
      WidgetTester tester,
    ) async {
      final repo = _FakeCaptureRepository(item: _itemWithId(_uuidItem));
      await tester.pumpWidget(_wrapScreen(repo, _uuidItem));
      await tester.pumpAndSettle();

      expect(repo.logCalls, 0);
    });

    testWidgets('favorite toggle and save never log', (
      WidgetTester tester,
    ) async {
      final repo = _FakeCaptureRepository(item: _itemWithId(_uuidItem));
      await tester.pumpWidget(_wrapScreen(repo, _uuidItem));
      await tester.pumpAndSettle();

      // Enter edit mode, toggle favorite twice (net no change), save.
      // Plain pumps (not settle): the edit form never fully settles in
      // the test harness, and nothing here depends on animations.
      await tester.tap(find.byIcon(Icons.edit_rounded).first);
      await tester.pump();
      await tester.pump();
      await tester.tap(find.text('Favorite'));
      await tester.pump();
      await tester.tap(find.text('Favorite'));
      await tester.pump();
      // Save via the always-visible app-bar action (no scrolling needed).
      await tester.tap(find.byIcon(Icons.save_rounded));
      await tester.pump();
      await tester.pump();

      expect(repo.logCalls, 0);
      expect(find.text('Wear logged'), findsNothing);
    });

    testWidgets('success stays on the details screen (no navigation)', (
      WidgetTester tester,
    ) async {
      final repo = _FakeCaptureRepository(
        item: _itemWithId(_uuidItem),
        logResult: _ok(created: true),
      );
      await tester.pumpWidget(_wrapScreen(repo, _uuidItem));
      await tester.pumpAndSettle();

      await tester.tap(find.text('I wore this'));
      await tester.pumpAndSettle();

      expect(find.text('Wear logged'), findsOneWidget);
      expect(find.text('Merino Crew Neck'), findsWidgets);
      expect(find.text('I wore this'), findsOneWidget);
    });
  });
}

/// Repository double recording wear-capture calls; item reads return the
/// configured item, everything else is out of scope for these tests.
class _FakeCaptureRepository implements WardrobeRepository {
  _FakeCaptureRepository({required this.item, this.logResult});

  final WardrobeItemData item;
  final WearEventLogResponse? logResult;

  Future<WearEventLogResponse?> Function(List<String> ids, String? key)?
      logHandler;

  int logCalls = 0;
  List<String>? lastIds;
  String? lastKey;

  @override
  Future<WardrobeItemData?> getItem({required String itemId}) async => item;

  @override
  Future<WearEventLogResponse?> logWear({
    required List<String> itemIds,
    DateTime? wornAt,
    String? idempotencyKey,
  }) async {
    logCalls++;
    lastIds = itemIds;
    lastKey = idempotencyKey;
    if (logHandler != null) return logHandler!(itemIds, idempotencyKey);
    return logResult;
  }

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
  Future<WardrobeInsightData?> getInsight() => throw UnimplementedError();

  @override
  Future<WearSummary?> getWearSummary() => throw UnimplementedError();
}
