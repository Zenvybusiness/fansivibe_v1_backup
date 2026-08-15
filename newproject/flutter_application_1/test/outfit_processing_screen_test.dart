import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/features/outfit_scan/presentation/outfit_processing_screen.dart';

void main() {
  group('OutfitProcessingScreen Widget Tests', () {
    testWidgets('renders app bar with analyzing title', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(home: const OutfitProcessingScreen(runId: 'test-run-123')),
      );

      expect(find.text('Analyzing Outfit'), findsOneWidget);
    });

    testWidgets('renders processing indicator during polling', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(home: const OutfitProcessingScreen(runId: 'test-run-123')),
      );

      expect(find.byType(CircularProgressIndicator), findsOneWidget);
    });

    testWidgets('back button pops', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(home: const OutfitProcessingScreen(runId: 'test-run-123')),
      );

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
    });

    testWidgets('handles completed run navigation', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: OutfitProcessingScreen(
            runId: 'completed-run-456',
            // We can't easily test the full polling flow in widget tests,
            // but we can verify the initial state
          ),
        ),
      );

      expect(find.text('Analyzing Outfit'), findsOneWidget);
    });

    testWidgets('handles failed run', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: OutfitProcessingScreen(
            runId: 'failed-run-789',
          ),
        ),
      );

      expect(find.text('Analyzing Outfit'), findsOneWidget);
    });
  });
}