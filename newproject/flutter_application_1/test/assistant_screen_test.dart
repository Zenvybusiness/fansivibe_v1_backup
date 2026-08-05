import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

import 'package:fansivibe/app/app.dart';
import 'package:fansivibe/app/router/app_router.dart';
import 'package:fansivibe/features/assistant/domain/assistant_service.dart';

Widget _app({AssistantService? service}) {
  return FansivibeApp(
    router: GoRouter(initialLocation: '/assistant', routes: appRoutes),
  );
}

void main() {
  testWidgets('renders empty state with suggestion prompts', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(_app());

    expect(find.text('Your AI stylist'), findsOneWidget);
    expect(find.text('What should I wear to a date?'), findsOneWidget);
    expect(find.text('Grooming tips'), findsOneWidget);
  });

  testWidgets('typing and sending a message produces an assistant reply', (
    WidgetTester tester,
  ) async {
    final service = AssistantService();
    await tester.pumpWidget(_app(service: service));
    await tester.pump();

    await tester.enterText(find.byType(TextField), 'hello');
    await tester.tap(find.byIcon(Icons.send_rounded));
    await tester.pumpAndSettle();

    expect(find.text('hello'), findsOneWidget);
    expect(find.textContaining('stylist'), findsWidgets);
  });

  testWidgets('ambiguous outfit question shows clarification chips', (
    WidgetTester tester,
  ) async {
    final service = AssistantService();
    await tester.pumpWidget(_app(service: service));
    await tester.pump();

    await tester.enterText(find.byType(TextField), 'what should I wear?');
    await tester.tap(find.byIcon(Icons.send_rounded));
    await tester.pumpAndSettle();

    expect(find.textContaining("What's the occasion"), findsOneWidget);
    expect(find.widgetWithText(ActionChip, 'Office'), findsOneWidget);
  });

  testWidgets('tapping a clarification chip resolves to an outfit card', (
    WidgetTester tester,
  ) async {
    final service = AssistantService();
    await tester.pumpWidget(_app(service: service));
    await tester.pump();

    await tester.enterText(find.byType(TextField), 'what should I wear?');
    await tester.tap(find.byIcon(Icons.send_rounded));
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(ActionChip, 'Date'));
    await tester.pumpAndSettle();

    expect(find.textContaining('For date'), findsOneWidget);
    expect(find.text('Date Night Refined'), findsOneWidget);
  });

  testWidgets('card Open action navigates to the outfit builder', (
    WidgetTester tester,
  ) async {
    final service = AssistantService();
    await tester.pumpWidget(_app(service: service));
    await tester.pump();

    await tester.enterText(
      find.byType(TextField),
      'suggest an outfit for work',
    );
    await tester.tap(find.byIcon(Icons.send_rounded));
    await tester.pumpAndSettle();

    expect(find.text('Refined Office Ensemble'), findsOneWidget);

    await tester.tap(find.text('Open'));
    await tester.pumpAndSettle();

    expect(find.text('Create Your Look'), findsOneWidget);
  });

  testWidgets('empty suggestion prompt triggers a reply', (
    WidgetTester tester,
  ) async {
    final service = AssistantService();
    await tester.pumpWidget(_app(service: service));
    await tester.pump();

    await tester.tap(find.text('Show my wardrobe'));
    await tester.pumpAndSettle();

    expect(find.textContaining('Here\u2019s what I know'), findsOneWidget);
  });

  testWidgets(
    'navigation from the pushed assistant does not duplicate shell page keys',
    (WidgetTester tester) async {
      await tester.pumpWidget(
        FansivibeApp(
          router: GoRouter(initialLocation: '/home', routes: appRoutes),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.byType(FloatingActionButton));
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField), 'open my wardrobe');
      await tester.tap(find.byIcon(Icons.send_rounded));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Open My Wardrobe'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));

      expect(find.text('My Wardrobe'), findsWidgets);
      expect(tester.takeException(), isNull);
    },
  );
}
