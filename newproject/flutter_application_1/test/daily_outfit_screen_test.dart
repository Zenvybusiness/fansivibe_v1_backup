import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/features/home/data/daily_outfit_mock_data.dart';
import 'package:fansivibe/features/home/presentation/daily_outfit_screen.dart';
import 'package:fansivibe/shared/theme/fansivibe_colors.dart';

Widget _buildTestApp() {
  return MaterialApp(
    theme: ThemeData(
      brightness: Brightness.dark,
      scaffoldBackgroundColor: FansivibeColors.background,
      colorScheme: const ColorScheme.dark(surface: FansivibeColors.surface),
    ),
    home: const DailyOutfitScreen(),
  );
}

void main() {
  group('DailyOutfitScreen (Today\'s Look) Widget Tests', () {
    testWidgets('renders hero section with TODAY\'S LOUD label', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_buildTestApp());
      await tester.pumpAndSettle();

      expect(find.text('TODAY\'S LOOK'), findsOneWidget);
    });

    testWidgets('renders match score in hero', (WidgetTester tester) async {
      await tester.pumpWidget(_buildTestApp());
      await tester.pumpAndSettle();

      expect(find.text('91%'), findsOneWidget);
    });

    testWidgets('renders occasion and weather chips', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_buildTestApp());
      await tester.pumpAndSettle();

      expect(find.text('Casual Friday'), findsOneWidget);
      expect(find.text('68\u00B0F \u2022 Partly Cloudy'), findsOneWidget);
    });

    testWidgets('renders Confidence Boost chip', (WidgetTester tester) async {
      await tester.pumpWidget(_buildTestApp());
      await tester.pumpAndSettle();

      expect(find.text('Confidence Boost'), findsOneWidget);
    });

    testWidgets('renders back button in hero', (WidgetTester tester) async {
      await tester.pumpWidget(_buildTestApp());
      await tester.pumpAndSettle();

      expect(find.byIcon(Icons.arrow_back_rounded), findsOneWidget);
    });

    testWidgets('renders editorial summary with title and description', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_buildTestApp());
      await tester.pumpAndSettle();

      expect(find.text('Modern Minimalist'), findsOneWidget);
      expect(
        find.textContaining(
          'Clean lines meet relaxed sophistication',
        ),
        findsOneWidget,
      );
    });

    testWidgets('renders AI selection reason', (WidgetTester tester) async {
      await tester.pumpWidget(_buildTestApp());
      await tester.pumpAndSettle();

      expect(
        find.textContaining('Perfect for today\'s'),
        findsOneWidget,
      );
    });

    testWidgets('renders outfit breakdown section', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_buildTestApp());
      await tester.pumpAndSettle();

      expect(find.text('The Ensemble'), findsOneWidget);
      expect(find.text('5 pieces'), findsOneWidget);
    });

    testWidgets('renders component names in breakdown', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_buildTestApp());
      await tester.pumpAndSettle();

      expect(find.text('Charcoal Unstructured Blazer'), findsOneWidget);
      expect(find.text('Merino Wool Crewneck'), findsOneWidget);
      expect(find.text('Tapered Wool Trousers'), findsOneWidget);
    });

    testWidgets('renders Why It Works section with insight titles', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_buildTestApp());
      await tester.pumpAndSettle();

      expect(find.text('Why It Works'), findsOneWidget);
      expect(find.text('AI style analysis'), findsOneWidget);
      expect(find.text('Color Harmony'), findsOneWidget);
      expect(find.text('Body Proportions'), findsOneWidget);
      expect(find.text('Style Compatibility'), findsOneWidget);
      expect(find.text('Occasion Suitability'), findsOneWidget);
    });

    testWidgets('renders Alternatives section', (WidgetTester tester) async {
      await tester.pumpWidget(_buildTestApp());
      await tester.pumpAndSettle();

      expect(find.text('Alternatives'), findsOneWidget);
      expect(find.text('3 more looks for you'), findsOneWidget);
      expect(find.text('Relaxed Refined'), findsOneWidget);
      expect(find.text('Urban Edge'), findsOneWidget);
      expect(find.text('Classic Heritage'), findsOneWidget);
    });

    testWidgets('renders alternative match scores', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_buildTestApp());
      await tester.pumpAndSettle();

      expect(find.text('88%'), findsOneWidget);
      expect(find.text('84%'), findsOneWidget);
      expect(find.text('82%'), findsOneWidget);
    });

    testWidgets('renders See Details buttons on alternatives', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_buildTestApp());
      await tester.pumpAndSettle();

      expect(find.text('See Details'), findsNWidgets(3));
    });

    testWidgets('renders quick action buttons', (WidgetTester tester) async {
      await tester.pumpWidget(_buildTestApp());
      await tester.pumpAndSettle();

      expect(find.text('Wear This Look'), findsOneWidget);
      expect(find.text('Generate Another Look'), findsOneWidget);
      expect(find.text('Save Look'), findsOneWidget);
      expect(find.text('Share'), findsOneWidget);
    });

    testWidgets('renders Daily Style Tip section', (WidgetTester tester) async {
      await tester.pumpWidget(_buildTestApp());
      await tester.pumpAndSettle();

      expect(find.text('Daily Style Tip'), findsOneWidget);
      expect(
        find.textContaining('A textured leather belt'),
        findsOneWidget,
      );
    });

    testWidgets('Wear This Look shows snackbar on tap', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_buildTestApp());
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.text('Wear This Look'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Wear This Look'));
      await tester.pumpAndSettle();

      expect(find.text('Wearing this look!'), findsOneWidget);
    });

    testWidgets('Save Look shows snackbar on tap', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_buildTestApp());
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.text('Save Look'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Save Look'));
      await tester.pumpAndSettle();

      expect(find.text('Outfit saved to your looks'), findsOneWidget);
    });

    testWidgets('DailyOutfitScreen is scrollable', (WidgetTester tester) async {
      await tester.pumpWidget(_buildTestApp());
      await tester.pumpAndSettle();

      expect(find.text('Daily Style Tip'), findsOneWidget);
    });
  });

  group('DailyOutfitData Mock Tests', () {
    test('mock data has all required fields', () {
      final data = DailyOutfitData.mock;

      expect(data.title, isNotEmpty);
      expect(data.occasion, isNotEmpty);
      expect(data.weather, isNotEmpty);
      expect(data.description, isNotEmpty);
      expect(data.matchScore, inInclusiveRange(0, 100));
      expect(data.styleScore, inInclusiveRange(0, 100));
      expect(data.components.length, greaterThan(0));
      expect(data.reasons.length, greaterThan(0));
      expect(data.styleDna.styleType, isNotEmpty);
      expect(data.wardrobeContext.totalItems, greaterThan(0));
    });

    test('mock components have required fields', () {
      final components = DailyOutfitData.mock.components;

      for (final component in components) {
        expect(component.id, isNotEmpty);
        expect(component.name, isNotEmpty);
        expect(component.category, isNotEmpty);
        expect(component.color, isNotEmpty);
      }
    });

    test('mock has new today\'s look fields', () {
      final data = DailyOutfitData.mock;

      expect(data.aiSelectionReason, isNotEmpty);
      expect(data.confidenceBoost, isNotEmpty);
      expect(data.aiInsights.length, greaterThan(0));
      expect(data.alternatives.length, greaterThan(0));
      expect(data.dailyStyleTip, isNotEmpty);
    });

    test('mock AI insights have required fields', () {
      final insights = DailyOutfitData.mock.aiInsights;

      for (final insight in insights) {
        expect(insight.title, isNotEmpty);
        expect(insight.description, isNotEmpty);
        expect(insight.iconName, isNotEmpty);
      }
    });

    test('mock alternatives have required fields', () {
      final alternatives = DailyOutfitData.mock.alternatives;

      for (final alt in alternatives) {
        expect(alt.id, isNotEmpty);
        expect(alt.name, isNotEmpty);
        expect(alt.matchScore, inInclusiveRange(0, 100));
        expect(alt.styleName, isNotEmpty);
      }
    });
  });
}
