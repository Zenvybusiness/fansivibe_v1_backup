import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:fansivibe/features/assistant/data/models.dart';
import 'package:fansivibe/features/assistant/presentation/widgets/assistant_widgets.dart';
import 'package:fansivibe/features/assistant/presentation/widgets/outfit_recommendation_card.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';

void main() {
  final sampleWardrobe = [
    const WardrobeItemData(
      id: 'top-1',
      name: 'Silk Blend Knit',
      category: 'tops',
      color: 'Charcoal',
    ),
    const WardrobeItemData(
      id: 'bottom-1',
      name: 'Pleated Linen Trousers',
      category: 'bottoms',
      color: 'Navy',
    ),
    const WardrobeItemData(
      id: 'shoes-1',
      name: 'Leather Derbies',
      category: 'footwear',
      color: 'Brown',
    ),
    const WardrobeItemData(
      id: 'unselected-1',
      name: 'Canvas Sneaker',
      category: 'footwear',
      color: 'White',
    ),
  ];

  OutfitIntelligence sampleIntelligence({
    int? matchScore = 88,
    double confidence = 0.88,
    String? status = 'success',
    List<String> selectedIds = const ['top-1', 'bottom-1', 'shoes-1'],
    String occasion = 'Date Night',
  }) {
    return OutfitIntelligence(
      occasion: occasion,
      confidence: confidence,
      matchScore: matchScore,
      status: status,
      outfitComposition: const OutfitComposition(
        topIds: ['top-1'],
        bottomIds: ['bottom-1'],
        footwearIds: ['shoes-1'],
        outerwearIds: [],
        accessoryIds: [],
        styleScore: 88,
      ),
      stylingRationale: 'Linen trousers and silk knit provide balanced texture contrast.',
      compatibilityRationale: 'Ensemble components matched with a score of 88% for Date Night.',
      explanation: 'Balanced texture contrast',
      dataAvailability: 'full',
      selectedItemIds: selectedIds,
    );
  }

  Widget buildBubble({
    required AssistantMessage message,
    List<WardrobeItemData>? wardrobe,
    void Function(SuggestionCard card)? onCardAction,
    Future<bool> Function(OutfitIntelligence)? onOutfitSave,
  }) {
    return MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: MessageBubble(
            message: message,
            wardrobe: wardrobe,
            onCardAction: onCardAction,
            onOutfitSave: onOutfitSave,
          ),
        ),
      ),
    );
  }

  group('Batch 4B.4: Assistant Response Harmonization', () {
    testWidgets('1. Only one outfit recommendation card is rendered (duplicate eliminated)', (
      tester,
    ) async {
      final message = AssistantMessage(
        role: 'assistant',
        text: 'For date night, here is a coordinated ensemble.',
        cards: const [
          SuggestionCard(
            kind: 'outfit',
            title: 'Date Night Coordinated',
            subtitle: 'Silk knit with pleated trousers',
            score: 88,
            items: ['Silk Blend Knit - Tops', 'Pleated Linen Trousers - Bottoms'],
            action: 'open_outfit',
          ),
        ],
        outfitIntelligence: sampleIntelligence(),
      );

      await tester.pumpWidget(buildBubble(message: message, wardrobe: sampleWardrobe));
      await tester.pumpAndSettle();

      // Exactly ONE outfit recommendation card is rendered
      expect(find.byType(OutfitRecommendationCard), findsOneWidget);

      // The duplicate outfit SuggestionCardView is suppressed
      expect(find.text('Date Night Coordinated'), findsNothing);
    });

    testWidgets('2. Actual selected garments and categories are shown', (
      tester,
    ) async {
      final message = AssistantMessage(
        role: 'assistant',
        text: 'Here is your outfit recommendation.',
        cards: const [
          SuggestionCard(
            kind: 'outfit',
            title: 'Date Night Ensemble',
            subtitle: '',
            action: 'open_outfit',
          ),
        ],
        outfitIntelligence: sampleIntelligence(),
      );

      await tester.pumpWidget(buildBubble(message: message, wardrobe: sampleWardrobe));
      await tester.pumpAndSettle();

      // Shows actual selected garments
      expect(find.text('Silk Blend Knit'), findsOneWidget);
      expect(find.text('Pleated Linen Trousers'), findsOneWidget);
      expect(find.text('Leather Derbies'), findsOneWidget);

      // Shows resolved category headers
      expect(find.text('Top'), findsOneWidget);
      expect(find.text('Bottom'), findsOneWidget);
      expect(find.text('Footwear'), findsOneWidget);

      // Unselected item is NOT shown
      expect(find.text('Canvas Sneaker'), findsNothing);

      // Canonical reasons are displayed
      expect(
        find.text('Linen trousers and silk knit provide balanced texture contrast.'),
        findsOneWidget,
      );
    });

    testWidgets('3. Ensemble Match is displayed accurately', (
      tester,
    ) async {
      final message = AssistantMessage(
        role: 'assistant',
        text: 'Recommended ensemble.',
        outfitIntelligence: sampleIntelligence(matchScore: 88, confidence: 0.88),
      );

      await tester.pumpWidget(buildBubble(message: message, wardrobe: sampleWardrobe));
      await tester.pumpAndSettle();

      // Header pill displays Ensemble Match
      expect(find.text('88% Ensemble Match'), findsOneWidget);

      // Score row displays Ensemble Match: 88%
      expect(find.text('Ensemble Match: 88%'), findsOneWidget);
    });

    testWidgets('4. Confidence and probability wording is absent', (
      tester,
    ) async {
      final message = AssistantMessage(
        role: 'assistant',
        text: 'Recommended look.',
        outfitIntelligence: sampleIntelligence(matchScore: 88, confidence: 0.88),
      );

      await tester.pumpWidget(buildBubble(message: message, wardrobe: sampleWardrobe));
      await tester.pumpAndSettle();

      // Unsupported confidence/probability claims must be absent
      expect(find.textContaining('confident'), findsNothing);
      expect(find.textContaining('probability'), findsNothing);
      expect(find.textContaining('guaranteed'), findsNothing);
      expect(find.textContaining('Style Score:'), findsNothing);
    });

    testWidgets('5. Empty and error states do not render as successful outfits', (
      tester,
    ) async {
      final emptyMessage = AssistantMessage(
        role: 'assistant',
        text: 'Your wardrobe needs clothes before I can generate outfits.',
        cards: const [
          SuggestionCard(
            kind: 'outfit',
            title: 'Empty Wardrobe',
            subtitle: 'Add tops and bottoms to your wardrobe to get recommendations.',
            action: 'open_wardrobe',
          ),
        ],
        outfitIntelligence: sampleIntelligence(
          status: 'empty_wardrobe',
          matchScore: null,
          confidence: 0.0,
          selectedIds: const [],
        ),
      );

      await tester.pumpWidget(buildBubble(message: emptyMessage, wardrobe: const []));
      await tester.pumpAndSettle();

      // Must NOT render OutfitRecommendationCard
      expect(find.byType(OutfitRecommendationCard), findsNothing);
      expect(find.text('Your Outfit'), findsNothing);
      expect(find.text('Save'), findsNothing);

      // Must render empty state card with functional navigation action
      expect(find.text('Empty Wardrobe'), findsOneWidget);
      expect(find.text('Open'), findsOneWidget);
    });

    testWidgets('6. Existing assistant text and unrelated suggestion cards remain functional', (
      tester,
    ) async {
      final message = AssistantMessage(
        role: 'assistant',
        text: 'Here is your outfit and a hairstyle idea.',
        cards: const [
          SuggestionCard(
            kind: 'outfit',
            title: 'Casual Outfit',
            subtitle: '',
            action: 'open_outfit',
          ),
          SuggestionCard(
            kind: 'hairstyle',
            title: 'Textured Quiff',
            subtitle: 'Clean faded sides with styled top volume',
            score: 92,
            action: 'open_hairstyle',
          ),
        ],
        outfitIntelligence: sampleIntelligence(),
      );

      await tester.pumpWidget(buildBubble(message: message, wardrobe: sampleWardrobe));
      await tester.pumpAndSettle();

      // Assistant text preserved
      expect(find.text('Here is your outfit and a hairstyle idea.'), findsOneWidget);

      // Unrelated hairstyle card rendered
      expect(find.text('Textured Quiff'), findsOneWidget);
      expect(find.text('92% match'), findsOneWidget);

      // Outfit card rendered via OutfitRecommendationCard
      expect(find.byType(OutfitRecommendationCard), findsOneWidget);

      // Duplicate outfit SuggestionCardView is suppressed
      expect(find.text('Casual Outfit'), findsNothing);
    });

    testWidgets('7. Navigation actions still work from both cards', (
      tester,
    ) async {
      SuggestionCard? tappedCard;
      final message = AssistantMessage(
        role: 'assistant',
        text: 'Explore your look.',
        cards: const [
          SuggestionCard(
            kind: 'outfit',
            title: 'Date Night Refined',
            subtitle: '',
            action: 'open_outfit',
          ),
          SuggestionCard(
            kind: 'grooming',
            title: 'Stubble Beard',
            subtitle: 'Neat shape',
            action: 'open_grooming',
          ),
        ],
        outfitIntelligence: sampleIntelligence(),
      );

      await tester.pumpWidget(
        buildBubble(
          message: message,
          wardrobe: sampleWardrobe,
          onCardAction: (card) => tappedCard = card,
        ),
      );
      await tester.pumpAndSettle();

      // Tap Open Outfit on OutfitRecommendationCard
      expect(find.text('Open Outfit'), findsOneWidget);
      await tester.scrollUntilVisible(
        find.text('Open Outfit'),
        100,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Open Outfit'));
      await tester.pumpAndSettle();

      expect(tappedCard, isNotNull);
      expect(tappedCard!.action, equals('open_outfit'));

      // Tap Open on the grooming SuggestionCardView
      tappedCard = null;
      await tester.scrollUntilVisible(
        find.text('Open'),
        -100,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Open'));
      await tester.pumpAndSettle();

      expect(tappedCard, isNotNull);
      expect(tappedCard!.action, equals('open_grooming'));
    });
  });
}
