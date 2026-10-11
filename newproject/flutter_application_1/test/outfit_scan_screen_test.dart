import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/outfit_scan/presentation/outfit_analysis_screen.dart';
import 'package:fansivibe/features/outfit_scan/presentation/outfit_processing_screen.dart';
import 'package:fansivibe/features/outfit_scan/presentation/outfit_scan_screen.dart';
import 'package:fansivibe/features/outfit_scan/presentation/widgets/outfit_scan_widgets.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

/// A 1×1 PNG so the selected-image preview can decode in-memory bytes.
Uint8List _png() => base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
);

Future<XFile?> _fakePick(ImageSource source) async =>
    XFile.fromData(_png(), name: 'outfit.jpg', mimeType: 'image/jpeg');


final GoRouter _scanRouter = GoRouter(
  initialLocation: '/',
  routes: [
    GoRoute(
      path: '/',
      name: RouteNames.scanOutfit,
      builder: (_, __) => const OutfitScanScreen(),
      routes: [
        GoRoute(
          path: 'processing',
          name: RouteNames.scanProcessing,
          builder: (context, state) {
            final runId = state.extra as String?;
            return OutfitProcessingScreen(runId: runId);
          },
          routes: [
            GoRoute(
              path: 'analysis',
              name: RouteNames.scanAnalysis,
              builder: (context, state) {
                final analysisResult = state.extra as Map<String, dynamic>?;
                return OutfitAnalysisScreen(analysisResult: analysisResult);
              },
            ),
          ],
        ),
      ],
    ),
  ],
);

void main() {
  group('OutfitScanScreen Widget Tests', () {
    testWidgets('renders app bar with title', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const OutfitScanScreen()));

      expect(find.text('Scan My Outfit'), findsOneWidget);
      expect(find.byIcon(Icons.arrow_back_rounded), findsOneWidget);
    });

    testWidgets('renders camera preview placeholder', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp(home: const OutfitScanScreen()));

      expect(find.byType(CameraPreviewPlaceholder), findsOneWidget);
      expect(find.text('Camera Preview'), findsOneWidget);
    });

    testWidgets('renders camera starting indicator', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp(home: const OutfitScanScreen()));

      expect(find.text('Starting Camera'), findsOneWidget);
      expect(find.text('AI Analysis Active'), findsNothing);
      expect(find.text('Camera Ready'), findsNothing);
    });

    testWidgets('renders photo tips instead of fake detection states', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp(home: const OutfitScanScreen()));

      expect(find.text('PHOTO TIPS'), findsOneWidget);
      expect(find.textContaining('Lighting:'), findsOneWidget);
      expect(find.textContaining('Framing:'), findsOneWidget);
      expect(find.textContaining('Posture:'), findsOneWidget);
    });

    testWidgets('renders Capture Photo button', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const OutfitScanScreen()));

      expect(find.text('Capture Photo'), findsOneWidget);
      expect(find.byIcon(Icons.camera_alt_rounded), findsWidgets);
    });

    testWidgets('gallery picker available', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const OutfitScanScreen()));

      expect(find.text('Choose from Gallery'), findsOneWidget);
    });

    testWidgets('switch camera button available', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const OutfitScanScreen()));

      expect(find.text('Switch Camera'), findsOneWidget);
    });

    testWidgets('capture photo navigates to processing screen', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp.router(routerConfig: _scanRouter));

      await tester.tap(find.text('Capture Photo'));
      for (var i = 0; i < 30; i++) {
        await tester.pump(const Duration(milliseconds: 16));
      }

      expect(find.byType(OutfitProcessingScreen), findsOneWidget);
      expect(find.text('Analysis Status'), findsOneWidget);
    });

    testWidgets('back button pops', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const OutfitScanScreen()));

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
    });
  });

  group('OutfitScanScreen layout regression', () {
    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      LocalStorage.init(prefs: await SharedPreferences.getInstance());
    });

    tearDown(LocalStorage.resetForTest);

    Future<void> tapVisible(WidgetTester tester, Finder finder) async {
      await tester.ensureVisible(finder);
      await tester.pump();
      await tester.tap(finder);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
    }

    testWidgets(
      'selected-image preview lays out without unbounded Stack/ClipRRect',
      (WidgetTester tester) async {
        // A compact phone viewport; the previous failure was an unbounded
        // height inside the scroll view, which this path must now bound.
        tester.view.physicalSize = const Size(360, 640);
        tester.view.devicePixelRatio = 1.0;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);

        await tester.pumpWidget(
          MaterialApp(home: OutfitScanScreen(pickImage: _fakePick)),
        );

        await tapVisible(tester, find.text('Choose from Gallery'));

        // The primary rendering assertion (BoxConstraints forces an
        // infinite height) and its cascading RenderStack/RenderClipRRect
        // failures must not occur.
        expect(tester.takeException(), isNull);
        expect(find.byType(Image), findsOneWidget);
        expect(tester.getSize(find.byType(Image)).height.isFinite, isTrue);
        expect(find.text('Analyze Photo'), findsOneWidget);
      },
    );

    testWidgets(
      'renders saved guest-analysis banner with its controls',
      (WidgetTester tester) async {
        stashPendingEphemeralResult(
          feature: EphemeralFeature.outfit,
          snapshot: const {'appearance': {'faceShape': 'oval'}},
        );

        await tester.pumpWidget(
          const MaterialApp(home: OutfitScanScreen()),
        );

        expect(tester.takeException(), isNull);
        expect(find.text('Your outfit analysis is saved'), findsOneWidget);
        expect(find.text('View Result'), findsOneWidget);
        expect(find.text('Dismiss'), findsOneWidget);
        expect(find.text('Choose from Gallery'), findsOneWidget);
        expect(find.text('Switch Camera'), findsOneWidget);
        expect(find.text('Capture Photo'), findsOneWidget);
        expect(find.byType(CameraPreviewPlaceholder), findsOneWidget);
      },
    );

    testWidgets(
      'dismissing the banner clears it without breaking layout',
      (WidgetTester tester) async {
        stashPendingEphemeralResult(
          feature: EphemeralFeature.outfit,
          snapshot: const {'appearance': {'faceShape': 'oval'}},
        );

        await tester.pumpWidget(
          const MaterialApp(home: OutfitScanScreen()),
        );
        expect(find.text('View Result'), findsOneWidget);

        await tester.tap(find.text('Dismiss'));
        await tester.pump();

        expect(tester.takeException(), isNull);
        expect(find.text('Your outfit analysis is saved'), findsNothing);
        expect(find.text('View Result'), findsNothing);
        expect(peekPendingEphemeralResult(), isNull);
        expect(find.text('Choose from Gallery'), findsOneWidget);
        expect(find.text('Switch Camera'), findsOneWidget);
      },
    );
  });
}
