import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:fansivibe/features/knowledge/data/knowledge_api_models.dart';
import 'package:fansivibe/features/knowledge/data/knowledge_client.dart';
import 'package:fansivibe/features/knowledge/data/knowledge_repository.dart';

void main() {
  group('Ffo models', () {
    test('FfoSchemaSummary parses and roundtrips', () {
      const json = {'name': 'outfit', 'title': 'FFO Outfit'};
      final summary = FfoSchemaSummary.fromJson(json);
      expect(summary.name, 'outfit');
      expect(summary.title, 'FFO Outfit');
      expect(summary.toJson(), json);
      expect(summary.copyWith(title: 'X').title, 'X');
    });

    test('FfoSchemaSummary throws on wrong types', () {
      expect(
        () => FfoSchemaSummary.fromJson({'name': 'outfit', 'title': 42}),
        throwsA(isA<TypeError>()),
      );
    });

    test('FfoSchemaList parses envelope with wire key', () {
      final json = {
        'items': [
          {'name': 'outfit', 'title': 'FFO Outfit'},
        ],
        'page': 1,
        'page_size': 30,
        'total': 26,
      };
      final list = FfoSchemaList.fromJson(json);
      expect(list.items.length, 1);
      expect(list.items.first.name, 'outfit');
      expect(list.pageSize, 30);
      expect(list.total, 26);
      expect(list.isEmpty, isFalse);
      expect(list.toJson(), json);
    });

    test('empty FfoSchemaList parses to isEmpty', () {
      const json = {
        'items': <Map<String, dynamic>>[],
        'page': 1,
        'page_size': 20,
        'total': 0,
      };
      final list = FfoSchemaList.fromJson(json);
      expect(list.isEmpty, isTrue);
    });
  });

  group('KnowledgeClient FFO reads', () {
    test('listFfoSchemas hits exact path with auth headers', () async {
      final client = KnowledgeClient(
        client: MockClient((request) async {
          expect(request.url.path, '/v1/knowledge/ffo');
          expect(request.headers['Authorization'], 'Bearer dev');
          return http.Response(
            jsonEncode({
              'items': [
                {'name': 'outfit', 'title': 'FFO Outfit'},
              ],
              'page': 1,
              'page_size': 20,
              'total': 27,
            }),
            200,
          );
        }),
      );

      final list = await client.listFfoSchemas();

      expect(list, isNotNull);
      expect(list!.total, 27);
      expect(list.items.first.name, 'outfit');
    });

    test('listFfoSchemas passes pagination query parameters', () async {
      final client = KnowledgeClient(
        client: MockClient((request) async {
          expect(request.url.queryParameters['page'], '2');
          expect(request.url.queryParameters['page_size'], '30');
          return http.Response(
            jsonEncode({
              'items': <Map<String, dynamic>>[],
              'page': 2,
              'page_size': 30,
              'total': 26,
            }),
            200,
          );
        }),
      );

      final list = await client.listFfoSchemas(page: 2, pageSize: 30);

      expect(list, isNotNull);
      expect(list!.isEmpty, isTrue);
    });

    test('getFfoSchema returns verbatim schema JSON', () async {
      final client = KnowledgeClient(
        client: MockClient((request) async {
          expect(request.url.path, '/v1/knowledge/ffo/outfit');
          return http.Response(
            jsonEncode({
              r'$id': 'https://fansivibe.local/ffo/v1/outfit.schema.json',
              'title': 'FFO Outfit',
              'type': 'object',
            }),
            200,
          );
        }),
      );

      final schema = await client.getFfoSchema('outfit');

      expect(schema, isNotNull);
      expect(schema!['title'], 'FFO Outfit');
    });

    test('getFfoSchema yields null on 404, 500, network failure', () async {
      final notFound = KnowledgeClient(
        client: MockClient((request) async => http.Response('{}', 404)),
      );
      expect(await notFound.getFfoSchema('nope'), isNull);

      final serverError = KnowledgeClient(
        client: MockClient((request) async => http.Response('{}', 500)),
      );
      expect(await serverError.getFfoSchema('outfit'), isNull);
      expect(await serverError.listFfoSchemas(), isNull);

      final offline = KnowledgeClient(
        client: MockClient((request) async => throw Exception('offline')),
      );
      expect(await offline.getFfoSchema('outfit'), isNull);
      expect(await offline.listFfoSchemas(), isNull);
    });

    test('getFfoSchema never requests empty names', () async {
      var requested = false;
      final client = KnowledgeClient(
        client: MockClient((request) async {
          requested = true;
          return http.Response('{}', 200);
        }),
      );
      expect(await client.getFfoSchema(''), isNull);
      expect(requested, isFalse);
    });
  });

  group('KnowledgeRepositoryImpl FFO reads', () {
    test('passes FFO envelopes through verbatim', () async {
      final repo = KnowledgeRepositoryImpl(
        client: KnowledgeClient(
          client: MockClient((request) async {
            if (request.url.path == '/v1/knowledge/ffo/outfit') {
              return http.Response(
                jsonEncode({'title': 'FFO Outfit'}),
                200,
              );
            }
            return http.Response(
              jsonEncode({
                'items': [
                  {'name': 'outfit', 'title': 'FFO Outfit'},
                ],
                'page': 1,
                'page_size': 20,
                'total': 27,
              }),
              200,
            );
          }),
        ),
      );

      final list = await repo.listFfoSchemas();
      expect(list, isNotNull);
      expect(list!.total, 27);

      final schema = await repo.getFfoSchema('outfit');
      expect(schema, isNotNull);
      expect(schema!['title'], 'FFO Outfit');
    });

    test('unavailable backend yields null with no mock substitution', () async {
      final repo = KnowledgeRepositoryImpl(
        client: KnowledgeClient(
          client: MockClient((request) async => http.Response('{}', 500)),
        ),
      );
      expect(await repo.listFfoSchemas(), isNull);
      expect(await repo.getFfoSchema('outfit'), isNull);
    });
  });

  group('Reasoning models and client integration', () {
    final validResponseJson = {
      'answer': 'Denim is a durable cotton twill textile.',
      'conclusions': [
        {
          'statement': 'Denim is a durable twill textile.',
          'evidence_ids': ['term-denim'],
          'ffo_refs': ['denim', 'textile'],
          'reasoning_note': 'Grounded in term-denim.',
          'standing': 'supported',
        },
      ],
      'uncertainties': <String>[],
      'missing_evidence': <String>[],
      'contradictions': <String>[],
      'confidence': 'high',
      'unsupported': false,
      'versions': {
        'ffo_version': '1.0',
        'corpus_digest': 'a' * 64,
        'evidence_schema': 'evidence-pack/1',
        'reasoning_contract_version': '2.0',
      },
    };

    test('FashionReasoningResponse roundtrips valid JSON', () {
      final resp = FashionReasoningResponse.fromJson(validResponseJson);
      expect(resp.answer, contains('Denim'));
      expect(resp.confidence, 'high');
      expect(resp.unsupported, isFalse);
      expect(resp.conclusions.length, 1);
      expect(resp.conclusions.first.evidenceIds, ['term-denim']);
      expect(resp.conclusions.first.ffoRefs, ['denim', 'textile']);
      expect(resp.versions.reasoningContractVersion, '2.0');
      expect(resp.toJson(), validResponseJson);
    });

    test('KnowledgeClient reasonQuery calls /v1/reasoning and returns response', () async {
      final client = KnowledgeClient(
        client: MockClient((request) async {
          expect(request.url.path, '/v1/reasoning');
          expect(request.method, 'POST');
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          expect(body['query'], 'what is denim');
          return http.Response(jsonEncode(validResponseJson), 200);
        }),
      );

      final resp = await client.reasonQuery(
        const FashionReasoningRequest(query: 'what is denim'),
      );
      expect(resp, isNotNull);
      expect(resp!.answer, contains('Denim'));
      expect(resp.conclusions.first.statement, contains('Denim'));
    });

    test('KnowledgeRepositoryImpl reasonQuery delegates to client', () async {
      final repo = KnowledgeRepositoryImpl(
        client: KnowledgeClient(
          client: MockClient((request) async {
            return http.Response(jsonEncode(validResponseJson), 200);
          }),
        ),
      );

      final resp = await repo.reasonQuery(
        const FashionReasoningRequest(query: 'what is denim'),
      );
      expect(resp, isNotNull);
      expect(resp!.confidence, 'high');
    });

    test('KnowledgeClient reasonQuery returns null on failure without throwing', () async {
      final client = KnowledgeClient(
        client: MockClient((request) async => http.Response('{"error": "fail"}', 503)),
      );
      final resp = await client.reasonQuery(
        const FashionReasoningRequest(query: 'what is denim'),
      );
      expect(resp, isNull);
    });
  });
}

