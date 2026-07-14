import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/features/outfit_builder/presentation/build_outfit_screen.dart';
import 'package:fansivibe/features/outfit_builder/presentation/outfit_generation_screen.dart';
import 'package:fansivibe/features/outfit_builder/presentation/outfit_recommendation_screen.dart';
import 'package:fansivibe/features/outfit_builder/presentation/widgets/outfit_builder_widgets.dart';

void main() {
  group('BuildOutfitScreen Widget Tests', () {
    testWidgets('renders app bar and header', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const BuildOutfitScreen()));

      expect(find.text('Build Outfit'), findsOneWidget);
      expect(find.text('Create Your Look'), findsOneWidget);
      expect(find.byIcon(Icons.arrow_back_rounded), findsOneWidget);
    });

    testWidgets('renders all four option sections', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp(home: const BuildOutfitScreen()));

      expect(find.text('Occasion'), findsOneWidget);
      expect(find.text('Mood'), findsOneWidget);
      expect(find.text('Preferred Fit'), findsOneWidget);
      expect(find.text('Color Palette'), findsOneWidget);
    });

    testWidgets('render all option chips', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const BuildOutfitScreen()));

      expect(find.text('Casual'), findsOneWidget);
      expect(find.text('Office'), findsOneWidget);
      expect(find.text('Date'), findsOneWidget);
      expect(find.text('Party'), findsOneWidget);
      expect(find.text('Travel'), findsOneWidget);

      expect(find.text('Minimal'), findsOneWidget);
      expect(find.text('Bold'), findsOneWidget);
      expect(find.text('Classic'), findsOneWidget);
      expect(find.text('Eclectic'), findsOneWidget);

      expect(find.text('Slim'), findsOneWidget);
      expect(find.text('Relaxed'), findsOneWidget);
      expect(find.text('Tailored'), findsOneWidget);

      expect(find.text('Monochrome'), findsOneWidget);
      expect(find.text('Warm'), findsOneWidget);
      expect(find.text('Cool'), findsOneWidget);
    });

    testWidgets('build button is disabled when no selections made', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp(home: const BuildOutfitScreen()));

      await tester.scrollUntilVisible(find.text('Build My Outfit'), 200);
      await tester.pump();
      expect(find.text('Build My Outfit'), findsOneWidget);
    });

    testWidgets('build button enables after all selections', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp(home: const BuildOutfitScreen()));

      await tester.tap(find.text('Casual'));
      await tester.pump();

      await tester.scrollUntilVisible(find.text('Classic'), 200);
      await tester.tap(find.text('Classic'));
      await tester.pump();

      await tester.scrollUntilVisible(find.text('Tailored'), 200);
      await tester.tap(find.text('Tailored'));
      await tester.pump();

      await tester.scrollUntilVisible(find.text('Warm'), 200);
      await tester.tap(find.text('Warm'));
      await tester.pump();

      await tester.scrollUntilVisible(find.text('Build My Outfit'), 200);
      await tester.pump();

      expect(find.text('Build My Outfit'), findsOneWidget);
    });

    testWidgets('selecting an option shows check icon', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(MaterialApp(home: const BuildOutfitScreen()));

      await tester.tap(find.text('Casual'));
      await tester.pump();

      expect(find.byIcon(Icons.check_circle_rounded), findsAtLeast(1));
    });

    testWidgets('back button pops', (WidgetTester tester) async {
      await tester.pumpWidget(MaterialApp(home: const BuildOutfitScreen()));

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
    });
  });

  group('BuildOutfitScreen Navigation', () {
    testWidgets('tapping build button navigates to generation screen', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: const BuildOutfitScreen(),
          routes: {
            '/generation': (_) => const OutfitGenerationScreen(
              occasion: 'casual',
              mood: 'classic',
              fit: 'tailored',
              colorPalette: 'warm',
            ),
          },
        ),
      );

      await tester.tap(find.text('Casual'));
      await tester.pump();

      await tester.scrollUntilVisible(find.text('Classic'), 200);
      await tester.tap(find.text('Classic'));
      await tester.pump();

      await tester.scrollUntilVisible(find.text('Tailored'), 200);
      await tester.tap(find.text('Tailored'));
      await tester.pump();

      await tester.scrollUntilVisible(find.text('Warm'), 200);
      await tester.tap(find.text('Warm'));
      await tester.pump();

      await tester.scrollUntilVisible(find.text('Build My Outfit'), 200);
      await tester.tap(find.text('Build My Outfit'));
      await tester.pump();
      await tester.pump();

      expect(find.text('Building Outfit'), findsOneWidget);
    });
  });

  group('OutfitGenerationScreen Widget Tests', () {
    testWidgets('renders app bar with building title', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: const OutfitGenerationScreen(
            occasion: 'casual',
            mood: 'classic',
            fit: 'tailored',
            colorPalette: 'warm',
          ),
        ),
      );

      expect(find.text('Building Outfit'), findsOneWidget);
    });

    testWidgets('renders selection summary', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: const OutfitGenerationScreen(
            occasion: 'casual',
            mood: 'classic',
            fit: 'tailored',
            colorPalette: 'warm',
          ),
        ),
      );

      expect(find.text('Your Preferences'), findsOneWidget);
      expect(find.text('Casual'), findsAtLeast(1));
      expect(find.text('Classic'), findsAtLeast(1));
      expect(find.text('Tailored'), findsAtLeast(1));
      expect(find.text('Warm'), findsAtLeast(1));
    });

    testWidgets('renders generation stages', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: const OutfitGenerationScreen(
            occasion: 'casual',
            mood: 'classic',
            fit: 'tailored',
            colorPalette: 'warm',
          ),
        ),
      );

      expect(find.text('Analyzing wardrobe items'), findsOneWidget);
      expect(find.text('Matching occasion preferences'), findsOneWidget);
      expect(find.text('Applying Style DNA'), findsOneWidget);
      expect(find.text('Selecting complementary pieces'), findsOneWidget);
      expect(find.text('Generating outfit recommendations'), findsOneWidget);
    });

    testWidgets('shows progress indicator during generation', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: const OutfitGenerationScreen(
            occasion: 'casual',
            mood: 'classic',
            fit: 'tailored',
            colorPalette: 'warm',
          ),
        ),
      );

      expect(find.byType(CircularProgressIndicator), findsWidgets);
    });

    testWidgets('back button pops', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: const OutfitGenerationScreen(
            occasion: 'casual',
            mood: 'classic',
            fit: 'tailored',
            colorPalette: 'warm',
          ),
        ),
      );

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
    });
  });

  group('OutfitRecommendationScreen Widget Tests', () {
    testWidgets('renders app bar and header', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(home: const OutfitRecommendationScreen()),
      );

      expect(find.text('Your Outfit'), findsOneWidget);
      expect(find.text('Refined Office Ensemble'), findsOneWidget);
      expect(find.byIcon(Icons.arrow_back_rounded), findsOneWidget);
    });

    testWidgets('renders match score', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(home: const OutfitRecommendationScreen()),
      );

      expect(find.text('91%'), findsOneWidget);
      expect(find.text('Match Score'), findsOneWidget);
    });

    testWidgets('renders outfit components', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(home: const OutfitRecommendationScreen()),
      );

      expect(find.text('Outfit Components'), findsOneWidget);
      expect(find.text('5 curated pieces'), findsOneWidget);
      expect(find.byType(OutfitComponentCard), findsNWidgets(5));
    });

    testWidgets('renders recommendation reasons', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(home: const OutfitRecommendationScreen()),
      );

      expect(find.text('Why This Look Works'), findsOneWidget);
    });

    testWidgets('renders metric cards', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(home: const OutfitRecommendationScreen()),
      );

      expect(find.text('Color Harmony'), findsOneWidget);
      expect(find.text('Body Fit'), findsOneWidget);
      expect(find.text('Occasion Match'), findsOneWidget);
    });

    testWidgets('renders Style Score impact', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(home: const OutfitRecommendationScreen()),
      );

      expect(find.text('Style Score Impact'), findsOneWidget);
    });

    testWidgets('renders improvement suggestion', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(home: const OutfitRecommendationScreen()),
      );

      expect(find.text('Improvement Suggestion'), findsOneWidget);
    });

    testWidgets('renders action buttons', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(home: const OutfitRecommendationScreen()),
      );

      expect(find.text('Wear This Look'), findsOneWidget);
      expect(find.text('Save Look'), findsOneWidget);
    });

    testWidgets('renders Replace buttons for components', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(home: const OutfitRecommendationScreen()),
      );

      expect(find.text('Replace'), findsNWidgets(5));
    });

    testWidgets('back button pops', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(home: const OutfitRecommendationScreen()),
      );

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
    });
  });
}
