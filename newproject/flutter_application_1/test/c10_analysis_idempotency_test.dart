import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/features/grooming/data/grooming_client.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_client.dart';
import 'package:fansivibe/features/outfit_scan/data/outfit_scan_client.dart';
import 'package:fansivibe/features/wardrobe/data/garment_client.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    LocalStorage.init(prefs: await SharedPreferences.getInstance());
    AuthSession.resetForTest();
  });

  tearDown(() async {
    AuthSession.resetForTest();
  });

  final uuidPattern = RegExp(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
  );

  group('Requirement O & Q: Idempotency Key Generators', () {
    test('newGarmentIdempotencyKey generates valid, unique v4 UUIDs', () {
      final key1 = newGarmentIdempotencyKey();
      final key2 = newGarmentIdempotencyKey();
      expect(key1, matches(uuidPattern));
      expect(key2, matches(uuidPattern));
      expect(key1, isNot(equals(key2)));
    });

    test('newOutfitScanIdempotencyKey generates valid, unique v4 UUIDs', () {
      final key1 = newOutfitScanIdempotencyKey();
      final key2 = newOutfitScanIdempotencyKey();
      expect(key1, matches(uuidPattern));
      expect(key2, matches(uuidPattern));
      expect(key1, isNot(equals(key2)));
    });

    test('newHairstyleIdempotencyKey generates valid, unique v4 UUIDs', () {
      final key1 = newHairstyleIdempotencyKey();
      final key2 = newHairstyleIdempotencyKey();
      expect(key1, matches(uuidPattern));
      expect(key2, matches(uuidPattern));
      expect(key1, isNot(equals(key2)));
    });

    test('newGroomingIdempotencyKey generates valid, unique v4 UUIDs', () {
      final key1 = newGroomingIdempotencyKey();
      final key2 = newGroomingIdempotencyKey();
      expect(key1, matches(uuidPattern));
      expect(key2, matches(uuidPattern));
      expect(key1, isNot(equals(key2)));
    });
  });

  group('Requirement P, Q, R: GarmentClient Idempotency', () {
    test('sends Idempotency-Key header, reuses key on failure, clears on 202', () async {
      final capturedHeaders = <String?>[];
      var shouldFail = true;

      final client = GarmentClient(
        client: MockClient((request) async {
          capturedHeaders.add(request.headers['Idempotency-Key']);
          if (shouldFail) {
            return http.Response('server timeout', 504);
          }
          return http.Response(jsonEncode({'run_id': 'run-garment-123'}), 202);
        }),
      );

      final bytes = Uint8List.fromList([1, 2, 3]);

      // 1. First attempt fails: key generated and stored
      final res1 = await client.submitGarmentAnalysisBytes(bytes, filename: 'shirt.jpg');
      expect(res1, isNull);
      expect(capturedHeaders.length, equals(1));
      final keyFirstAttempt = capturedHeaders[0];
      expect(keyFirstAttempt, isNotNull);
      expect(client.activeIdempotencyKey, equals(keyFirstAttempt));

      // 2. Retry attempt: should reuse the EXACT SAME key (P)
      shouldFail = false;
      final res2 = await client.submitGarmentAnalysisBytes(bytes, filename: 'shirt.jpg');
      expect(res2, equals('run-garment-123'));
      expect(capturedHeaders.length, equals(2));
      expect(capturedHeaders[1], equals(keyFirstAttempt));

      // 3. Success clears active key; subsequent action gets fresh key (Q)
      expect(client.activeIdempotencyKey, isNull);
      final res3 = await client.submitGarmentAnalysisBytes(bytes, filename: 'shirt.jpg');
      expect(res3, equals('run-garment-123'));
      expect(capturedHeaders.length, equals(3));
      expect(capturedHeaders[2], isNot(equals(keyFirstAttempt)));
    });
  });

  group('Requirement P, Q, R: OutfitScanClient Idempotency', () {
    test('sends Idempotency-Key header, reuses on retry, resets on success', () async {
      final capturedHeaders = <String?>[];
      var shouldFail = true;

      final client = OutfitScanClient(
        client: MockClient((request) async {
          capturedHeaders.add(request.headers['Idempotency-Key']);
          if (shouldFail) {
            return http.Response('timeout', 504);
          }
          return http.Response(jsonEncode({'run_id': 'run-outfit-456'}), 202);
        }),
      );

      // Attempt 1 fails
      final res1 = await client.submitOutfitAnalysisBytes(
        Uint8List.fromList([10, 20, 30]),
        filename: 'outfit.jpg',
      );
      expect(res1, isNull);
      expect(capturedHeaders.length, equals(1));
      final initialKey = capturedHeaders[0];
      expect(initialKey, isNotNull);
      expect(client.activeIdempotencyKey, equals(initialKey));

      // Attempt 2 (retry) succeeds with SAME key
      shouldFail = false;
      final res2 = await client.submitOutfitAnalysisBytes(
        Uint8List.fromList([10, 20, 30]),
        filename: 'outfit.jpg',
      );
      expect(res2, equals('run-outfit-456'));
      expect(capturedHeaders.length, equals(2));
      expect(capturedHeaders[1], equals(initialKey));

      // Attempt 3 gets fresh key
      expect(client.activeIdempotencyKey, isNull);
      await client.submitOutfitAnalysisBytes(
        Uint8List.fromList([10, 20, 30]),
        filename: 'outfit.jpg',
      );
      expect(capturedHeaders.length, equals(3));
      expect(capturedHeaders[2], isNot(equals(initialKey)));
    });
  });

  group('Requirement P, Q, R: HairstyleClient Idempotency', () {
    test('sends Idempotency-Key header on both image and profile-only passes', () async {
      final capturedHeaders = <String?>[];
      var returnStatus = 202;

      final client = HairstyleClient(
        client: MockClient((request) async {
          capturedHeaders.add(request.headers['Idempotency-Key']);
          return http.Response(
            jsonEncode({'run_id': 'run-hs-789'}),
            returnStatus,
          );
        }),
      );

      // 1. Profile-only pass sends key
      final run1 = await client.submitHairstyleAnalysis();
      expect(run1, equals('run-hs-789'));
      expect(capturedHeaders.length, equals(1));
      expect(capturedHeaders[0], matches(uuidPattern));

      // 2. Image pass sends key
      final run2 = await client.submitHairstyleAnalysis(
        imageBytes: Uint8List.fromList([1, 2, 3]),
        imageFilename: 'face.jpg',
      );
      expect(run2, equals('run-hs-789'));
      expect(capturedHeaders.length, equals(2));
      expect(capturedHeaders[1], matches(uuidPattern));
      expect(capturedHeaders[1], isNot(equals(capturedHeaders[0])));

      // 3. Retry on failure preserves key
      returnStatus = 500;
      await client.submitHairstyleAnalysis();
      final failedKey = client.activeIdempotencyKey;
      expect(failedKey, isNotNull);

      // Re-invoke with error: reuses failedKey
      await client.submitHairstyleAnalysis();
      expect(capturedHeaders.last, equals(failedKey));
    });
  });

  group('Requirement P, Q, R: GroomingClient Idempotency', () {
    test('sends Idempotency-Key header on grooming submit, reuses on retry', () async {
      final capturedHeaders = <String?>[];
      var returnStatus = 503;

      final client = GroomingClient(
        client: MockClient((request) async {
          capturedHeaders.add(request.headers['Idempotency-Key']);
          return http.Response(
            jsonEncode({'run_id': 'run-grooming-999'}),
            returnStatus,
          );
        }),
      );

      // 1. Failure retains key
      final res1 = await client.submitGroomingAnalysis();
      expect(res1, isNull);
      expect(capturedHeaders.length, equals(1));
      final key1 = capturedHeaders[0];
      expect(key1, matches(uuidPattern));
      expect(client.activeIdempotencyKey, equals(key1));

      // 2. Retry reuses same key
      returnStatus = 202;
      final res2 = await client.submitGroomingAnalysis();
      expect(res2, equals('run-grooming-999'));
      expect(capturedHeaders.length, equals(2));
      expect(capturedHeaders[1], equals(key1));

      // 3. Success clears key
      expect(client.activeIdempotencyKey, isNull);
    });
  });

  group('Requirement S: Polling Behavior Unchanged', () {
    test('polling routes still query run_id without idempotency header', () async {
      final polledUrls = <String>[];
      final client = GroomingClient(
        pollInterval: const Duration(milliseconds: 1),
        client: MockClient((request) async {
          polledUrls.add(request.url.path);
          expect(request.headers.containsKey('Idempotency-Key'), isFalse);
          return http.Response(
            jsonEncode({
              'run_id': 'run-123',
              'run_type': 'grooming',
              'status': 'completed',
              'result': {'recommendations': {'top': {'name': 'Clean Shave'}}},
            }),
            200,
          );
        }),
      );

      final run = await client.pollGroomingRun(runId: 'run-123');
      expect(run, isNotNull);
      expect(run!.isCompleted, isTrue);
      expect(polledUrls, contains('/v1/analysis/runs/run-123'));
    });
  });
}
