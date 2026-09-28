import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:fansivibe/features/outfit_builder/data/outfit_models.dart';
import 'package:fansivibe/features/outfit_builder/data/outfit_repository.dart';
import 'package:fansivibe/features/outfit_builder/presentation/outfit_recommendation_screen.dart';

const String _uuid1 = '78ff3686-c950-4cd6-84c3-7e18d6634dfa';
const String _uuid2 = '4412f646-56a9-4afa-8717-b330da03b3d0';

Map<String, dynamic> _wire(List<String> reasons) => {
  'title': 'Office Outfit',
  'matchScore': 0.87,
  'components': [
    {
      'id': _uuid1,
      'name': 'White Tee',
      'category': 'tops',
      'color': 'white',
      'reason': 'Chosen tops piece for your Office outfit',
    },
    {
      'id': _uuid2,
      'name': 'Dark Jeans',
      'category': 'bottoms',
      'color': 'black',
      'reason': 'Chosen bottoms piece for your Office outfit',
    },
  ],
  'reasons': reasons,
  'colorHarmony': 'warm palette across 2 pieces: white, black.',
  'bodyFit': 'Assembled for a tailored fit across 2 pieces.',
  'occasionMatch': 'Matched for Office across 2 categories.',
  'styleScoreImpact': '87% ensemble match from 2 owned pieces.',
  'improvementSuggestion':
      'Consider adding footwear to complete the coverage.',
  'selectedOccasion': 'office',
  'selectedMood': 'classic',
  'selectedColorPalette': 'warm',
};

const OutfitGenerateRequest _request = OutfitGenerateRequest(
  occasion: 'office',
  mood: 'classic',
  fit: 'tailored',
  colorPalette: 'warm',
);

class _FakeRepo implements OutfitBuilderRepository {
  @override
  Future<OutfitResult> generateOutfit({
    required String occasion,
    required String mood,
    required String fit,
    required String colorPalette,
    String? seed,
    List<String>? preferredItemIds,
  }) async => OutfitResult.noneAvailable();

  @override
  Future<SavedOutfit?> saveOutfit({
    String? lookId,
    required String title,
    required Map<String, dynamic> snapshot,
    required String idempotencyKey,
  }) async => null;
}

Widget _harness(OutfitRecommendation rec) {
  return MaterialApp(
    home: OutfitRecommendationScreen(
      recommendation: rec,
      request: _request,
      outfitRepository: _FakeRepo(),
    ),
  );
}

void main() {
  group('OutfitRecommendation reasons (Phase 2 Step 2)', () {
    testWidgets('renders deterministic backend reasons verbatim', (
      WidgetTester tester,
    ) async {
      final rec = OutfitRecommendation.fromJson(_wire([
        'Picked for a Office occasion',
        'Covers 2 categories: tops, bottoms',
        'Matches your preferred palette',
        'Matches your preferred fit',
        'Uses an item you selected',
        'Matches the selected occasion',
        "Similar to outfits you've liked",
        'Previously worn combination',
      ]));
      await tester.pumpWidget(_harness(rec));
      await tester.pumpAndSettle();

      expect(find.text('Why This Look Works'), findsOneWidget);
      expect(find.text('Matches your preferred palette'), findsOneWidget);
      expect(find.text('Matches your preferred fit'), findsOneWidget);
      expect(find.text('Uses an item you selected'), findsOneWidget);
      expect(find.text('Matches the selected occasion'), findsOneWidget);
      expect(
        find.text("Similar to outfits you've liked"),
        findsOneWidget,
      );
      expect(find.text('Previously worn combination'), findsOneWidget);
    });

    testWidgets('empty reasons render fallback without crashing', (
      WidgetTester tester,
    ) async {
      final rec = OutfitRecommendation.fromJson(_wire([]));
      await tester.pumpWidget(_harness(rec));
      await tester.pumpAndSettle();

      expect(find.text('Why This Look Works'), findsOneWidget);
      expect(
        find.text('No grounded explanation available.'),
        findsOneWidget,
      );
    });

    testWidgets('reasons keep backend order', (
      WidgetTester tester,
    ) async {
      final reasons = [
        'Picked for a Office occasion',
        'Covers 2 categories: tops, bottoms',
        'Matches your preferred palette',
        'Uses an item you selected',
      ];
      final rec = OutfitRecommendation.fromJson(_wire(reasons));
      await tester.pumpWidget(_harness(rec));
      await tester.pumpAndSettle();

      final positions = [
        for (final r in reasons) tester.getTopLeft(find.text(r)).dy,
      ];
      final sortedPositions = List<double>.from(positions)..sort();
      expect(positions, sortedPositions);
    });
  });
}
