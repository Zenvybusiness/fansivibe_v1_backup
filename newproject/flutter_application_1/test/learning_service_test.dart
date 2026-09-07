import 'package:flutter_test/flutter_test.dart';

import 'package:fansivibe/features/learning/data/models.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';

void main() {
  setUp(LearningService.instance.resetForTest);

  group('UserModel serialization', () {
    test('round-trips through JSON', () {
      final model = UserModel(
        wardrobe: [
          const WardrobeEntry(
            id: '99',
            name: 'Silk Blouse',
            category: 'tops',
            color: 'Blush',
            material: 'Silk',
          ),
        ],
        face: const FaceProfile(
          faceShape: 'Oval',
          skinTone: 'Warm Medium',
          styleType: 'Modern Minimalist',
        ),
        savedLooks: const ['Modern Minimalist'],
        preferredOccasions: const ['date'],
      );

      final decoded = UserModel.decode(model.encode());

      expect(decoded.wardrobe.length, 1);
      expect(decoded.wardrobe.first.name, 'Silk Blouse');
      expect(decoded.face?.faceShape, 'Oval');
      expect(decoded.face?.styleType, 'Modern Minimalist');
      expect(decoded.savedLooks, ['Modern Minimalist']);
      expect(decoded.preferredOccasions, ['date']);
    });
  });

  group('LearningService', () {
    test('seeds a default wardrobe', () {
      expect(LearningService.instance.wardrobe.length, 24);
    });

    test('adds an item and records a signal', () {
      LearningService.instance.addItem(
        const WardrobeEntry(
          id: '25',
          name: 'Bomber Jacket',
          category: 'outerwear',
          color: 'Olive',
        ),
      );

      expect(LearningService.instance.wardrobe.length, 25);
      expect(LearningService.instance.signals.last.type, 'item_added');
      expect(
        LearningService.instance.signals.last.label,
        'Bomber Jacket (outerwear)',
      );
    });

    test('stores face profile', () {
      LearningService.instance.setFace(
        const FaceProfile(
          faceShape: 'Square',
          skinTone: 'Deep',
          styleType: 'Bold',
        ),
      );

      expect(LearningService.instance.face?.faceShape, 'Square');
      expect(LearningService.instance.styleType, isNull);
    });

    test('records saved looks and occasions once', () {
      LearningService.instance.addSavedLook('Date Night');
      LearningService.instance.addSavedLook('Date Night');
      LearningService.instance.addPreferredOccasion('date');
      LearningService.instance.addPreferredOccasion('date');

      expect(LearningService.instance.savedLooks, ['Date Night']);
      expect(LearningService.instance.preferredOccasions, ['date']);
    });

    test('style score rises as the model fills in', () {
      final base = LearningService.instance.styleScore;
      expect(base, greaterThanOrEqualTo(60));

      for (var i = 0; i < 5; i++) {
        LearningService.instance.addItem(
          WardrobeEntry(
            id: 'x$i',
            name: 'Item $i',
            category: 'tops',
            color: 'Black',
          ),
        );
      }
      LearningService.instance.addSavedLook('Smart Business');

      expect(LearningService.instance.styleScore, greaterThan(base));
    });

    test('updates matching item and preserves unrelated items', () {
      // Start with the default wardrobe (24 items including item '1')
      final item1 = WardrobeEntry(
        id: '1',
        name: 'Merino Crew Neck',
        category: 'tops',
        color: 'Charcoal',
        isFavorite: true,
      );
      final item2 = WardrobeEntry(
        id: '2',
        name: 'Linen Button-Down',
        category: 'tops',
        color: 'White',
      );

      // The default wardrobe already has item '1', so we can update it
      LearningService.instance.updateItem('1', item1);
      expect(LearningService.instance.wardrobe.length, 24);
      expect(LearningService.instance.wardrobe[0].name, 'Merino Crew Neck');

      // Update the first item with new data
      final updated = WardrobeEntry(
        id: '1',
        name: 'Updated Crew Neck',
        category: 'tops',
        color: 'Navy',
        isFavorite: false,
      );
      LearningService.instance.updateItem('1', updated);

      // The updated item should replace the old one at index 0
      expect(LearningService.instance.wardrobe.length, 24);
      expect(LearningService.instance.wardrobe[0].name, 'Updated Crew Neck');
      expect(LearningService.instance.wardrobe[0].color, 'Navy');
      expect(LearningService.instance.wardrobe[0].isFavorite, false);

      // Item at index 1 should be unchanged (Linen Button-Down)
      expect(LearningService.instance.wardrobe[1].name, 'Linen Button-Down');
    });

    test('records an item_updated signal', () {
      // Use an ID that exists in the default wardrobe (e.g., '1' = 'Merino Crew Neck')
      final item = WardrobeEntry(
        id: '1',
        name: 'Updated Crew Neck',
        category: 'tops',
        color: 'Navy',
      );

      LearningService.instance.updateItem('1', item);

      expect(LearningService.instance.signals.isNotEmpty, isTrue);
      expect(LearningService.instance.signals.last.type, 'item_updated');
      expect(LearningService.instance.signals.last.label, 'Updated Crew Neck (tops) updated');
    });

    test('handles unknown ID safely - no crash', () {
      // Updating an ID that doesn't exist in the current model should be safe
      // The default wardrobe has IDs '1' through '24', so '999' is safe
      final item = WardrobeEntry(
        id: '999',
        name: 'Ghost Item',
        category: 'tops',
        color: 'Black',
      );

      // This should not throw or crash the service
      LearningService.instance.updateItem('999', item);

      // The wardrobe should be unchanged (still has 24 items from default)
      expect(LearningService.instance.wardrobe.length, 24);
    });
  });
}
