import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:fansivibe/features/assistant/data/assistant_client.dart';
import 'package:fansivibe/features/assistant/data/models.dart';
import 'package:fansivibe/features/assistant/domain/assistant_service.dart';

const String _uuidA = '78ff3686-c950-4cd6-84c3-7e18d6634dfa';
const String _uuidB = '4412f646-56a9-4afa-8717-b330da03b3d0';

OutfitIntelligence intelligence({List<String> ids = const ['1', '2']}) {
  return OutfitIntelligence(
    selectedItemIds: ids,
    outfitComposition: const OutfitComposition(
      topIds: [],
      bottomIds: [],
      outerwearIds: [],
      footwearIds: [],
      accessoryIds: [],
      styleScore: 0,
    ),
    occasion: 'office',
    stylingRationale: 'r',
    compatibilityRationale: 'c',
    confidence: 0.9,
    explanation: 'e',
    dataAvailability: 'full',
  );
}

void main() {
  group('isBackendUuidShape', () {
    test('accepts canonical UUIDs (either case)', () {
      expect(isBackendUuidShape(_uuidA), isTrue);
      expect(isBackendUuidShape(_uuidA.toUpperCase()), isTrue);
    });

    test('rejects local engine IDs and malformed values', () {
      for (final bad in [
        '1',
        '24',
        'blazer-001',
        'comp_1',
        '',
        _uuidA.substring(1),
        '${_uuidA}x',
        _uuidA.replaceFirst('-', 'x'),
        'zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz',
      ]) {
        expect(isBackendUuidShape(bad), isFalse, reason: bad);
      }
    });
  });

  group('OutfitSaveRequest sanitization (P1-1)', () {
    test('drops local IDs, keeps UUIDs in order', () {
      final request = OutfitSaveRequest.fromOutfitIntelligence(
        intelligence(ids: ['1', _uuidA, 'deleted-id', _uuidB, '24']),
      );
      expect(request.snapshot['selectedItemIds'], [_uuidA, _uuidB]);
    });

    test('omits selectedItemIds when nothing UUID-shaped survives', () {
      final request = OutfitSaveRequest.fromOutfitIntelligence(
        intelligence(ids: ['1', 'blazer-001']),
      );
      expect(request.snapshot, isNot(contains('selectedItemIds')));
    });

    test('keeps sourceContext outfit (frozen M7 vocabulary)', () {
      final request = OutfitSaveRequest.fromOutfitIntelligence(
        intelligence(ids: [_uuidA]),
      );
      expect(request.sourceContext, 'outfit');
      expect(request.lookId, isNull);
    });

    test('no local ID appears anywhere in the wire body', () {
      final request = OutfitSaveRequest.fromOutfitIntelligence(
        intelligence(ids: ['1', _uuidA]),
      );
      final encoded = jsonEncode(request.toJson());
      expect(encoded.contains('"1"'), isFalse);
      expect(encoded, contains(_uuidA));
    });
  });

  group('saveOutfitLook client (P1-1)', () {
    test('sends Authorization + Idempotency-Key and parses 201', () async {
      Map<String, String>? seenHeaders;
      final client = AssistantClient(
        client: MockClient((request) async {
          seenHeaders = request.headers;
          return http.Response(
            jsonEncode({'id': 's-1', 'title': 'Office Outfit'}),
            201,
          );
        }),
      );
      final saved = await client.saveOutfitLook(
        request: OutfitSaveRequest.fromOutfitIntelligence(
          intelligence(ids: [_uuidA]),
        ),
        idempotencyKey: 'k-1',
      );
      expect(seenHeaders!['Authorization'], 'Bearer dev');
      expect(seenHeaders!['Idempotency-Key'], 'k-1');
      expect(saved, isNotNull);
      expect(saved!.id, 's-1');
      client.dispose();
    });

    test(
      '401/409/422 map to null (unsaved, retryable) without throwing',
      () async {
        for (final status in [401, 409, 422]) {
          final client = AssistantClient(
            client: MockClient((_) async => http.Response('{}', status)),
          );
          final saved = await client.saveOutfitLook(
            request: OutfitSaveRequest.fromOutfitIntelligence(intelligence()),
            idempotencyKey: 'k-$status',
          );
          expect(saved, isNull, reason: 'status $status');
          client.dispose();
        }
      },
    );

    test('offline transport maps to null without throwing', () async {
      final client = AssistantClient(
        client: MockClient((_) async => throw Exception('offline')),
      );
      final saved = await client.saveOutfitLook(
        request: OutfitSaveRequest.fromOutfitIntelligence(intelligence()),
        idempotencyKey: 'k-off',
      );
      expect(saved, isNull);
      client.dispose();
    });
  });

  group('saveOutfit service (P1-1)', () {
    test('true on 201, false on 401 with retry re-issuing', () async {
      var calls = 0;
      final ok = AssistantService(
        client: AssistantClient(
          client: MockClient(
            (_) async => http.Response(
              jsonEncode({'id': 's-1', 'title': 'Office Outfit'}),
              201,
            ),
          ),
        ),
      );
      expect(await ok.saveOutfit(intelligence(ids: [_uuidA])), isTrue);

      final denied = AssistantService(
        client: AssistantClient(
          client: MockClient((_) async {
            calls++;
            return http.Response('{}', 401);
          }),
        ),
      );
      expect(await denied.saveOutfit(intelligence(ids: [_uuidA])), isFalse);
      expect(await denied.saveOutfit(intelligence(ids: [_uuidA])), isFalse);
      expect(calls, 2);
      ok.dispose();
      denied.dispose();
    });
  });
}
