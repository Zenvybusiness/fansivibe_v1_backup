import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/onboarding/presentation/screens/photo_capture_screen.dart';
import 'package:fansivibe/features/onboarding/presentation/screens/your_analysis_screen.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

/// Regression tests for the Analyze My Style result handoff (guest).
///
/// 1. The screen must never render fabricated analysis data (no mock
///    score, palette, or insights posing as a real result).
/// 2. "Retake Photo" must open a fresh capture screen — never the
///    AiAnalysis processing timer (the old pop() loop).
/// 3. "Save My Progress" and "Continue Without Account" keep working.
GoRouter _router() {
  return GoRouter(
    initialLocation: '/your-analysis',
    routes: [
      GoRoute(
        path: '/your-analysis',
        builder: (context, state) => const YourAnalysisScreen(),
      ),
      GoRoute(
        path: '/photo-capture',
        name: RouteNames.photoCapture,
        builder: (context, state) => const PhotoCaptureScreen(),
      ),
      GoRoute(
        path: '/analysis',
        name: RouteNames.aiAnalysis,
        builder: (context, state) =>
            const Scaffold(body: Text('analysis-marker')),
      ),
      GoRoute(
        path: '/create-account',
        name: RouteNames.createAccount,
        builder: (context, state) =>
            const Scaffold(body: Text('create-account-marker')),
      ),
      GoRoute(
        path: '/stylist',
        name: RouteNames.stylist,
        builder: (context, state) =>
            const Scaffold(body: Text('stylist-marker')),
      ),
    ],
  );
}

Future<void> _tapVisible(WidgetTester tester, String label) async {
  final finder = find.text(label);
  await tester.scrollUntilVisible(finder, 300.0);
  await tester.pumpAndSettle();
  await tester.tap(finder);
  await tester.pumpAndSettle();
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    LocalStorage.init(prefs: await SharedPreferences.getInstance());
    AuthSession.resetForTest();
  });

  tearDown(() async {
    AuthSession.resetForTest();
    await AuthSession.clearSession();
    LocalStorage.resetForTest();
  });

  group('YourAnalysisScreen (guest handoff)', () {
    testWidgets('shows honest handoff state, never mock analysis data',
        (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp.router(routerConfig: _router()),
      );
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      // Honest state.
      expect(find.text('Photo ready'), findsOneWidget);
      expect(find.text('Continue Without Account'), findsOneWidget);
      expect(find.text('Save My Progress'), findsOneWidget);
      expect(find.text('Retake Photo'), findsOneWidget);
      // Mock analysis data must be gone.
      expect(find.text('Style Score'), findsNothing);
      expect(find.text('Strong Silhouette'), findsNothing);
      expect(find.text('Color Harmony'), findsNothing);
      expect(find.text('Refinement Tip'), findsNothing);
      expect(find.text('AI Insights'), findsNothing);
      expect(find.text('Appearance Intelligence'), findsNothing);
    });

    testWidgets('Retake Photo opens capture, not processing', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp.router(routerConfig: _router()),
      );
      await tester.pumpAndSettle();

      await _tapVisible(tester, 'Retake Photo');

      expect(tester.takeException(), isNull);
      // Fresh capture screen (idle Take Photo), not the timer.
      expect(find.byType(PhotoCaptureScreen), findsOneWidget);
      expect(find.text('Take Photo'), findsOneWidget);
      expect(find.text('analysis-marker'), findsNothing);
    });

    testWidgets('Save My Progress still routes to account creation', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp.router(routerConfig: _router()),
      );
      await tester.pumpAndSettle();

      await _tapVisible(tester, 'Save My Progress');

      expect(tester.takeException(), isNull);
      expect(find.text('create-account-marker'), findsOneWidget);
    });

    testWidgets('Continue Without Account still reaches the Stylist tab', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp.router(routerConfig: _router()),
      );
      await tester.pumpAndSettle();

      await _tapVisible(tester, 'Continue Without Account');

      expect(tester.takeException(), isNull);
      expect(find.text('stylist-marker'), findsOneWidget);
      expect(LocalStorage.savedLocally, isTrue);
      expect(LocalStorage.onboardingComplete, isTrue);
    });
  });
}
