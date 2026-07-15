import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/outfit_scan/presentation/outfit_analysis_screen.dart';
import 'package:fansivibe/features/outfit_scan/presentation/outfit_processing_screen.dart';
import 'package:fansivibe/features/outfit_scan/presentation/outfit_scan_screen.dart';
import 'package:fansivibe/features/outfit_scan/presentation/widgets/outfit_scan_widgets.dart';

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
            final localPath = state.extra as String?;
            return OutfitProcessingScreen(capturedImagePath: localPath);
          },
          routes: [
            GoRoute(
              path: 'analysis',
              name: RouteNames.scanAnalysis,
              builder: (context, state) {
                final localPath = state.extra as String?;
                return OutfitAnalysisScreen(capturedImagePath: localPath);
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

    testWidgets('renders AI Analysis Active indicator', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp(home: const OutfitScanScreen()));

      expect(find.text('AI Analysis Active'), findsOneWidget);
    });

    testWidgets('renders check indicators', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const OutfitScanScreen()));

      expect(find.byType(CheckIndicator), findsNWidgets(3));
      expect(find.text('Lighting'), findsOneWidget);
      expect(find.text('Framing'), findsOneWidget);
      expect(find.text('Posture'), findsOneWidget);
    });

    testWidgets('renders posture improvement message', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp(home: const OutfitScanScreen()));

      expect(find.text('Adjust posture for better analysis'), findsOneWidget);
    });

    testWidgets('renders Capture Look button', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const OutfitScanScreen()));

      expect(find.text('Capture Look'), findsOneWidget);
      expect(find.byIcon(Icons.camera_alt_rounded), findsWidgets);
    });

    testWidgets('renders Gallery and Switch Camera buttons', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp(home: const OutfitScanScreen()));

      expect(find.text('Gallery'), findsOneWidget);
      expect(find.text('Switch Camera'), findsOneWidget);
    });

    testWidgets('capture look navigates to processing screen', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp.router(routerConfig: _scanRouter));

      await tester.tap(find.text('Capture Look'));
      for (var i = 0; i < 30; i++) {
        await tester.pump(const Duration(milliseconds: 16));
      }

      expect(find.text('Analyzing Outfit'), findsOneWidget);
      expect(find.text('Detecting clothing items'), findsOneWidget);
    });

    testWidgets('back button pops', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const OutfitScanScreen()));

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
    });
  });
}
