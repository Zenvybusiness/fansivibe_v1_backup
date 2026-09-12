import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:fansivibe/features/home/data/today_look_client.dart';
import 'package:fansivibe/features/home/data/today_look_models.dart';
import 'package:fansivibe/features/home/data/today_look_repository.dart';

const String _uuid1 = '78ff3686-c950-4cd6-84c3-7e18d6634dfa';
const String _uuid2 = '4412f646-56a9-4afa-8717-b330da03b3d0';
const String _uuid3 = '9d8f2c1a-3b4e-4f5a-8c6d-7e8f9a0b1c2d';
const String _uuidAlt = '3fa85f64-5717-4562-b3fc-2c963f66afa6';
const String _savedId = 'b3e1a2c4-5d6f-47a8-b9c0-d1e2f3a4b5c6';

/// Exact M9 wire shape (honesty subset: no weather, no colorHex, no AI
/// prose, minimal alternatives, additive selectedItemIds).
Map<String, dynamic> wireTodayLook({
  String title = "Today's Look",
  Object? occasion = 'formal',
}) {
  return {
    'title': title,
    if (occasion != null) 'occasion': occasion,
    'description': 'Sharp tailoring grounded in owned staples.',
    'matchScore': 87,
    'styleScore': 87,
    'components': [
      {
        'id': _uuid1,
        'name': 'Navy Blazer',
        'category': 'outerwear',
        'color': 'navy',
        'material': 'wool',
      },
      {'id': _uuid2, 'name': 'White Tee', 'category': 'tops', 'color': 'white'},
      {
        'id': _uuid3,
        'name': 'Dark Jeans',
        'category': 'bottoms',
        'color': 'indigo',
        'material': 'denim',
      },
    ],
    'reasons': [
      'Picked for a formal occasion',
      'Covers 3 owned wardrobe staples',
    ],
    'wardrobeContext': {'totalItems': 3, 'matchingItems': 3},
    'alternatives': [
      {'id': _uuidAlt, 'matchScore': 81},
    ],
    'selectedItemIds': [_uuid1, _uuid2, _uuid3],
  };
}

Map<String, dynamic> wireSavedLook(Map<String, dynamic> snapshot) {
  return {
    'id': _savedId,
    'lookId': null,
    'title': "Today's Look",
    'sourceContext': 'daily',
    'snapshot': snapshot,
    'sourceRunId': null,
    'createdAt': '2030-08-15T10:00:00.000Z',
  };
}

