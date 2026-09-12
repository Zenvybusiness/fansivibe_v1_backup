import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/events/data/event_models.dart';
import 'package:fansivibe/features/events/data/events_repository.dart';
import 'package:fansivibe/features/events/presentation/add_event_screen.dart';
import 'package:fansivibe/features/events/presentation/event_details_screen.dart';
import 'package:fansivibe/features/events/presentation/event_list_screen.dart';
import 'package:fansivibe/features/events/presentation/widgets/events_widgets.dart';

/// Stateful fake: the scripted backend. Creates append server-style UUID
/// rows, updates replace by UUID, deletes remove by UUID — exactly the
/// semantics the real backend owns. Call logs prove UUID safety.
class FakeEventsRepository implements EventsRepository {
  FakeEventsRepository({List<EventItem>? seed})
    : _items = [...?seed],
      _counter = 0;

  final List<EventItem> _items;
  int _counter;
  final List<String> calls = [];

  bool failList = false;
  bool failCreate = false;
  bool failUpdate = false;
  bool failDelete = false;
  EventOutfitResult? outfitResult;

  String _nextUuid() {
    _counter++;
    return '00000000-0000-4000-8000-${_counter.toString().padLeft(12, '0')}';
  }

  @override
  Future<EventListPage?> listEvents({int page = 1, int pageSize = 20}) async {
    calls.add('list');
    if (failList) return null;
    return EventListPage(
      items: [..._items],
      page: page,
      pageSize: pageSize,
      total: _items.length,
    );
  }

  @override
  Future<EventItem?> createEvent(EventCreateRequest request) async {
    calls.add('create:${request.eventType}:${request.eventDate}');
    if (failCreate) return null;
    final created = EventItem(
      id: _nextUuid(),
      title: request.title,
      eventType: request.eventType,
      eventDate: request.eventDate,
      eventTime: request.eventTime,
      location: request.location,
      notes: request.notes,
      createdAt: DateTime.utc(2030, 1, 1),
      updatedAt: DateTime.utc(2030, 1, 1),
    );
    _items.add(created);
    return created;
  }

  @override
  Future<EventItem?> updateEvent({
    required String id,
    required EventUpdateRequest request,
  }) async {
    calls.add('update:$id:${request.eventType}');
    if (failUpdate) return null;
    final index = _items.indexWhere((e) => e.id == id);
    if (index == -1) return null;
    final updated = _items[index].copyWith(
      title: request.title,
      eventType: request.eventType,
      eventDate: request.eventDate,
      eventTime: () => request.eventTime,
      location: () => request.location,
      notes: () => request.notes,
    );
    _items[index] = updated;
    return updated;
  }

  @override
  Future<EventDeleteOutcome?> deleteEvent({required String id}) async {
    calls.add('delete:$id');
    if (failDelete) return null;
    final index = _items.indexWhere((e) => e.id == id);
    if (index == -1) return EventDeleteOutcome.alreadyGone;
    _items.removeAt(index);
    return EventDeleteOutcome.deleted;
  }

  @override
  Future<EventOutfitResult?> generateEventOutfit({required String id}) async {
    calls.add('outfit:$id');
    return outfitResult;
  }
}

EventItem _backendItem({
  required String id,
  required String title,
  String eventType = 'formal',
  String eventDate = '2030-08-15',
  String? eventTime = '19:00',
  String? location,
  String? notes,
}) {
  return EventItem(
    id: id,
    title: title,
    eventType: eventType,
    eventDate: eventDate,
    eventTime: eventTime,
    location: location,
    notes: notes,
    createdAt: DateTime.utc(2030, 1, 1),
    updatedAt: DateTime.utc(2030, 1, 1),
  );
}

EventOutfit _backendOutfit() {
  return const EventOutfit(
    title: 'Formal Outfit',
    matchScore: 0.39,
    components: [
      EventOutfitComponent(
        id: '4412f646-56a9-4afa-8717-b330da03b3d0',
        name: 'Navy Blazer',
        category: 'outerwear',
        color: 'navy',
        reason: 'Chosen outerwear piece',
      ),
    ],
    reasons: ['Picked for a Formal occasion'],
    selectedOccasion: 'formal',
  );
}

