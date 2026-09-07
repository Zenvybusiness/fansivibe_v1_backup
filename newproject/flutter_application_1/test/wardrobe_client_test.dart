import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:fansivibe/features/wardrobe/data/wardrobe_client.dart';

void main() {
  group('WardrobeClient.listItems', () {
    test('returns ListEnvelope on 200 with correct headers', () async {
      final client = WardrobeClient(
        client: MockClient((request) async {
          expect(request.url.path, '/v1/wardrobe/items');
          expect(request.headers['Authorization'], 'Bearer dev');
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

      final envelope = await client.listItems();

      expect(envelope, isNotNull);
      expect(envelope!.items.length, 1);
      expect(envelope.items.first.name, 'Merino Crew Neck');
      expect(envelope.page, 1);
      expect(envelope.total, 1);
    });

    test('passes query parameters for category filter', () async {
      final client = WardrobeClient(
        client: MockClient((request) async {
          expect(request.url.path, '/v1/wardrobe/items');
          expect(request.url.queryParameters['category'], 'tops');
          expect(request.url.queryParameters['color'], null);
          expect(request.headers['Authorization'], 'Bearer dev');
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

      final envelope = await client.listItems(category: 'tops');

      expect(envelope, isNotNull);
      expect(envelope!.items.isEmpty, isTrue);
    });

    test('passes query parameters for sort and order', () async {
      final client = WardrobeClient(
        client: MockClient((request) async {
          expect(request.url.path, '/v1/wardrobe/items');
          expect(request.url.queryParameters['sort'], 'created_at');
          expect(request.url.queryParameters['order'], 'desc');
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

      final envelope = await client.listItems(sortBy: 'created_at', order: 'desc');

      expect(envelope, isNotNull);
    });

    test('passes page and page_size query parameters', () async {
      final client = WardrobeClient(
        client: MockClient((request) async {
          expect(request.url.queryParameters['page'], '2');
          expect(request.url.queryParameters['page_size'], '50');
          return http.Response(
            jsonEncode({
              'items': [],
              'page': 2,
              'page_size': 50,
              'total': 5,
            }),
            200,
          );
        }),
      );

      final envelope = await client.listItems(page: 2, pageSize: 50);

      expect(envelope, isNotNull);
      expect(envelope!.page, 2);
      expect(envelope.pageSize, 50);
    });

    test('returns null on 401', () async {
      final client = WardrobeClient(
        client: MockClient(
          (request) async => http.Response('{"error":{}}', 401),
        ),
      );

      final envelope = await client.listItems();

      expect(envelope, isNull);
    });

    test('returns null on network failure', () async {
      final client = WardrobeClient(
        client: MockClient(
          (request) async => throw http.ClientException('connection refused'),
        ),
      );

      final envelope = await client.listItems();

      expect(envelope, isNull);
    });
  });

  group('WardrobeClient.getItem', () {
    test('returns WardrobeItem on 200', () async {
      final client = WardrobeClient(
        client: MockClient((request) async {
          expect(request.url.path, '/v1/wardrobe/items/item-1');
          expect(request.headers['Authorization'], 'Bearer dev');
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

      final item = await client.getItem(itemId: 'item-1');

      expect(item, isNotNull);
      expect(item!.id, 'item-1');
      expect(item.name, 'Merino Crew Neck');
    });

    test('returns null on 404', () async {
      final client = WardrobeClient(
        client: MockClient((request) async => http.Response('{"error":{}}', 404)),
      );

      final item = await client.getItem(itemId: 'nonexistent');

      expect(item, isNull);
    });

    test('returns null on 500', () async {
      final client = WardrobeClient(
        client: MockClient((request) async => http.Response('', 500)),
      );

      final item = await client.getItem(itemId: 'item-1');

      expect(item, isNull);
    });

    test('returns null on network failure', () async {
      final client = WardrobeClient(
        client: MockClient(
          (request) async => throw http.ClientException('connection refused'),
        ),
      );

      final item = await client.getItem(itemId: 'item-1');

      expect(item, isNull);
    });
  });

  group('WardrobeClient.createItem', () {
    test('returns WardrobeItem on 201 with correct headers and body', () async {
      final client = WardrobeClient(
        client: MockClient((request) async {
          expect(request.url.path, '/v1/wardrobe/items');
          expect(request.headers['Authorization'], 'Bearer dev');
          expect(request.headers['Content-Type'],
              contains('application/json; charset=UTF-8'));
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          expect(body['name'], 'Merino Crew Neck');
          expect(body['category'], 'tops');
          expect(body['color'], 'Charcoal');
          expect(body['material'], 'Wool');
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

      final item = await client.createItem(
        name: 'Merino Crew Neck',
        category: 'tops',
        color: 'Charcoal',
        material: 'Wool',
      );

      expect(item, isNotNull);
      expect(item!.id, 'new-item-1');
      expect(item.name, 'Merino Crew Neck');
    });

    test('creates item without material', () async {
      final client = WardrobeClient(
        client: MockClient((request) async {
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          expect(body['material'], isNull);
          return http.Response(
            jsonEncode({
              'id': 'new-item-2',
              'name': 'Test Item',
              'category': 'bottoms',
              'color': 'Black',
              'isFavorite': false,
              'createdAt': '2024-01-15T10:00:00Z',
              'updatedAt': '2024-01-15T10:00:00Z',
            }),
            201,
          );
        }),
      );

      final item = await client.createItem(
        name: 'Test Item',
        category: 'bottoms',
        color: 'Black',
      );

      expect(item, isNotNull);
      expect(item!.name, 'Test Item');
    });

    test('returns null on 401', () async {
      final client = WardrobeClient(
        client: MockClient(
          (request) async => http.Response('{"error":{}}', 401),
        ),
      );

      final item = await client.createItem(
        name: 'Test',
        category: 'tops',
        color: 'Black',
      );

      expect(item, isNull);
    });

    test('returns null on network failure', () async {
      final client = WardrobeClient(
        client: MockClient(
          (request) async => throw http.ClientException('connection refused'),
        ),
      );

      final item = await client.createItem(
        name: 'Test',
        category: 'tops',
        color: 'Black',
      );

      expect(item, isNull);
    });
  });

  group('WardrobeClient.updateItem', () {
    test('returns updated WardrobeItem on 200 with correct headers and body', () async {
      final client = WardrobeClient(
        client: MockClient((request) async {
          expect(request.url.path, '/v1/wardrobe/items/item-1');
          expect(request.headers['Authorization'], 'Bearer dev');
          expect(request.headers['Content-Type'],
              contains('application/json; charset=UTF-8'));
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          expect(body['name'], 'Updated Name');
          expect(body['isFavorite'], true);
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

      final item = await client.updateItem(
        itemId: 'item-1',
        name: 'Updated Name',
        isFavorite: true,
      );

      expect(item, isNotNull);
      expect(item!.name, 'Updated Name');
      expect(item.isFavorite, true);
      expect(item.updatedAt?.day, 20);
    });

    test('partial update - only name provided', () async {
      final client = WardrobeClient(
        client: MockClient((request) async {
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          expect(body['name'], 'New Name');
          expect(body.containsKey('isFavorite'), isFalse);
          return http.Response(
            jsonEncode({
              'id': 'item-1',
              'name': 'New Name',
              'category': 'tops',
              'color': 'Charcoal',
              'isFavorite': false,
              'createdAt': '2024-01-15T10:00:00Z',
              'updatedAt': '2024-02-20T14:30:00Z',
            }),
            200,
          );
        }),
      );

      final item = await client.updateItem(
        itemId: 'item-1',
        name: 'New Name',
      );

      expect(item, isNotNull);
      expect(item!.name, 'New Name');
    });

    test('returns null on 404', () async {
      final client = WardrobeClient(
        client: MockClient((request) async => http.Response('{"error":{}}', 404)),
      );

      final item = await client.updateItem(
        itemId: 'nonexistent',
        name: 'Test',
      );

      expect(item, isNull);
    });

    test('returns null on 401', () async {
      final client = WardrobeClient(
        client: MockClient(
          (request) async => http.Response('{"error":{}}', 401),
        ),
      );

      final item = await client.updateItem(
        itemId: 'item-1',
        name: 'Test',
      );

      expect(item, isNull);
    });

    test('returns null on network failure', () async {
      final client = WardrobeClient(
        client: MockClient(
          (request) async => throw http.ClientException('connection refused'),
        ),
      );

      final item = await client.updateItem(
        itemId: 'item-1',
        name: 'Test',
      );

      expect(item, isNull);
    });
  });

  group('WardrobeClient.deleteItem', () {
    test('returns true on 204', () async {
      final client = WardrobeClient(
        client: MockClient((request) async {
          expect(request.url.path, '/v1/wardrobe/items/item-1');
          expect(request.headers['Authorization'], 'Bearer dev');
          return http.Response('', 204);
        }),
      );

      final result = await client.deleteItem(itemId: 'item-1');

      expect(result, isTrue);
    });

    test('returns null on 404', () async {
      final client = WardrobeClient(
        client: MockClient((request) async => http.Response('{"error":{}}', 404)),
      );

      final result = await client.deleteItem(itemId: 'nonexistent');

      expect(result, isNull);
    });

    test('returns null on 401', () async {
      final client = WardrobeClient(
        client: MockClient(
          (request) async => http.Response('{"error":{}}', 401),
        ),
      );

      final result = await client.deleteItem(itemId: 'item-1');

      expect(result, isNull);
    });

    test('returns null on network failure', () async {
      final client = WardrobeClient(
        client: MockClient(
          (request) async => throw http.ClientException('connection refused'),
        ),
      );

      final result = await client.deleteItem(itemId: 'item-1');

      expect(result, isNull);
    });
  });
}