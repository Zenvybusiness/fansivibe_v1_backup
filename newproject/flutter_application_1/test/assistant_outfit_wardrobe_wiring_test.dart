import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:fansivibe/features/assistant/data/models.dart';
import 'package:fansivibe/features/assistant/data/offline_assistant.dart';
import 'package:fansivibe/features/assistant/domain/assistant_service.dart';
import 'package:fansivibe/features/assistant/presentation/widgets/assistant_widgets.dart';
import 'package:fansivibe/features/assistant/presentation/widgets/outfit_recommendation_card.dart';
import 'package:fansivibe/features/learning/data/models.dart';
import 'package:fansivibe/features/learning/learning_repository.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';

/// STEP 13.17 — wiring tests: `selectedItemIds` resolved against the
/// already-loaded learning wardrobe and passed to [OutfitRecommendationCard].
///
/// No network, no backend, no new data models: pure resolution plus the
/// existing [MessageBubble] composition rendering.

class _FakeLearningRepository implements LearningRepository {
  _FakeLearningRepository({List<WardrobeEntry> wardrobe = const []})
    : _wardrobe = List.of(wardrobe);

  final List<WardrobeEntry> _wardrobe;

  @override
  List<WardrobeEntry> get wardrobe => List.unmodifiable(_wardrobe);

  @override
  FaceProfile? get face => null;

  @override
  String? get styleType => null;

  @override
  List<String> get savedLooks => const [];

  @override
  List<String> get preferredOccasions => const [];

  @override
  List<LearningSignal> get signals => const [];

  @override
  int get styleScore => 0;

  @override
  Future<void> load() async {}

  @override
  void addItem(WardrobeEntry item) => _wardrobe.add(item);

  @override
  void setFace(FaceProfile face) {}

  @override
  void setStyleType(String value) {}

  @override
  void addSavedLook(String title) {}

  @override
  void addPreferredOccasion(String occasion) {}

  @override
  void recordSignal(String type, String label) {}

  @override
  void updateItem(String itemId, WardrobeEntry item) {}
}

const _wardrobe = [
  WardrobeItemData(
    id: '1',
    name: 'Merino Crew Neck',
    category: 'tops',
    color: 'Charcoal',
    material: 'Wool',
    isFavorite: true,
  ),
  WardrobeItemData(
    id: '2',
    name: 'Linen Button-Down',
    category: 'tops',
    color: 'White',
    material: 'Linen',
  ),
  WardrobeItemData(
    id: '9',
    name: 'Tapered Trousers',
    category: 'bottoms',
    color: 'Charcoal',
    material: 'Wool',
  ),
  WardrobeItemData(
    id: '18',
    name: 'Leather Chelsea Boots',
    category: 'footwear',
    color: 'Black',
    material: 'Leather',
  ),
];

OutfitIntelligence _intelligence({
  List<String> selectedIds = const ['1', '9'],
}) => OutfitIntelligence(
  selectedItemIds: selectedIds,
  outfitComposition: const OutfitComposition(
    topIds: ['1'],
    bottomIds: ['9'],
    outerwearIds: [],
    footwearIds: [],
    accessoryIds: [],
    styleScore: 0,
  ),
  occasion: 'date',
  stylingRationale: 'Charcoal knit works with charcoal trousers.',
  compatibilityRationale: 'Both items are owned and coordinate.',
  confidence: 0.9,
  explanation: 'Based on your wardrobe.',
  dataAvailability: 'full',
);

Widget _bubble({
  required AssistantMessage message,
  List<WardrobeItemData>? wardrobe,
}) => MaterialApp(
  home: Scaffold(
    body: SingleChildScrollView(
      child: MessageBubble(message: message, wardrobe: wardrobe),
    ),
  ),
);

