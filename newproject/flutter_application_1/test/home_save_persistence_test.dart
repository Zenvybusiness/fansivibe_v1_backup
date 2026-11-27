import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/app/app.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/events/data/event_models.dart';
import 'package:fansivibe/features/events/data/events_repository.dart';
import 'package:fansivibe/features/home/data/today_look_models.dart';
import 'package:fansivibe/features/home/data/today_look_repository.dart';
import 'package:fansivibe/features/home/presentation/home_screen.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/learning/learning_summary.dart';
import 'package:fansivibe/features/profile/data/saved_looks_models.dart';
import 'package:fansivibe/features/profile/data/saved_looks_repository.dart';
import 'package:fansivibe/features/profile/presentation/saved_looks_screen.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

const String _item1 = '78ff3686-c950-4cd6-84c3-7e18d6634dfa';
const String _item2 = '4412f646-56a9-4afa-8717-b330da03b3d0';

TodayLook _sampleTodayLook({String title = 'City Layers'}) {
  return TodayLook.fromJson({
    'title': title,
    'occasion': 'work',
    'description': 'Layered neutrals built from owned staples.',
    'matchScore': 88,
    'styleScore': 88,
    'components': [
      {
        'id': _item1,
        'name': 'Camel Overcoat',
        'category': 'outerwear',
        'color': 'Camel',
      },
      {'id': _item2, 'name': 'Grey Knit', 'category': 'tops', 'color': 'Grey'},
    ],
    'reasons': ['Picked for a work occasion'],
    'wardrobeContext': {'totalItems': 2, 'matchingItems': 2},
    'alternatives': <Map<String, dynamic>>[],
    'selectedItemIds': [_item2, _item1],
  });
}

/// Shared in-memory backend double scoped by active [AuthSession.token],
/// simulating persisted PostgreSQL `saved_looks` across restarts and accounts.
class _FakePersistedSavedLooksBackend
    implements TodayLookRepository, SavedLooksRepository {
  final Map<String, List<SavedLookItem>> _byToken = {};
  final Map<String, TodayLook> _todayLookByToken = {};

  int saveCalls = 0;
  int deleteCalls = 0;
  int listCalls = 0;
  int _idSeq = 0;

  bool failNextSave = false;
  bool failNextDelete = false;
  bool expireAuthOnNextSave = false;
  Completer<void>? saveGate;
  Completer<void>? deleteGate;

  String get _currentToken => AuthSession.token ?? 'anonymous';

  List<SavedLookItem> rowsFor(String token) =>
      _byToken.putIfAbsent(token, () => <SavedLookItem>[]);

  void setTodayLook(String token, TodayLook look) {
    _todayLookByToken[token] = look;
  }

  @override
  Future<TodayLookResult> getTodayLook({
    String? city,
    double? latitude,
    double? longitude,
  }) async {
    final look = _todayLookByToken[_currentToken] ?? _sampleTodayLook();
    return TodayLookResult.available(look);
  }

  @override
  Future<TodayLookResult> regenerateTodayLook({
    String? seed,
    String? city,
    double? latitude,
    double? longitude,
  }) => getTodayLook();

  @override
  Future<SavedTodayLook?> saveTodayLook({
    String? lookId,
    required String title,
    required Map<String, dynamic> snapshot,
    required String idempotencyKey,
  }) async {
    saveCalls++;
    if (saveGate != null) {
      await saveGate!.future;
    }
    if (expireAuthOnNextSave) {
      expireAuthOnNextSave = false;
      AuthSession.notifyUnauthorized();
      return null;
    }
    if (failNextSave) {
      failNextSave = false;
      return null;
    }
    _idSeq++;
    final newId = 'saved-look-$_idSeq';
    final now = DateTime.utc(2026, 11, 27, 12, 0, _idSeq);
    final item = SavedLookItem(
      id: newId,
      lookId: lookId,
      title: title,
      sourceContext: 'daily',
      snapshot: Map<String, dynamic>.from(snapshot),
      createdAt: now,
    );
    rowsFor(_currentToken).insert(0, item);
    return SavedTodayLook(
      id: newId,
      lookId: lookId,
      title: title,
      sourceContext: 'daily',
      snapshot: Map<String, dynamic>.from(snapshot),
      createdAt: now,
    );
  }

  @override
  Future<SavedLookListPage?> listSavedLooks({
    int page = 1,
    int pageSize = 20,
  }) async {
    listCalls++;
    final all = rowsFor(_currentToken);
    final start = (page - 1) * pageSize;
    final items = start >= all.length
        ? const <SavedLookItem>[]
        : all.skip(start).take(pageSize).toList();
    return SavedLookListPage(
      items: items,
      page: page,
      pageSize: pageSize,
      total: all.length,
    );
  }

  @override
  Future<SavedLookItem?> getSavedLook({
    required String id,
    bool includeItems = true,
  }) async {
    for (final item in rowsFor(_currentToken)) {
      if (item.id == id) return item;
    }
    return null;
  }

  @override
  Future<SavedLookDeleteOutcome?> deleteSavedLook({required String id}) async {
    deleteCalls++;
    if (deleteGate != null) {
      await deleteGate!.future;
    }
    if (failNextDelete) {
      failNextDelete = false;
      return null;
    }
    final list = rowsFor(_currentToken);
    final before = list.length;
    list.removeWhere((item) => item.id == id);
    return list.length < before
        ? SavedLookDeleteOutcome.deleted
        : SavedLookDeleteOutcome.alreadyGone;
  }
}

