import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';

import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';

void main() {
  group('MediaRef', () {
    final tMediaRef = MediaRef(
      objectKey: 'users/1/wardrobe/image1.jpg',
      mediaType: 'image/jpeg',
      width: 1024,
      height: 768,
      sizeBytes: 245760,
      contentHash: 'abc123def456',
      isGenerated: false,
      uploadedAt: DateTime.parse('2024-01-15T00:00:00Z'),
    );

    test('fromJson/toJson roundtrip', () async {
      final json = tMediaRef.toJson();
      final roundtrip = MediaRef.fromJson(json);
      expect(roundtrip.objectKey, tMediaRef.objectKey);
      expect(roundtrip.mediaType, tMediaRef.mediaType);
      expect(roundtrip.width, tMediaRef.width);
      expect(roundtrip.height, tMediaRef.height);
      expect(roundtrip.sizeBytes, tMediaRef.sizeBytes);
      expect(roundtrip.contentHash, tMediaRef.contentHash);
      expect(roundtrip.isGenerated, tMediaRef.isGenerated);
      expect(roundtrip.uploadedAt, tMediaRef.uploadedAt);
    });

    test('copyWith preserves fields', () {
      final copied = tMediaRef.copyWith();
      expect(copied.objectKey, tMediaRef.objectKey);
      expect(copied.mediaType, tMediaRef.mediaType);
    });

    test('copyWith updates specific fields', () {
      final updated = tMediaRef.copyWith(width: 2048);
      expect(updated.width, 2048);
      expect(updated.objectKey, tMediaRef.objectKey);
    });
  });

  group('VocabularyItem', () {
    final tVocab = VocabularyItem(code: 'tops', label: 'Tops');

    test('fromJson/toJson roundtrip', () {
      final json = tVocab.toJson();
      final roundtrip = VocabularyItem.fromJson(json);
      expect(roundtrip.code, tVocab.code);
      expect(roundtrip.label, tVocab.label);
    });

    test('default active is true', () {
      final vocab = VocabularyItem(code: 'colors', label: 'Colors');
      expect(vocab.active, true);
    });
  });

  group('WardrobeItem', () {
    final tItem = WardrobeItem(
      id: 'item-1',
      name: 'Merino Crew Neck',
      category: 'tops',
      color: 'Charcoal',
      material: 'Wool',
      isFavorite: true,
      createdAt: DateTime.parse('2024-01-15T10:00:00Z'),
      updatedAt: DateTime.parse('2024-01-15T10:00:00Z'),
    );

    test('fromJson/toJson roundtrip without imageRef', () {
      final json = tItem.toJson();
      final roundtrip = WardrobeItem.fromJson(json);
      expect(roundtrip.id, tItem.id);
      expect(roundtrip.name, tItem.name);
      expect(roundtrip.category, tItem.category);
      expect(roundtrip.color, tItem.color);
      expect(roundtrip.material, tItem.material);
      expect(roundtrip.isFavorite, tItem.isFavorite);
      expect(roundtrip.createdAt, tItem.createdAt);
      expect(roundtrip.updatedAt, tItem.updatedAt);
      expect(roundtrip.imageRef, isNull);
    });

    test('fromJson/toJson roundtrip with imageRef', () {
      final mediaRef = MediaRef(
        objectKey: 'users/1/wardrobe/image1.jpg',
        mediaType: 'image/jpeg',
        uploadedAt: DateTime.parse('2024-01-15T00:00:00Z'),
      );
      final itemWithImage = tItem.copyWith(imageRef: mediaRef);
      final json = itemWithImage.toJson();
      final roundtrip = WardrobeItem.fromJson(json);
      expect(roundtrip.id, itemWithImage.id);
      expect(roundtrip.name, itemWithImage.name);
      expect(roundtrip.imageRef, isNotNull);
      expect(roundtrip.imageRef!.objectKey, mediaRef.objectKey);
      expect(roundtrip.imageRef!.mediaType, mediaRef.mediaType);
    });

    test('copyWith preserves fields', () {
      final copied = tItem.copyWith();
      expect(copied.id, tItem.id);
      expect(copied.name, tItem.name);
      expect(copied.isFavorite, tItem.isFavorite);
    });

    test('copyWith updates specific fields', () {
      final updated = tItem.copyWith(name: 'Updated Name');
      expect(updated.name, 'Updated Name');
      expect(updated.id, tItem.id);
    });
  });

  group('WardrobeItemCreate', () {
    final tCreate = WardrobeItemCreate(
      name: 'Merino Crew Neck',
      category: 'tops',
      color: 'Charcoal',
      material: 'Wool',
    );

    test('fromJson/toJson roundtrip', () {
      final json = tCreate.toJson();
      final roundtrip = WardrobeItemCreate.fromJson(json);
      expect(roundtrip.name, tCreate.name);
      expect(roundtrip.category, tCreate.category);
      expect(roundtrip.color, tCreate.color);
      expect(roundtrip.material, tCreate.material);
    });

    test('fromJson handles optional material', () {
      final json = {'name': 'Test', 'category': 'tops', 'color': 'Black'};
      final create = WardrobeItemCreate.fromJson(json);
      expect(create.material, isNull);
    });
  });

  group('WardrobeItemPatch', () {
    final tPatch = WardrobeItemPatch(
      name: 'Updated Name',
      isFavorite: true,
    );

    test('fromJson/toJson roundtrip', () {
      final json = tPatch.toJson();
      final roundtrip = WardrobeItemPatch.fromJson(json);
      expect(roundtrip.name, tPatch.name);
      expect(roundtrip.isFavorite, tPatch.isFavorite);
    });

    test('fromJson with all optional fields', () {
      final json = {
        'name': 'New Name',
        'category': 'bottoms',
        'color': 'Indigo',
        'material': 'Denim',
        'isFavorite': false,
      };
      final patch = WardrobeItemPatch.fromJson(json);
      expect(patch.name, 'New Name');
      expect(patch.category, 'bottoms');
      expect(patch.color, 'Indigo');
      expect(patch.material, 'Denim');
      expect(patch.isFavorite, false);
    });

    test('fromJson with null fields omitted', () {
      final json = {
        'name': 'New Name',
      };
      final patch = WardrobeItemPatch.fromJson(json);
      expect(patch.name, 'New Name');
      expect(patch.category, isNull);
      expect(patch.color, isNull);
      expect(patch.material, isNull);
      expect(patch.isFavorite, isNull);
    });
  });

  group('ListEnvelope', () {
    final tItems = <WardrobeItem>[
      WardrobeItem(
        id: '1',
        name: 'Item 1',
        category: 'tops',
        color: 'Black',
        isFavorite: true,
        createdAt: DateTime.parse('2024-01-15T10:00:00Z'),
        updatedAt: DateTime.parse('2024-01-15T10:00:00Z'),
      ),
      WardrobeItem(
        id: '2',
        name: 'Item 2',
        category: 'bottoms',
        color: 'White',
        isFavorite: false,
        createdAt: DateTime.parse('2023-12-01T10:00:00Z'),
        updatedAt: DateTime.parse('2023-12-01T10:00:00Z'),
      ),
    ];

    final tEnvelope = ListEnvelope(
      items: tItems,
      page: 1,
      pageSize: 20,
      total: 2,
    );

    test('fromJson/toJson roundtrip', () {
      final json = tEnvelope.toJson();
      final roundtrip = ListEnvelope.fromJson(json);
      expect(roundtrip.items.length, tEnvelope.items.length);
      expect(roundtrip.page, tEnvelope.page);
      expect(roundtrip.pageSize, tEnvelope.pageSize);
      expect(roundtrip.total, tEnvelope.total);
      expect(roundtrip.items.first.id, tItems.first.id);
      expect(roundtrip.items.last.id, tItems.last.id);
    });

    test('sortedByCreatedAt returns newest first', () {
      final sorted = tEnvelope.sortedByCreatedAt;
      expect(sorted.first.id, '1'); // 2024-01-15 > 2023-12-01
      expect(sorted.last.id, '2');
    });

    test('sortedByName returns alphabetical', () {
      final sorted = tEnvelope.sortedByName;
      expect(sorted.first.id, '1');
      expect(sorted.last.id, '2');
    });

    test('isEmpty on empty items', () {
      final empty = ListEnvelope(items: [], page: 1, pageSize: 20, total: 0);
      expect(empty.isEmpty, isTrue);
    });

    test('isEmpty is false when items present', () {
      expect(tEnvelope.isEmpty, isFalse);
    });
  });
}