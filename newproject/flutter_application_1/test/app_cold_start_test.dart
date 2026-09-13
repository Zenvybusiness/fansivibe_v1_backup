import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/app/router/app_router.dart';
import 'package:fansivibe/features/onboarding/presentation/screens/entry_screen.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/theme/fansivibe_theme.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

/// P0-3 — Flutter cold-start auth initialization.
///
/// Production contract: `main()` initializes SharedPreferences +
/// LocalStorage BEFORE runApp(), so EntryScreen evaluates the restored
/// persistent session on cold start (returning authenticated users reach
/// home; signed-out users stay on entry).
///
/// These tests simulate that cold-start ordering: prefs are seeded, then
/// LocalStorage is initialized (as main() does), and only then is the
/// EntryScreen pumped.

Future<void> _coldStart({Map<String, Object> seed = const {}}) async {
  SharedPreferences.setMockInitialValues(seed);
  LocalStorage.init(prefs: await SharedPreferences.getInstance());
}

Widget _harness() {
  return MaterialApp.router(
    theme: FansivibeTheme.darkTheme,
    routerConfig: GoRouter(
      initialLocation: '/test',
      routes: [
        GoRoute(path: '/test', builder: (_, __) => const EntryScreen()),
        ...appRoutes,
      ],
    ),
  );
}

void main() {
  setUp(() async {
    LocalStorage.resetForTest();
    AuthSession.resetForTest();
  });

  tearDown(() async {
    AuthSession.resetForTest();
    await AuthSession.clearSession();
    LocalStorage.resetForTest();
  });

  group('P0-3 cold start', () {
    test('storage is initialized before first frame (main() contract)', () async {
      await _coldStart();
      expect(LocalStorage.isInitialized, isTrue);
    });

    testWidgets('returning authenticated user reaches home after restart',
        (WidgetTester tester) async {
      await _coldStart(
        seed: const {'auth_token': 'returning-session-token'},
      );
      expect(AuthSession.isAuthenticated, isTrue);

      await tester.pumpWidget(_harness());
      await tester.pump(const Duration(milliseconds: 300));
      // Returning-user redirect fires after the entry animation delay.
      await tester.pump(const Duration(milliseconds: 1500));
      await tester.pump(const Duration(milliseconds: 500));

      expect(tester.takeException(), isNull);
      // Home route reached: entry CTAs are gone.
      expect(find.text('Analyze My Style'), findsNothing);
    });

    testWidgets('onboarded user without token reaches home after restart',
        (WidgetTester tester) async {
      await _coldStart(
        seed: const {'onboarding_complete': true},
      );
      expect(LocalStorage.onboardingComplete, isTrue);

      await tester.pumpWidget(_harness());
      await tester.pump(const Duration(milliseconds: 300));
      await tester.pump(const Duration(milliseconds: 1500));
      await tester.pump(const Duration(milliseconds: 500));

      expect(tester.takeException(), isNull);
      expect(find.text('Analyze My Style'), findsNothing);
    });

    testWidgets('signed-out first launch stays on entry',
        (WidgetTester tester) async {
      await _coldStart();
      expect(AuthSession.isAuthenticated, isFalse);
      expect(LocalStorage.onboardingComplete, isFalse);

      await tester.pumpWidget(_harness());
      await tester.pump(const Duration(milliseconds: 300));
      await tester.pump(const Duration(milliseconds: 1500));
      await tester.pump(const Duration(milliseconds: 500));

      expect(tester.takeException(), isNull);
      expect(find.text('FANSIVIBE'), findsOneWidget);
      expect(find.text('Analyze My Style'), findsOneWidget);
    });
  });
}