void main() {
  group('A. TodayLook JSON parsing', () {
    test('parses the exact backend wire shape', () {
      final look = TodayLook.fromJson(wireTodayLook());

      expect(look.title, "Today's Look");
      expect(look.occasion, 'formal');
      expect(look.description, isNotEmpty);
      expect(look.matchScore, 87);
      expect(look.styleScore, 87);
      expect(look.components, hasLength(3));
      expect(look.components.first.id, _uuid1);
      expect(look.components.first.name, 'Navy Blazer');
      expect(look.components.first.material, 'wool');
      expect(look.components[1].material, isNull);
      expect(look.reasons, hasLength(2));
      expect(look.wardrobeContext.totalItems, 3);
      expect(look.wardrobeContext.matchingItems, 3);
      expect(look.alternatives, hasLength(1));
      expect(look.alternatives.single.id, _uuidAlt);
      expect(look.alternatives.single.matchScore, 81);
      expect(look.selectedItemIds, [_uuid1, _uuid2, _uuid3]);
      expect(look.styleDna, isNull);
    });

    test('occasion absent stays absent (no fallback invented)', () {
      final look = TodayLook.fromJson(wireTodayLook(occasion: null));

      expect(look.occasion, isNull);
    });

    test('styleDna projects present subfields only', () {
      final look = TodayLook.fromJson({
        ...wireTodayLook(),
        'styleDna': {'bodyType': 'Athletic', 'faceShape': 'Oval'},
      });

      expect(look.styleDna, isNotNull);
      expect(look.styleDna!.bodyType, 'Athletic');
      expect(look.styleDna!.faceShape, 'Oval');
      expect(look.styleDna!.styleType, isNull);
      expect(look.styleDna!.skinTone, isNull);
    });

    test('wire map carries no weather and no banned keys', () {
      final wire = wireTodayLook();

      for (final banned in [
        'weather',
        'colorHex',
        'aiSelectionReason',
        'confidenceBoost',
        'aiInsights',
        'dailyStyleTip',
        'selectedMood',
        'colorHarmony',
        'bodyFit',
      ]) {
        expect(wire.containsKey(banned), isFalse, reason: banned);
        for (final component in wire['components'] as List<dynamic>) {
          expect(
            (component as Map<String, dynamic>).containsKey(banned),
            isFalse,
          );
        }
      }
    });

    test('strict parsing throws on malformed bodies', () {
      expect(() => TodayLook.fromJson({}), throwsA(anything));
      expect(
        () => TodayLook.fromJson({...wireTodayLook(), 'matchScore': '87'}),
        throwsA(anything),
      );
      expect(
        () => TodayLook.fromJson({...wireTodayLook(), 'components': 'nope'}),
        throwsA(anything),
      );
    });

    test('snapshot is the response body verbatim', () {
      final wire = wireTodayLook();
      final look = TodayLook.fromJson(wire);

      expect(jsonEncode(look.snapshot), jsonEncode(wire));
      expect(look.snapshot['selectedItemIds'], [_uuid1, _uuid2, _uuid3]);
    });

    test('SavedTodayLook parses the 201 body', () {
      final wire = wireTodayLook();
      final saved = SavedTodayLook.fromJson(wireSavedLook(wire));

      expect(saved.id, _savedId);
      expect(saved.title, "Today's Look");
      expect(saved.sourceContext, 'daily');
      expect(jsonEncode(saved.snapshot), jsonEncode(wire));
    });
  });

  group('B. client GET path', () {
    test('getTodayLook hits GET /v1/looks/today with auth', () async {
      late Uri seen;
      late String method;
      late Map<String, String> headers;
      final client = TodayLookClient(
        client: MockClient((request) async {
          seen = request.url;
          method = request.method;
          headers = request.headers;
          return http.Response(jsonEncode(wireTodayLook()), 200);
        }),
      );

      final result = await client.getTodayLook();

      expect(method, 'GET');
      expect(seen.path, '/v1/looks/today');
      expect(seen.queryParameters, isEmpty);
      expect(headers['Authorization'], 'Bearer dev');
      expect(result.available, isTrue);
      expect(result.look!.title, "Today's Look");
      expect(result.look!.components.first.id, _uuid1);
    });

    test('getTodayLook maps 404 to noneAvailable (not an error)', () async {
      final client = TodayLookClient(
        client: MockClient((_) async => http.Response('{}', 404)),
      );

      final result = await client.getTodayLook();

      expect(result.available, isFalse);
      expect(result.noneAvailable, isTrue);
      expect(result.failure, isNull);
    });
  });

  group('C. client POST regenerate path + seed', () {
    test(
      'regenerate posts to /v1/looks/today with the seed verbatim',
      () async {
        late Uri seen;
        late String method;
        final client = TodayLookClient(
          client: MockClient((request) async {
            seen = request.url;
            method = request.method;
            return http.Response(
              jsonEncode(wireTodayLook(title: 'Regenerated Look')),
              200,
            );
          }),
        );

        final result = await client.regenerateTodayLook(seed: 'look-1');

        expect(method, 'POST');
        expect(seen.path, '/v1/looks/today');
        expect(seen.queryParameters['seed'], 'look-1');
        expect(result.available, isTrue);
        expect(result.look!.title, 'Regenerated Look');
      },
    );

    test('regenerate without seed posts with no query', () async {
      late Uri seen;
      final client = TodayLookClient(
        client: MockClient((request) async {
          seen = request.url;
          return http.Response(jsonEncode(wireTodayLook()), 200);
        }),
      );

      await client.regenerateTodayLook();

      expect(seen.path, '/v1/looks/today');
      expect(seen.queryParameters, isEmpty);
    });
  });

  group('errors map to typed failures, never fake looks', () {
    test('status mapping covers the frozen table', () async {
      final cases = {
        401: TodayLookFailure.unauthorized,
        422: TodayLookFailure.invalidInput,
        429: TodayLookFailure.rateLimited,
        503: TodayLookFailure.serviceUnavailable,
        500: TodayLookFailure.unknown,
      };
      for (final entry in cases.entries) {
        final client = TodayLookClient(
          client: MockClient((_) async => http.Response('{}', entry.key)),
        );
        final getResult = await client.getTodayLook();
        expect(getResult.available, isFalse, reason: '${entry.key}');
        expect(getResult.noneAvailable, isFalse, reason: '${entry.key}');
        expect(getResult.failure, entry.value, reason: '${entry.key}');

        final regenResult = await client.regenerateTodayLook(seed: 'look-1');
        expect(regenResult.failure, entry.value, reason: '${entry.key}');
      }
    });

    test('network failure and malformed 200 fail closed', () async {
      final offline = TodayLookClient(
        client: MockClient((_) async => throw Exception('down')),
      );
      expect(
        (await offline.getTodayLook()).failure,
        TodayLookFailure.networkError,
      );
      expect(
        (await offline.regenerateTodayLook(seed: 'look-1')).failure,
        TodayLookFailure.networkError,
      );

      final malformed = TodayLookClient(
        client: MockClient(
          (_) async => http.Response(jsonEncode({'nope': true}), 200),
        ),
      );
      final result = await malformed.getTodayLook();
      expect(result.available, isFalse);
      expect(result.failure, TodayLookFailure.unknown);
    });
  });

  group('D. save path + required idempotency key', () {
    test('save posts daily snapshot with the key header', () async {
      late Uri seen;
      late String method;
      late Map<String, String> headers;
      late Map<String, dynamic> body;
      final wire = wireTodayLook();
      final client = TodayLookClient(
        client: MockClient((request) async {
          seen = request.url;
          method = request.method;
          headers = request.headers;
          body = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(jsonEncode(wireSavedLook(wire)), 201);
        }),
      );

      final saved = await client.saveTodayLook(
        title: "Today's Look",
        snapshot: wire,
        idempotencyKey: 'key-1',
      );

      expect(method, 'POST');
      expect(seen.path, '/v1/looks/today/save');
      expect(headers['Idempotency-Key'], 'key-1');
      expect(headers['Authorization'], 'Bearer dev');
      // P. sourceContext is daily (hardcoded, never parameterized).
      expect(body['sourceContext'], 'daily');
      expect(body['title'], "Today's Look");
      // Q. snapshot travels verbatim.
      expect(jsonEncode(body['snapshot']), jsonEncode(wire));
      expect(saved, isNotNull);
      expect(saved!.sourceContext, 'daily');
    });

    test('save without a key fails closed with no network call', () async {
      var calls = 0;
      final client = TodayLookClient(
        client: MockClient((_) async {
          calls += 1;
          return http.Response('{}', 201);
        }),
      );

      final saved = await client.saveTodayLook(
        title: "Today's Look",
        snapshot: wireTodayLook(),
        idempotencyKey: '',
      );

      expect(saved, isNull);
      expect(calls, 0);
    });

    test('save rejection/conflict and offline map to null', () async {
      for (final status in [401, 404, 409, 422, 429, 500]) {
        final client = TodayLookClient(
          client: MockClient((_) async => http.Response('{}', status)),
        );
        expect(
          await client.saveTodayLook(
            title: "Today's Look",
            snapshot: wireTodayLook(),
            idempotencyKey: 'key-$status',
          ),
          isNull,
          reason: '$status',
        );
      }
      final offline = TodayLookClient(
        client: MockClient((_) async => throw Exception('down')),
      );
      expect(
        await offline.saveTodayLook(
          title: "Today's Look",
          snapshot: wireTodayLook(),
          idempotencyKey: 'key-offline',
        ),
        isNull,
      );
    });

    test('idempotency keys are fresh per attempt and UUID-shaped', () {
      final first = newTodayLookIdempotencyKey();
      final second = newTodayLookIdempotencyKey();
      final uuid = RegExp(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
      );

      expect(first, isNot(second));
      expect(uuid.hasMatch(first), isTrue);
      expect(uuid.hasMatch(second), isTrue);
    });
  });

  group('E. repository mapping', () {
    test('repository passes fetch/regenerate through verbatim', () async {
      final repo = TodayLookRepositoryImpl(
        client: TodayLookClient(
          client: MockClient((request) async {
            if (request.method == 'POST') {
              return http.Response(
                jsonEncode(wireTodayLook(title: 'Seeded Look')),
                200,
              );
            }
            return http.Response(jsonEncode(wireTodayLook()), 200);
          }),
        ),
      );

      final getResult = await repo.getTodayLook();
      expect(getResult.available, isTrue);
      expect(getResult.look!.title, "Today's Look");

      final regenResult = await repo.regenerateTodayLook(seed: 'look-2');
      expect(regenResult.available, isTrue);
      expect(regenResult.look!.title, 'Seeded Look');

      final empty = TodayLookRepositoryImpl(
        client: TodayLookClient(
          client: MockClient((_) async => http.Response('{}', 404)),
        ),
      );
      expect((await empty.getTodayLook()).noneAvailable, isTrue);
    });

    test(
      'repository save passes snapshot through and null on failure',
      () async {
        final wire = wireTodayLook();
        final repo = TodayLookRepositoryImpl(
          client: TodayLookClient(
            client: MockClient(
              (_) async => http.Response(jsonEncode(wireSavedLook(wire)), 201),
            ),
          ),
        );

        final saved = await repo.saveTodayLook(
          title: "Today's Look",
          snapshot: wire,
          idempotencyKey: 'repo-key-1',
        );

        expect(saved, isNotNull);
        expect(jsonEncode(saved!.snapshot), jsonEncode(wire));

        final failing = TodayLookRepositoryImpl(
          client: TodayLookClient(
            client: MockClient((_) async => http.Response('{}', 500)),
          ),
        );
        expect(
          await failing.saveTodayLook(
            title: "Today's Look",
            snapshot: wire,
            idempotencyKey: 'repo-key-2',
          ),
          isNull,
        );
      },
    );
  });

  group('R/S/W. wire safety: no wear, no local IDs, no event fetch', () {
    test('fetch/regenerate/save never touch wear or event endpoints', () async {
      final paths = <String>[];
      final wire = wireTodayLook();
      final client = TodayLookClient(
        client: MockClient((request) async {
          paths.add(request.url.path);
          if (request.url.path.endsWith('/save')) {
            return http.Response(jsonEncode(wireSavedLook(wire)), 201);
          }
          return http.Response(jsonEncode(wire), 200);
        }),
      );

      await client.getTodayLook();
      await client.regenerateTodayLook(seed: 'look-1');
      await client.saveTodayLook(
        title: "Today's Look",
        snapshot: wire,
        idempotencyKey: 'safety-key',
      );

      expect(paths, [
        '/v1/looks/today',
        '/v1/looks/today',
        '/v1/looks/today/save',
      ]);
      expect(paths.any((p) => p.contains('wear')), isFalse);
      expect(paths.any((p) => p.contains('event')), isFalse);
      expect(paths.any((p) => p.contains('signal')), isFalse);
    });

    test('S. no local numeric IDs are ever sent', () async {
      late Map<String, dynamic> saveBody;
      final wire = wireTodayLook();
      final client = TodayLookClient(
        client: MockClient((request) async {
          if (request.url.path.endsWith('/save')) {
            saveBody = jsonDecode(request.body) as Map<String, dynamic>;
            return http.Response(jsonEncode(wireSavedLook(wire)), 201);
          }
          return http.Response(jsonEncode(wire), 200);
        }),
      );

      await client.getTodayLook();
      await client.regenerateTodayLook(seed: 'look-3');
      await client.saveTodayLook(
        title: "Today's Look",
        snapshot: wire,
        idempotencyKey: 'numeric-key',
      );

      final encoded = jsonEncode(saveBody);
      expect(RegExp(r'"id"\s*:\s*"\d+"').hasMatch(encoded), isFalse);
      expect(
        (saveBody['snapshot'] as Map<String, dynamic>)['selectedItemIds'],
        [_uuid1, _uuid2, _uuid3],
      );
      expect(
        ((saveBody['snapshot'] as Map<String, dynamic>)['components']
                as List<dynamic>)
            .map((e) => (e as Map<String, dynamic>)['id']),
        [_uuid1, _uuid2, _uuid3],
      );
    });
  });
}
