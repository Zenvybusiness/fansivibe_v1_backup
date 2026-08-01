import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/app_router.dart';
import 'package:fansivibe/features/home/presentation/first_time_light_path_home_screen.dart';
import 'package:fansivibe/shared/theme/fansivibe_theme.dart';

GoRouter _testRouter(Widget home) {
  return GoRouter(
    initialLocation: '/test',
    routes: [
      GoRoute(path: '/test', builder: (context, state) => home),
      ...appRoutes,
    ],
  );
}

Widget _wrap(Widget home) {
  return MaterialApp.router(
    theme: FansivibeTheme.darkTheme,
    routerConfig: _testRouter(home),
  );
}

void main() {
  group('FirstTimeLightPathHomeScreen', () {
    testWidgets('renders greeting, analysis CTA, preview look and quote', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        _wrap(const FirstTimeLightPathHomeScreen(vibeName: 'minimalist')),
      );
      await tester.pumpAndSettle();

      expect(find.text('WELCOME TO FANSIVIBE'), findsOneWidget);
      expect(find.text('Your style journey\nbegins today.'), findsOneWidget);
      expect(find.text('YOUR ANALYSIS IS WAITING'), findsOneWidget);
      expect(find.text('Unlock your Style DNA'), findsOneWidget);
      expect(find.text('Analyze My Style'), findsOneWidget);
      expect(find.text('A PREVIEW OF WHAT\'S WAITING'), findsOneWidget);
      expect(find.text('Modern Minimalist'), findsOneWidget);
      expect(find.text('Try This Look'), findsOneWidget);
      expect(find.text('EXPLORE THE ATELIER'), findsOneWidget);
      expect(find.text('AI IS READY WHEN YOU ARE'), findsOneWidget);
    });

    testWidgets('reflects the selected style direction', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        _wrap(const FirstTimeLightPathHomeScreen(vibeName: 'classic')),
      );
      await tester.pumpAndSettle();

      expect(find.text('STYLE DIRECTION'), findsOneWidget);
      expect(find.text('Classic'), findsOneWidget);
      expect(
        find.text('Timeless tailoring, refined silhouettes, investment pieces'),
        findsOneWidget,
      );
    });

    testWidgets('shows open state when no vibe was chosen', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_wrap(const FirstTimeLightPathHomeScreen()));
      await tester.pumpAndSettle();

      expect(find.text('Open to Everything'), findsOneWidget);
      expect(
        find.text('You haven\'t chosen a direction yet — and that\'s fine.'),
        findsOneWidget,
      );
    });

    testWidgets('Analyze My Style navigates to camera permission', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        _wrap(const FirstTimeLightPathHomeScreen(vibeName: 'bold')),
      );
      await tester.pumpAndSettle();

      final scrollable = find.byType(SingleChildScrollView).first;
      await tester.dragUntilVisible(
        find.text('Analyze My Style'),
        scrollable,
        const Offset(0, -200),
        maxIteration: 20,
      );

      await tester.tap(find.text('Analyze My Style'));
      await tester.pumpAndSettle();

      expect(find.text('One Photo Is\nAll It Takes'), findsOneWidget);
    });
  });
}