void main() {
  group('resolveOutfitWardrobeItems', () {
    test('A. selected IDs resolve to matching items', () {
      final resolved = resolveOutfitWardrobeItems(
        selectedIds: const ['1', '9'],
        wardrobe: _wardrobe,
      );
      expect(resolved.map((i) => i.id), equals(['1', '9']));
      expect(
        resolved.map((i) => i.name),
        equals(['Merino Crew Neck', 'Tapered Trousers']),
      );
    });

    test('B. selectedItemIds order is preserved, not wardrobe order', () {
      final resolved = resolveOutfitWardrobeItems(
        selectedIds: const ['18', '1', '9'],
        wardrobe: _wardrobe,
      );
      expect(resolved.map((i) => i.id), equals(['18', '1', '9']));
    });

    test('C. missing IDs are skipped safely without throwing', () {
      final resolved = resolveOutfitWardrobeItems(
        selectedIds: const ['1', 'deleted-id', '9', 'ghost'],
        wardrobe: _wardrobe,
      );
      expect(resolved.map((i) => i.id), equals(['1', '9']));
    });

    test('D. empty IDs produce an empty list (static fallback)', () {
      expect(
        resolveOutfitWardrobeItems(selectedIds: const [], wardrobe: _wardrobe),
        isEmpty,
      );
      expect(
        resolveOutfitWardrobeItems(selectedIds: const ['1'], wardrobe: null),
        isEmpty,
      );
      expect(
        resolveOutfitWardrobeItems(
          selectedIds: const ['1'],
          wardrobe: const [],
        ),
        isEmpty,
      );
    });

    test('category strings are preserved verbatim for the card', () {
      final resolved = resolveOutfitWardrobeItems(
        selectedIds: const ['1', '9', '18'],
        wardrobe: _wardrobe,
      );
      expect(
        resolved.map((i) => i.category),
        equals(['tops', 'bottoms', 'footwear']),
      );
    });

    test('resolution never mutates the source intelligence IDs', () {
      final intelligence = _intelligence(
        selectedIds: const ['1', 'ghost', '9'],
      );
      resolveOutfitWardrobeItems(
        selectedIds: intelligence.selectedItemIds,
        wardrobe: _wardrobe,
      );
      expect(intelligence.selectedItemIds, equals(['1', 'ghost', '9']));
    });
  });

  group('AssistantService.wardrobe read-only accessor', () {
    test('empty when no learning repository is attached', () {
      final service = AssistantService();
      expect(service.wardrobe, isEmpty);
      service.dispose();
    });

    test('exposes the attached learning wardrobe as a copy', () {
      final service = AssistantService(
        learning: _FakeLearningRepository(
          wardrobe: const [
            WardrobeEntry(
              id: '1',
              name: 'Merino Crew Neck',
              category: 'tops',
              color: 'Charcoal',
            ),
            WardrobeEntry(
              id: '9',
              name: 'Tapered Trousers',
              category: 'bottoms',
              color: 'Charcoal',
            ),
          ],
        ),
      );
      expect(service.wardrobe.map((e) => e.id), equals(['1', '9']));
      expect(
        () => service.wardrobe.add(
          const WardrobeEntry(
            id: 'x',
            name: 'X',
            category: 'tops',
            color: 'Red',
          ),
        ),
        throwsUnsupportedError,
      );
      service.dispose();
    });
  });

  group('MessageBubble outfit composition rendering', () {
    testWidgets('E. resolved items display as category chips', (tester) async {
      final message = AssistantMessage(
        role: 'assistant',
        text: 'For date, a charcoal pairing.',
        outfitIntelligence: _intelligence(),
      );
      await tester.pumpWidget(_bubble(message: message, wardrobe: _wardrobe));
      await tester.pumpAndSettle();

      expect(find.byType(OutfitRecommendationCard), findsOneWidget);
      expect(find.text('Merino Crew Neck'), findsOneWidget);
      expect(find.text('Tapered Trousers'), findsOneWidget);
      expect(find.text('Top'), findsOneWidget);
      expect(find.text('Bottom'), findsOneWidget);
      // Unselected wardrobe items must not render.
      expect(find.text('Linen Button-Down'), findsNothing);
      expect(find.text('Leather Chelsea Boots'), findsNothing);
    });

    testWidgets('E. missing IDs render only the resolvable items', (
      tester,
    ) async {
      final message = AssistantMessage(
        role: 'assistant',
        text: 'For date, a charcoal pairing.',
        outfitIntelligence: _intelligence(
          selectedIds: const ['1', 'deleted-id'],
        ),
      );
      await tester.pumpWidget(_bubble(message: message, wardrobe: _wardrobe));
      await tester.pumpAndSettle();

      expect(find.text('Merino Crew Neck'), findsOneWidget);
      expect(find.text('Tapered Trousers'), findsNothing);
    });

    testWidgets('empty selection keeps the historical empty composition', (
      tester,
    ) async {
      final message = AssistantMessage(
        role: 'assistant',
        text: 'For date, a charcoal pairing.',
        outfitIntelligence: _intelligence(selectedIds: const []),
      );
      await tester.pumpWidget(_bubble(message: message, wardrobe: _wardrobe));
      await tester.pumpAndSettle();

      expect(find.byType(OutfitRecommendationCard), findsOneWidget);
      expect(find.text('Your Outfit'), findsOneWidget);
      expect(find.text('Merino Crew Neck'), findsNothing);
    });

    testWidgets('null wardrobe falls back exactly as before', (tester) async {
      final message = AssistantMessage(
        role: 'assistant',
        text: 'For date, a charcoal pairing.',
        outfitIntelligence: _intelligence(),
      );
      await tester.pumpWidget(_bubble(message: message));
      await tester.pumpAndSettle();

      expect(find.byType(OutfitRecommendationCard), findsOneWidget);
      expect(find.text('Your Outfit'), findsOneWidget);
      expect(find.text('Merino Crew Neck'), findsNothing);
    });
  });

  group('Save behavior unchanged', () {
    test(
      'F. snapshot keeps full selectedItemIds even when display skips one',
      () {
        final intelligence = _intelligence(
          selectedIds: const ['1', 'deleted-id', '9'],
        );
        // Display resolves only what exists...
        final resolved = resolveOutfitWardrobeItems(
          selectedIds: intelligence.selectedItemIds,
          wardrobe: _wardrobe,
        );
        expect(resolved.map((i) => i.id), equals(['1', '9']));
        // ...while save still snapshots the untouched intelligence.
        final request = OutfitSaveRequest.fromOutfitIntelligence(intelligence);
        expect(request.lookId, isNull);
        expect(request.sourceContext, equals('outfit'));
        expect(
          request.snapshot['selectedItemIds'],
          equals(['1', 'deleted-id', '9']),
        );
      },
    );
  });

  group('OUTFIT parsing unchanged', () {
    test('G. wire JSON still parses to retained IDs and composition', () {
      const json = '''
        {
          "intent": "outfit",
          "text": "For date, a charcoal pairing.",
          "outfitIntelligence": {
            "selectedItemIds": ["1", "9"],
            "outfitComposition": {
              "topIds": ["1"],
              "bottomIds": ["9"],
              "outerwearIds": [],
              "footwearIds": [],
              "accessoryIds": [],
              "styleScore": 0
            },
            "occasion": "date",
            "stylingRationale": "r",
            "compatibilityRationale": "c",
            "confidence": 0.9,
            "explanation": "e",
            "dataAvailability": "full"
          }
        }
      ''';
      final reply = AssistantReply.fromJson(
        jsonDecode(json) as Map<String, dynamic>,
      );
      expect(reply.outfitIntelligence?.selectedItemIds, equals(['1', '9']));
      expect(reply.outfitIntelligence?.outfitComposition.topIds, equals(['1']));
      expect(reply.outfitIntelligence?.occasion, equals('date'));
    });
  });

  group('WARDROBE assistant behavior unchanged', () {
    test('H. offline wardrobe reply carries no outfit intelligence', () {
      const context = AssistantUserContext(
        wardrobe: [
          WardrobeEntry(
            id: '1',
            name: 'Merino Crew Neck',
            category: 'tops',
            color: 'Charcoal',
          ),
        ],
      );
      final reply = OfflineAssistant().replyFor('show my wardrobe', context);
      expect(reply.intent, equals('wardrobe'));
      expect(reply.outfitIntelligence, isNull);
      expect(reply.cards.single.kind, equals('wardrobe'));
    });

    testWidgets('H. wardrobe message renders cards, never the outfit card', (
      tester,
    ) async {
      const context = AssistantUserContext();
      final reply = OfflineAssistant().replyFor('show my wardrobe', context);
      final message = AssistantMessage(
        role: 'assistant',
        text: reply.text,
        cards: reply.cards,
        outfitIntelligence: reply.outfitIntelligence,
      );
      await tester.pumpWidget(_bubble(message: message, wardrobe: _wardrobe));
      await tester.pumpAndSettle();

      expect(find.byType(OutfitRecommendationCard), findsNothing);
      expect(find.text('Wardrobe Health'), findsOneWidget);
    });
  });
}
