import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/onboarding/presentation/screens/photo_capture_screen.dart';
import 'package:fansivibe/features/onboarding/presentation/screens/your_analysis_screen.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

/// Regression tests for the Analyze My Style result handoff (guest).
///
/// 1. The screen must never render fabricated analysis data (no mock
///    score, palette, or insights posing as a real result).
/// 2. "Retake Photo" must open a fresh capture screen — never the
///    AiAnalysis processing timer (the old pop() loop).
/// 3. "Sign In to Continue" and "Continue Without Account" keep working:
///    conversion still routes to account creation, while continuing lands
///    on the Home experience (Today's Look via the persisted vibe).
Object? _seenExtra;

GoRouter _router({Widget? resultScreen}) {
  return GoRouter(
    initialLocation: '/your-analysis',
    routes: [
      GoRoute(
        path: '/your-analysis',
        builder: (context, state) => resultScreen ?? const YourAnalysisScreen(),
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
        path: '/home',
        name: RouteNames.home,
        builder: (context, state) {
          _seenExtra = state.extra;
          return const Scaffold(body: Text('home-marker'));
        },
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
    testWidgets('shows honest handoff state, never mock analysis data', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp.router(routerConfig: _router()));
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      // Honest state.
      expect(find.text('Photo ready'), findsOneWidget);
      expect(find.text('Continue Without Account'), findsOneWidget);
      expect(find.text('Sign In to Continue'), findsOneWidget);
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
      await tester.pumpWidget(MaterialApp.router(routerConfig: _router()));
      await tester.pumpAndSettle();

      await _tapVisible(tester, 'Retake Photo');

      expect(tester.takeException(), isNull);
      // Fresh capture screen (idle Take Photo), not the timer.
      expect(find.byType(PhotoCaptureScreen), findsOneWidget);
      expect(find.text('Take Photo'), findsOneWidget);
      expect(find.text('analysis-marker'), findsNothing);
    });

    testWidgets('Sign In to Continue routes to account creation', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp.router(routerConfig: _router()));
      await tester.pumpAndSettle();

      await _tapVisible(tester, 'Sign In to Continue');

      expect(tester.takeException(), isNull);
      expect(find.text('create-account-marker'), findsOneWidget);
    });

    testWidgets('Continue Without Account reaches Home with the vibe', (
      WidgetTester tester,
    ) async {
      _seenExtra = null;
      LocalStorage.vibe = 'minimalist';
      await tester.pumpWidget(MaterialApp.router(routerConfig: _router()));
      await tester.pumpAndSettle();

      await _tapVisible(tester, 'Continue Without Account');

      expect(tester.takeException(), isNull);
      expect(find.text('home-marker'), findsOneWidget);
      expect(LocalStorage.savedLocally, isTrue);
      expect(LocalStorage.onboardingComplete, isTrue);
      expect((_seenExtra as Map<String, dynamic>?)?['vibe'], 'minimalist');
    });

    testWidgets('Continue Without Account reports no cache without a preview', (
      WidgetTester tester,
    ) async {
      _seenExtra = null;
      await tester.pumpWidget(MaterialApp.router(routerConfig: _router()));
      await tester.pumpAndSettle();

      await _tapVisible(tester, 'Continue Without Account');

      expect(tester.takeException(), isNull);
      expect(find.text('home-marker'), findsOneWidget);
      expect(
        (_seenExtra as Map<String, dynamic>?)?['analysis_cached'],
        isFalse,
      );
    });

    testWidgets('Continue Without Account reports no cache after a failure', (
      WidgetTester tester,
    ) async {
      _seenExtra = null;
      await tester.pumpWidget(
        MaterialApp.router(
          routerConfig: _router(
            resultScreen: const YourAnalysisScreen(
              outfitFailure: 'no_face_detected',
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Preview unavailable'), findsOneWidget);
      await _tapVisible(tester, 'Continue Without Account');

      expect(tester.takeException(), isNull);
      expect(find.text('home-marker'), findsOneWidget);
      expect(
        (_seenExtra as Map<String, dynamic>?)?['analysis_cached'],
        isFalse,
      );
    });

    testWidgets(
      'Continue Without Account reports a cache when the preview is stashed',
      (WidgetTester tester) async {
        _seenExtra = null;
        stashPendingEphemeralResult(
          feature: EphemeralFeature.outfit,
          snapshot: <String, dynamic>{
            'appearance': <String, dynamic>{'faceShape': 'oval'},
          },
        );
        await tester.pumpWidget(
          MaterialApp.router(
            routerConfig: _router(
              resultScreen: YourAnalysisScreen(
                outfitSnapshot: <String, dynamic>{
                  'appearance': <String, dynamic>{'faceShape': 'oval'},
                },
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();

        expect(find.text('Your Style Preview'), findsOneWidget);
        await _tapVisible(tester, 'Continue Without Account');

        expect(tester.takeException(), isNull);
        expect(find.text('home-marker'), findsOneWidget);
        expect(
          (_seenExtra as Map<String, dynamic>?)?['analysis_cached'],
          isTrue,
        );
      },
    );

    testWidgets('Continue Without Account ignores a malformed outfit stash', (
      WidgetTester tester,
    ) async {
      _seenExtra = null;
      stashPendingEphemeralResult(
        feature: EphemeralFeature.outfit,
        snapshot: <String, dynamic>{
          'appearance': 'not-a-map',
          'garment': <String, dynamic>{},
        },
      );
      await tester.pumpWidget(
        MaterialApp.router(
          routerConfig: _router(
            resultScreen: YourAnalysisScreen(
              outfitSnapshot: <String, dynamic>{
                'appearance': <String, dynamic>{'faceShape': 'oval'},
              },
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(peekPendingEphemeralResult(), isNotNull);
      await _tapVisible(tester, 'Continue Without Account');

      expect(tester.takeException(), isNull);
      expect(find.text('home-marker'), findsOneWidget);
      expect(
        (_seenExtra as Map<String, dynamic>?)?['analysis_cached'],
        isFalse,
      );
    });

    testWidgets('no-photo handoff clears an older outfit stash', (
      WidgetTester tester,
    ) async {
      _seenExtra = null;
      stashPendingEphemeralResult(
        feature: EphemeralFeature.outfit,
        snapshot: <String, dynamic>{
          'appearance': <String, dynamic>{'faceShape': 'oval'},
        },
      );
      await tester.pumpWidget(MaterialApp.router(routerConfig: _router()));
      await tester.pumpAndSettle();

      expect(peekPendingEphemeralResult(), isNull);
      expect(
        find.textContaining('Nothing has been analyzed yet'),
        findsOneWidget,
      );
      await _tapVisible(tester, 'Continue Without Account');

      expect(tester.takeException(), isNull);
      expect(find.text('home-marker'), findsOneWidget);
      expect(
        (_seenExtra as Map<String, dynamic>?)?['analysis_cached'],
        isFalse,
      );
    });

    testWidgets('no-photo handoff preserves an unrelated stashed result', (
      WidgetTester tester,
    ) async {
      _seenExtra = null;
      stashPendingEphemeralResult(
        feature: EphemeralFeature.hairstyle,
        snapshot: <String, dynamic>{'style': 'curtain'},
      );
      await tester.pumpWidget(MaterialApp.router(routerConfig: _router()));
      await tester.pumpAndSettle();

      expect(peekPendingEphemeralResult()?.feature, EphemeralFeature.hairstyle);
      await _tapVisible(tester, 'Continue Without Account');

      expect(tester.takeException(), isNull);
      expect(find.text('home-marker'), findsOneWidget);
      expect(
        (_seenExtra as Map<String, dynamic>?)?['analysis_cached'],
        isFalse,
      );
    });

    testWidgets('route preview without a stash does not claim a cache', (
      WidgetTester tester,
    ) async {
      _seenExtra = null;
      await tester.pumpWidget(
        MaterialApp.router(
          routerConfig: _router(
            resultScreen: YourAnalysisScreen(
              outfitSnapshot: <String, dynamic>{
                'appearance': <String, dynamic>{'faceShape': 'oval'},
              },
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Your Style Preview'), findsOneWidget);
      await _tapVisible(tester, 'Continue Without Account');

      expect(tester.takeException(), isNull);
      expect(find.text('home-marker'), findsOneWidget);
      expect(
        (_seenExtra as Map<String, dynamic>?)?['analysis_cached'],
        isFalse,
      );
    });

    testWidgets('malformed appearance branch does not crash the preview', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp.router(
          routerConfig: _router(
            resultScreen: YourAnalysisScreen(
              outfitSnapshot: <String, dynamic>{
                'appearance': 'not-a-map',
                'garment': <String, dynamic>{'category': 'tops', 'color': 7},
              },
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      expect(find.text('Your Style Preview'), findsOneWidget);
      expect(find.text('Garment: Tops'), findsOneWidget);
      expect(find.textContaining('Color:'), findsNothing);
      expect(
        find.text("Face shape wasn't measurable in this photo."),
        findsOneWidget,
      );
    });

    testWidgets('malformed optional snapshot fields are ignored', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp.router(
          routerConfig: _router(
            resultScreen: YourAnalysisScreen(
              outfitSnapshot: <String, dynamic>{
                'appearance': <String, dynamic>{'faceShape': 42},
                'garment': 'not-a-map',
                'appearance_error': 'not-a-map',
                'garment_error': <String, dynamic>{'reason': 7},
                'recommendations': 'not-a-map',
                'confidence': 'high',
                'needs_more_data': 'yes',
              },
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      expect(find.text('Your Style Preview'), findsOneWidget);
      expect(find.textContaining('Face shape:'), findsNothing);
      expect(find.textContaining('Garment:'), findsNothing);
      expect(
        find.text('No clear outfit details in this photo.'),
        findsOneWidget,
      );
      expect(
        find.text("Face shape wasn't measurable in this photo."),
        findsOneWidget,
      );
    });

    testWidgets('snapshot without a renderable branch shows the empty state', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp.router(
          routerConfig: _router(
            resultScreen: YourAnalysisScreen(
              outfitSnapshot: <String, dynamic>{
                'appearance': 'not-a-map',
                'garment': <String, dynamic>{},
                'appearance_error': 'not-a-map',
              },
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      expect(find.text('Your Style Preview'), findsNothing);
      expect(
        find.textContaining('Nothing has been analyzed yet'),
        findsOneWidget,
      );
    });
  });
}
