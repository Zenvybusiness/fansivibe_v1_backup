import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/events/data/event_models.dart';
import 'package:fansivibe/features/events/data/events_client.dart';
import 'package:fansivibe/features/events/data/events_repository.dart';
import 'package:fansivibe/features/home/data/today_look_models.dart';
import 'package:fansivibe/features/home/data/today_look_repository.dart';
import 'package:fansivibe/features/home/presentation/home_screen.dart';
import 'package:fansivibe/features/home/presentation/widgets/backend_summary_cards.dart';
import 'package:fansivibe/features/home/presentation/widgets/existing_user_home_widgets.dart';
import 'package:fansivibe/features/learning/learning_summary.dart';
import 'package:fansivibe/features/profile/data/saved_looks_models.dart';
import 'package:fansivibe/features/profile/data/saved_looks_repository.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:fansivibe/shared/utils/user_session.dart';

class _EstablishedSummaryRepo implements LearningSummaryRepository {
  @override
  Future<LearningSummary?> getSummary() async => const LearningSummary(
    styleScore: 76,
    breakdown: LearningSummaryBreakdown(
      base: 60,
      wardrobePoints: 8,
      savedPoints: 8,
      total: 76,
    ),
    streak: 3,
    recentSignals: ['sig-1'],
  );
}

class _FakeTodayLookRepo implements TodayLookRepository {
  @override
  Future<TodayLookResult> getTodayLook({
    String? city,
    double? latitude,
    double? longitude,
  }) async => const TodayLookResult.noneAvailable();

  @override
  Future<TodayLookResult> regenerateTodayLook({
    String? seed,
    String? city,
    double? latitude,
    double? longitude,
  }) async => const TodayLookResult.noneAvailable();

  @override
  Future<SavedTodayLook?> saveTodayLook({
    String? lookId,
    required String title,
    required Map<String, dynamic> snapshot,
    required String idempotencyKey,
  }) async => null;
}

class _FakeWardrobeRepo implements WardrobeRepository {
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

class _FakeSavedLooksRepo implements SavedLooksRepository {
  @override
  Future<SavedLookListPage?> listSavedLooks({
    int page = 1,
    int pageSize = 20,
  }) async =>
      const SavedLookListPage(items: [], page: 1, pageSize: 20, total: 0);

  @override
  Future<SavedLookItem?> getSavedLook({
    required String id,
    bool includeItems = false,
  }) async => null;

  @override
  Future<SavedLookDeleteOutcome?> deleteSavedLook({required String id}) async =>
      SavedLookDeleteOutcome.deleted;
}

class _ScriptedEventsRepo implements EventsRepository {
  _ScriptedEventsRepo(this.handlers);

  final List<Future<EventListResult> Function()> handlers;
  int listCalls = 0;

  @override
  Future<EventListResult> listEventsResult({
    int page = 1,
    int pageSize = 20,
    String? fromDate,
  }) {
    final index = listCalls < handlers.length ? listCalls : handlers.length - 1;
    listCalls++;
    return handlers[index]();
  }

  @override
  Future<EventListPage?> listEvents({
    int page = 1,
    int pageSize = 20,
    String? fromDate,
  }) async {
    final res = await listEventsResult(
      page: page,
      pageSize: pageSize,
      fromDate: fromDate,
    );
    return res.page;
  }

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

EventItem _sampleEvent({
  String id = '11111111-1111-4111-8111-111111111111',
  String title = 'Gallery Opening',
  String eventType = 'cocktail',
  String eventDate = '2030-05-15',
  String? eventTime = '19:30',
  String? location = 'Atelier Nord',
}) {
  return EventItem(
    id: id,
    title: title,
    eventType: eventType,
    eventDate: eventDate,
    eventTime: eventTime,
    location: location,
    createdAt: DateTime.utc(2030, 1, 1),
    updatedAt: DateTime.utc(2030, 1, 1),
  );
}

Widget _buildHomeTestApp(EventsRepository eventsRepository) {
  final router = GoRouter(
    initialLocation: '/home',
    routes: [
      GoRoute(
        path: '/home',
        name: RouteNames.home,
        builder: (context, state) => HomeScreen(
          summaryRepository: _EstablishedSummaryRepo(),
          todayLookRepository: _FakeTodayLookRepo(),
          wardrobeRepository: _FakeWardrobeRepo(),
          eventsRepository: eventsRepository,
          savedLooksRepository: _FakeSavedLooksRepo(),
        ),
      ),
      GoRoute(
        path: '/events/add',
        name: RouteNames.eventAdd,
        builder: (context, state) => const Scaffold(body: Text('Add Event')),
      ),
      GoRoute(
        path: '/build-outfit',
        name: RouteNames.buildOutfit,
        builder: (context, state) => const Scaffold(body: Text('Build Outfit')),
      ),
      GoRoute(
        path: '/profile',
        name: RouteNames.profile,
        builder: (context, state) => const Scaffold(body: Text('Profile')),
      ),
    ],
  );
  return MaterialApp.router(routerConfig: router);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    LocalStorage.init(prefs: prefs);
    AuthSession.resetForTest();
    await AuthSession.saveSession('test-jwt-token');
  });