Widget wrapApp(Widget child) {
  return MaterialApp(home: child);
}

GoRouter _eventRouter(Widget child, {FakeEventsRepository? repository}) {
  return GoRouter(
    initialLocation: '/',
    routes: [
      GoRoute(
        path: '/',
        name: RouteNames.events,
        builder: (_, __) => child,
        routes: [
          GoRoute(
            path: 'add',
            name: RouteNames.eventAdd,
            builder: (_, __) => AddEventScreen(repository: repository),
          ),
          GoRoute(
            path: 'details',
            name: RouteNames.eventDetails,
            builder: (_, state) {
              final event = state.extra as EventItem?;
              return event != null
                  ? EventDetailsScreen(event: event, repository: repository)
                  : const SizedBox();
            },
          ),
          GoRoute(
            path: 'edit',
            name: RouteNames.eventEdit,
            builder: (_, state) {
              final event = state.extra as EventItem?;
              return event != null
                  ? AddEventScreen(event: event, repository: repository)
                  : const SizedBox();
            },
          ),
        ],
      ),
    ],
  );
}

void main() {
  group('EventListScreen backend-first', () {
    testWidgets('renders app bar and header', (WidgetTester tester) async {
      final repository = FakeEventsRepository();
      await tester.pumpWidget(wrapApp(EventListScreen(repository: repository)));
      await tester.pump();

      expect(find.text('My Events'), findsOneWidget);
      expect(find.text('Upcoming Events'), findsOneWidget);
      expect(find.text('Plan outfits for your events'), findsOneWidget);
    });

    testWidgets('shows loading then backend rows', (WidgetTester tester) async {
      final repository = FakeEventsRepository(
        seed: [
          _backendItem(
            id: '11111111-1111-4111-8111-111111111111',
            title: 'Company Gala',
          ),
        ],
      );
      await tester.pumpWidget(wrapApp(EventListScreen(repository: repository)));

      expect(find.byType(CircularProgressIndicator), findsOneWidget);
      await tester.pump();

      expect(find.text('Company Gala'), findsOneWidget);
      expect(find.text('Formal'), findsOneWidget);
      expect(find.textContaining('Aug 15, 2030'), findsOneWidget);
      expect(find.byType(EventCard), findsOneWidget);
    });

    testWidgets('shows empty state for an empty backend page', (
      WidgetTester tester,
    ) async {
      final repository = FakeEventsRepository();
      await tester.pumpWidget(wrapApp(EventListScreen(repository: repository)));
      await tester.pump();

      expect(find.text('No events yet'), findsOneWidget);
      expect(find.byType(EventCard), findsNothing);
    });

    testWidgets('shows error with retry when the backend is unavailable', (
      WidgetTester tester,
    ) async {
      final repository = FakeEventsRepository()..failList = true;
      await tester.pumpWidget(wrapApp(EventListScreen(repository: repository)));
      await tester.pump();

      expect(find.textContaining('Couldn\'t load your events'), findsOneWidget);
      expect(find.byType(EventCard), findsNothing);

      repository.failList = false;
      await tester.tap(find.text('Try Again'));
      await tester.pump();
      await tester.pump();

      expect(find.text('No events yet'), findsOneWidget);
    });

    testWidgets('renders no mock rows without a backend', (
      WidgetTester tester,
    ) async {
      final repository = FakeEventsRepository(
        seed: [
          _backendItem(
            id: '11111111-1111-4111-8111-111111111111',
            title: 'Gala',
          ),
        ],
      );
      await tester.pumpWidget(wrapApp(EventListScreen(repository: repository)));
      await tester.pump();

      expect(find.text('Weekend Brunch'), findsNothing);
      expect(find.text('Client Presentation'), findsNothing);
      expect(find.text('Anniversary Dinner'), findsNothing);
      expect(find.text('Gala'), findsOneWidget);
    });

    testWidgets('backend-created event appears after add flow', (
      WidgetTester tester,
    ) async {
      final repository = FakeEventsRepository();
      await tester.pumpWidget(
        MaterialApp.router(
          routerConfig: _eventRouter(
            EventListScreen(repository: repository),
            repository: repository,
          ),
        ),
      );
      await tester.pump();
      expect(find.text('No events yet'), findsOneWidget);

      await tester.tap(find.byIcon(Icons.add_rounded).first);
      await tester.pump();
      await tester.pump();
      expect(find.text('New Event'), findsOneWidget);

      await tester.enterText(find.byType(TextField).first, 'Rooftop Party');
      await tester.tap(find.text('Select date'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('OK'));
      await tester.pump();
      await tester.scrollUntilVisible(
        find.text('Party'),
        100,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Party'));
      await tester.pump();
      expect(find.byIcon(Icons.check_circle_rounded), findsOneWidget);
      await tester.scrollUntilVisible(
        find.text('Select time (optional)'),
        100,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Select time (optional)'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('OK'));
      await tester.pumpAndSettle();

      await tester.scrollUntilVisible(
        find.byType(FilledButton),
        100,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.byType(FilledButton));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text('Upcoming Events'), findsOneWidget);
      expect(find.text('Rooftop Party'), findsOneWidget);
      expect(
        repository.calls.any((c) => c.startsWith('create:party:')),
        isTrue,
      );
    });

    testWidgets('tapping event card opens EventDetailsScreen', (
      WidgetTester tester,
    ) async {
      final repository = FakeEventsRepository(
        seed: [
          _backendItem(
            id: '11111111-1111-4111-8111-111111111111',
            title: 'Company Gala',
          ),
        ],
      );
      await tester.pumpWidget(
        MaterialApp.router(
          routerConfig: _eventRouter(
            EventListScreen(repository: repository),
            repository: repository,
          ),
        ),
      );
      await tester.pump();

      await tester.tap(find.text('Company Gala'));
      await tester.pump();
      await tester.pump();

      expect(find.text('Event Details'), findsOneWidget);
    });
  });

  group('AddEventScreen backend-first', () {
    testWidgets('renders app bar, fields, and type grid', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(wrapApp(const AddEventScreen()));

      expect(find.text('Add Event'), findsAtLeast(1));
      expect(find.text('New Event'), findsOneWidget);
      expect(find.text('Event Name'), findsOneWidget);
      expect(find.text('Date'), findsOneWidget);
      expect(find.text('Time (optional)'), findsOneWidget);
      expect(find.text('Select time (optional)'), findsOneWidget);
      expect(find.text('Event Type'), findsOneWidget);
      expect(find.text('Location (optional)'), findsOneWidget);
      expect(find.text('Notes (optional)'), findsOneWidget);
      for (final label in [
        'Casual',
        'Formal',
        'Business',
        'Date Night',
        'Party',
        'Travel',
        'Workout',
        'Other',
      ]) {
        expect(find.text(label), findsOneWidget);
      }
    });

    testWidgets('selecting event type shows check icon', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(wrapApp(const AddEventScreen()));

      await tester.tap(find.text('Formal'));
      await tester.pump();

      expect(find.byIcon(Icons.check_circle_rounded), findsOneWidget);
    });

    testWidgets('failed create keeps the form with a truthful message', (
      WidgetTester tester,
    ) async {
      final repository = FakeEventsRepository()..failCreate = true;
      final event = _backendItem(
        id: '11111111-1111-4111-8111-111111111111',
        title: 'Gala',
      );
      await tester.pumpWidget(
        wrapApp(AddEventScreen(event: event, repository: repository)),
      );

      await tester.scrollUntilVisible(
        find.text('Save Changes'),
        100,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Save Changes'));
      await tester.pump();

      expect(find.text('Save Changes'), findsOneWidget);
      expect(
        find.textContaining('Couldn\'t save your changes'),
        findsOneWidget,
      );
      expect(repository.calls.any((c) => c.startsWith('update:')), isTrue);
    });

    testWidgets('edit mode prefills backend values and puts codes', (
      WidgetTester tester,
    ) async {
      final event = _backendItem(
        id: '11111111-1111-4111-8111-111111111111',
        title: 'Gala',
        eventType: 'date',
        eventDate: '2030-08-15',
        eventTime: '19:00',
        location: 'Hall',
        notes: 'Tie',
      );
      final repository = FakeEventsRepository(seed: [event]);
      EventItem? popped;
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => TextButton(
              onPressed: () async {
                popped = await Navigator.of(context).push<EventItem?>(
                  MaterialPageRoute<EventItem?>(
                    builder: (_) =>
                        AddEventScreen(event: event, repository: repository),
                  ),
                );
              },
              child: const Text('open'),
            ),
          ),
        ),
      );

      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();

      expect(find.text('Edit Event'), findsAtLeast(1));
      expect(find.text('Gala'), findsOneWidget);
      expect(find.text('Hall'), findsOneWidget);
      expect(find.text('Tie'), findsOneWidget);

      await tester.scrollUntilVisible(
        find.text('Save Changes'),
        100,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Save Changes'));
      await tester.pump();

      expect(
        repository.calls,
        contains('update:11111111-1111-4111-8111-111111111111:date'),
      );
      expect(popped, isNotNull);
      expect(popped!.id, '11111111-1111-4111-8111-111111111111');
      expect(popped!.location, 'Hall');
    });

    testWidgets('back button pops', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const AddEventScreen()));

      await tester.tap(find.byIcon(Icons.close_rounded));
      await tester.pumpAndSettle();
    });
  });

  group('EventDetailsScreen backend-first', () {
    EventItem detailsEvent() => _backendItem(
      id: '11111111-1111-4111-8111-111111111111',
      title: 'Company Gala',
      eventType: 'formal',
      eventDate: '2030-08-15',
      eventTime: '19:00',
      location: 'Grand Ballroom',
      notes: 'Black tie',
    );

    testWidgets('renders backend event data', (WidgetTester tester) async {
      await tester.pumpWidget(
        wrapApp(
          EventDetailsScreen(
            event: detailsEvent(),
            repository: FakeEventsRepository(),
          ),
        ),
      );

      expect(find.text('Event Details'), findsOneWidget);
      expect(find.text('Company Gala'), findsOneWidget);
      expect(find.text('Formal'), findsAtLeast(1));
      expect(find.text('Aug 15, 2030'), findsOneWidget);
      expect(find.text('7:00 PM'), findsOneWidget);
      expect(find.text('Grand Ballroom'), findsOneWidget);
      expect(find.text('Black tie'), findsOneWidget);
      expect(find.text('Date'), findsOneWidget);
      expect(find.text('Time'), findsOneWidget);
      expect(find.text('Type'), findsOneWidget);
      expect(find.text('Location'), findsOneWidget);
      expect(find.text('Notes'), findsOneWidget);
    });

    testWidgets('renders dash for events without time', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        wrapApp(
          EventDetailsScreen(
            event: detailsEvent().copyWith(eventTime: () => null),
            repository: FakeEventsRepository(),
          ),
        ),
      );

      expect(find.text('—'), findsOneWidget);
    });

    testWidgets('delete asks for confirmation then deletes the exact UUID', (
      WidgetTester tester,
    ) async {
      final repository = FakeEventsRepository();
      bool? popped;
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => TextButton(
              onPressed: () async {
                popped = await Navigator.of(context).push(
                  MaterialPageRoute<bool>(
                    builder: (_) => EventDetailsScreen(
                      event: detailsEvent(),
                      repository: repository,
                    ),
                  ),
                );
              },
              child: const Text('open'),
            ),
          ),
        ),
      );
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();

      await tester.tap(find.byIcon(Icons.delete_outline_rounded));
      await tester.pump();
      expect(find.text('Delete Event'), findsOneWidget);

      await tester.tap(find.text('Delete').last);
      await tester.pump();

      expect(
        repository.calls,
        contains('delete:11111111-1111-4111-8111-111111111111'),
      );
      expect(popped, isTrue);
    });

    testWidgets('cancelled delete sends nothing', (WidgetTester tester) async {
      final repository = FakeEventsRepository();
      await tester.pumpWidget(
        wrapApp(
          EventDetailsScreen(event: detailsEvent(), repository: repository),
        ),
      );

      await tester.tap(find.byIcon(Icons.delete_outline_rounded));
      await tester.pump();
      await tester.tap(find.text('Cancel'));
      await tester.pump();

      expect(repository.calls, isEmpty);
      expect(find.text('Event Details'), findsOneWidget);
    });

    testWidgets('failed delete retains the event with a message', (
      WidgetTester tester,
    ) async {
      final repository = FakeEventsRepository()..failDelete = true;
      await tester.pumpWidget(
        wrapApp(
          EventDetailsScreen(event: detailsEvent(), repository: repository),
        ),
      );

      await tester.tap(find.byIcon(Icons.delete_outline_rounded));
      await tester.pump();
      await tester.tap(find.text('Delete').last);
      await tester.pump();

      expect(find.text('Event Details'), findsOneWidget);
      expect(
        find.textContaining('Couldn\'t delete your event'),
        findsOneWidget,
      );
    });

    testWidgets('edit button opens the edit route with the backend event', (
      WidgetTester tester,
    ) async {
      final repository = FakeEventsRepository();
      await tester.pumpWidget(
        MaterialApp.router(
          routerConfig: _eventRouter(
            EventDetailsScreen(event: detailsEvent(), repository: repository),
            repository: repository,
          ),
        ),
      );

      await tester.tap(find.text('Edit Event'));
      await tester.pump();
      await tester.pump();

      expect(find.text('Edit Event'), findsAtLeast(1));
      expect(find.text('Company Gala'), findsNWidgets(2));
    });

    testWidgets('generate outfit renders the backend recommendation', (
      WidgetTester tester,
    ) async {
      final repository = FakeEventsRepository()
        ..outfitResult = EventOutfitResult.available(_backendOutfit());
      await tester.pumpWidget(
        wrapApp(
          EventDetailsScreen(event: detailsEvent(), repository: repository),
        ),
      );

      await tester.tap(find.text('Generate Outfit'));
      await tester.pump();

      expect(
        repository.calls,
        contains('outfit:11111111-1111-4111-8111-111111111111'),
      );
      expect(find.text('Formal Outfit'), findsOneWidget);
      expect(find.text('Navy Blazer'), findsOneWidget);
      expect(find.text('Match Score'), findsOneWidget);
      expect(find.text('Picked for a Formal occasion'), findsOneWidget);
      expect(find.text('Event Details'), findsOneWidget);
    });

    testWidgets('generate outfit shows a truthful empty state on 204', (
      WidgetTester tester,
    ) async {
      final repository = FakeEventsRepository()
        ..outfitResult = const EventOutfitResult.noneAvailable();
      await tester.pumpWidget(
        wrapApp(
          EventDetailsScreen(event: detailsEvent(), repository: repository),
        ),
      );

      await tester.tap(find.text('Generate Outfit'));
      await tester.pump();

      expect(find.text('No outfit available'), findsOneWidget);
      expect(
        find.text('Add more pieces to your wardrobe and try again.'),
        findsOneWidget,
      );
    });

    testWidgets('failed outfit keeps the screen with a message', (
      WidgetTester tester,
    ) async {
      final repository = FakeEventsRepository();
      await tester.pumpWidget(
        wrapApp(
          EventDetailsScreen(event: detailsEvent(), repository: repository),
        ),
      );

      await tester.tap(find.text('Generate Outfit'));
      await tester.pump();

      expect(find.text('Event Details'), findsOneWidget);
      expect(
        find.textContaining('Couldn\'t generate an outfit'),
        findsOneWidget,
      );
      expect(find.text('No outfit available'), findsNothing);
    });
  });
}
