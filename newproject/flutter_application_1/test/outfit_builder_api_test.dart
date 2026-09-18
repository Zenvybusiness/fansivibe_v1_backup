import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:fansivibe/features/outfit_builder/data/outfit_client.dart';
import 'package:fansivibe/features/outfit_builder/data/outfit_models.dart';
import 'package:fansivibe/features/outfit_builder/data/outfit_repository.dart';

const String _uuid1 = '78ff3686-c950-4cd6-84c3-7e18d6634dfa';
const String _uuid2 = '4412f646-56a9-4afa-8717-b330da03b3d0';
const String _uuid3 = '9d8f2c1a-3b4e-4f5a-8c6d-7e8f9a0b1c2d';
const String _savedId = 'b3e1a2c4-5d6f-47a8-b9c0-d1e2f3a4b5c6';

/// Exact M13 wire shape (honesty subset: no colorHex, no alternatives,
/// no description).
Map<String, dynamic> wireOutfit({String title = 'Office Outfit'}) {
  return {
    'title': title,
    'matchScore': 0.87,
    'components': [
      {
        'id': _uuid1,
        'name': 'Navy Blazer',
        'category': 'outerwear',
        'color': 'navy',
        'material': 'wool',
        'reason': 'Chosen outerwear piece for your Office outfit',
      },
      {
        'id': _uuid2,
        'name': 'White Tee',
        'category': 'tops',
        'color': 'white',
        'reason': 'Chosen tops piece for your Office outfit',
      },
      {
        'id': _uuid3,
        'name': 'Dark Jeans',
        'category': 'bottoms',
        'color': 'indigo',
        'material': 'denim',
        'reason': 'Chosen bottoms piece for your Office outfit',
      },
    ],
    'reasons': [
      'Picked for a Office occasion',
      'Covers 3 categories: tops, bottoms, outerwear',
    ],
    'colorHarmony': 'warm palette across 3 pieces: navy, white, indigo.',
    'bodyFit': 'Assembled for a tailored fit across 3 pieces.',
    'occasionMatch': 'Matched for Office across 3 categories.',
    'styleScoreImpact': '87% ensemble match from 3 owned pieces.',
    'improvementSuggestion':
        'Consider adding footwear to complete the coverage.',
    'selectedOccasion': 'office',
    'selectedMood': 'classic',
    'selectedColorPalette': 'warm',
  };
}

Map<String, dynamic> wireSavedOutfit(Map<String, dynamic> snapshot) => {
  'id': _savedId,
  'lookId': null,
  'title': 'Office Outfit',
  'sourceContext': 'outfit',
  'snapshot': snapshot,
  'sourceRunId': null,
  'createdAt': '2030-08-15T10:00:00.000Z',
};

