import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/features/outfit_scan/presentation/outfit_analysis_screen.dart';
import 'package:fansivibe/features/outfit_scan/presentation/widgets/outfit_scan_widgets.dart';

void main() {
  group('OutfitAnalysisScreen Widget Tests', () {
    testWidgets('renders app bar with title and share button', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp(home: const OutfitAnalysisScreen()));

      expect(find.text('Outfit Analysis'), findsOneWidget);
      expect(find.byIcon(Icons.share_outlined), findsOneWidget);
      expect(find.byIcon(Icons.arrow_back_rounded), findsOneWidget);
    });

    testWidgets('renders analysis title header', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const OutfitAnalysisScreen()));

      expect(find.text('Modern Minimalist Look'), findsOneWidget);
      expect(find.text('AI-powered style analysis'), findsOneWidget);
    });

    testWidgets('renders outfit visual placeholder', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp(home: const OutfitAnalysisScreen()));

      expect(find.text('Outfit Visual'), findsOneWidget);
      expect(find.text('Analysis Ready'), findsOneWidget);
    });

    testWidgets('renders all analysis sections', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const OutfitAnalysisScreen()));

      expect(find.byType(AnalysisSectionCard), findsNWidgets(6));
      expect(find.text('Silhouette & Proportions'), findsOneWidget);
      expect(find.text('Balance'), findsOneWidget);
      expect(find.text('Fit'), findsOneWidget);
      expect(find.text('Volume'), findsOneWidget);
      expect(find.text('Color Harmony'), findsOneWidget);
      expect(find.text('Structure & Form'), findsOneWidget);
    });

    testWidgets('renders detected items section', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const OutfitAnalysisScreen()));

      expect(find.text('Detected Items'), findsOneWidget);
      expect(find.text('5 items identified'), findsOneWidget);
      expect(find.byType(DetectedItemChip), findsNWidgets(5));
    });

    testWidgets('renders action buttons', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const OutfitAnalysisScreen()));

      expect(find.text('Scan Again'), findsOneWidget);
      expect(find.text('Save Look'), findsOneWidget);
    });

    testWidgets('Scan Again navigates back', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const OutfitAnalysisScreen()));

      await tester.scrollUntilVisible(find.text('Scan Again'), 200);
      await tester.tap(find.text('Scan Again'));
      await tester.pumpAndSettle();
    });
  });
}
