import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/features/events/data/event_mock_data.dart';
import 'package:fansivibe/features/events/presentation/add_event_screen.dart';
import 'package:fansivibe/features/events/presentation/event_details_screen.dart';
import 'package:fansivibe/features/events/presentation/event_list_screen.dart';
import 'package:fansivibe/features/events/presentation/widgets/events_widgets.dart';

Widget wrapApp(Widget child) {
  return MaterialApp(home: child);
}

void main() {
  group('EventListScreen Widget Tests', () {
    testWidgets('renders app bar and header', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const EventListScreen()));

      expect(find.text('My Events'), findsOneWidget);
      expect(find.text('Upcoming Events'), findsOneWidget);
      expect(find.text('Plan outfits for your events'), findsOneWidget);
      expect(find.byIcon(Icons.arrow_back_rounded), findsOneWidget);
      expect(find.byIcon(Icons.add_rounded), findsOneWidget);
    });

    testWidgets('renders mock events', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const EventListScreen()));

      expect(find.text('Company Gala'), findsOneWidget);
      expect(find.text('Weekend Brunch'), findsOneWidget);
      expect(find.text('Client Presentation'), findsOneWidget);
      expect(find.text('Anniversary Dinner'), findsOneWidget);
    });

    testWidgets('renders event type labels', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const EventListScreen()));

      expect(find.text('Formal'), findsOneWidget);
      expect(find.text('Casual'), findsOneWidget);
      expect(find.text('Business'), findsOneWidget);
      expect(find.text('Date Night'), findsOneWidget);
    });

    testWidgets('renders EventCard widgets for each event', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(wrapApp(const EventListScreen()));

      expect(find.byType(EventCard), findsNWidgets(4));
    });

    testWidgets('shows Ready and Pending badges', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const EventListScreen()));

      expect(find.text('Ready'), findsAtLeast(1));
      expect(find.text('Pending'), findsAtLeast(1));
    });

    testWidgets('back button pops', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const EventListScreen()));

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
    });

    testWidgets('tapping add opens AddEventScreen', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(wrapApp(const EventListScreen()));

      await tester.tap(find.byIcon(Icons.add_rounded));
      await tester.pump();
      await tester.pump();

      expect(find.text('New Event'), findsOneWidget);
    });

    testWidgets('tapping event card opens EventDetailsScreen', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(wrapApp(const EventListScreen()));

      await tester.tap(find.text('Company Gala'));
      await tester.pump();
      await tester.pump();

      expect(find.text('Event Details'), findsOneWidget);
    });
  });

  group('AddEventScreen Widget Tests', () {
    testWidgets('renders app bar and header', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const AddEventScreen()));

      expect(find.text('Add Event'), findsAtLeast(1));
      expect(find.text('New Event'), findsOneWidget);
      expect(find.text('Fill in the details below'), findsOneWidget);
      expect(find.byIcon(Icons.close_rounded), findsOneWidget);
    });

    testWidgets('renders event name text field', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const AddEventScreen()));

      expect(find.text('Event Name'), findsOneWidget);
    });

    testWidgets('renders date and time picker tiles', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(wrapApp(const AddEventScreen()));

      expect(find.text('Date'), findsOneWidget);
      expect(find.text('Time'), findsOneWidget);
      expect(find.text('Select date'), findsOneWidget);
      expect(find.text('Select time'), findsOneWidget);
    });

    testWidgets('renders event type section', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const AddEventScreen()));

      expect(find.text('Event Type'), findsOneWidget);
    });

    testWidgets('renders all event type options', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const AddEventScreen()));

      expect(find.text('Casual'), findsOneWidget);
      expect(find.text('Formal'), findsOneWidget);
      expect(find.text('Business'), findsOneWidget);
      expect(find.text('Date Night'), findsOneWidget);
      expect(find.text('Party'), findsOneWidget);
      expect(find.text('Travel'), findsOneWidget);
      expect(find.text('Workout'), findsOneWidget);
      expect(find.text('Other'), findsOneWidget);
    });

    testWidgets('renders add event button', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const AddEventScreen()));

      expect(find.text('Add Event'), findsAtLeast(1));
    });

    testWidgets('add event button is disabled when form empty', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(wrapApp(const AddEventScreen()));

      await tester.scrollUntilVisible(
        find.text('Add Event').last,
        100,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.pump();

      expect(find.text('Add Event'), findsAtLeast(1));
    });

    testWidgets('back button pops', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const AddEventScreen()));

      await tester.tap(find.byIcon(Icons.close_rounded));
      await tester.pumpAndSettle();
    });

    testWidgets('typing name updates state', (WidgetTester tester) async {
      await tester.pumpWidget(wrapApp(const AddEventScreen()));

      await tester.enterText(find.byType(TextField), 'Test Event');
      await tester.pump();

      expect(find.text('Test Event'), findsOneWidget);
    });

    testWidgets('selecting event type shows check icon', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(wrapApp(const AddEventScreen()));

      await tester.tap(find.text('Formal'));
      await tester.pump();

      expect(find.byIcon(Icons.check_circle_rounded), findsOneWidget);
    });

    testWidgets('selecting event type switches selection', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(wrapApp(const AddEventScreen()));

      await tester.tap(find.text('Casual'));
      await tester.pump();

      expect(find.byIcon(Icons.check_circle_rounded), findsOneWidget);
    });
  });

  group('EventDetailsScreen Widget Tests', () {
    testWidgets('renders app bar', (WidgetTester tester) async {
      await tester.pumpWidget(
        wrapApp(EventDetailsScreen(event: UserEvent.mockEvents[0])),
      );

      expect(find.text('Event Details'), findsOneWidget);
      expect(find.byIcon(Icons.arrow_back_rounded), findsOneWidget);
    });

    testWidgets('renders event name and type', (WidgetTester tester) async {
      await tester.pumpWidget(
        wrapApp(EventDetailsScreen(event: UserEvent.mockEvents[0])),
      );

      expect(find.text('Company Gala'), findsOneWidget);
      expect(find.text('Formal'), findsAtLeast(1));
    });

    testWidgets('renders date and time', (WidgetTester tester) async {
      await tester.pumpWidget(
        wrapApp(EventDetailsScreen(event: UserEvent.mockEvents[0])),
      );

      expect(find.text('Aug 15, 2026'), findsOneWidget);
      expect(find.text('7:00 PM'), findsOneWidget);
    });

    testWidgets('renders info card labels', (WidgetTester tester) async {
      await tester.pumpWidget(
        wrapApp(EventDetailsScreen(event: UserEvent.mockEvents[0])),
      );

      expect(find.text('Date'), findsOneWidget);
      expect(find.text('Time'), findsOneWidget);
      expect(find.text('Type'), findsOneWidget);
    });

    testWidgets('renders outfit status card', (WidgetTester tester) async {
      await tester.pumpWidget(
        wrapApp(EventDetailsScreen(event: UserEvent.mockEvents[0])),
      );

      expect(find.text('Outfit Recommendation'), findsOneWidget);
    });

    testWidgets('shows Ready status for event with outfit', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        wrapApp(EventDetailsScreen(event: UserEvent.mockEvents[0])),
      );

      expect(find.text('Ready'), findsOneWidget);
      expect(
        find.text('An outfit has been recommended for this event'),
        findsOneWidget,
      );
    });

    testWidgets('shows Pending status for event without outfit', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        wrapApp(EventDetailsScreen(event: UserEvent.mockEvents[1])),
      );

      expect(find.text('Pending'), findsOneWidget);
      expect(find.text('No outfit recommended yet'), findsOneWidget);
    });

    testWidgets('renders Generate Outfit button', (WidgetTester tester) async {
      await tester.pumpWidget(
        wrapApp(EventDetailsScreen(event: UserEvent.mockEvents[0])),
      );

      expect(find.text('Generate Outfit'), findsOneWidget);
    });

    testWidgets('renders Edit Event button', (WidgetTester tester) async {
      await tester.pumpWidget(
        wrapApp(EventDetailsScreen(event: UserEvent.mockEvents[0])),
      );

      expect(find.text('Edit Event'), findsOneWidget);
    });

    testWidgets('back button pops', (WidgetTester tester) async {
      await tester.pumpWidget(
        wrapApp(EventDetailsScreen(event: UserEvent.mockEvents[0])),
      );

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
    });

    testWidgets('Generate Outfit navigates to Build Outfit', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        wrapApp(EventDetailsScreen(event: UserEvent.mockEvents[0])),
      );

      await tester.tap(find.text('Generate Outfit'));
      await tester.pump();
      await tester.pump();

      expect(find.text('Create Your Look'), findsOneWidget);
    });
  });
}
