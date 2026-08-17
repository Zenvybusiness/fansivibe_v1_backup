import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/app_router.dart';
import 'package:fansivibe/features/onboarding/presentation/screens/entry_screen.dart';
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
  group('EntryScreen', () {
    testWidgets(
      'renders without LateInitializationError when breathing animation is active',
      (WidgetTester tester) async {
        await tester.pumpWidget(_wrap(const EntryScreen()));
        await tester.pump(const Duration(milliseconds: 300));
        await tester.pump(const Duration(milliseconds: 300));

        expect(tester.takeException(), isNull);
        expect(find.text('FANSIVIBE'), findsOneWidget);
        expect(find.text('Analyze My Style'), findsOneWidget);
        expect(find.text('Explore Without Scanning'), findsOneWidget);
      },
    );

    testWidgets('breathing mirror animation keeps advancing frames', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_wrap(const EntryScreen()));
      await tester.pump(const Duration(milliseconds: 100));
      await tester.pump(const Duration(milliseconds: 100));

      expect(tester.takeException(), isNull);
      expect(find.text('Your best style,\ndiscovered by AI.'), findsOneWidget);
    });
  });
}