import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:fansivibe/features/wardrobe/data/wardrobe_client.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';

void main() {
  group('WardrobeRepository.listItems', () {
    test('API success → domain model', () async {
      final client = WardrobeClient(
        client: MockClient((request) async {
          return http.Response(
            jsonEncode({
              'items': [
                {
                  'id': '1',
                  'name': 'Merino Crew Neck',
                  'category': 'tops',
                  'color': 'Charcoal',
                  'isFavorite': true,
                  'createdAt': '2024-01-15T10:00:00Z',
                  'updatedAt': '2024-01-15T10:00:00Z',
                }
              ],
              'page': 1,
              'page_size': 20,
              'total': 1,
            }),
            200,
          );
        }),
      );

      final repo = WardrobeRepositoryImpl(client: client);
      final result = await repo.listItems();

      expect(result, isNotEmpty);
      expect(result.first, isA<WardrobeItemData>());
      expect(result.first.name, 'Merino Crew Neck');
      expect(result.first.category, 'tops');
      expect(result.first.color, 'Charcoal');
      expect(result.first.isFavorite, true);
    });

    test('API success with category filter → empty list', () async {
      final client = WardrobeClient(
        client: MockClient((request) async {
          return http.Response(
            jsonEncode({
              'items': [],
              'page': 1,
              'page_size': 20,
              'total': 0,
            }),
            200,
          );
        }),
      );

      final repo = WardrobeRepositoryImpl(client: client);
      final result = await repo.listItems(category: 'tops');

      expect(result, isEmpty);
    });

    test('API failure → WardrobeMockData fallback', () async {
      final client = WardrobeClient(
        client: MockClient(
          (request) async => http.Response('{}', 500),
        ),
      );

      final repo = WardrobeRepositoryImpl(client: client);
      final result = await repo.listItems();

      expect(result, isNotEmpty);
      expect(result.first, isA<WardrobeItemData>());
      expect(result.first.name, 'Merino Crew Neck');
    });

    test('no accidental data loss during fallback', () async {
      final client = WardrobeClient(
        client: MockClient(
          (request) async => http.Response('{}', 500),
        ),
      );

      final repo = WardrobeRepositoryImpl(client: client);
      final result = await repo.listItems();

      expect(result.length, WardrobeMockData.items.length);
      expect(result.any((item) => item.id == '1'), isTrue);
    });
  });

  group('WardrobeRepository.getItem', () {
test('API success → domain model', () async {
      final client = WardrobeClient(
        client: MockClient((request) async {
          return http.Response(
            jsonEncode({
              'id': 'item-1',
              'name': 'Merino Crew Neck',
              'category': 'tops',
              'color': 'Charcoal',
              'isFavorite': true,
              'createdAt': '2024-01-15T10:00:00Z',
              'updatedAt': '2024-01-15T10:00:00Z',
            }),
            200,
          );
        }),
      );

      final repo = WardrobeRepositoryImpl(client: client);
      final result = await repo.getItem(itemId: 'item-1');

      expect(result, isNotNull);
      expect(result!.name, 'Merino Crew Neck');
      expect(result.category, 'tops');
      expect(result.color, 'Charcoal');
      expect(result.isFavorite, true);
    });

    test('API failure → WardrobeMockData fallback', () async {
      final client = WardrobeClient(
        client: MockClient(
          (request) async => http.Response('{}', 500),
        ),
      );

      final repo = WardrobeRepositoryImpl(client: client);
      final result = await repo.getItem(itemId: '1');

      expect(result, isNotNull);
      expect(result?.name, 'Merino Crew Neck');
    });

    test('mock item found by ID when API returns 404', () async {
      final client = WardrobeClient(
        client: MockClient(
          (request) async => http.Response('{"error":{}}', 404),
        ),
      );

      final repo = WardrobeRepositoryImpl(client: client);
      final result = await repo.getItem(itemId: '1');

      expect(result, isNotNull);
      expect(result!.id, '1');
      expect(result.name, 'Merino Crew Neck');
    });
  });

  group('WardrobeRepository.createItem', () {
    test('API success → domain model', () async {
      final client = WardrobeClient(
        client: MockClient((request) async {
          return http.Response(
            jsonEncode({
              'id': 'new-item-1',
              'name': 'Merino Crew Neck',
              'category': 'tops',
              'color': 'Charcoal',
              'isFavorite': false,
              'createdAt': '2024-01-15T10:00:00Z',
              'updatedAt': '2024-01-15T10:00:00Z',
            }),
            201,
          );
        }),
      );

      final repo = WardrobeRepositoryImpl(client: client);
      final result = await repo.createItem(
        name: 'Merino Crew Neck',
        category: 'tops',
        color: 'Charcoal',
        material: 'Wool',
      );

      expect(result, isNotNull);
      expect(result!.id, 'new-item-1');
      expect(result.name, 'Merino Crew Neck');
    });

    test('API failure → no accidental data loss', () async {
      final client = WardrobeClient(
        client: MockClient(
          (request) async => http.Response('{}', 500),
        ),
      );

      final repo = WardrobeRepositoryImpl(client: client);
      final before = List.of(WardrobeMockData.items);
      final beforeCount = before.length;

      final result = await repo.createItem(
        name: 'Test Item',
        category: 'bottoms',
        color: 'Black',
        material: 'Cotton',
      );

      expect(result, isNull);
      expect(WardrobeMockData.items.length, beforeCount);
    });
  });

  group('WardrobeRepository.updateItem', () {
    test('API success → domain model', () async {
      final client = WardrobeClient(
        client: MockClient((request) async {
          return http.Response(
            jsonEncode({
              'id': 'item-1',
              'name': 'Updated Name',
              'category': 'tops',
              'color': 'Charcoal',
              'isFavorite': true,
              'createdAt': '2024-01-15T10:00:00Z',
              'updatedAt': '2024-02-20T14:30:00Z',
            }),
            200,
          );
        }),
      );

      final repo = WardrobeRepositoryImpl(client: client);
      final result = await repo.updateItem(
        itemId: 'item-1',
        name: 'Updated Name',
        isFavorite: true,
      );

      expect(result, isNotNull);
      expect(result!.name, 'Updated Name');
      expect(result.isFavorite, true);
    });

    test('API failure → no accidental data loss', () async {
      final client = WardrobeClient(
        client: MockClient(
          (request) async => http.Response('{}', 500),
        ),
      );

      final repo = WardrobeRepositoryImpl(client: client);
      final before = List.of(WardrobeMockData.items);
      final beforeItem = before.firstWhere((item) => item.id == '1');
      final beforeName = beforeItem.name;

      final result = await repo.updateItem(
        itemId: '1',
        name: 'Should Not Appear',
      );

      expect(result, isNull);
      expect(WardrobeMockData.items.firstWhere((item) => item.id == '1').name, beforeName);
    });
  });

  group('WardrobeRepository.deleteItem', () {
    test('API success → true', () async {
      final client = WardrobeClient(
        client: MockClient((request) async {
          return http.Response('', 204);
        }),
      );

      final repo = WardrobeRepositoryImpl(client: client);
      final result = await repo.deleteItem(itemId: 'item-1');

      expect(result, isTrue);
    });

    test('API failure → no accidental data loss', () async {
      final client = WardrobeClient(
        client: MockClient(
          (request) async => http.Response('{}', 500),
        ),
      );

      final repo = WardrobeRepositoryImpl(client: client);
      final before = List.of(WardrobeMockData.items);
      final beforeCount = before.length;

      final result = await repo.deleteItem(itemId: '1');

      expect(result, isNull);
      expect(WardrobeMockData.items.length, beforeCount);
    });
  });
}