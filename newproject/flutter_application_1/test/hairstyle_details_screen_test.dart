import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_mock_data.dart';
import 'package:fansivibe/features/hairstyle/presentation/hairstyle_details_screen.dart';
import 'support/controllable_hairstyle_service.dart';

void main() {
  group('HairstyleDetailsScreen Widget Tests', () {
    testWidgets('renders app bar with hairstyle name', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: HairstyleDetailsScreen(
            recommendation: HairstyleAnalysisResult.mock.topRecommendation,
          ),
        ),
      );

      expect(find.text('Textured Quiff'), findsAtLeast(1));
      expect(find.byIcon(Icons.arrow_back_rounded), findsOneWidget);
    });

    testWidgets('renders match score', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: HairstyleDetailsScreen(
            recommendation: HairstyleAnalysisResult.mock.topRecommendation,
          ),
        ),
      );

      expect(find.text('94%'), findsOneWidget);
      expect(find.text('match'), findsOneWidget);
    });

    testWidgets('renders description card', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: HairstyleDetailsScreen(
            recommendation: HairstyleAnalysisResult.mock.topRecommendation,
          ),
        ),
      );

      expect(
        find.textContaining('A modern take on the classic quiff'),
        findsOneWidget,
      );
    });

    testWidgets('renders reasons section', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: HairstyleDetailsScreen(
            recommendation: HairstyleAnalysisResult.mock.topRecommendation,
          ),
        ),
      );

      expect(find.text('Why This Works For You'), findsOneWidget);
      expect(
        find.textContaining('Oval face shapes benefit from volume'),
        findsOneWidget,
      );
    });

    testWidgets('renders styling tips', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: HairstyleDetailsScreen(
            recommendation: HairstyleAnalysisResult.mock.topRecommendation,
          ),
        ),
      );

      expect(find.text('Styling Tips'), findsOneWidget);
      expect(find.textContaining('volumizing mousse'), findsOneWidget);
    });

    testWidgets('renders maintenance info', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: HairstyleDetailsScreen(
            recommendation: HairstyleAnalysisResult.mock.topRecommendation,
          ),
        ),
      );

      expect(find.text('Maintenance'), findsOneWidget);
      expect(find.textContaining('Trim every 4-5 weeks'), findsOneWidget);
    });

    testWidgets('renders best for info', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: HairstyleDetailsScreen(
            recommendation: HairstyleAnalysisResult.mock.topRecommendation,
          ),
        ),
      );

      expect(find.text('Best For'), findsOneWidget);
      expect(
        find.textContaining('Oval, Heart, and Rectangle'),
        findsAtLeast(1),
      );
    });

    testWidgets('renders Try This Style button', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: HairstyleDetailsScreen(
            recommendation: HairstyleAnalysisResult.mock.topRecommendation,
          ),
        ),
      );

      expect(find.text('Try This Style'), findsOneWidget);
    });

    testWidgets('back button pops', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: HairstyleDetailsScreen(
            recommendation: HairstyleAnalysisResult.mock.topRecommendation,
          ),
        ),
      );

      await tester.tap(find.byIcon(Icons.arrow_back_rounded));
      await tester.pumpAndSettle();
    });

    testWidgets('saving calls saveLook and shows the success snackbar', (
      WidgetTester tester,
    ) async {
      final service = StubSaveHairstyleService()..saveResult = true;
      addTearDown(service.dispose);
      await tester.pumpWidget(
        MaterialApp(
          home: HairstyleDetailsScreen(
            recommendation: HairstyleAnalysisResult.mock.topRecommendation,
            service: service,
          ),
        ),
      );

      await tester.ensureVisible(find.text('Try This Style'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Try This Style'));
      await tester.pumpAndSettle();

      expect(service.saveCalls, 1);
      expect(service.savedLookIds, ['textured_quiff']);
      expect(service.savedTitles, ['Textured Quiff']);
      expect(
        find.text('Textured Quiff saved to profile'),
        findsOneWidget,
      );
    });

    testWidgets('saving shows the failure snackbar when save fails', (
      WidgetTester tester,
    ) async {
      final service = StubSaveHairstyleService()..saveResult = false;
      addTearDown(service.dispose);
      await tester.pumpWidget(
        MaterialApp(
          home: HairstyleDetailsScreen(
            recommendation: HairstyleAnalysisResult.mock.topRecommendation,
            service: service,
          ),
        ),
      );

      await tester.ensureVisible(find.text('Try This Style'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Try This Style'));
      await tester.pumpAndSettle();

      expect(service.saveCalls, 1);
      expect(find.text('Could not save hairstyle'), findsOneWidget);
    });
  });
}
