import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/onboarding/presentation/screens/camera_permission_screen.dart';
import 'package:fansivibe/features/onboarding/presentation/screens/photo_capture_screen.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

/// Regression tests for Flow 1 (Analyze My Style capture step).
///
/// Covers the reported bug where "Allow Camera" opened the gallery on
/// desktop web: the camera path must use the live camera controller
/// (unavailable, honestly, under widget tests) and must never invoke the
/// gallery picker, while "Choose from Gallery" keeps using image_picker
/// gallery and forwards real bytes to the real processing route.
GoRouter _router(Widget home, {void Function(Object? extra)? onProcessing}) {
  return GoRouter(
    initialLocation: '/test',
    routes: [
      GoRoute(path: '/test', builder: (context, state) => home),
      GoRoute(
        path: '/photo-capture',
        name: RouteNames.photoCapture,
        builder: (context, state) {
          final extra = state.extra as Map<String, dynamic>?;
          return PhotoCaptureScreen(source: extra?['source'] as String?);
        },
      ),
      GoRoute(
        path: '/processing',
        name: RouteNames.hairstyleProcessing,
        builder: (context, state) {
          onProcessing?.call(state.extra);
          return const Scaffold(body: Text('processing-marker'));
        },
      ),
      GoRoute(
        path: '/analysis',
        name: RouteNames.aiAnalysis,
        builder: (context, state) =>
            const Scaffold(body: Text('analysis-marker')),
      ),
    ],
  );
}

Widget _wrap(Widget home, {void Function(Object? extra)? onProcessing}) {
  return MaterialApp.router(
    routerConfig: _router(home, onProcessing: onProcessing),
  );
}

/// A real 1x1 PNG so Image.memory can decode it in tests.
Uint8List _bytes() => base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
);

/// Scrolls a below-the-fold button into the 800x600 test viewport.
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

  group('PhotoCaptureScreen', () {
    testWidgets('renders Take Photo and Choose from Gallery', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_wrap(const PhotoCaptureScreen()));
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      expect(find.text('Take Photo'), findsOneWidget);
      expect(find.text('Choose from Gallery'), findsOneWidget);
      expect(find.text('Continue'), findsNothing);
    });

    testWidgets('gallery pick shows preview and Continue', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        _wrap(
          PhotoCaptureScreen(
            pickImage: (_) async =>
                XFile.fromData(_bytes(), name: 'g.jpg', mimeType: 'image/jpeg'),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await _tapVisible(tester, 'Choose from Gallery');

      expect(tester.takeException(), isNull);
      expect(find.text('Continue'), findsOneWidget);
      expect(find.text('Retake Photo'), findsOneWidget);
    });

    testWidgets('gallery cancel stays with a truthful message', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        _wrap(const PhotoCaptureScreen(pickImage: _nullPick)),
      );
      await tester.pumpAndSettle();

      await _tapVisible(tester, 'Choose from Gallery');

      expect(tester.takeException(), isNull);
      expect(find.text('Continue'), findsNothing);
      expect(find.textContaining('No photo selected'), findsOneWidget);
    });

    testWidgets('Continue forwards real bytes to the processing route', (
      WidgetTester tester,
    ) async {
      // Authenticated: real analysis pipeline (POST hairstyle + poll).
      await AuthSession.saveSession('capture-branch-token');
      Object? seenExtra;
      await tester.pumpWidget(
        _wrap(
          PhotoCaptureScreen(
            pickImage: (_) async =>
                XFile.fromData(_bytes(), name: 'g.jpg', mimeType: 'image/jpeg'),
          ),
          onProcessing: (extra) => seenExtra = extra,
        ),
      );
      await tester.pumpAndSettle();

      await _tapVisible(tester, 'Choose from Gallery');
      await _tapVisible(tester, 'Continue');

      expect(tester.takeException(), isNull);
      expect(find.text('processing-marker'), findsOneWidget);
      final extra = seenExtra as Map<String, dynamic>?;
      expect(extra, isNotNull);
      expect((extra!['imageBytes'] as Uint8List), isNotEmpty);
      expect(extra['imageFilename'], 'style_capture.jpg');
    });

    testWidgets('guest Continue stays on the public results chain', (
      WidgetTester tester,
    ) async {
      // No session: public onboarding preview (analysis → results →
      // Continue Without Account → Stylist tab), never the guarded
      // processing route.
      expect(AuthSession.isAuthenticated, isFalse);
      await tester.pumpWidget(
        _wrap(
          PhotoCaptureScreen(
            pickImage: (_) async =>
                XFile.fromData(_bytes(), name: 'g.jpg', mimeType: 'image/jpeg'),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await _tapVisible(tester, 'Choose from Gallery');
      await _tapVisible(tester, 'Continue');

      expect(tester.takeException(), isNull);
      expect(find.text('analysis-marker'), findsOneWidget);
      expect(find.text('processing-marker'), findsNothing);
    });

    testWidgets('camera source never opens gallery; honest unavailable state', (
      WidgetTester tester,
    ) async {
      var galleryCalls = 0;
      await tester.pumpWidget(
        _wrap(
          PhotoCaptureScreen(
            source: 'camera',
            pickImage: (_) async {
              galleryCalls += 1;
              return null;
            },
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      // No platform camera under tests: honest unavailable card, no crash.
      expect(find.text('Camera unavailable'), findsOneWidget);
      expect(find.text('Capture Photo'), findsOneWidget);
      // The camera path must not touch the gallery picker.
      expect(galleryCalls, 0);
      // Gallery remains available as an explicit alternative.
      expect(find.text('Choose from Gallery'), findsOneWidget);
    });
  });

  group('CameraPermissionScreen routing', () {
    testWidgets('Allow Camera opens capture with source=camera', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_wrap(const CameraPermissionScreen()));
      await tester.pumpAndSettle();

      await _tapVisible(tester, 'Allow Camera');

      expect(tester.takeException(), isNull);
      expect(find.byType(PhotoCaptureScreen), findsOneWidget);
      // Camera path is active (Capture Photo), not the idle Take Photo.
      expect(find.text('Capture Photo'), findsOneWidget);
    });

    testWidgets('Choose from Gallery opens capture with source=gallery', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_wrap(const CameraPermissionScreen()));
      await tester.pumpAndSettle();

      // The gallery variant auto-invokes the real ImagePicker (no platform
      // channel under tests), so settle is not guaranteed afterwards:
      // pump explicitly instead of pumpAndSettle.
      await tester.scrollUntilVisible(find.text('Choose from Gallery'), 300.0);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Choose from Gallery'));
      for (var i = 0; i < 20; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }

      expect(tester.takeException(), isNull);
      expect(find.byType(PhotoCaptureScreen), findsOneWidget);
    });
  });
}

Future<XFile?> _nullPick(ImageSource source) async => null;
