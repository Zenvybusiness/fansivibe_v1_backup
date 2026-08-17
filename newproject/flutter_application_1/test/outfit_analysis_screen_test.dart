import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/features/outfit_scan/presentation/outfit_analysis_screen.dart';

void main() {
  group('OutfitAnalysisScreen Widget Tests', () {
    testWidgets('renders app bar with title and share button', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: OutfitAnalysisScreen(
            analysisResult: {
              'appearance': {
                'faceShape': 'oval',
                'skinTone': 'W30',
                'bodyType': 'average',
                'styleType': 'casual',
              },
              'confidence': 0.78,
              'needs_more_data': false,
              'recommendations': {
                'top': {
                  'id': 'leather-jacket-formal',
                  'name': 'Leather Jacket Formal',
                  'description':
                      'A classic leather jacket for formal occasions',
                  'matchScore': 0.92,
                  'reasons': ['Strong face shape match', 'Formal style vibe'],
                  'stylingTips': 'Keep accessories minimal',
                  'maintenance': 'Wipe clean regularly',
                  'bestFor': 'Daily wear',
                },
                'alternatives': [],
              },
            },
          ),
        ),
      );

      expect(find.text('Outfit Analysis'), findsOneWidget);
      expect(find.byIcon(Icons.share_outlined), findsOneWidget);
      expect(find.byIcon(Icons.arrow_back_rounded), findsOneWidget);
    });

    testWidgets('renders appearance profile fields', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: OutfitAnalysisScreen(
            analysisResult: {
              'appearance': {
                'faceShape': 'oval',
                'skinTone': 'W30',
                'bodyType': 'average',
                'styleType': 'casual',
              },
              'confidence': 0.78,
              'needs_more_data': false,
            },
          ),
        ),
      );

      expect(find.text('Your Appearance Profile'), findsOneWidget);
      expect(find.text('Face Shape: oval'), findsOneWidget);
      expect(find.text('Skin Tone: W30'), findsOneWidget);
      expect(find.text('Body Type: average'), findsOneWidget);
      expect(find.text('Style Vibe: casual'), findsOneWidget);
    });

    testWidgets('renders confidence indicator', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: OutfitAnalysisScreen(
            analysisResult: {
              'appearance': {
                'faceShape': 'oval',
                'skinTone': 'W30',
                'bodyType': 'average',
                'styleType': 'casual',
              },
              'confidence': 0.78,
              'needs_more_data': false,
            },
          ),
        ),
      );

      expect(find.text('Confidence: 78%'), findsOneWidget);
    });

    testWidgets('renders needs_more_data warning', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: OutfitAnalysisScreen(
            analysisResult: {
              'appearance': {'faceShape': 'oval'},
              'confidence': 0.5,
              'needs_more_data': true,
            },
          ),
        ),
      );

      expect(find.text('Needs more data'), findsOneWidget);
    });

    testWidgets('renders recommendation card', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: OutfitAnalysisScreen(
            analysisResult: {
              'appearance': {
                'faceShape': 'oval',
                'skinTone': 'W30',
                'bodyType': 'average',
                'styleType': 'casual',
              },
              'confidence': 0.78,
              'needs_more_data': false,
              'recommendations': {
                'top': {
                  'id': 'leather-jacket-formal',
                  'name': 'Leather Jacket Formal',
                  'description':
                      'A classic leather jacket for formal occasions',
                  'matchScore': 0.92,
                  'reasons': ['Strong face shape match'],
                  'stylingTips': 'Keep accessories minimal',
                  'maintenance': 'Wipe clean regularly',
                  'bestFor': 'Daily wear',
                },
                'alternatives': [
                  {
                    'id': 'cotton-blazer-business',
                    'name': 'Cotton Blazer Business',
                    'description': 'A crisp cotton blazer',
                    'matchScore': 0.78,
                    'reasons': ['Good color harmony'],
                    'stylingTips': 'Pair with a white shirt',
                    'maintenance': 'Dry clean only',
                    'bestFor': 'Work environment',
                  },
                ],
              },
            },
          ),
        ),
      );

      expect(find.text('Recommended for you'), findsOneWidget);
      expect(find.text('Leather Jacket Formal'), findsOneWidget);
      expect(find.text('92% match'), findsOneWidget); // 0.92 * 100 rounded
      expect(find.text('Why this works for you:'), findsOneWidget);
      expect(find.text('Strong face shape match'), findsOneWidget);
    });

    testWidgets('renders save profile button', (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: OutfitAnalysisScreen(
            analysisResult: {
              'appearance': {
                'faceShape': 'oval',
                'skinTone': 'W30',
                'bodyType': 'average',
                'styleType': 'casual',
              },
              'confidence': 0.78,
              'needs_more_data': false,
            },
          ),
        ),
      );

      expect(find.text('Save Profile'), findsOneWidget);
    });

    testWidgets('renders see recommendations button', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: OutfitAnalysisScreen(
            analysisResult: {
              'appearance': {
                'faceShape': 'oval',
                'skinTone': 'W30',
                'bodyType': 'average',
                'styleType': 'casual',
              },
              'confidence': 0.78,
              'needs_more_data': false,
            },
          ),
        ),
      );

      expect(find.text('See Recommendations'), findsOneWidget);
    });
  });
}
