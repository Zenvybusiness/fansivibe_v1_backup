import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_mock_data.dart';
import 'package:fansivibe/features/hairstyle/presentation/face_processing_screen.dart';
import 'package:fansivibe/features/hairstyle/presentation/face_scan_screen.dart';
import 'package:fansivibe/features/hairstyle/presentation/hairstyle_result_screen.dart';
import 'package:fansivibe/features/hairstyle/presentation/widgets/hairstyle_widgets.dart';
import 'support/controllable_hairstyle_service.dart';

Future<XFile?> _neverPick(ImageSource source) async => null;

/// Minimal decodable 1x1 PNG for the in-memory preview (`Image.memory`
/// rejects arbitrary bytes in widget tests; production never decodes).
Uint8List _testPng() => base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
);

/// Taps a widget that may be below the fold of the test viewport: the scan
/// screen scrolls, so targets are brought into view before tapping.
Future<void> _tapVisible(WidgetTester tester, Finder finder) async {
  await tester.ensureVisible(finder);
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 500));
  await tester.tap(finder);
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 500));
}

GoRouter _router({
  required ControllableHairstyleService service,
  Future<XFile?> Function(ImageSource source)? pickImage,
  void Function(Map<String, dynamic>? extra)? onProcessing,
}) {
  return GoRouter(
    initialLocation: '/',
    routes: [
      GoRoute(
        path: '/',
        name: RouteNames.hairstyle,
        builder: (_, __) => FaceScanScreen(
          pickImage: pickImage ?? _neverPick,
        ),
        routes: [
          GoRoute(
            path: 'processing',
            name: RouteNames.hairstyleProcessing,
            builder: (context, state) {
              // Mirrors the production handoff in app_router.dart.
              final extra = state.extra as Map<String, dynamic>?;
              onProcessing?.call(extra);
              return FaceProcessingScreen(
                service: service,
                imageBytes: extra?['imageBytes'] as Uint8List?,
                imageFilename: extra?['imageFilename'] as String?,
                angleFront: extra?['angleFront'] as Uint8List?,
                angleLeft: extra?['angleLeft'] as Uint8List?,
                angleRight: extra?['angleRight'] as Uint8List?,
              );
            },
            routes: [
              GoRoute(
                path: 'result',
                name: RouteNames.hairstyleResult,
                builder: (_, state) => HairstyleResultScreen(
                  result: state.extra as HairstyleAnalysisResult?,
                ),
              ),
            ],
          ),
        ],
      ),
    ],
  );
}

Future<void> _captureCurrentAngle(
  WidgetTester tester,
  Uint8List image,
) async {
  await tester.scrollUntilVisible(
    find.text('Gallery'),
    100,
    scrollable: find.byType(Scrollable).first,
  );
  await tester.tap(find.text('Gallery'));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 200));
}

