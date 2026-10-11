import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/app/router/app_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/home/presentation/widgets/first_time_home_widgets.dart';
import 'package:fansivibe/features/onboarding/presentation/screens/vibe_select_screen.dart';
import 'package:fansivibe/features/onboarding/presentation/screens/your_analysis_screen.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

/// Regression tests for the new-user Analyze My Style journey correction.
///
/// The style-preference screen requires one deliberate selection: no Skip
/// action, no default, Continue validates before the photo journey. The
/// saved preference drives the Home Today's Look through the existing
/// pipeline; a successful analysis lands on Home. Fakes stand in for
/// routes only — selection state and persistence are real.
GoRouter _vibeRouter({
  required Map<String, dynamic> vibeExtra,
  Map<String, dynamic>? seenExtra,
}) {
  Object? captured;
  return GoRouter(
    initialLocation: '/',
    routes: [
      GoRoute(
        path: '/',
        builder: (context, state) => TextButton(
          onPressed: () => context.pushNamed(
            RouteNames.vibeSelect,
            extra: vibeExtra,
          ),
          child: const Text('open'),
        ),
      ),
      GoRoute(
        path: '/vibe',
        name: RouteNames.vibeSelect,
        builder: (context, state) => const VibeSelectScreen(),
      ),
      GoRoute(
        path: '/camera',
        name: RouteNames.cameraPermission,
        builder: (context, state) {
          captured = state.extra;
          if (seenExtra != null && captured is Map<String, dynamic>) {
            seenExtra.addAll(captured as Map<String, dynamic>);
          }
          return const Scaffold(body: Text('camera-marker'));
        },
      ),
      GoRoute(
        path: '/discover-stub',
        name: RouteNames.discover,
        builder: (context, state) {
          captured = state.extra;
          if (seenExtra != null && captured is Map<String, dynamic>) {
            seenExtra.addAll(captured as Map<String, dynamic>);
          }
          return const Scaffold(body: Text('discover-marker'));
        },
      ),
    ],
  );
}

Future<void> resetEnv() async {
  SharedPreferences.setMockInitialValues({});
  LocalStorage.init(prefs: await SharedPreferences.getInstance());
  AuthSession.resetForTest();
  await AuthSession.clearSession();
}

Future<void> openVibe(
  WidgetTester tester,
  Map<String, dynamic> extra,
) async {
  await tester.pumpWidget(
    MaterialApp.router(
      routerConfig: _vibeRouter(vibeExtra: extra, seenExtra: _seen),
    ),
  );
  await tester.pumpAndSettle();
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
}

Future<void> tapVisible(WidgetTester tester, String label) async {
  // The vibe grid is taller than the default viewport and owns its own
  // Scrollable: tests run on a tall viewport instead so every action is
  // directly tappable with no scroll choreography.
  tester.view.physicalSize = const Size(800.0, 3000.0);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  await tester.pumpAndSettle();
  final finder = find.text(label);
  await tester.tap(finder);
  await tester.pumpAndSettle();
}

final Map<String, dynamic> _seen = {};

