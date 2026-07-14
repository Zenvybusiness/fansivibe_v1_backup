import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/features/grooming/data/grooming_mock_data.dart';
import 'package:fansivibe/features/grooming/presentation/grooming_details_screen.dart';

void main() {
  group('GroomingDetailsScreen Widget Tests', () {
    testWidgets('renders app bar with recommendation name', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: GroomingDetailsScreen(
            recommendation: GroomingAnalysisResult.mock.topRecommendation,
          ),
        ),
      );

      expect(find.text('Structured Goatee'), findsAtLeast(1));
      expect(find.byIcon(Icons.arrow_back_rounded), findsOneWidget);
    });

    testWidgets('renders match score', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: GroomingDetailsScreen(
            recommendation: GroomingAnalysisResult.mock.topRecommendation,
          ),
        ),
      );

      expect(find.text('92%'), findsOneWidget);
      expect(find.text('match'), findsOneWidget);
    });

    testWidgets('renders description card', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: GroomingDetailsScreen(
            recommendation: GroomingAnalysisResult.mock.topRecommendation,
          ),
        ),
      );

      expect(
        find.textContaining('A refined goatee that frames the chin'),
        findsOneWidget,
      );
    });

    testWidgets('renders reasons section', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: GroomingDetailsScreen(
            recommendation: GroomingAnalysisResult.mock.topRecommendation,
          ),
        ),
      );

      expect(find.text('Why This Works For You'), findsOneWidget);
      expect(
        find.textContaining('Oval faces benefit from chin definition'),
        findsOneWidget,
      );
    });

    testWidgets('renders beard length spec', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: GroomingDetailsScreen(
            recommendation: GroomingAnalysisResult.mock.topRecommendation,
          ),
        ),
      );

      expect(find.text('Beard Length'), findsOneWidget);
      expect(find.textContaining('Medium - Long (10-15mm)'), findsOneWidget);
    });

    testWidgets('renders cheek line spec', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: GroomingDetailsScreen(
            recommendation: GroomingAnalysisResult.mock.topRecommendation,
          ),
        ),
      );

      expect(find.text('Cheek Line'), findsOneWidget);
    });

    testWidgets('renders eyewear frame spec', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: GroomingDetailsScreen(
            recommendation: GroomingAnalysisResult.mock.topRecommendation,
          ),
        ),
      );

      expect(find.text('Eyewear Frame'), findsOneWidget);
      expect(find.text('Rectangular'), findsOneWidget);
    });

    testWidgets('renders eyewear recommendation', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: GroomingDetailsScreen(
            recommendation: GroomingAnalysisResult.mock.topRecommendation,
          ),
        ),
      );

      expect(find.text('Eyewear Recommendation'), findsOneWidget);
      expect(
        find.textContaining('Rectangular or wayfarer frames'),
        findsOneWidget,
      );
    });

    testWidgets('renders styling tips', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: GroomingDetailsScreen(
            recommendation: GroomingAnalysisResult.mock.topRecommendation,
          ),
        ),
      );

      expect(find.text('Styling Tips'), findsOneWidget);
      expect(find.textContaining('beard oil'), findsOneWidget);
    });

    testWidgets('renders maintenance info', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: GroomingDetailsScreen(
            recommendation: GroomingAnalysisResult.mock.topRecommendation,
          ),
        ),
      );

      expect(find.text('Maintenance'), findsOneWidget);
      expect(find.textContaining('Trim every 3-4 days'), findsOneWidget);
    });

    testWidgets('renders best for info', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: GroomingDetailsScreen(
            recommendation: GroomingAnalysisResult.mock.topRecommendation,
          ),
        ),
      );

      expect(find.text('Best For'), findsOneWidget);
      expect(
        find.textContaining('Oval, Rectangular, and Diamond'),
        findsAtLeast(1),
      );
    });

    testWidgets('renders Save Recommendation button', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: GroomingDetailsScreen(
            recommendation: GroomingAnalysisResult.mock.topRecommendation,
          ),
        ),
      );

      expect(find.text('Save Recommendation'), findsOneWidget);
    });

    testWidgets('back button pops', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: GroomingDetailsScreen(
            recommendation: GroomingAnalysisResult.mock.topRecommendation,
          ),
        ),
      );

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
    });
  });
}