void main() {
  group('FaceScanScreen guided multi-angle capture', () {
    testWidgets('renders stepper, guidance, actions, and consent', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp(home: const FaceScanScreen()));

      expect(find.text('Face Scan'), findsOneWidget);
      expect(find.text('Front'), findsOneWidget);
      expect(find.text('Left'), findsOneWidget);
      expect(find.text('Right'), findsOneWidget);
      expect(
        find.text('Front — face the camera straight on'),
        findsOneWidget,
      );
      expect(find.text('Take Photo'), findsOneWidget);
      expect(find.text('Gallery'), findsOneWidget);
      expect(find.text('Analyze Photo (0/3)'), findsOneWidget);
      expect(find.text('Skip for now'), findsOneWidget);
      expect(
        find.textContaining('I consent to these photos'),
        findsOneWidget,
      );
      expect(tester.widget<Checkbox>(find.byType(Checkbox)).value, isFalse);
    });

    testWidgets('Take Photo never opens the gallery picker', (
      WidgetTester tester,
    ) async {
      var galleryCalls = 0;
      Future<XFile?> countingPick(ImageSource source) async {
        galleryCalls++;
        return null;
      }

      await tester.pumpWidget(
        MaterialApp(
          home: FaceScanScreen(pickImage: countingPick),
        ),
      );

      // Test binding has no camera plugin: Take Photo is a no-op here and
      // must NOT fall back to the gallery picker.
      await tester.tap(find.text('Take Photo'));
      await tester.pump();
      expect(galleryCalls, 0);
      expect(find.text('Analyze Photo (0/3)'), findsOneWidget);
    });

    testWidgets('gallery capture confirms step by step with retake', (
      WidgetTester tester,
    ) async {
      final service = ControllableHairstyleService();
      addTearDown(service.dispose);
      final image = _testPng();
      await tester.pumpWidget(
        MaterialApp.router(
          routerConfig: _router(
            service: service,
            pickImage: (_) async => XFile.fromData(
              image,
              name: 'face.jpg',
              mimeType: 'image/jpeg',
            ),
          ),
        ),
      );

      // FRONT capture → preview + Continue.
      await _captureCurrentAngle(tester, image);
      expect(find.text('Continue'), findsOneWidget);
      expect(find.text('Retake'), findsOneWidget);

      // Retake clears the current angle.
      await _tapVisible(tester, find.text('Retake'));
      expect(find.text('Continue'), findsNothing);
      expect(find.text('Analyze Photo (0/3)'), findsOneWidget);

      // Recapture FRONT and continue to LEFT with left guidance.
      await _captureCurrentAngle(tester, image);
      await _tapVisible(tester, find.text('Continue'));
      expect(find.text('Turn slowly to your left'), findsOneWidget);
      expect(find.text('Analyze Photo (1/3)'), findsOneWidget);

      // LEFT then RIGHT.
      await _captureCurrentAngle(tester, image);
      await _tapVisible(tester, find.text('Continue'));
      expect(find.text('Turn slowly to your right'), findsOneWidget);
      await _captureCurrentAngle(tester, image);
      // Last angle shows Done (nothing to advance to) + final Analyze.
      expect(find.text('Done'), findsOneWidget);
      expect(find.text('Analyze Photos'), findsOneWidget);
    });

    testWidgets('incomplete scan cannot submit even with consent', (
      WidgetTester tester,
    ) async {
      final service = ControllableHairstyleService();
      addTearDown(service.dispose);
      final image = _testPng();
      Map<String, dynamic>? seenExtra;
      await tester.pumpWidget(
        MaterialApp.router(
          routerConfig: _router(
            service: service,
            pickImage: (_) async => XFile.fromData(
              image,
              name: 'face.jpg',
              mimeType: 'image/jpeg',
            ),
            onProcessing: (extra) => seenExtra = extra,
          ),
        ),
      );

      await _captureCurrentAngle(tester, image);
      await _tapVisible(tester, find.byType(Checkbox));
      await tester.pump();
      await _tapVisible(tester, find.textContaining('Analyze Photo'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));

      expect(seenExtra, isNull);
      expect(find.text('Face Scan'), findsOneWidget);
    });

    testWidgets('completed consented scan hands all three angles over', (
      WidgetTester tester,
    ) async {
      final service = ControllableHairstyleService();
      addTearDown(service.dispose);
      final image = _testPng();
      Map<String, dynamic>? seenExtra;
      await tester.pumpWidget(
        MaterialApp.router(
          routerConfig: _router(
            service: service,
            pickImage: (_) async => XFile.fromData(
              image,
              name: 'face.jpg',
              mimeType: 'image/jpeg',
            ),
            onProcessing: (extra) => seenExtra = extra,
          ),
        ),
      );

      for (var i = 0; i < 2; i++) {
        await _captureCurrentAngle(tester, image);
        await _tapVisible(tester, find.text('Continue'));
      }
      await _captureCurrentAngle(tester, image);
      expect(find.text('Done'), findsOneWidget);
      await _tapVisible(tester, find.byType(Checkbox));
      await tester.pump();
      await _tapVisible(tester, find.text('Analyze Photos'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));

      expect(seenExtra?['angleFront'], image);
      expect(seenExtra?['angleLeft'], image);
      expect(seenExtra?['angleRight'], image);
      expect(service.multiAngleCalls, 1);
      expect(service.receivedAngleBytes, [image, image, image]);
      expect(find.text('Hairstyle Results'), findsOneWidget);
      expect(find.text('Textured Quiff'), findsOneWidget);
    });

    testWidgets('skip navigates without images', (WidgetTester tester) async {
      final service = ControllableHairstyleService();
      addTearDown(service.dispose);
      await tester.pumpWidget(
        MaterialApp.router(routerConfig: _router(service: service)),
      );

      await _tapVisible(tester, find.text('Skip for now'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));

      expect(service.started, isTrue);
      expect(find.text('Analyzing Face'), findsOneWidget);
    });

    testWidgets('renders face preview placeholder', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp(home: const FaceScanScreen()));

      expect(find.byType(FacePreviewPlaceholder), findsOneWidget);
      expect(
        find.text('Position your face within the oval guide'),
        findsOneWidget,
      );
    });

    testWidgets('back button pops', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const FaceScanScreen()));

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
    });

    testWidgets('empty gallery image is rejected honestly and not counted', (
      WidgetTester tester,
    ) async {
      final service = ControllableHairstyleService();
      addTearDown(service.dispose);
      await tester.pumpWidget(
        MaterialApp(
          home: FaceScanScreen(
            pickImage: (_) async =>
                XFile.fromData(Uint8List(0), name: 'empty.png'),
          ),
        ),
      );

      await _tapVisible(tester, find.text('Gallery'));

      // A blank/empty pick never counts as a capture and never advances the
      // stage silently — the user gets honest feedback instead.
      expect(find.byType(SnackBar), findsOneWidget);
      expect(find.text('Analyze Photo (0/3)'), findsOneWidget);
      expect(find.text('Continue'), findsNothing);

      // Let the snackbar's dismiss timer elapse before the test ends.
      await tester.pump(const Duration(seconds: 5));
      await tester.pump(const Duration(seconds: 1));
    });

    testWidgets(
      'camera capture advances Front -> Left -> Right automatically without lifecycle interaction',
      (WidgetTester tester) async {
        final image = _testPng();
        var captureCount = 0;
        Future<XFile?> fakeTakePhoto() async {
          captureCount++;
          return XFile.fromData(
            image,
            name: 'camera_$captureCount.jpg',
            mimeType: 'image/jpeg',
          );
        }

        await tester.pumpWidget(
          MaterialApp(
            home: FaceScanScreen(takePhoto: fakeTakePhoto),
          ),
        );

        // 1. Initial stage: Front angle
        expect(find.text('Front — face the camera straight on'), findsOneWidget);
        expect(find.text('Analyze Photo (0/3)'), findsOneWidget);

        // 2. Capture Front -> advances to Left automatically
        await _tapVisible(tester, find.text('Take Photo'));
        expect(captureCount, 1);
        expect(find.text('Turn slowly to your left'), findsOneWidget);
        expect(find.text('Analyze Photo (1/3)'), findsOneWidget);

        // 3. Capture Left -> advances to Right automatically
        await _tapVisible(tester, find.text('Take Photo'));
        expect(captureCount, 2);
        expect(find.text('Turn slowly to your right'), findsOneWidget);
        expect(find.text('Analyze Photo (2/3)'), findsOneWidget);

        // 4. Capture Right -> completes capture sequence
        await _tapVisible(tester, find.text('Take Photo'));
        expect(captureCount, 3);
        expect(find.text('Done'), findsOneWidget);
        expect(find.text('Analyze Photos'), findsOneWidget);

        // 5. Consent and analysis flow can proceed
        await _tapVisible(tester, find.byType(Checkbox));
        expect(tester.widget<Checkbox>(find.byType(Checkbox)).value, isTrue);
      },
    );

    testWidgets(
      'empty camera capture is rejected honestly and capture state does not get stuck',
      (WidgetTester tester) async {
        var calls = 0;
        Future<XFile?> emptyTakePhoto() async {
          calls++;
          return XFile.fromData(Uint8List(0), name: 'empty.jpg');
        }

        await tester.pumpWidget(
          MaterialApp(
            home: FaceScanScreen(takePhoto: emptyTakePhoto),
          ),
        );

        // Tapping Take Photo with an empty frame
        await _tapVisible(tester, find.text('Take Photo'));
        expect(calls, 1);

        // Honest SnackBar feedback shown
        expect(find.byType(SnackBar), findsOneWidget);
        expect(
          find.textContaining('Blank photo captured'),
          findsOneWidget,
        );

        // Stage is NOT advanced, still Front 0/3
        expect(find.text('Front — face the camera straight on'), findsOneWidget);
        expect(find.text('Analyze Photo (0/3)'), findsOneWidget);

        // Clean up snackbar timer
        await tester.pump(const Duration(seconds: 5));
        await tester.pump(const Duration(seconds: 1));
      },
    );

    testWidgets(
      'camera switch toggles between back camera and front camera',
      (WidgetTester tester) async {
        await tester.pumpWidget(
          const MaterialApp(
            home: FaceScanScreen(),
          ),
        );

        // Initially on Front camera, option is to switch to Back Camera
        expect(find.text('Switch to Back Camera'), findsOneWidget);

        // Tap to switch to Back Camera
        await _tapVisible(tester, find.text('Switch to Back Camera'));
        expect(find.text('Switch to Front Camera'), findsOneWidget);

        // Tap again to switch back to Front Camera
        await _tapVisible(tester, find.text('Switch to Front Camera'));
        expect(find.text('Switch to Back Camera'), findsOneWidget);
      },
    );
  });
}


