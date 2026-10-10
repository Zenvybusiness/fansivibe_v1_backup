import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/onboarding/presentation/screens/ai_analysis_screen.dart';
import 'package:fansivibe/features/onboarding/presentation/screens/photo_capture_screen.dart';
import 'package:fansivibe/features/onboarding/presentation/screens/your_analysis_screen.dart';
import 'package:fansivibe/features/outfit_scan/data/outfit_scan_client.dart';
import 'package:fansivibe/features/wardrobe/data/garment_client.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:fansivibe/shared/utils/pending_auth_intent.dart';

/// Guest AI Preview for Analyze My Outfit.
///
/// The onboarding guest photo now runs one real pass over the existing
/// unauthenticated ephemeral endpoints (outfit + garment, in parallel) and
/// the result screen renders only the fields those backends returned.
/// Nothing is fabricated, and the account-conversion journey is preserved.
///
/// 1. A valid guest photo reaches the preview with genuine response fields.
/// 2. Missing/empty attributes are omitted, never defaulted or sampled.
/// 3. A rejected photo shows the validation message + retake (no success).
/// 4. Loading, failure, and retry states behave (retry re-runs, no stale).
/// 5. Create Account records the resume intent; Retake clears the stash.

/// A real 1x1 PNG so Image.memory can decode it in tests.
Uint8List _png() => base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
);

Map<String, dynamic> _outfitSnapshot() => {
  'appearance': {
    'faceShape': 'oval',
    'skinTone': '',
    'bodyType': '',
    'styleType': '',
    'sourceRunId': 'ephemeral-test-id',
  },
  'confidence': 0.83,
  'needs_more_data': true,
  'recommendations': {
    'top': {
      'id': 'textured_quiff',
      'name': 'Textured Quiff',
      'description': 'A test recommendation.',
      'matchScore': 0.94,
      'reasons': ['Suits an oval face'],
      'stylingTips': 'Tips',
      'maintenance': 'Low',
      'bestFor': 'Oval',
    },
    'alternatives': <dynamic>[],
  },
};

Map<String, dynamic> _garmentSnapshot() => {
  'category': 'tops',
  'subcategory': null,
  'color': 'light blue',
  'pattern': null,
  'material': 'cotton',
  'style': null,
  'fit': null,
  'confidence': 0.84,
  'needs_review': false,
  'sourceRunId': 'ephemeral-test-id',
};

http.Response _ok(Map<String, dynamic> body) =>
    http.Response(jsonEncode(body), 200);

http.Response _unprocessable(String reason) => http.Response(
  jsonEncode({
    'error': {
      'code': 'VALIDATION_ERROR',
      'message': 'validation failed',
      'details': {
        'field_errors': <Map<String, String>>[
          {'field': 'image', 'error': reason},
        ],
      },
    },
  }),
  422,
);

/// Mock transport answering the two ephemeral endpoints independently.
MockClient _ephemeralTransport({
  http.Response Function()? outfit,
  http.Response Function()? garment,
}) {
  return MockClient((request) async {
    final path = request.url.path;
    if (path.endsWith('/v1/analysis/outfit/ephemeral')) {
      return (outfit ?? () => _ok(_outfitSnapshot()))();
    }
    if (path.endsWith('/v1/analysis/garment/ephemeral')) {
      return (garment ?? () => _ok(_garmentSnapshot()))();
    }
    return http.Response('not found', 404);
  });
}

