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
                'alternatives': <dynamic>[],
              },
            },
          ),
        ),
      );

      expect(find.text('Outfit Analysis'), findsOneWidget);
      expect(find.byIcon(Icons.share_outlined), findsOneWidget);
      expect(find.byIcon(Icons.arrow_back_rounded), findsOneWidget);
    });

    testWidgets('renders appearance profile fields when all genuine values present', (
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

    testWidgets('renders confidence indicator when genuine confidence provided', (
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

    testWidgets('renders recommendation card without fabricated match percentage', (
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
                  'reasons': ['Strong face shape match'],
                  'stylingTips': 'Keep accessories minimal',
                  'maintenance': 'Wipe clean regularly',
                  'bestFor': 'Daily wear',
                },
              },
            },
          ),
        ),
      );

      expect(find.text('Recommended for you'), findsOneWidget);
      expect(find.text('Leather Jacket Formal'), findsOneWidget);
      // Fabricated match score badge is removed per Phase 3 & 4 policy
      expect(find.textContaining('% match'), findsNothing);
      expect(find.text('Why it may suit you'), findsOneWidget);
      expect(find.text('Strong face shape match'), findsOneWidget);
      expect(find.text('Considerations'), findsOneWidget);
      expect(find.text('Maintenance: Wipe clean regularly'), findsOneWidget);
      expect(find.text('Styling tip: Keep accessories minimal'), findsOneWidget);
      expect(find.text('Best for: Daily wear'), findsOneWidget);
    });

    testWidgets('missing face shape never defaults to round or oval', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: OutfitAnalysisScreen(
            analysisResult: {
              'appearance': {
                'faceShape': '',
                'skinTone': '',
                'bodyType': '',
              },
            },
          ),
        ),
      );

      expect(find.text('Face Shape: Unable to determine from this photo'), findsOneWidget);
      expect(find.textContaining('round'), findsNothing);
      expect(find.textContaining('oval'), findsNothing);
    });

    testWidgets('missing confidence never becomes a fabricated percentage', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: OutfitAnalysisScreen(
            analysisResult: {
              'appearance': {'faceShape': 'oval'},
              // Missing confidence: must not fabricate 0% or any percentage
              'needs_more_data': false,
            },
          ),
        ),
      );

      expect(find.text('Confidence unavailable'), findsOneWidget);
      expect(find.textContaining('Confidence: 0%'), findsNothing);
      expect(find.textContaining('%'), findsNothing);
    });

    testWidgets('missing recommendation score never becomes 99% or fabricated badge', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: OutfitAnalysisScreen(
            analysisResult: {
              'appearance': {'faceShape': 'round'},
              'confidence': 0.38,
              'needs_more_data': true,
              'recommendations': {
                'top': {
                  'name': 'Classic Pompadour',
                  'description': 'A polished look',
                  'matchScore': 0.99,
                  'reasons': ['Vertical emphasis suits a round face'],
                },
              },
            },
          ),
        ),
      );

      expect(find.text('Classic Pompadour'), findsOneWidget);
      expect(find.textContaining('99% match'), findsNothing);
      expect(find.textContaining('% match'), findsNothing);
      expect(find.textContaining('Reasons may include face shape match'), findsNothing);
    });

    testWidgets('empty or malformed analysis results never produce personalized mock recommendations', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        const MaterialApp(home: OutfitAnalysisScreen()),
      );

      expect(find.text('Face Shape: Unable to determine from this photo'), findsOneWidget);
      expect(find.text('Skin Tone: Not detected'), findsOneWidget);
      expect(find.text('Body Type: Not enough visual information'), findsOneWidget);
      expect(find.text('Confidence unavailable'), findsOneWidget);
      expect(find.text('Recommended for you'), findsNothing);
      expect(find.textContaining('classic_pompadour'), findsNothing);
      expect(find.textContaining('Classic Pompadour'), findsNothing);
      expect(find.textContaining('% match'), findsNothing);
    });

    testWidgets('partial results display only supported attributes and honest placeholders', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: OutfitAnalysisScreen(
            analysisResult: {
              'appearance': {
                'faceShape': 'square',
                'skinTone': '',
                'bodyType': '',
                'styleType': '',
              },
              'confidence': 0.35,
              'needs_more_data': true,
            },
          ),
        ),
      );

      expect(find.text('Face Shape: square'), findsOneWidget);
      expect(find.text('Skin Tone: Not detected'), findsOneWidget);
      expect(find.text('Body Type: Not enough visual information'), findsOneWidget);
      expect(find.textContaining('Style Vibe'), findsNothing);
      expect(find.text('Confidence: 35%'), findsOneWidget);
      expect(find.text('Recommended for you'), findsNothing);
      expect(
        find.text('Outfit observations are unavailable in this result.'),
        findsOneWidget,
      );
      expect(find.textContaining('No clothing items detected'), findsNothing);
    });

    testWidgets('backend errors show an error state and allow retry', (
      WidgetTester tester,
    ) async {
      bool retryTapped = false;
      await tester.pumpWidget(
        MaterialApp(
          home: OutfitAnalysisScreen(
            analysisResult: const {
              'error': {
                'message': 'We couldn\'t finish this request. Please try again.',
                'details': {'reason': 'analyzer_timeout'},
              },
            },
            onRetry: () => retryTapped = true,
          ),
        ),
      );

      expect(find.text('Analysis Failed'), findsOneWidget);
      expect(find.text('analyzer_timeout'), findsOneWidget);
      expect(find.text('Try Again'), findsOneWidget);

      await tester.tap(find.text('Try Again'));
      expect(retryTapped, isTrue);
    });

    testWidgets('renders the live appearance snapshot with genuine attributes and no fabricated score', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: OutfitAnalysisScreen(
            analysisResult: {
              'appearance': {
                'faceShape': 'round',
                'skinTone': '',
                'bodyType': '',
                'styleType': '',
                'sourceRunId': 'transient-id',
              },
              'confidence': 0.38,
              'needs_more_data': true,
              'recommendations': {
                'top': {
                  'id': 'classic_pompadour',
                  'name': 'Classic Pompadour',
                  'description': 'A polished, formal alternative.',
                  'matchScore': 0.99,
                  'reasons': ['Vertical emphasis suits a round face'],
                  'stylingTips': 'Strong-hold pomade',
                  'maintenance': 'High',
                  'bestFor': 'Oval, Round, and Square face shapes',
                },
                'alternatives': <dynamic>[],
              },
            },
          ),
        ),
      );

      expect(find.text('Face Shape: round'), findsOneWidget);
      expect(find.text('Skin Tone: Not detected'), findsOneWidget);
      expect(find.text('Body Type: Not enough visual information'), findsOneWidget);
      expect(find.text('Confidence: 38%'), findsOneWidget);
      expect(find.text('Classic Pompadour'), findsOneWidget);
      expect(find.text('Why it may suit you'), findsOneWidget);
      expect(find.text('Vertical emphasis suits a round face'), findsOneWidget);
      expect(find.text('Considerations'), findsOneWidget);
      expect(find.text('Maintenance: High'), findsOneWidget);
      expect(find.text('Styling tip: Strong-hold pomade'), findsOneWidget);
      expect(find.text('Best for: Oval, Round, and Square face shapes'), findsOneWidget);
      expect(find.text('Needs more data'), findsOneWidget);
      expect(find.textContaining('General Styling Advice'), findsOneWidget);
      // Verified: fabricated 99% match badge removed
      expect(find.textContaining('99% match'), findsNothing);
      expect(find.textContaining('% match'), findsNothing);
    });

    testWidgets('long text and attribute chips do not overflow on narrow screens', (
      WidgetTester tester,
    ) async {
      tester.view.physicalSize = const Size(320, 640);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      FlutterErrorDetails? errorDetails;
      final originalOnError = FlutterError.onError;
      FlutterError.onError = (FlutterErrorDetails details) {
        errorDetails = details;
      };

      await tester.pumpWidget(
        MaterialApp(
          home: OutfitAnalysisScreen(
            analysisResult: {
              'appearance': {
                'faceShape': '',
                'skinTone': '',
                'bodyType': '',
              },
              'confidence': 0.38,
              'needs_more_data': true,
              'recommendations': {
                'top': {
                  'name': 'Extremely Long Recommendation Look Name For Testing Overflow Resilience',
                  'description': 'A detailed explanation that spans multiple lines to verify text wrap layout integrity.',
                  'reasons': [
                    'Very long detailed reason outlining why vertical volume balances width for specific facial geometry without overflowing',
                  ],
                },
              },
            },
          ),
        ),
      );
      await tester.pumpAndSettle();
      FlutterError.onError = originalOnError;

      expect(errorDetails, isNull);
      expect(find.text('Face Shape: Unable to determine from this photo'), findsOneWidget);
      expect(find.text('Body Type: Not enough visual information'), findsOneWidget);
    });

    testWidgets('renders save profile and see recommendations buttons', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: OutfitAnalysisScreen(
            analysisResult: {
              'appearance': {'faceShape': 'oval'},
              'confidence': 0.78,
              'needs_more_data': false,
            },
          ),
        ),
      );

      expect(find.text('Save Profile'), findsOneWidget);
      expect(find.text('See Recommendations'), findsOneWidget);
    });

    testWidgets('share button honestly reports the feature is unavailable', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: OutfitAnalysisScreen(
            analysisResult: {
              'appearance': {'faceShape': 'oval'},
              'confidence': 0.78,
              'needs_more_data': false,
            },
          ),
        ),
      );

      await tester.tap(find.byIcon(Icons.share_outlined));
      await tester.pump();

      expect(find.text('Share feature coming soon'), findsOneWidget);
    });

    testWidgets('renders integer confidence without crashing', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: OutfitAnalysisScreen(
            analysisResult: {
              'appearance': {'faceShape': 'oval'},
              'confidence': 1,
              'needs_more_data': false,
              'recommendations': {
                'top': {
                  'name': 'Test Look',
                  'matchScore': 1,
                  'reasons': ['Fits well', 42],
                },
              },
            },
          ),
        ),
      );

      expect(find.text('Confidence: 100%'), findsOneWidget);
      expect(find.text('Test Look'), findsOneWidget);
      expect(find.text('Fits well'), findsOneWidget);
      expect(find.text('42'), findsOneWidget);
      expect(find.textContaining('% match'), findsNothing);
    });

    testWidgets('missing recommendations produce the honest unavailable state with retry action', (
      WidgetTester tester,
    ) async {
      bool retried = false;
      await tester.pumpWidget(
        MaterialApp(
          home: OutfitAnalysisScreen(
            analysisResult: {
              'appearance': {'faceShape': 'oval'},
              'confidence': 0.75,
              'needs_more_data': false,
            },
            onRetry: () => retried = true,
          ),
        ),
      );

      expect(
        find.text('Personalized recommendation unavailable for this photo.'),
        findsOneWidget,
      );
      expect(find.text('Retry Analysis'), findsOneWidget);
      expect(find.text('Recommended for you'), findsNothing);
      expect(find.textContaining('Classic Pompadour'), findsNothing);

      await tester.tap(find.text('Retry Analysis'));
      expect(retried, isTrue);
    });

    testWidgets('an uncertain face shape never produces a round-face-specific claim', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: OutfitAnalysisScreen(
            analysisResult: {
              'appearance': {
                'faceShape': '', // Empty / inconclusive
              },
              'confidence': 0.38,
              'needs_more_data': true,
              'recommendations': {
                'top': {
                  'name': 'Classic Pompadour',
                  'description': 'A timeless pompadour with swept-back volume.',
                  'reasons': [
                    'Strongest match for your round face shape (+0.12 face-shape fit).',
                    'Vertical emphasis suits a round face',
                    'Pairs naturally with structured tailored pieces',
                  ],
                },
              },
            },
          ),
        ),
      );

      // Face shape fallback
      expect(find.text('Face Shape: Unable to determine from this photo'), findsOneWidget);
      // Face-shape-specific claims must be completely filtered out
      expect(find.textContaining('round face'), findsNothing);
      expect(find.textContaining('face shape'), findsNothing);
      // General non-face reason must be preserved
      expect(find.text('Pairs naturally with structured tailored pieces'), findsOneWidget);
    });

    testWidgets('loading state renders loading spinner and honest status', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: OutfitAnalysisScreen(
            isLoading: true,
          ),
        ),
      );

      expect(find.text('Analyzing Photo…'), findsOneWidget);
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
      expect(find.text('Your Appearance Profile'), findsNothing);
    });

    testWidgets('general catalog recommendations are labeled as general advice when data is incomplete', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: OutfitAnalysisScreen(
            analysisResult: {
              'appearance': {'faceShape': 'oval'},
              'confidence': 0.38,
              'needs_more_data': true,
              'recommendations': {
                'top': {
                  'name': 'Classic Pompadour',
                  'description': 'A timeless pompadour.',
                  'maintenance': 'High • Trim every 3-4 weeks',
                  'stylingTips': 'Strong-hold pomade',
                  'bestFor': 'Oval, Round, and Square face shapes',
                },
              },
            },
          ),
        ),
      );

      expect(find.text('General Styling Advice'), findsOneWidget);
      expect(
        find.text('General styling suggestion based on aesthetic principles because photo provided partial appearance data.'),
        findsOneWidget,
      );
      expect(find.text('Maintenance: High • Trim every 3-4 weeks'), findsOneWidget);
      expect(find.text('Styling tip: Strong-hold pomade'), findsOneWidget);
      expect(find.text('Best for: Oval, Round, and Square face shapes'), findsOneWidget);
    });

    testWidgets('garment-only partial shows the typed appearance failure', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: OutfitAnalysisScreen(
            analysisResult: const {
              'garment': {
                'category': 'tops',
                'color': 'navy',
                'material': 'cotton',
              },
              'appearance_error': {'reason': 'no_face_detected'},
            },
          ),
        ),
      );

      expect(find.text('Face Shape: Not detected in this photo'), findsOneWidget);
      expect(
        find.textContaining('No face was clearly visible'),
        findsOneWidget,
      );
      expect(find.text('tops'), findsOneWidget);
      expect(find.text('navy'), findsOneWidget);
      expect(find.textContaining('round'), findsNothing);
      expect(find.textContaining('oval'), findsNothing);
    });

    testWidgets(
      'garment-only generic appearance failure is not a face detection claim',
      (WidgetTester tester) async {
        await tester.pumpWidget(
          MaterialApp(
            home: OutfitAnalysisScreen(
              analysisResult: const {
                'garment': {
                  'category': 'tops',
                  'color': 'navy',
                  'material': 'cotton',
                },
                'appearance_error': {'reason': 'analysis_failed'},
              },
            ),
          ),
        );

        expect(
          find.text('Face Shape: Unable to determine from this photo'),
          findsOneWidget,
        );
        expect(
          find.textContaining('This part of the analysis could not be completed'),
          findsOneWidget,
        );
        expect(
          find.text('Face Shape: Not detected in this photo'),
          findsNothing,
        );
      },
    );

    testWidgets('appearance-only partial shows the typed garment failure', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: OutfitAnalysisScreen(
            analysisResult: const {
              'appearance': {'faceShape': 'oval'},
              'confidence': 0.6,
              'garment_error': {'reason': 'no_garment_detected'},
            },
          ),
        ),
      );

      expect(find.text('Face Shape: oval'), findsOneWidget);
      expect(
        find.textContaining('No clear outfit was visible'),
        findsOneWidget,
      );
      expect(find.text('Outfit observations are unavailable in this result.'), findsNothing);
    });
  });
}
