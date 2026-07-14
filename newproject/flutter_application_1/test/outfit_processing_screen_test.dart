import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/features/outfit_scan/presentation/outfit_processing_screen.dart';
import 'package:fansivibe/features/outfit_scan/presentation/widgets/outfit_scan_widgets.dart';

void main() {
  group('OutfitProcessingScreen Widget Tests', () {
    testWidgets('renders app bar with analyzing title', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(home: const OutfitProcessingScreen()),
      );

      expect(find.text('Analyzing Outfit'), findsOneWidget);
    });

    testWidgets('renders processing stages', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(home: const OutfitProcessingScreen()),
      );

      expect(find.text('Detecting clothing items'), findsOneWidget);
      expect(find.byType(ProcessingStageIndicator), findsNWidgets(5));
    });

    testWidgets('shows progress indicator during processing', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(home: const OutfitProcessingScreen()),
      );

      expect(find.byType(CircularProgressIndicator), findsWidgets);
    });

    testWidgets('back button pops', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(home: const OutfitProcessingScreen()),
      );

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
    });
  });
}