GoRouter _router({required MockClient transport}) {
  OutfitScanClient outfit() => OutfitScanClient(client: transport);
  GarmentClient garm() => GarmentClient(client: transport);
  return GoRouter(
    initialLocation: '/capture',
    routes: [
      GoRoute(
        path: '/capture',
        builder: (context, state) => PhotoCaptureScreen(
          pickImage: (_) async =>
              XFile.fromData(_png(), name: 'g.jpg', mimeType: 'image/jpeg'),
        ),
      ),
      GoRoute(
        path: '/analysis',
        name: RouteNames.aiAnalysis,
        builder: (context, state) {
          final extra = state.extra as Map<String, dynamic>?;
          return AiAnalysisScreen(
            imageBytes: extra?['imageBytes'] as Uint8List?,
            outfitClient: outfit(),
            garmentClient: garm(),
          );
        },
      ),
      GoRoute(
        path: '/result',
        name: RouteNames.yourAnalysis,
        builder: (context, state) {
          final extra = state.extra as Map<String, dynamic>?;
          return YourAnalysisScreen(
            imageBytes: extra?['imageBytes'] as Uint8List?,
            outfitSnapshot: extra?['outfitSnapshot'] as Map<String, dynamic>?,
            garmentSnapshot: extra?['garmentSnapshot'] as Map<String, dynamic>?,
            outfitFailure: extra?['outfitFailure'] as String?,
            garmentFailure: extra?['garmentFailure'] as String?,
          );
        },
      ),
      GoRoute(
        path: '/photo-capture',
        name: RouteNames.photoCapture,
        builder: (context, state) =>
            const Scaffold(body: Text('capture-marker')),
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

  group('Guest preview (Analyze My Outfit)', () {
    testWidgets('valid guest photo reaches a genuine preview', (
      WidgetTester tester,
    ) async {
      expect(AuthSession.isAuthenticated, isFalse);
      await tester.pumpWidget(
        MaterialApp.router(
          routerConfig: _router(transport: _ephemeralTransport()),
        ),
      );
      await tester.pumpAndSettle();

      await _tapVisible(tester, 'Choose from Gallery');
      await _tapVisible(tester, 'Continue');
      // Ephemeral pass runs on the analysis step, then forwards.
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      expect(find.text('Your Style Preview'), findsOneWidget);
      // Genuine garment fields, verbatim from the mocked backend.
      expect(find.text('Garment: Tops'), findsOneWidget);
      expect(find.text('Color: Light blue'), findsOneWidget);
      expect(find.text('Material: Cotton'), findsOneWidget);
      // Genuine face observation.
      expect(find.text('Face shape: Oval'), findsOneWidget);
      // One styling direction from the real engine snapshot.
      expect(find.text('Styling direction: Textured Quiff'), findsOneWidget);
      expect(find.text('Suits an oval face'), findsOneWidget);
      // Real confidence, honestly flagged as an early preview.
      expect(find.textContaining('Analysis confidence: 83%'), findsOneWidget);
      // The photo itself travels with the preview.
      expect(find.byType(Image), findsWidgets);
      // Stashed for a later Save → sign-in replay (existing slot).
      final pending = peekPendingEphemeralResult();
      expect(pending, isNotNull);
      expect(pending!.feature, EphemeralFeature.outfit);
      // Conversion CTA is present; legacy actions keep working.
      expect(find.text('Create Account'), findsOneWidget);
      expect(find.text('Continue Without Account'), findsOneWidget);
      expect(find.text('Save My Progress'), findsOneWidget);
      expect(find.text('Retake Photo'), findsOneWidget);
    });

    testWidgets('missing attributes are omitted, never fabricated', (
      WidgetTester tester,
    ) async {
      final transport = _ephemeralTransport(
        outfit: () => _ok({
          'appearance': {
            'faceShape': '',
            'skinTone': '',
            'bodyType': '',
            'styleType': '',
            'sourceRunId': 'ephemeral-test-id',
          },
          'confidence': 0.4,
          'needs_more_data': true,
          'recommendations': <String, dynamic>{},
        }),
        garment: () => _ok({
          'category': null,
          'subcategory': null,
          'color': null,
          'pattern': null,
          'material': null,
          'style': null,
          'fit': null,
          'confidence': 0.5,
          'needs_review': true,
          'sourceRunId': 'ephemeral-test-id',
        }),
      );
      await tester.pumpWidget(
        MaterialApp.router(routerConfig: _router(transport: transport)),
      );
      await tester.pumpAndSettle();

      await _tapVisible(tester, 'Choose from Gallery');
      await _tapVisible(tester, 'Continue');
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      expect(find.text('Your Style Preview'), findsOneWidget);
      // Nothing measurable → plain unavailable notes, no invented values.
      expect(
        find.text('No clear outfit details in this photo.'),
        findsOneWidget,
      );
      expect(
        find.text("Face shape wasn't measurable in this photo."),
        findsOneWidget,
      );
      expect(find.textContaining('Face shape:'), findsNothing);
      expect(find.textContaining('Garment:'), findsNothing);
      expect(find.textContaining('Color:'), findsNothing);
      expect(find.textContaining('Pattern:'), findsNothing);
      expect(find.textContaining('Material:'), findsNothing);
      expect(find.textContaining('Styling direction:'), findsNothing);
      expect(find.text('Not detected'), findsNothing);
    });

    testWidgets('rejected photo shows validation, never a success state', (
      WidgetTester tester,
    ) async {
      final transport = _ephemeralTransport(
        outfit: () => _unprocessable('no_face_detected'),
        garment: () => _unprocessable('no_garment_detected'),
      );
      await tester.pumpWidget(
        MaterialApp.router(routerConfig: _router(transport: transport)),
      );
      await tester.pumpAndSettle();

      await _tapVisible(tester, 'Choose from Gallery');
      await _tapVisible(tester, 'Continue');
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      expect(find.text('Your Style Preview'), findsNothing);
      expect(find.text('Preview unavailable'), findsOneWidget);
      expect(find.textContaining('No face was clearly visible'), findsOneWidget);
      expect(find.text('Try Again'), findsOneWidget);
      expect(find.text('Retake Photo'), findsOneWidget);
      expect(peekPendingEphemeralResult(), isNull);
    });

    testWidgets('partial preview renders what succeeded', (
      WidgetTester tester,
    ) async {
      // Face pass rejected, garment pass genuine: the preview shows the
      // garment facts with an honest face-unavailable note.
      final transport = _ephemeralTransport(
        outfit: () => _unprocessable('no_face_detected'),
      );
      await tester.pumpWidget(
        MaterialApp.router(routerConfig: _router(transport: transport)),
      );
      await tester.pumpAndSettle();

      await _tapVisible(tester, 'Choose from Gallery');
      await _tapVisible(tester, 'Continue');
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      expect(find.text('Your Style Preview'), findsOneWidget);
      expect(find.text('Garment: Tops'), findsOneWidget);
      expect(
        find.text("Face shape wasn't measurable in this photo."),
        findsOneWidget,
      );
      expect(find.text('Preview unavailable'), findsNothing);
    });

    testWidgets('service failure offers retry that re-runs the pass', (
      WidgetTester tester,
    ) async {
      var failing = true;
      final transport = MockClient((request) async {
        if (failing) return http.Response('down', 503);
        final path = request.url.path;
        if (path.endsWith('/v1/analysis/outfit/ephemeral')) {
          return _ok(_outfitSnapshot());
        }
        return _ok(_garmentSnapshot());
      });
      await tester.pumpWidget(
        MaterialApp.router(routerConfig: _router(transport: transport)),
      );
      await tester.pumpAndSettle();

      await _tapVisible(tester, 'Choose from Gallery');
      await _tapVisible(tester, 'Continue');
      await tester.pumpAndSettle();

      expect(find.text('Preview unavailable'), findsOneWidget);
      expect(find.textContaining('unavailable'), findsWidgets);

      // Retry re-runs the live pass (no stale result): now it succeeds.
      failing = false;
      await _tapVisible(tester, 'Try Again');
      await tester.pumpAndSettle();
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      expect(find.text('Your Style Preview'), findsOneWidget);
      expect(find.text('Garment: Tops'), findsOneWidget);
    });

    testWidgets('analysis step shows progress while the pass runs', (
      WidgetTester tester,
    ) async {
      final gate = Completer<http.Response>();
      final transport = MockClient((request) async => gate.future);
      await tester.pumpWidget(
        MaterialApp.router(routerConfig: _router(transport: transport)),
      );
      await tester.pumpAndSettle();

      await _tapVisible(tester, 'Choose from Gallery');
      // Scroll without settling: the pending pass keeps the next screen's
      // progress animation repeating, which never settles by design.
      await tester.scrollUntilVisible(find.text('Continue'), 300.0);
      await tester.pump();
      await tester.tap(find.text('Continue'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));

      expect(tester.takeException(), isNull);
      // Indeterminate progress with honest copy — no fake percentages.
      expect(find.text('Analyzing your style…'), findsOneWidget);
      expect(find.text('Your Style Preview'), findsNothing);

      // Completing the pass forwards to the result (both mock calls
      // share this gate; the outfit-shaped body yields face facts with a
      // garment-unavailable note — still a genuine preview).
      gate.complete(_ok(_outfitSnapshot()));
      await tester.pumpAndSettle();
      expect(find.text('Your Style Preview'), findsOneWidget);
      expect(find.text('Face shape: Oval'), findsOneWidget);
    });

    testWidgets('Create Account records the resume intent', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp.router(
          routerConfig: _router(transport: _ephemeralTransport()),
        ),
      );
      await tester.pumpAndSettle();

      await _tapVisible(tester, 'Choose from Gallery');
      await _tapVisible(tester, 'Continue');
      await tester.pumpAndSettle();
      await _tapVisible(tester, 'Create Account');

      expect(tester.takeException(), isNull);
      expect(find.text('create-account-marker'), findsOneWidget);
      final intent = takePendingAuthIntent();
      expect(intent, isNotNull);
      expect(intent!.action, 'save_progress');
      expect(intent.route, '/home');
      // The preview stash survives for post-auth replay.
      expect(peekPendingEphemeralResult(), isNotNull);
    });

    testWidgets('Retake clears the stashed preview (no stale results)', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp.router(
          routerConfig: _router(transport: _ephemeralTransport()),
        ),
      );
      await tester.pumpAndSettle();

      await _tapVisible(tester, 'Choose from Gallery');
      await _tapVisible(tester, 'Continue');
      await tester.pumpAndSettle();
      expect(peekPendingEphemeralResult(), isNotNull);

      await _tapVisible(tester, 'Retake Photo');

      expect(tester.takeException(), isNull);
      expect(find.text('capture-marker'), findsOneWidget);
      expect(peekPendingEphemeralResult(), isNull);
    });

    testWidgets('legacy handoff without preview data is unchanged', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        const MaterialApp(home: Scaffold(body: YourAnalysisScreen())),
      );
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      expect(find.text('Your Style Preview'), findsNothing);
      expect(find.text('Preview unavailable'), findsNothing);
      expect(
        find.textContaining('Nothing has been analyzed yet'),
        findsOneWidget,
      );
      expect(find.text('Photo ready'), findsOneWidget);
      expect(find.text('Create Account'), findsOneWidget);
      expect(find.text('Continue Without Account'), findsOneWidget);
      expect(find.text('Save My Progress'), findsOneWidget);
      expect(find.text('Retake Photo'), findsOneWidget);
    });
  });
}
