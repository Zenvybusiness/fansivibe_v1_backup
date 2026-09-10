import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import 'package:fansivibe/app/router/route_names.dart';
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
}

GoRouter _router({
  required ControllableHairstyleService service,
  Future<XFile?> Function(ImageSource source)? pickImage,
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
              return FaceProcessingScreen(
                service: service,
                imageBytes: extra?['imageBytes'] as Uint8List?,
                imageFilename: extra?['imageFilename'] as String?,
              );
            },
            routes: [
              GoRoute(
                path: 'result',
                name: RouteNames.hairstyleResult,
                builder: (_, __) => const HairstyleResultScreen(),
              ),
            ],
          ),
        ],
      ),
    ],
  );
}

void main() {
  group('FaceScanScreen Widget Tests', () {
    testWidgets('renders app bar with title', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const FaceScanScreen()));

      expect(find.text('Face Scan'), findsOneWidget);
      expect(find.byIcon(Icons.arrow_back_rounded), findsOneWidget);
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

    testWidgets('renders Face Detection Active indicator', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp(home: const FaceScanScreen()));

      expect(find.text('Face Detection Active'), findsOneWidget);
    });

    testWidgets('renders check indicators', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const FaceScanScreen()));

      expect(find.byType(HairstyleCheckIndicator), findsNWidgets(3));
      expect(find.text('Lighting'), findsOneWidget);
      expect(find.text('Distance'), findsOneWidget);
      expect(find.text('Alignment'), findsOneWidget);
    });

    testWidgets('renders alignment improvement message', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp(home: const FaceScanScreen()));

      expect(find.text('Center your face in the frame'), findsOneWidget);
    });

    testWidgets('renders photo actions, consent, and skip', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp(home: const FaceScanScreen()));

      expect(find.text('Take Photo'), findsOneWidget);
      expect(find.text('Gallery'), findsOneWidget);
      expect(find.text('Analyze Photo'), findsOneWidget);
      expect(find.text('Skip for now'), findsOneWidget);
      expect(
        find.textContaining('I consent to this photo'),
        findsOneWidget,
      );
      // Consent is explicit opt-in: unchecked until the user agrees.
      expect(tester.widget<Checkbox>(find.byType(Checkbox)).value, isFalse);
    });

    testWidgets('analyze does nothing without image and consent', (
      WidgetTester tester,
    ) async {
      final service = ControllableHairstyleService();
      addTearDown(service.dispose);
      await tester.pumpWidget(
        MaterialApp.router(routerConfig: _router(service: service)),
      );

      await tester.tap(find.text('Analyze Photo'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));

      expect(service.started, isFalse);
      expect(find.text('Face Scan'), findsOneWidget);
    });

    testWidgets('analyze stays disabled until consent is given', (
      WidgetTester tester,
    ) async {
      final service = ControllableHairstyleService();
      addTearDown(service.dispose);
      final image = _testPng();
      await tester.pumpWidget(
        MaterialApp.router(
          routerConfig: _router(
            service: service,
            pickImage: (_) async =>
                XFile.fromData(image, name: 'face.jpg', mimeType: 'image/jpeg'),
          ),
        ),
      );

      await tester.tap(find.text('Gallery'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 200));

      // Image selected (preview shown) but no consent → still no navigation.
      await tester.ensureVisible(find.text('Analyze Photo'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Analyze Photo'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));

      expect(service.started, isFalse);
      expect(find.text('Face Scan'), findsOneWidget);
    });

    testWidgets('consented image navigates with bytes to processing', (
      WidgetTester tester,
    ) async {
      final service = ControllableHairstyleService();
      addTearDown(service.dispose);
      final image = _testPng();
      await tester.pumpWidget(
        MaterialApp.router(
          routerConfig: _router(
            service: service,
            pickImage: (_) async =>
                XFile.fromData(image, name: 'face.jpg', mimeType: 'image/jpeg'),
          ),
        ),
      );

      await tester.tap(find.text('Gallery'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 200));

      await _tapVisible(tester, find.byType(Checkbox));
      await tester.pump();

      await _tapVisible(tester, find.text('Analyze Photo'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));

      expect(service.started, isTrue);
      expect(service.receivedImageBytes, image);
      expect(find.text('Analyzing Face'), findsOneWidget);
      expect(find.text('Detecting face features'), findsOneWidget);
    });

    testWidgets('skip navigates without image and without analysis input', (
      WidgetTester tester,
    ) async {
      final service = ControllableHairstyleService();
      addTearDown(service.dispose);
      await tester.pumpWidget(
        MaterialApp.router(routerConfig: _router(service: service)),
      );

      await _tapVisible(tester, find.text('Skip for now'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));

      expect(service.started, isTrue);
      // Skip hands over no image: no backend image analysis, no FaceProfile
      // fabrication — the existing offline path resolves downstream.
      expect(service.receivedImageBytes, isNull);
      expect(find.text('Analyzing Face'), findsOneWidget);
    });

    testWidgets('back button pops', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const FaceScanScreen()));

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
    });
  });
}
