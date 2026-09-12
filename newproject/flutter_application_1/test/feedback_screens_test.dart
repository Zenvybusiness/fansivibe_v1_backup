import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:fansivibe/features/feedback/feedback.dart';
import 'package:fansivibe/features/profile/data/saved_looks_models.dart';
import 'package:fansivibe/features/profile/data/saved_looks_repository.dart';
import 'package:fansivibe/features/profile/presentation/saved_looks_screen.dart';

const String _rowId = '78ff3686-c950-4cd6-84c3-7e18d6634dfa';

SavedLookItem _row() => SavedLookItem(
  id: _rowId,
  title: 'Office Outfit',
  createdAt: DateTime.utc(2026, 9, 1, 10),
  sourceContext: 'outfit',
  snapshot: const {
    'selectedItemIds': ['a-uuid-1', 'a-uuid-2'],
  },
);

/// Scriptable saved-looks double: one backend row, no network.
class _FakeSavedLooksRepository implements SavedLooksRepository {
  @override
  Future<SavedLookListPage?> listSavedLooks({
    int page = 1,
    int pageSize = 20,
  }) async => SavedLookListPage(
    items: [_row()],
    page: page,
    pageSize: pageSize,
    total: 1,
  );

  @override
  Future<SavedLookDeleteOutcome?> deleteSavedLook({required String id}) async =>
      SavedLookDeleteOutcome.deleted;
}

/// Scriptable feedback double: scripted results, full call accounting.
class _FakeFeedbackRepository implements FeedbackRepository {
  _FakeFeedbackRepository();

  Future<FeedbackResult> Function()? handler;

  int calls = 0;
  final List<String> ratings = [];
  final List<String?> targetIds = [];
  final List<String> keys = [];

  @override
  Future<FeedbackResult> submitFeedback({
    required String rating,
    String? reason,
    String? targetLookId,
    String? targetSavedLookId,
    required String idempotencyKey,
  }) {
    calls += 1;
    ratings.add(rating);
    targetIds.add(targetSavedLookId);
    keys.add(idempotencyKey);
    return handler!();
  }
}

Widget _screen(_FakeFeedbackRepository feedback) {
  return MaterialApp(
    theme: ThemeData.dark(),
    home: SavedLooksScreen(
      repository: _FakeSavedLooksRepository(),
      feedbackRepository: feedback,
    ),
  );
}

Future<void> _tapReaction(WidgetTester tester, IconData icon) async {
  final button = find.byIcon(icon).first;
  await tester.scrollUntilVisible(button, 500.0);
  await tester.pumpAndSettle();
  await tester.tap(button);
  await tester.pumpAndSettle();
}