  tearDown(() {
    AuthSession.resetForTest();
  });

  group('Home Upcoming Events — States, Retry, Stale Guard & Honesty', () {
    testWidgets('1. Shows loading state while upcoming events are fetching', (
      WidgetTester tester,
    ) async {
      final completer = Completer<EventListResult>();
      final repo = _ScriptedEventsRepo([() => completer.future]);

      await tester.pumpWidget(_buildHomeTestApp(repo));
      await tester.pump();
      await tester.pump();

      final loadingFinder = find.widgetWithText(SummaryLoadingCard, 'Upcoming');
      await tester.scrollUntilVisible(loadingFinder, 300.0);
      expect(loadingFinder, findsOneWidget);
      expect(find.text('Planning something special?'), findsNothing);

      completer.complete(
        const EventListResult.success(
          EventListPage(items: [], page: 1, pageSize: 5, total: 0),
        ),
      );
      await tester.pumpAndSettle();
    });

    testWidgets(
      '2. Shows event on success without misleading CALENDAR SYNCED claim',
      (WidgetTester tester) async {
        final repo = _ScriptedEventsRepo([
          () async => EventListResult.success(
            EventListPage(
              items: [_sampleEvent()],
              page: 1,
              pageSize: 5,
              total: 1,
            ),
          ),
        ]);

        await tester.pumpWidget(_buildHomeTestApp(repo));
        await tester.pumpAndSettle();

        final eventFinder = find.text('Gallery Opening');
        await tester.scrollUntilVisible(eventFinder, 300.0);
        expect(eventFinder, findsOneWidget);
        expect(find.text('Atelier Nord • 19:30'), findsOneWidget);
        expect(find.text('COCKTAIL'), findsOneWidget);
        expect(find.text('PLAN MY LOOK →'), findsOneWidget);
        expect(find.text('CALENDAR SYNCED'), findsNothing);
      },
    );

    testWidgets('3. Shows genuine empty state on successful empty response', (
      WidgetTester tester,
    ) async {
      final repo = _ScriptedEventsRepo([
        () async => const EventListResult.success(
          EventListPage(items: [], page: 1, pageSize: 5, total: 0),
        ),
      ]);

      await tester.pumpWidget(_buildHomeTestApp(repo));
      await tester.pumpAndSettle();

      final emptyFinder = find.text('Planning something special?');
      await tester.scrollUntilVisible(emptyFinder, 300.0);
      expect(emptyFinder, findsOneWidget);
      expect(find.text('CREATE AN EVENT →'), findsOneWidget);
      expect(find.widgetWithText(SummaryErrorCard, 'Upcoming'), findsNothing);
    });

    testWidgets(
      '4. Shows server error and Retry on API failure, never empty state',
      (WidgetTester tester) async {
        final repo = _ScriptedEventsRepo([
          () async =>
              const EventListResult.failure(EventListFailure.serverError),
        ]);

        await tester.pumpWidget(_buildHomeTestApp(repo));
        await tester.pumpAndSettle();

        final errorCard = find.widgetWithText(SummaryErrorCard, 'Upcoming');
        await tester.scrollUntilVisible(errorCard, 300.0);
        expect(errorCard, findsOneWidget);
        expect(
          find.text("Couldn't load upcoming events. Please try again."),
          findsOneWidget,
        );
        expect(find.text('Try Again'), findsWidgets);
        expect(find.text('Planning something special?'), findsNothing);
        expect(find.text('No upcoming events'), findsNothing);
      },
    );

    testWidgets(
      '5. Shows connection error and Retry on network/offline failure',
      (WidgetTester tester) async {
        final repo = _ScriptedEventsRepo([
          () async => Future<EventListResult>.error(
            const SocketException('Network unreachable'),
          ),
        ]);

        await tester.pumpWidget(_buildHomeTestApp(repo));
        await tester.pumpAndSettle();

        final errorCard = find.widgetWithText(SummaryErrorCard, 'Upcoming');
        await tester.scrollUntilVisible(errorCard, 300.0);
        expect(errorCard, findsOneWidget);
        expect(
          find.text(
            "Couldn't load upcoming events. Please check your connection.",
          ),
          findsOneWidget,
        );
        expect(find.text('Planning something special?'), findsNothing);
      },
    );

    testWidgets(
      '6. Retry repeats the failed request and renders events on recovery',
      (WidgetTester tester) async {
        final repo = _ScriptedEventsRepo([
          () async =>
              const EventListResult.failure(EventListFailure.serverError),
          () async => EventListResult.success(
            EventListPage(
              items: [_sampleEvent(title: 'Recovered Gala')],
              page: 1,
              pageSize: 5,
              total: 1,
            ),
          ),
        ]);

        await tester.pumpWidget(_buildHomeTestApp(repo));
        await tester.pumpAndSettle();

        final errorCard = find.widgetWithText(SummaryErrorCard, 'Upcoming');
        await tester.scrollUntilVisible(errorCard, 300.0);
        expect(repo.listCalls, 1);

        final retryBtn = find.descendant(
          of: errorCard,
          matching: find.text('Try Again'),
        );
        await tester.ensureVisible(retryBtn);
        await tester.tap(retryBtn);
        await tester.pumpAndSettle();

        expect(repo.listCalls, 2);
        expect(find.text('Recovered Gala'), findsOneWidget);
        expect(find.widgetWithText(SummaryErrorCard, 'Upcoming'), findsNothing);
      },
    );

    test(
      '7. EventsClient handles 401 expiry and classifies 500 vs network',
      () async {
        var expiredCount = 0;
        AuthSession.onSessionExpired = () => expiredCount++;

        final client401 = EventsClient(
          client: MockClient((_) async => http.Response('Unauthorized', 401)),
        );
        final res401 = await client401.listEventsResult();
        expect(res401.failure, EventListFailure.unauthorized);
        expect(AuthSession.isAuthenticated, isFalse);
        expect(expiredCount, 1);

        await AuthSession.saveSession('fresh-token');
        final client500 = EventsClient(
          client: MockClient((_) async => http.Response('Server Error', 500)),
        );
        final res500 = await client500.listEventsResult();
        expect(res500.failure, EventListFailure.serverError);

        final clientOffline = EventsClient(
          client: MockClient(
            (_) async => throw const SocketException('Offline'),
          ),
        );
        final resOffline = await clientOffline.listEventsResult();
        expect(resOffline.failure, EventListFailure.networkError);
      },
    );

    testWidgets('8. Ignores stale response from earlier request after retry', (
      WidgetTester tester,
    ) async {
      final staleFirst = Completer<EventListResult>();
      final newerSecond = Completer<EventListResult>();
      var call = 0;
      final repo = _ScriptedEventsRepo([
        () {
          call++;
          return call == 1 ? staleFirst.future : newerSecond.future;
        },
      ]);

      await tester.pumpWidget(_buildHomeTestApp(repo));
      await tester.pump();
      await tester.pump();

      // Trigger a session refresh/reset on Home (simulating account/refresh transition)
      await AuthSession.saveSession('second-token');
      await tester.pump();

      // Newer request resolves first with 'Newer Event'
      newerSecond.complete(
        EventListResult.success(
          EventListPage(
            items: [_sampleEvent(title: 'Newer Event')],
            page: 1,
            pageSize: 5,
            total: 1,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Stale first request resolves late with 'Stale Event'
      staleFirst.complete(
        EventListResult.success(
          EventListPage(
            items: [_sampleEvent(title: 'Stale Event')],
            page: 1,
            pageSize: 5,
            total: 1,
          ),
        ),
      );
      await tester.pumpAndSettle();

      final newerFinder = find.text('Newer Event');
      await tester.scrollUntilVisible(newerFinder, 300.0);
      expect(newerFinder, findsOneWidget);
      expect(find.text('Stale Event'), findsNothing);
    });

    test('9. Deduplicates duplicate event IDs preserving order', () {
      final decoded = EventListPage.fromJson({
        'items': [
          {
            'id': 'evt-1',
            'title': 'First Copy',
            'eventType': 'dinner',
            'eventDate': '2030-06-01',
            'createdAt': '2030-01-01T00:00:00Z',
            'updatedAt': '2030-01-01T00:00:00Z',
          },
          {
            'id': 'evt-1',
            'title': 'Duplicate Copy',
            'eventType': 'dinner',
            'eventDate': '2030-06-01',
            'createdAt': '2030-01-01T00:00:00Z',
            'updatedAt': '2030-01-01T00:00:00Z',
          },
          {
            'id': 'evt-2',
            'title': 'Second Event',
            'eventType': 'work',
            'eventDate': '2030-06-02',
            'createdAt': '2030-01-01T00:00:00Z',
            'updatedAt': '2030-01-01T00:00:00Z',
          },
        ],
        'page': 1,
        'page_size': 5,
        'total': 2,
      });

      expect(decoded.items.length, 2);
      expect(decoded.items.map((e) => e.id).toList(), ['evt-1', 'evt-2']);
      expect(decoded.items.first.title, 'First Copy');
    });

    testWidgets(
      '10. ExistingUserUpcomingCard shows CALENDAR SYNCED only when isCalendarSynced is true',
      (WidgetTester tester) async {
        await tester.pumpWidget(
          const MaterialApp(
            home: Scaffold(
              body: ExistingUserUpcomingCard(
                hasEvent: true,
                title: 'Local Event',
                isCalendarSynced: false,
              ),
            ),
          ),
        );
        expect(find.text('CALENDAR SYNCED'), findsNothing);

        await tester.pumpWidget(
          const MaterialApp(
            home: Scaffold(
              body: ExistingUserUpcomingCard(
                hasEvent: true,
                title: 'Synced Event',
                isCalendarSynced: true,
              ),
            ),
          ),
        );
        expect(find.text('CALENDAR SYNCED'), findsOneWidget);
      },
    );

    testWidgets(
      '11. Omits fake location when backend summary has null location and shows formatted date/time',
      (WidgetTester tester) async {
        final repo = _ScriptedEventsRepo([
          () async => EventListResult.success(
            EventListPage(
              items: [
                _sampleEvent(
                  title: 'Summary Gala',
                  eventType: 'date',
                  eventDate: '2030-05-15',
                  eventTime: '19:30',
                  location: null,
                ),
              ],
              page: 1,
              pageSize: 5,
              total: 1,
            ),
          ),
        ]);

        await tester.pumpWidget(_buildHomeTestApp(repo));
        await tester.pumpAndSettle();

        final eventFinder = find.text('Summary Gala');
        await tester.scrollUntilVisible(eventFinder, 300.0);
        expect(eventFinder, findsOneWidget);
        expect(find.text('May 15, 2030 • 7:30 PM'), findsOneWidget);
        expect(find.textContaining('Fansivibe Atelier'), findsNothing);
        expect(find.text('DATE NIGHT'), findsOneWidget);
      },
    );

    testWidgets(
      '12. Filters past-date events from Home Upcoming and refreshes on eventsVersion',
      (WidgetTester tester) async {
        final repo = _ScriptedEventsRepo([
          () async => EventListResult.success(
            EventListPage(
              items: [
                _sampleEvent(
                  id: 'past-1',
                  title: 'Yesterday Event',
                  eventDate: '2000-01-01',
                  eventTime: '10:00',
                  location: null,
                ),
              ],
              page: 1,
              pageSize: 5,
              total: 1,
            ),
          ),
          () async => EventListResult.success(
            EventListPage(
              items: [
                _sampleEvent(
                  id: 'future-1',
                  title: 'Freshly Created Event',
                  eventDate: '2030-09-01',
                  eventTime: null,
                  location: null,
                ),
              ],
              page: 1,
              pageSize: 5,
              total: 1,
            ),
          ),
        ]);

        await tester.pumpWidget(_buildHomeTestApp(repo));
        await tester.pumpAndSettle();

        final emptyFinder = find.text('Planning something special?');
        await tester.scrollUntilVisible(emptyFinder, 300.0);
        expect(emptyFinder, findsOneWidget);
        expect(find.text('Yesterday Event'), findsNothing);

        UserSession.notifyEventsChanged();
        await tester.pumpAndSettle();

        expect(find.text('Freshly Created Event'), findsOneWidget);
        expect(find.text('Sep 1, 2030'), findsOneWidget);
      },
    );
  });
}
