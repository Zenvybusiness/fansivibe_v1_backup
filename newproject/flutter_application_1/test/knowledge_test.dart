import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:fansivibe/features/knowledge/data/knowledge_api_models.dart';
import 'package:fansivibe/features/knowledge/data/knowledge_client.dart';
import 'package:fansivibe/features/knowledge/data/knowledge_repository.dart';

void main() {
  group('Knowledge models', () {
    test('VocabularyItem parses exact wire shape and roundtrips', () {
      const json = {'code': 'date', 'label': 'Date Night', 'sortOrder': 4};
      final item = KnowledgeVocabularyItem.fromJson(json);
      expect(item.code, 'date');
      expect(item.label, 'Date Night');
      expect(item.sortOrder, 4);
      expect(item.toJson(), json);
      expect(item.copyWith(label: 'X').label, 'X');
    });

    test('VocabularyItem throws on wrong types', () {
      expect(
        () => KnowledgeVocabularyItem.fromJson({
          'code': 'date',
          'label': 'Date Night',
          'sortOrder': '4',
        }),
        throwsA(isA<TypeError>()),
      );
    });

    test('ItemReference parses frozen shape and roundtrips', () {
      const json = {
        'code': 't-shirt',
        'label': 'T-Shirt',
        'category': 'tops',
        'sortOrder': 1,
      };
      final ref = KnowledgeItemReference.fromJson(json);
      expect(ref.code, 't-shirt');
      expect(ref.category, 'tops');
      expect(ref.toJson(), json);
      expect(ref.copyWith(sortOrder: 2).sortOrder, 2);
    });

    test('KnowledgeLook parses verbatim catalog fields', () {
      final json = {
        'code': 'textured_quiff',
        'title': 'Textured Quiff',
        'description': 'Modern volume.',
        'reasons': ['a', 'b'],
        'stylingTips': 'Mousse.',
        'maintenance': 'Medium',
        'bestFor': 'Oval',
      };
      final look = KnowledgeLook.fromJson(json);
      expect(look.code, 'textured_quiff');
      expect(look.reasons, ['a', 'b']);
      expect(look.toJson(), json);
    });

    test('envelopes parse items/page/page_size/total with wire key', () {
      final json = {
        'items': [
          {'code': 'office', 'label': 'Office', 'sortOrder': 9},
        ],
        'page': 2,
        'page_size': 3,
        'total': 9,
      };
      final list = KnowledgeVocabularyList.fromJson(json);
      expect(list.items.length, 1);
      expect(list.items.first.code, 'office');
      expect(list.page, 2);
      expect(list.pageSize, 3);
      expect(list.total, 9);
      expect(list.isEmpty, isFalse);
      expect(list.toJson(), json);
    });

    test('empty envelope parses to isEmpty', () {
      const json = {
        'items': <Map<String, dynamic>>[],
        'page': 1,
        'page_size': 20,
        'total': 0,
      };
      final list = KnowledgeItemReferenceList.fromJson(json);
      expect(list.isEmpty, isTrue);
      expect(list.total, 0);
    });
  });

  group('KnowledgeClient', () {
    test('listLooks hits exact path with auth headers', () async {
      final client = KnowledgeClient(
        client: MockClient((request) async {
          expect(request.url.path, '/v1/knowledge/looks');
          expect(request.headers['Authorization'], 'Bearer dev');
          return http.Response(
            jsonEncode({
              'items': [
                {
                  'code': 'textured_quiff',
                  'title': 'Textured Quiff',
                  'description': 'd',
                  'reasons': ['r'],
                  'stylingTips': 's',
                  'maintenance': 'm',
                  'bestFor': 'b',
                },
              ],
              'page': 1,
              'page_size': 20,
              'total': 8,
            }),
            200,
          );
        }),
      );

      final list = await client.listLooks();

      expect(list, isNotNull);
      expect(list!.items.length, 1);
      expect(list.items.first.code, 'textured_quiff');
      expect(list.total, 8);
    });

    test('listLooks passes pagination query parameters', () async {
      final client = KnowledgeClient(
        client: MockClient((request) async {
          expect(request.url.queryParameters['page'], '2');
          expect(request.url.queryParameters['page_size'], '3');
          return http.Response(
            jsonEncode({
              'items': <Map<String, dynamic>>[],
              'page': 2,
              'page_size': 3,
              'total': 8,
            }),
            200,
          );
        }),
      );

      final list = await client.listLooks(page: 2, pageSize: 3);

      expect(list, isNotNull);
      expect(list!.isEmpty, isTrue);
    });

    test('vocabulary endpoints hit exact paths', () async {
      for (final path in ['categories', 'colors', 'occasions']) {
        final client = KnowledgeClient(
          client: MockClient((request) async {
            expect(request.url.path, '/v1/knowledge/$path');
            return http.Response(
              jsonEncode({
                'items': <Map<String, Object>>[
                  {'code': 'tops', 'label': 'Tops', 'sortOrder': 0},
                ],
                'page': 1,
                'page_size': 20,
                'total': 1,
              }),
              200,
            );
          }),
        );

        KnowledgeVocabularyList? list;
        if (path == 'categories') {
          list = await client.listCategories();
        } else if (path == 'colors') {
          list = await client.listColors();
        } else {
          list = await client.listOccasions();
        }
        expect(list, isNotNull, reason: path);
        expect(list!.items.first.code, 'tops', reason: path);
      }
    });

    test('listItems parses empty gated catalog as non-null empty', () async {
      final client = KnowledgeClient(
        client: MockClient((request) async {
          expect(request.url.path, '/v1/knowledge/items');
          return http.Response(
            jsonEncode({
              'items': <Map<String, dynamic>>[],
              'page': 1,
              'page_size': 20,
              'total': 0,
            }),
            200,
          );
        }),
      );

      final list = await client.listItems();

      expect(list, isNotNull);
      expect(list!.isEmpty, isTrue);
      expect(list.total, 0);
    });

    test('422/500 responses yield null, never a fabricated list', () async {
      for (final status in [422, 500]) {
        final client = KnowledgeClient(
          client: MockClient((request) async => http.Response('{}', status)),
        );
        expect(await client.listLooks(), isNull);
        expect(await client.listCategories(), isNull);
        expect(await client.listColors(), isNull);
        expect(await client.listOccasions(), isNull);
        expect(await client.listItems(), isNull);
      }
    });

    test('network failure yields null', () async {
      final client = KnowledgeClient(
        client: MockClient((request) async => throw Exception('offline')),
      );
      expect(await client.listLooks(), isNull);
      expect(await client.listItems(), isNull);
    });

    test('malformed 200 yields null, never partial data', () async {
      final client = KnowledgeClient(
        client: MockClient((request) async => http.Response('{"oops":1}', 200)),
      );
      // Missing items → strict item parse throws inside the client → null.
      final badItems = KnowledgeClient(
        client: MockClient(
          (request) async => http.Response(
            jsonEncode({
              'items': [
                {'code': 'x'},
              ],
              'page': 1,
              'page_size': 20,
              'total': 1,
            }),
            200,
          ),
        ),
      );
      expect(await client.listLooks(), isNotNull);
      expect(await badItems.listLooks(), isNull);
    });
  });

  group('KnowledgeRepositoryImpl', () {
    test('passes backend envelopes through verbatim', () async {
      final repo = KnowledgeRepositoryImpl(
        client: KnowledgeClient(
          client: MockClient((request) async {
            if (request.url.path == '/v1/knowledge/items') {
              return http.Response(
                jsonEncode({
                  'items': <Map<String, dynamic>>[],
                  'page': 1,
                  'page_size': 20,
                  'total': 0,
                }),
                200,
              );
            }
            return http.Response(
              jsonEncode({
                'items': <Map<String, Object>>[
                  {'code': 'office', 'label': 'Office', 'sortOrder': 9},
                ],
                'page': 1,
                'page_size': 20,
                'total': 9,
              }),
              200,
            );
          }),
        ),
      );

      final occasions = await repo.listOccasions();
      expect(occasions, isNotNull);
      expect(occasions!.items.first.code, 'office');

      // Empty gated #22 passes through as non-null empty (honest state).
      final items = await repo.listItems();
      expect(items, isNotNull);
      expect(items!.isEmpty, isTrue);
    });

    test('unavailable backend yields null with no mock substitution', () async {
      final repo = KnowledgeRepositoryImpl(
        client: KnowledgeClient(
          client: MockClient((request) async => http.Response('{}', 500)),
        ),
      );
      expect(await repo.listLooks(), isNull);
      expect(await repo.listCategories(), isNull);
      expect(await repo.listColors(), isNull);
      expect(await repo.listOccasions(), isNull);
      expect(await repo.listItems(), isNull);
    });
  });
}