void main() {
  group('SavedLooksScreen reactions (M11)', () {
    testWidgets('like/dislike buttons render per saved row', (
      WidgetTester tester,
    ) async {
      final feedback = _FakeFeedbackRepository()
        ..handler = () async => const FeedbackResult.sent();
      await tester.pumpWidget(_screen(feedback));
      await tester.pumpAndSettle();

      expect(find.text('Office Outfit'), findsOneWidget);
      expect(find.byIcon(Icons.thumb_up_outlined), findsOneWidget);
      expect(find.byIcon(Icons.thumb_down_outlined), findsOneWidget);
      // Delete surface preserved.
      expect(find.text('Remove'), findsOneWidget);
    });

    testWidgets('like submits the row UUID with a fresh key', (
      WidgetTester tester,
    ) async {
      final feedback = _FakeFeedbackRepository()
        ..handler = () async => const FeedbackResult.sent();
      await tester.pumpWidget(_screen(feedback));
      await tester.pumpAndSettle();

      await _tapReaction(tester, Icons.thumb_up_outlined);

      expect(feedback.calls, 1);
      expect(feedback.ratings, ['like']);
      expect(feedback.targetIds, [_rowId]);
      expect(feedback.keys.single, isNotEmpty);
      expect(find.text('Thanks — feedback recorded'), findsOneWidget);
      // The row stays put after a successful reaction.
      expect(find.text('Office Outfit'), findsOneWidget);
    });

    testWidgets('dislike submits dislike for the same row', (
      WidgetTester tester,
    ) async {
      final feedback = _FakeFeedbackRepository()
        ..handler = () async => const FeedbackResult.sent();
      await tester.pumpWidget(_screen(feedback));
      await tester.pumpAndSettle();

      await _tapReaction(tester, Icons.thumb_down_outlined);

      expect(feedback.calls, 1);
      expect(feedback.ratings, ['dislike']);
      expect(feedback.targetIds, [_rowId]);
      expect(find.text('Thanks — feedback recorded'), findsOneWidget);
    });

    testWidgets('pending guard ignores repeated taps', (
      WidgetTester tester,
    ) async {
      final gate = Completer<FeedbackResult>();
      final feedback = _FakeFeedbackRepository()..handler = () => gate.future;
      await tester.pumpWidget(_screen(feedback));
      await tester.pumpAndSettle();

      final button = find.byIcon(Icons.thumb_up_outlined).first;
      await tester.scrollUntilVisible(button, 500.0);
      await tester.pumpAndSettle();
      // Two taps in the same frame: the second hits the pending guard
      // (the first registers synchronously before any rebuild).
      await tester.tap(button);
      await tester.tap(button);
      await tester.pump();
      expect(feedback.calls, 1);
      // Spinner replaces the buttons while pending.
      expect(find.byType(CircularProgressIndicator), findsWidgets);

      gate.complete(const FeedbackResult.sent());
      await tester.pumpAndSettle();
      expect(feedback.calls, 1);
      expect(find.text('Thanks — feedback recorded'), findsOneWidget);
    });

    testWidgets('failed submit keeps the row with truthful feedback', (
      WidgetTester tester,
    ) async {
      final feedback = _FakeFeedbackRepository()
        ..handler = () async =>
            const FeedbackResult.failure(FeedbackStatus.networkError);
      await tester.pumpWidget(_screen(feedback));
      await tester.pumpAndSettle();

      await _tapReaction(tester, Icons.thumb_up_outlined);

      expect(feedback.calls, 1);
      expect(find.text('Office Outfit'), findsOneWidget);
      expect(
        find.text('Couldn\'t send feedback. Please check your connection.'),
        findsOneWidget,
      );
      expect(find.text('Thanks — feedback recorded'), findsNothing);
      // Retry stays available.
      expect(find.byIcon(Icons.thumb_up_outlined), findsOneWidget);
    });

    testWidgets('conflict maps to an already-recorded message', (
      WidgetTester tester,
    ) async {
      final conflict = _FakeFeedbackRepository()
        ..handler = () async =>
            const FeedbackResult.failure(FeedbackStatus.conflict);
      await tester.pumpWidget(_screen(conflict));
      await tester.pumpAndSettle();
      await _tapReaction(tester, Icons.thumb_up_outlined);
      expect(find.text('Feedback already recorded'), findsOneWidget);
    });

    testWidgets('auth failure maps to a sign-in message', (
      WidgetTester tester,
    ) async {
      final auth = _FakeFeedbackRepository()
        ..handler = () async =>
            const FeedbackResult.failure(FeedbackStatus.unauthorized);
      await tester.pumpWidget(_screen(auth));
      await tester.pumpAndSettle();
      await _tapReaction(tester, Icons.thumb_down_outlined);
      expect(
        find.text('Please sign in again to send feedback.'),
        findsOneWidget,
      );
    });

    testWidgets('reactions never fabricate local signals or saves', (
      WidgetTester tester,
    ) async {
      final feedback = _FakeFeedbackRepository()
        ..handler = () async => const FeedbackResult.sent();
      await tester.pumpWidget(_screen(feedback));
      await tester.pumpAndSettle();

      await _tapReaction(tester, Icons.thumb_up_outlined);

      // No wear/save/signal copy anywhere on this surface.
      expect(find.text('Wearing this look!'), findsNothing);
      expect(find.text('Outfit saved'), findsNothing);
      expect(feedback.calls, 1);
    });
  });
}