void main() {
  group('OutfitRecommendation models', () {
    test('parses the exact backend wire shape', () {
      final rec = OutfitRecommendation.fromJson(wireOutfit());

      expect(rec.title, 'Office Outfit');
      expect(rec.matchScore, 0.87);
      expect(rec.components, hasLength(3));
      expect(rec.components.first.id, _uuid1);
      expect(rec.components.first.name, 'Navy Blazer');
      expect(rec.components.first.reason, contains('Office outfit'));
      expect(rec.components[1].material, isNull);
      expect(rec.reasons, hasLength(2));
      expect(rec.colorHarmony, contains('warm'));
      expect(rec.bodyFit, contains('tailored'));
      expect(rec.occasionMatch, contains('Office'));
      expect(rec.styleScoreImpact, contains('87%'));
      expect(rec.improvementSuggestion, isNotEmpty);
      expect(rec.selectedOccasion, 'office');
      expect(rec.selectedMood, 'classic');
      expect(rec.selectedColorPalette, 'warm');
    });

    test('wire map carries no colorHex, alternatives, or description', () {
      final wire = wireOutfit();

      for (final banned in [
        'colorHex',
        'alternatives',
        'description',
        'weather',
        'confidence',
        'occasion',
      ]) {
        expect(wire.containsKey(banned), isFalse, reason: banned);
      }
    });

    test('strict parsing throws on malformed bodies', () {
      expect(() => OutfitRecommendation.fromJson({}), throwsA(anything));
      expect(
        () => OutfitRecommendation.fromJson({
          ...wireOutfit(),
          'matchScore': 'high',
        }),
        throwsA(anything),
      );
      expect(
        () => OutfitRecommendation.fromJson({
          ...wireOutfit(),
          'components': 'nope',
        }),
        throwsA(anything),
      );
    });

    test('snapshot is the response body verbatim', () {
      final wire = wireOutfit();
      final rec = OutfitRecommendation.fromJson(wire);

      expect(jsonEncode(rec.snapshot), jsonEncode(wire));
    });

    test('SavedOutfit parses the 201 body', () {
      final wire = wireOutfit();
      final saved = SavedOutfit.fromJson(wireSavedOutfit(wire));

      expect(saved.id, _savedId);
      expect(saved.title, 'Office Outfit');
      expect(saved.sourceContext, 'outfit');
      expect(jsonEncode(saved.snapshot), jsonEncode(wire));
    });

    test('OutfitGenerateRequest serializes the four prefs', () {
      const request = OutfitGenerateRequest(
        occasion: 'office',
        mood: 'classic',
        fit: 'tailored',
        colorPalette: 'warm',
      );

      expect(request.toJson(), {
        'occasion': 'office',
        'mood': 'classic',
        'fit': 'tailored',
        'colorPalette': 'warm',
      });
      expect(
        OutfitGenerateRequest.fromJson(request.toJson()).occasion,
        'office',
      );
    });
  });

  group('OutfitBuilderClient generate path', () {
    test('generate posts prefs with auth and no seed by default', () async {
      late Uri seen;
      late String method;
      late Map<String, String> headers;
      late Map<String, dynamic> body;
      final client = OutfitBuilderClient(
        client: MockClient((request) async {
          seen = request.url;
          method = request.method;
          headers = request.headers;
          body = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(jsonEncode(wireOutfit()), 200);
        }),
      );

      final result = await client.generateOutfit(
        occasion: 'office',
        mood: 'classic',
        fit: 'tailored',
        colorPalette: 'warm',
      );

      expect(method, 'POST');
      expect(seen.path, '/v1/outfits/generate');
      expect(headers['Authorization'], 'Bearer dev');
      expect(body, {
        'occasion': 'office',
        'mood': 'classic',
        'fit': 'tailored',
        'colorPalette': 'warm',
      });
      expect(body.containsKey('seed'), isFalse);
      expect(result.available, isTrue);
      expect(result.outfit!.title, 'Office Outfit');
      expect(result.outfit!.components.first.id, _uuid1);
    });

    test('generate sends the seed in the body verbatim', () async {
      late Map<String, dynamic> body;
      final client = OutfitBuilderClient(
        client: MockClient((request) async {
          body = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(jsonEncode(wireOutfit()), 200);
        }),
      );

      await client.generateOutfit(
        occasion: 'office',
        mood: 'classic',
        fit: 'tailored',
        colorPalette: 'warm',
        seed: 'outfit-1',
      );

      expect(body['seed'], 'outfit-1');
    });

    test('generate maps 204 to noneAvailable (not an error)', () async {
      final client = OutfitBuilderClient(
        client: MockClient((_) async => http.Response('', 204)),
      );

      final result = await client.generateOutfit(
        occasion: 'office',
        mood: 'classic',
        fit: 'tailored',
        colorPalette: 'warm',
      );

      expect(result.available, isFalse);
      expect(result.noneAvailable, isTrue);
      expect(result.failure, isNull);
    });

    test('generate carries the verbatim 204 empty reason', () async {
      Future<String?> reason(Map<String, String> headers) async {
        final client = OutfitBuilderClient(
          client: MockClient(
            (_) async => http.Response('', 204, headers: headers),
          ),
        );
        final result = await client.generateOutfit(
          occasion: 'office',
          mood: 'classic',
          fit: 'tailored',
          colorPalette: 'warm',
        );
        expect(result.noneAvailable, isTrue);
        return result.emptyReason;
      }

      // Known backend code passes through verbatim.
      expect(
        await reason({'x-outfit-empty-reason': 'empty_wardrobe'}),
        'empty_wardrobe',
      );
      // Missing header (older backend) → null → generic empty copy.
      expect(await reason({}), isNull);
      // Unknown future code passes through untouched (screen falls back).
      expect(await reason({'x-outfit-empty-reason': 'future_code'}), 'future_code');
    });

    test('generate maps the frozen error table', () async {
      final cases = {
        401: OutfitFailure.unauthorized,
        422: OutfitFailure.invalidInput,
        429: OutfitFailure.rateLimited,
        503: OutfitFailure.serviceUnavailable,
        500: OutfitFailure.unknown,
      };
      for (final entry in cases.entries) {
        final client = OutfitBuilderClient(
          client: MockClient((_) async => http.Response('{}', entry.key)),
        );
        final result = await client.generateOutfit(
          occasion: 'office',
          mood: 'classic',
          fit: 'tailored',
          colorPalette: 'warm',
        );
        expect(result.available, isFalse, reason: '${entry.key}');
        expect(result.noneAvailable, isFalse, reason: '${entry.key}');
        expect(result.failure, entry.value, reason: '${entry.key}');
      }
    });

    test('network failure and malformed 200 fail closed', () async {
      final offline = OutfitBuilderClient(
        client: MockClient((_) async => throw Exception('down')),
      );
      expect(
        (await offline.generateOutfit(
          occasion: 'office',
          mood: 'classic',
          fit: 'tailored',
          colorPalette: 'warm',
        )).failure,
        OutfitFailure.networkError,
      );

      final malformed = OutfitBuilderClient(
        client: MockClient(
          (_) async => http.Response(jsonEncode({'nope': true}), 200),
        ),
      );
      final result = await malformed.generateOutfit(
        occasion: 'office',
        mood: 'classic',
        fit: 'tailored',
        colorPalette: 'warm',
      );
      expect(result.available, isFalse);
      expect(result.failure, OutfitFailure.unknown);
    });
  });

  group('OutfitBuilderClient save path + required idempotency key', () {
    test('save posts outfit snapshot with the key header', () async {
      late Uri seen;
      late String method;
      late Map<String, String> headers;
      late Map<String, dynamic> body;
      final wire = wireOutfit();
      final client = OutfitBuilderClient(
        client: MockClient((request) async {
          seen = request.url;
          method = request.method;
          headers = request.headers;
          body = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response(jsonEncode(wireSavedOutfit(wire)), 201);
        }),
      );

      final saved = await client.saveOutfit(
        title: 'Office Outfit',
        snapshot: wire,
        idempotencyKey: 'key-1',
      );

      expect(method, 'POST');
      expect(seen.path, '/v1/outfits/saved');
      expect(headers['Idempotency-Key'], 'key-1');
      expect(headers['Authorization'], 'Bearer dev');
      expect(body['sourceContext'], 'outfit');
      expect(body['title'], 'Office Outfit');
      expect(jsonEncode(body['snapshot']), jsonEncode(wire));
      expect(saved, isNotNull);
      expect(saved!.sourceContext, 'outfit');
    });

    test('save without a key fails closed with no network call', () async {
      var calls = 0;
      final client = OutfitBuilderClient(
        client: MockClient((_) async {
          calls += 1;
          return http.Response('{}', 201);
        }),
      );

      final saved = await client.saveOutfit(
        title: 'Office Outfit',
        snapshot: wireOutfit(),
        idempotencyKey: '',
      );

      expect(saved, isNull);
      expect(calls, 0);
    });

    test('save rejection/conflict and offline map to null', () async {
      for (final status in [401, 404, 409, 422, 429, 500]) {
        final client = OutfitBuilderClient(
          client: MockClient((_) async => http.Response('{}', status)),
        );
        expect(
          await client.saveOutfit(
            title: 'Office Outfit',
            snapshot: wireOutfit(),
            idempotencyKey: 'key-$status',
          ),
          isNull,
          reason: '$status',
        );
      }
      final offline = OutfitBuilderClient(
        client: MockClient((_) async => throw Exception('down')),
      );
      expect(
        await offline.saveOutfit(
          title: 'Office Outfit',
          snapshot: wireOutfit(),
          idempotencyKey: 'key-offline',
        ),
        isNull,
      );
    });

    test('idempotency keys are fresh per attempt and UUID-shaped', () {
      final first = newOutfitBuilderIdempotencyKey();
      final second = newOutfitBuilderIdempotencyKey();
      final uuid = RegExp(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
      );

      expect(first, isNot(second));
      expect(uuid.hasMatch(first), isTrue);
      expect(uuid.hasMatch(second), isTrue);
    });
  });

  group('OutfitBuilderRepository mapping', () {
    test('repository passes generate/save through verbatim', () async {
      final wire = wireOutfit();
      final seeds = <String?>[];
      final repo = OutfitBuilderRepositoryImpl(
        client: OutfitBuilderClient(
          client: MockClient((request) async {
            if (request.url.path.endsWith('/saved')) {
              return http.Response(jsonEncode(wireSavedOutfit(wire)), 201);
            }
            final body = jsonDecode(request.body) as Map<String, dynamic>;
            seeds.add(body['seed'] as String?);
            return http.Response(jsonEncode(wire), 200);
          }),
        ),
      );

      final first = await repo.generateOutfit(
        occasion: 'office',
        mood: 'classic',
        fit: 'tailored',
        colorPalette: 'warm',
      );
      expect(first.available, isTrue);

      final second = await repo.generateOutfit(
        occasion: 'office',
        mood: 'classic',
        fit: 'tailored',
        colorPalette: 'warm',
        seed: 'outfit-2',
      );
      expect(second.available, isTrue);
      expect(seeds, [isNull, 'outfit-2']);

      final saved = await repo.saveOutfit(
        title: 'Office Outfit',
        snapshot: wire,
        idempotencyKey: 'repo-key-1',
      );
      expect(saved, isNotNull);
      expect(jsonEncode(saved!.snapshot), jsonEncode(wire));

      final failing = OutfitBuilderRepositoryImpl(
        client: OutfitBuilderClient(
          client: MockClient((_) async => http.Response('{}', 500)),
        ),
      );
      expect(
        (await failing.generateOutfit(
          occasion: 'office',
          mood: 'classic',
          fit: 'tailored',
          colorPalette: 'warm',
        )).failure,
        OutfitFailure.unknown,
      );
      expect(
        await failing.saveOutfit(
          title: 'Office Outfit',
          snapshot: wire,
          idempotencyKey: 'repo-key-2',
        ),
        isNull,
      );
    });
  });

  group('wire safety: no wear, no local IDs, no event fetch', () {
    test(
      'generate/save never touch wear, event, or signal endpoints',
      () async {
        final paths = <String>[];
        final wire = wireOutfit();
        final client = OutfitBuilderClient(
          client: MockClient((request) async {
            paths.add(request.url.path);
            if (request.url.path.endsWith('/saved')) {
              return http.Response(jsonEncode(wireSavedOutfit(wire)), 201);
            }
            return http.Response(jsonEncode(wire), 200);
          }),
        );

        await client.generateOutfit(
          occasion: 'office',
          mood: 'classic',
          fit: 'tailored',
          colorPalette: 'warm',
          seed: 'outfit-1',
        );
        await client.saveOutfit(
          title: 'Office Outfit',
          snapshot: wire,
          idempotencyKey: 'safety-key',
        );

        expect(paths, ['/v1/outfits/generate', '/v1/outfits/saved']);
        expect(paths.any((p) => p.contains('wear')), isFalse);
        expect(paths.any((p) => p.contains('event')), isFalse);
        expect(paths.any((p) => p.contains('signal')), isFalse);
      },
    );

    test('no local numeric IDs are ever sent', () async {
      late Map<String, dynamic> saveBody;
      final wire = wireOutfit();
      final client = OutfitBuilderClient(
        client: MockClient((request) async {
          if (request.url.path.endsWith('/saved')) {
            saveBody = jsonDecode(request.body) as Map<String, dynamic>;
            return http.Response(jsonEncode(wireSavedOutfit(wire)), 201);
          }
          return http.Response(jsonEncode(wire), 200);
        }),
      );

      await client.generateOutfit(
        occasion: 'office',
        mood: 'classic',
        fit: 'tailored',
        colorPalette: 'warm',
      );
      await client.saveOutfit(
        title: 'Office Outfit',
        snapshot: wire,
        idempotencyKey: 'numeric-key',
      );

      final encoded = jsonEncode(saveBody);
      expect(RegExp(r'"id"\s*:\s*"\d+"').hasMatch(encoded), isFalse);
      expect(
        ((saveBody['snapshot'] as Map<String, dynamic>)['components']
                as List<dynamic>)
            .map((e) => (e as Map<String, dynamic>)['id']),
        [_uuid1, _uuid2, _uuid3],
      );
    });
  });
}