class _EstablishedSummaryRepository implements LearningSummaryRepository {
  @override
  Future<LearningSummary?> getSummary() async => const LearningSummary(
    styleScore: 73,
    breakdown: LearningSummaryBreakdown(
      base: 60,
      wardrobePoints: 5,
      savedPoints: 8,
      total: 73,
    ),
    streak: 5,
    recentSignals: ['backend-signal-1'],
  );
}

class _EmptyWardrobeRepository implements WardrobeRepository {
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
  Future<bool?> deleteItem({required String itemId}) async => null;

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

  @override
  Future<WearSummary?> getWearSummary() async => null;
}

class _EmptyEventsRepository implements EventsRepository {
  @override
  Future<EventListPage?> listEvents({
    int page = 1,
    int pageSize = 20,
    String? fromDate,
  }) async => const EventListPage(items: [], page: 1, pageSize: 20, total: 0);

  @override
  Future<EventListResult> listEventsResult({
    int page = 1,
    int pageSize = 20,
    String? fromDate,
  }) async => const EventListResult.success(
    EventListPage(items: [], page: 1, pageSize: 20, total: 0),
  );

  @override
  Future<EventItem?> getEvent({required String id}) async => null;

  @override
  Future<EventItem?> createEvent(EventCreateRequest request) async => null;

  @override
  Future<EventItem?> updateEvent({
    required String id,
    required EventUpdateRequest request,
  }) async => null;

  @override
  Future<EventDeleteOutcome?> deleteEvent({required String id}) async => null;

  @override
  Future<EventOutfitResult?> generateEventOutfit({required String id}) async =>
      null;
}

Widget _buildHomeApp(_FakePersistedSavedLooksBackend backend) {
  final router = GoRouter(
    initialLocation: '/home',
    routes: [
      GoRoute(
        path: '/home',
        name: RouteNames.home,
        builder: (context, state) => HomeScreen(
          summaryRepository: _EstablishedSummaryRepository(),
          todayLookRepository: backend,
          savedLooksRepository: backend,
          wardrobeRepository: _EmptyWardrobeRepository(),
          eventsRepository: _EmptyEventsRepository(),
        ),
      ),
      GoRoute(
        path: '/saved-looks',
        name: RouteNames.profileSavedLooks,
        builder: (context, state) => SavedLooksScreen(repository: backend),
      ),
      GoRoute(
        path: '/entry',
        name: RouteNames.entry,
        builder: (context, state) =>
            const Scaffold(body: Center(child: Text('Entry Screen'))),
      ),
      GoRoute(
        path: '/build-outfit',
        name: RouteNames.buildOutfit,
        builder: (context, state) => Scaffold(
          appBar: AppBar(title: const Text('Build Outfit')),
          body: const Center(child: Text('Build Outfit')),
        ),
      ),
    ],
  );
  return FansivibeApp(router: router);
}

