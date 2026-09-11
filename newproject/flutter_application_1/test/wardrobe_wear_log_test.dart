import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_client.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';

const _itemA = '11111111-1111-4111-8111-111111111111';
const _itemB = '22222222-2222-4222-8222-222222222222';
const _groupId = '33333333-3333-4333-8333-333333333333';

Map<String, dynamic> _logJson({required bool created}) => {
      'wears': [
        {
          'id': 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
          'wardrobeItemId': _itemA,
          'wornAt': '2024-08-01T12:00:00Z',
          'wearGroupId': _groupId,
          'createdAt': '2024-08-01T12:00:01Z',
        },
        {
          'id': 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
          'wardrobeItemId': _itemB,
          'wornAt': '2024-08-01T12:00:00Z',
          'wearGroupId': _groupId,
          'createdAt': '2024-08-01T12:00:01Z',
        },
      ],
      'wearGroupId': _groupId,
      'wornAt': '2024-08-01T12:00:00Z',
      'created': created,
    };

void main() {
  group('WearEventLogRequest serialization', () {
    test('preserves backend UUIDs exactly, omits wornAt when null', () {
      const request = WearEventLogRequest(itemIds: [_itemB, _itemA]);

      final body = request.toJson();

      expect(body['itemIds'], [_itemB, _itemA]);
      expect(body.containsKey('wornAt'), isFalse);
    });

    test('emits wornAt as UTC ISO-8601 when supplied', () {
      final request = WearEventLogRequest(
        itemIds: [_itemA],
        wornAt: DateTime.parse('2024-08-01T12:00:00Z'),
      );

      final body = request.toJson();

      expect(
        DateTime.parse(body['wornAt'] as String).toUtc(),
        DateTime.utc(2024, 8, 1, 12),
      );
    });

    test('fromJson roundtrip preserves ids and instant', () {
      final request = WearEventLogRequest.fromJson(const {
        'itemIds': [_itemA, _itemB],
        'wornAt': '2024-08-01T12:00:00+00:00',
      });

      expect(request.itemIds, [_itemA, _itemB]);
      expect(request.wornAt?.toUtc(), DateTime.utc(2024, 8, 1, 12));
    });
  });

  group('newWearIdempotencyKey', () {
    test('generates fresh v4-formatted keys per call', () {
      final first = newWearIdempotencyKey();
      final second = newWearIdempotencyKey();
      final v4 = RegExp(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
      );

      expect(first, matches(v4));
      expect(second, matches(v4));
      expect(first == second, isFalse);
    });
  });

  group('WardrobeClient.logWear', () {
    test('POSTs path, auth, content-type, key, and verbatim UUIDs', () async {
      String? seenKey;
      Map<String, dynamic>? seenBody;
      final client = WardrobeClient(
        client: MockClient((request) async {
          expect(request.method, 'POST');
          expect(request.url.path, '/v1/wardrobe/wears');
          expect(request.headers['Authorization'], 'Bearer dev');
          expect(
            request.headers['Content-Type'],
            'application/json; charset=UTF-8',
          );
          seenKey = request.headers['Idempotency-Key'];
          seenBody =
              jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(jsonEncode(_logJson(created: true)), 201);
        }),
      );

      final result = await client.logWear(itemIds: const [_itemB, _itemA]);

      expect(seenKey, isNotNull);
      expect(seenBody!['itemIds'], [_itemB, _itemA]);
      expect(seenBody!.containsKey('wornAt'), isFalse);
      expect(result, isNotNull);
      expect(result!.created, isTrue);
      expect(result.wearGroupId, _groupId);
      expect(result.wears.length, 2);
      expect(result.wears[0].wardrobeItemId, _itemA);
      expect(result.wears[1].wardrobeItemId, _itemB);
      expect(result.wears[0].wearGroupId, _groupId);
    });

    test('sends wornAt only when supplied', () async {
      Map<String, dynamic>? seenBody;
      final client = WardrobeClient(
        client: MockClient((request) async {
          seenBody =
              jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(jsonEncode(_logJson(created: true)), 201);
        }),
      );

      await client.logWear(
        itemIds: const [_itemA],
        wornAt: DateTime.parse('2024-08-01T12:00:00Z'),
      );

      expect(
        DateTime.parse(seenBody!['wornAt'] as String).toUtc(),
        DateTime.utc(2024, 8, 1, 12),
      );
    });

    test('generates a fresh key per call, forwards an explicit key', () async {
      final seenKeys = <String?>[];
      final client = WardrobeClient(
        client: MockClient((request) async {
          seenKeys.add(request.headers['Idempotency-Key']);
          return http.Response(jsonEncode(_logJson(created: true)), 201);
        }),
      );

      await client.logWear(itemIds: const [_itemA]);
      await client.logWear(itemIds: const [_itemA]);
      await client.logWear(
        itemIds: const [_itemA],
        idempotencyKey: 'retry-key-1',
      );

      expect(seenKeys[0], isNotNull);
      expect(seenKeys[1], isNotNull);
      expect(seenKeys[0] == seenKeys[1], isFalse);
      expect(seenKeys[2], 'retry-key-1');
    });

    test('parses a 201 replay distinctly via created=false', () async {
      final client = WardrobeClient(
        client: MockClient(
          (request) async =>
              http.Response(jsonEncode(_logJson(created: false)), 201),
        ),
      );

      final result = await client.logWear(itemIds: const [_itemA, _itemB]);

      expect(result, isNotNull);
      expect(result!.created, isFalse);
      expect(result.wearGroupId, _groupId);
      expect(result.wears.length, 2);
    });

    test('returns null on 404 without treating it as success', () async {
      final client = WardrobeClient(
        client: MockClient(
          (request) async => http.Response('{"error":{}}', 404),
        ),
      );

      expect(
        await client.logWear(itemIds: const ['dead-beef']),
        isNull,
      );
    });

    test('returns null on 409 conflict instead of inventing a result',
        () async {
      final client = WardrobeClient(
        client: MockClient(
          (request) async => http.Response('{"error":{}}', 409),
        ),
      );

      expect(
        await client.logWear(itemIds: const [_itemA]),
        isNull,
      );
    });

    test('returns null on 422 validation errors', () async {
      final client = WardrobeClient(
        client: MockClient(
          (request) async => http.Response('{"error":{}}', 422),
        ),
      );

      expect(await client.logWear(itemIds: const ['nope']), isNull);
    });

    test('returns null on 401', () async {
      final client = WardrobeClient(
        client: MockClient(
          (request) async => http.Response('{"error":{}}', 401),
        ),
      );

      expect(await client.logWear(itemIds: const [_itemA]), isNull);
    });

    test('returns null on 500', () async {
      final client = WardrobeClient(
        client: MockClient((request) async => http.Response('oops', 500)),
      );

      expect(await client.logWear(itemIds: const [_itemA]), isNull);
    });

    test('returns null on network failure', () async {
      final client = WardrobeClient(
        client: MockClient(
          (request) async => throw http.ClientException('connection refused'),
        ),
      );

      expect(await client.logWear(itemIds: const [_itemA]), isNull);
    });

    test('returns null on 201 with a malformed body instead of throwing',
        () async {
      final nonJson = WardrobeClient(
        client: MockClient((request) async => http.Response('not-json{{{', 201)),
      );
      expect(await nonJson.logWear(itemIds: const [_itemA]), isNull);

      final wrongTypes = WardrobeClient(
        client: MockClient(
          (request) async => http.Response(
            jsonEncode({'wears': 'nope', 'wearGroupId': 42}),
            201,
          ),
        ),
      );
      expect(await wrongTypes.logWear(itemIds: const [_itemA]), isNull);
    });
  });

  group('WardrobeRepository.logWear', () {
    test('delegates to the client and returns the parsed response', () async {
      final repository = WardrobeRepositoryImpl(
        client: WardrobeClient(
          client: MockClient(
            (request) async =>
                http.Response(jsonEncode(_logJson(created: true)), 201),
          ),
        ),
      );

      final result = await repository.logWear(itemIds: const [_itemA, _itemB]);

      expect(result, isNotNull);
      expect(result!.created, isTrue);
      expect(result.wearGroupId, _groupId);
      expect(result.wears.length, 2);
    });

    test('returns null when the client reports failure (no mock success)',
        () async {
      final repository = WardrobeRepositoryImpl(
        client: WardrobeClient(
          client: MockClient((request) async => http.Response('{}', 500)),
        ),
      );

      expect(
        await repository.logWear(itemIds: const [_itemA]),
        isNull,
      );
    });
  });
}