void main() {
  setUp(() async {
    await resetEnv();
    _seen.clear();
  });

  group('Analyze path requires a deliberate selection', () {
    const analyzeExtra = {'photoPath': true, 'vibeRequired': true};

    testWidgets('no Skip action is offered', (tester) async {
      await tester.pumpWidget(
        MaterialApp.router(
          routerConfig: _vibeRouter(vibeExtra: analyzeExtra, seenExtra: _seen),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();

      expect(find.text('Continue'), findsOneWidget);
      expect(find.text('Skip'), findsNothing);
      expect(find.text("I'm not sure — skip for now"), findsNothing);
      expect(find.text('Skip for now'), findsNothing);
    });

    testWidgets('Continue without a selection shows validation and stays',
        (tester) async {
      await openVibe(tester, analyzeExtra);

      await tapVisible(tester, 'Continue');

      expect(find.text('Select a style to continue'), findsOneWidget);
      expect(find.byType(VibeSelectScreen), findsOneWidget);
      expect(find.text('camera-marker'), findsNothing);
      expect(LocalStorage.vibe, isNull);
    });

    testWidgets('valid selection continues with the vibe saved', (
      tester,
    ) async {
      final router = _vibeRouter(vibeExtra: analyzeExtra, seenExtra: _seen);
      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      await tester.pumpAndSettle();
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();

      await tapVisible(tester, 'Minimalist');
      await tapVisible(tester, 'Continue');

      expect(find.text('camera-marker'), findsOneWidget);
      expect(LocalStorage.vibe, 'minimalist');
      expect(_seen['vibe'], 'minimalist');
    });

    testWidgets('deselecting returns to the unselected state (no default)',
        (tester) async {
      await openVibe(tester, analyzeExtra);

      await tapVisible(tester, 'Minimalist');
      await tapVisible(tester, 'Minimalist');
      await tapVisible(tester, 'Continue');

      expect(find.text('Select a style to continue'), findsOneWidget);
      expect(find.byType(VibeSelectScreen), findsOneWidget);
      expect(LocalStorage.vibe, isNull);
    });
  });

  group('optional paths keep working without a selection', () {
    testWidgets('explore Continue without selection still lands on Discover',
        (tester) async {
      const exploreExtra = {'photoPath': false, 'vibeRequired': false};
      final router = _vibeRouter(vibeExtra: exploreExtra, seenExtra: _seen);
      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      await tester.pumpAndSettle();
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();

      await tapVisible(tester, 'Continue');

      expect(find.text('Select a style to continue'), findsNothing);
      expect(find.text('discover-marker'), findsOneWidget);
      expect(LocalStorage.vibe, isNull);
    });

    testWidgets('explore selection is saved and carried to Discover',
        (tester) async {
      const exploreExtra = {'photoPath': false, 'vibeRequired': false};
      final router = _vibeRouter(vibeExtra: exploreExtra, seenExtra: _seen);
      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      await tester.pumpAndSettle();
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();

      await tapVisible(tester, 'Classic');
      await tapVisible(tester, 'Continue');

      expect(find.text('discover-marker'), findsOneWidget);
      expect(LocalStorage.vibe, 'classic');
      expect(_seen['vibe'], 'classic');
    });
  });

  group('entry routes Analyze into the required selection', () {
    testWidgets('Analyze My Style opens the vibe screen unselected',
        (tester) async {
      await tester.pumpWidget(
        MaterialApp.router(
          routerConfig: GoRouter(
            initialLocation: '/entry',
            routes: appRoutes,
          ),
        ),
      );
      await tester.pump(const Duration(milliseconds: 300));
      // Tall viewport: the entry CTA sits below the fold on the default
      // size. Fixed pumps only below: the entry breathing animation
      // repeats, and the vibe entrance completes within the budget.
      tester.view.physicalSize = const Size(800.0, 3000.0);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      await tester.pump(const Duration(milliseconds: 300));
      await tester.tap(find.text('Analyze My Style'));
      // Bounded fixed pumps (never settle): the entry breathing animation
      // repeats, while navigation plus the 800ms vibe entrance completes
      // well within this budget.
      for (var i = 0; i < 12; i++) {
        await tester.pump(const Duration(milliseconds: 200));
      }

      // Style options render with nothing preselected and no Skip.
      expect(find.text('Minimalist'), findsOneWidget);
      expect(find.text('Classic'), findsOneWidget);
      expect(find.text('Continue'), findsOneWidget);
      expect(find.text("I'm not sure — skip for now"), findsNothing);
    });
  });

  group('Today\'s Look follows the saved preference', () {
    test('selected vibe maps to its curated look', () {
      expect(
        getCuratedLookForVibe('minimalist').title,
        'Modern Minimalist',
      );
      expect(getCuratedLookForVibe('classic').title, 'Timeless Tailored');
    });

    test('missing vibe falls back to the honest default look', () {
      expect(getCuratedLookForVibe(null).title, 'Relaxed Streetwear');
      expect(LocalStorage.vibe, isNull);
    });
  });

  group('successful analysis lands on Home', () {
    GoRouter homeRouter(Map<String, dynamic> seen) {
      return GoRouter(
        initialLocation: '/your-analysis',
        routes: [
          GoRoute(
            path: '/your-analysis',
            builder: (context, state) => const YourAnalysisScreen(),
          ),
          GoRoute(
            path: '/home-stub',
            name: RouteNames.home,
            builder: (context, state) {
              final extra = state.extra;
              if (extra is Map<String, dynamic>) seen.addAll(extra);
              return const Scaffold(body: Text('home-marker'));
            },
          ),
          GoRoute(
            path: '/create-account',
            name: RouteNames.createAccount,
            builder: (context, state) =>
                const Scaffold(body: Text('create-account-marker')),
          ),
        ],
      );
    }

    Future<void> tapContinue(WidgetTester tester, String label) async {
      final finder = find.text(label);
      await tester.scrollUntilVisible(finder, 300.0);
      await tester.pumpAndSettle();
      await tester.tap(finder);
      await tester.pumpAndSettle();
    }

    testWidgets('Continue Without Account reaches Home with the vibe',
        (tester) async {
      LocalStorage.vibe = 'minimalist';
      final seen = <String, dynamic>{};
      await tester.pumpWidget(
        MaterialApp.router(routerConfig: homeRouter(seen)),
      );
      await tester.pumpAndSettle();

      await tapContinue(tester, 'Continue Without Account');

      expect(tester.takeException(), isNull);
      expect(find.text('home-marker'), findsOneWidget);
      expect(LocalStorage.savedLocally, isTrue);
      expect(LocalStorage.onboardingComplete, isTrue);
      expect(seen['vibe'], 'minimalist');
    });

    testWidgets('conversion buttons still route to account creation',
        (tester) async {
      final seen = <String, dynamic>{};
      await tester.pumpWidget(
        MaterialApp.router(routerConfig: homeRouter(seen)),
      );
      await tester.pumpAndSettle();

      await tapContinue(tester, 'Create Account');

      expect(tester.takeException(), isNull);
      expect(find.text('create-account-marker'), findsOneWidget);
    });
  });
}
