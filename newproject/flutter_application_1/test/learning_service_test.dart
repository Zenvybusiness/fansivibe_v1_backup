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
  });
}