Finder _heroHeartFilled() => find.descendant(
  of: find.bySemanticsLabel('Favorite'),
  matching: find.byIcon(Icons.favorite_rounded),
);

Finder _heroHeartOutline() => find.descendant(
  of: find.bySemanticsLabel('Favorite'),
  matching: find.byIcon(Icons.favorite_border_rounded),
);

Finder _heroBookmarkFilled() => find.descendant(
  of: find.bySemanticsLabel('Save'),
  matching: find.byIcon(Icons.bookmark_rounded),
);

Finder _heroBookmarkOutline() => find.descendant(
  of: find.bySemanticsLabel('Save'),
  matching: find.byIcon(Icons.bookmark_border_rounded),
);

void main() {
  group('Home Save / Heart Persistence (H1)', () {
    late _FakePersistedSavedLooksBackend backend;

    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      LocalStorage.init(prefs: await SharedPreferences.getInstance());
      LearningService.instance.resetForTest();
      AuthSession.resetForTest();
      await AuthSession.saveSession('user-a-token');
      backend = _FakePersistedSavedLooksBackend();
    });

    tearDown(() async {
      AuthSession.resetForTest();
      await AuthSession.clearSession();
      LocalStorage.resetForTest();
    });

    testWidgets('1 & 2. Save and unsave an outfit from Home', (tester) async {
      await tester.pumpWidget(_buildHomeApp(backend));
      await tester.pumpAndSettle();

      expect(_heroHeartOutline(), findsOneWidget);
      expect(_heroBookmarkOutline(), findsOneWidget);
      expect(backend.rowsFor('user-a-token'), isEmpty);

      // Tap heart to save
      await tester.tap(find.bySemanticsLabel('Favorite'));
      await tester.pumpAndSettle();

      expect(backend.saveCalls, 1);
      expect(backend.rowsFor('user-a-token').length, 1);
      expect(_heroHeartFilled(), findsOneWidget);
      expect(_heroBookmarkFilled(), findsOneWidget);

      // Tap heart again to unsave
      await tester.tap(find.bySemanticsLabel('Favorite'));
      await tester.pumpAndSettle();

      expect(backend.deleteCalls, 1);
      expect(backend.rowsFor('user-a-token'), isEmpty);
      expect(_heroHeartOutline(), findsOneWidget);
      expect(_heroBookmarkOutline(), findsOneWidget);
    });

    testWidgets(
      '3. State remains correct after navigating away and returning',
      (tester) async {
        await tester.pumpWidget(_buildHomeApp(backend));
        await tester.pumpAndSettle();

        // Save on Home
        await tester.tap(find.bySemanticsLabel('Favorite'));
        await tester.pumpAndSettle();
        expect(_heroHeartFilled(), findsOneWidget);

        // Navigate away to Build Outfit and return
        await tester.drag(
          find.byType(SingleChildScrollView).first,
          const Offset(0, -300),
        );
        await tester.pumpAndSettle();
        await tester.tap(find.text('SWAP ITEM'));
        await tester.pumpAndSettle();
        expect(find.text('Build Outfit'), findsWidgets);

        await tester.tap(find.byTooltip('Back'));
        await tester.pumpAndSettle();

        await tester.drag(
          find.byType(SingleChildScrollView).first,
          const Offset(0, 300),
        );
        await tester.pumpAndSettle();

        expect(_heroHeartFilled(), findsOneWidget);
        expect(_heroBookmarkFilled(), findsOneWidget);
      },
    );

    testWidgets('4. Reload Home restores persisted heart state', (
      tester,
    ) async {
      await tester.pumpWidget(_buildHomeApp(backend));
      await tester.pumpAndSettle();

      await tester.tap(find.bySemanticsLabel('Favorite'));
      await tester.pumpAndSettle();
      expect(_heroHeartFilled(), findsOneWidget);

      // Unmount and mount a fresh HomeScreen (reload)
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump();
      await tester.pumpWidget(_buildHomeApp(backend));
      await tester.pumpAndSettle();

      expect(_heroHeartFilled(), findsOneWidget);
      expect(_heroBookmarkFilled(), findsOneWidget);
    });

    testWidgets('5. Application restart restores persisted heart state', (
      tester,
    ) async {
      await tester.pumpWidget(_buildHomeApp(backend));
      await tester.pumpAndSettle();

      await tester.tap(find.bySemanticsLabel('Favorite'));
      await tester.pumpAndSettle();
      expect(backend.rowsFor('user-a-token').length, 1);

      // Simulate full app restart: tear down widget tree & reset in-memory state
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump();
      LocalStorage.resetForTest();
      LearningService.instance.resetForTest();
      AuthSession.resetForTest();

      SharedPreferences.setMockInitialValues({});
      LocalStorage.init(prefs: await SharedPreferences.getInstance());
      await AuthSession.saveSession('user-a-token');

      await tester.pumpWidget(_buildHomeApp(backend));
      await tester.pumpAndSettle();

      expect(_heroHeartFilled(), findsOneWidget);
      expect(_heroBookmarkFilled(), findsOneWidget);
    });

    testWidgets(
      '6. Rapid duplicate taps never trigger duplicate save or delete calls',
      (tester) async {
        backend.saveGate = Completer<void>();
        await tester.pumpWidget(_buildHomeApp(backend));
        await tester.pumpAndSettle();

        // Tap 3 times rapidly while save is in flight
        await tester.tap(find.bySemanticsLabel('Favorite'));
        await tester.pump();
        await tester.tap(find.bySemanticsLabel('Favorite'));
        await tester.pump();
        await tester.tap(find.bySemanticsLabel('Save'));
        await tester.pump();

        expect(backend.saveCalls, 1);
        backend.saveGate!.complete();
        backend.saveGate = null;
        await tester.pumpAndSettle();

        expect(backend.rowsFor('user-a-token').length, 1);
        expect(_heroHeartFilled(), findsOneWidget);

        // Tap 3 times rapidly while delete is in flight
        backend.deleteGate = Completer<void>();
        await tester.tap(find.bySemanticsLabel('Favorite'));
        await tester.pump();
        await tester.tap(find.bySemanticsLabel('Favorite'));
        await tester.pump();
        await tester.tap(find.bySemanticsLabel('Save'));
        await tester.pump();

        expect(backend.deleteCalls, 1);
        backend.deleteGate!.complete();
        backend.deleteGate = null;
        await tester.pumpAndSettle();

        expect(backend.rowsFor('user-a-token'), isEmpty);
        expect(_heroHeartOutline(), findsOneWidget);
      },
    );

    testWidgets('7. Failed save/unsave never displays false success state', (
      tester,
    ) async {
      await tester.pumpWidget(_buildHomeApp(backend));
      await tester.pumpAndSettle();

      // Failed save keeps heart outlined
      backend.failNextSave = true;
      await tester.tap(find.bySemanticsLabel('Favorite'));
      await tester.pumpAndSettle();

      expect(_heroHeartOutline(), findsOneWidget);
      expect(backend.rowsFor('user-a-token'), isEmpty);
      expect(
        find.text('Couldn\'t save this look. Please try again.'),
        findsOneWidget,
      );

      // Succeed save, then fail unsave -> heart remains filled
      ScaffoldMessenger.of(
        tester.element(find.byType(HomeScreen)),
      ).clearSnackBars();
      await tester.tap(find.bySemanticsLabel('Favorite'));
      await tester.pumpAndSettle();
      expect(_heroHeartFilled(), findsOneWidget);

      ScaffoldMessenger.of(
        tester.element(find.byType(HomeScreen)),
      ).clearSnackBars();
      backend.failNextDelete = true;
      await tester.tap(find.bySemanticsLabel('Favorite'));
      await tester.pumpAndSettle();

      expect(_heroHeartFilled(), findsOneWidget);
      expect(backend.rowsFor('user-a-token').length, 1);
      expect(
        find.text('Couldn\'t remove saved look. Please try again.'),
        findsOneWidget,
      );
    });

    testWidgets('8. Auth expiry clears session and resets Home heart state', (
      tester,
    ) async {
      await tester.pumpWidget(_buildHomeApp(backend));
      await tester.pumpAndSettle();

      var expiredCount = 0;
      AuthSession.onSessionExpired = () => expiredCount++;

      backend.expireAuthOnNextSave = true;
      await tester.tap(find.bySemanticsLabel('Favorite'));
      await tester.pumpAndSettle();

      expect(expiredCount, 1);
      expect(AuthSession.isAuthenticated, isFalse);
      expect(_heroHeartFilled(), findsNothing);
      expect(_heroBookmarkFilled(), findsNothing);
    });

    testWidgets('9. Account switching isolates saved heart state per user', (
      tester,
    ) async {
      await tester.pumpWidget(_buildHomeApp(backend));
      await tester.pumpAndSettle();

      // User A saves Today's Look
      await tester.tap(find.bySemanticsLabel('Favorite'));
      await tester.pumpAndSettle();
      expect(_heroHeartFilled(), findsOneWidget);

      // Switch to User B
      await AuthSession.saveSession('user-b-token');
      await tester.pumpAndSettle();

      expect(_heroHeartOutline(), findsOneWidget);
      expect(_heroBookmarkOutline(), findsOneWidget);

      // Switch back to User A -> User A's saved heart is restored
      await AuthSession.saveSession('user-a-token');
      await tester.pumpAndSettle();

      expect(_heroHeartFilled(), findsOneWidget);
      expect(_heroBookmarkFilled(), findsOneWidget);
    });

    testWidgets('10. Saved Looks screen and Home remain consistent', (
      tester,
    ) async {
      final router = GoRouter(
        initialLocation: '/home',
        routes: [
          GoRoute(
            path: '/home',
            name: RouteNames.home,
            builder: (context, state) => Column(
              children: [
                Expanded(
                  child: HomeScreen(
                    summaryRepository: _EstablishedSummaryRepository(),
                    todayLookRepository: backend,
                    savedLooksRepository: backend,
                    wardrobeRepository: _EmptyWardrobeRepository(),
                    eventsRepository: _EmptyEventsRepository(),
                  ),
                ),
                TextButton(
                  onPressed: () =>
                      context.pushNamed(RouteNames.profileSavedLooks),
                  child: const Text('Go Saved Looks'),
                ),
              ],
            ),
          ),
          GoRoute(
            path: '/saved-looks',
            name: RouteNames.profileSavedLooks,
            builder: (context, state) => SavedLooksScreen(repository: backend),
          ),
        ],
      );

      await tester.pumpWidget(FansivibeApp(router: router));
      await tester.pumpAndSettle();

      // Save from Home
      await tester.tap(find.bySemanticsLabel('Favorite'));
      await tester.pumpAndSettle();
      expect(_heroHeartFilled(), findsOneWidget);

      // Navigate to Saved Looks -> saved outfit appears
      await tester.tap(find.text('Go Saved Looks'));
      await tester.pumpAndSettle();
      expect(find.text('1 Saved Looks'), findsOneWidget);
      expect(find.text('City Layers'), findsOneWidget);

      // Delete from Saved Looks
      final remove = find.text('Remove').first;
      await tester.scrollUntilVisible(remove, 500.0);
      await tester.pumpAndSettle();
      await tester.tap(remove);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Delete'));
      await tester.pumpAndSettle();

      expect(find.text('0 Saved Looks'), findsOneWidget);

      // Return to Home -> Home heart is now unsaved
      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
      expect(_heroHeartOutline(), findsOneWidget);
      expect(_heroBookmarkOutline(), findsOneWidget);
    });
  });
}
