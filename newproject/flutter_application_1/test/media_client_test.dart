import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:fansivibe/features/media/data/media_client.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('MediaClient', () {
    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();
      LocalStorage.init(prefs: prefs);
      await AuthSession.saveSession('test-token-123');
    });

    tearDown(() {
      AuthSession.clearSession();
      LocalStorage.resetForTest();
    });

    test('authorizeUpload succeeds with valid payload', () async {
      final mockHttpClient = MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/v1/media/uploads');
        expect(request.headers['Authorization'], 'Bearer test-token-123');
        expect(request.headers['Idempotency-Key'], 'idem-key-1');

        final body = jsonDecode(request.body) as Map<String, dynamic>;
        expect(body['purpose'], 'wardrobe_item');
        expect(body['contentType'], 'image/webp');
        expect(body['sizeBytes'], 1024);
        expect(body['clientAssertionSha256'], 'a' * 64);

        return http.Response(
          jsonEncode({
            'uploadId': '00000000-0000-0000-0000-000000000001',
            'uploadUrl': 'https://r2.test/staging-put',
            'stagingKey': 'users/u1/staging/00000000-0000-0000-0000-000000000001.webp',
            'expiresAt': DateTime.now().add(const Duration(minutes: 15)).toIso8601String(),
            'expiresInSeconds': 900,
          }),
          201,
        );
      });

      final mediaClient = MediaClient(
        client: mockHttpClient,
        baseUrl: 'https://api.test',
      );

      final res = await mediaClient.authorizeUpload(
        clientSizeBytes: 1024,
        clientSha256: 'a' * 64,
        idempotencyKey: 'idem-key-1',
      );

      expect(res, isNotNull);
      expect(res!.uploadId, '00000000-0000-0000-0000-000000000001');
      expect(res.presignedPutUrl, 'https://r2.test/staging-put');
      expect(res.stagingKey, contains('staging'));
    });

    test('authorizeUpload returns null on server rejection', () async {
      final mockHttpClient = MockClient((request) async {
        return http.Response('{"detail": "Disallowed MIME type"}', 422);
      });

      final mediaClient = MediaClient(
        client: mockHttpClient,
        baseUrl: 'https://api.test',
      );

      final res = await mediaClient.authorizeUpload(
        clientSizeBytes: 1024,
        clientSha256: 'a' * 64,
        idempotencyKey: 'idem-key-2',
      );

      expect(res, isNull);
    });

    test('uploadBytesDirect executes PUT directly to storage URL', () async {
      final mockHttpClient = MockClient((request) async {
        expect(request.method, 'PUT');
        expect(request.url.toString(), 'https://r2.test/staging-put');
        expect(request.headers['Content-Type'], 'image/webp');
        expect(request.bodyBytes, equals(Uint8List.fromList([1, 2, 3, 4])));
        return http.Response('', 200);
      });

      final mediaClient = MediaClient(client: mockHttpClient);
      final ok = await mediaClient.uploadBytesDirect(
        presignedPutUrl: 'https://r2.test/staging-put',
        bytes: Uint8List.fromList([1, 2, 3, 4]),
      );

      expect(ok, isTrue);
    });

    test('uploadBytesDirect returns false on failure or rejection', () async {
      final mockHttpClient = MockClient((request) async {
        return http.Response('AccessDenied', 403);
      });

      final mediaClient = MediaClient(client: mockHttpClient);
      final ok = await mediaClient.uploadBytesDirect(
        presignedPutUrl: 'https://r2.test/staging-put',
        bytes: Uint8List.fromList([1, 2, 3]),
      );

      expect(ok, isFalse);
    });

    test('completeUpload posts completion and parses published media ref', () async {
      final mockHttpClient = MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/v1/media/uploads/up-123/complete');
        return http.Response(
          jsonEncode({
            'uploadId': 'up-123',
            'objectKey': 'users/u1/wardrobe/up-123/attempt_1_abc.webp',
            'mediaType': 'image/webp',
            'width': 800,
            'height': 1200,
            'sizeBytes': 2048,
            'contentHash': 'f' * 64,
            'uploadedAt': DateTime.now().toIso8601String(),
            'status': 'ready',
          }),
          200,
        );
      });

      final mediaClient = MediaClient(
        client: mockHttpClient,
        baseUrl: 'https://api.test',
      );

      final res = await mediaClient.completeUpload(uploadId: 'up-123');
      expect(res, isNotNull);
      expect(res!.uploadId, 'up-123');
      expect(res.canonicalKey, contains('attempt_1_abc.webp'));
      expect(res.width, 800);
      expect(res.height, 1200);
      expect(res.sha256, 'f' * 64);
      expect(res.status, 'ready');
    });

    test('getDownloadUrl fetches 15-minute temporary presigned GET URL', () async {
      final mockHttpClient = MockClient((request) async {
        expect(request.method, 'GET');
        expect(request.url.path, '/v1/media/url');
        expect(request.url.queryParameters['uploadId'], 'up-123');
        return http.Response(
          jsonEncode({
            'uploadId': 'up-123',
            'objectKey': 'users/u1/wardrobe/up-123/attempt_1_abc.webp',
            'downloadUrl': 'https://r2.test/presigned-get-signed',
            'expiresAt': DateTime.now().add(const Duration(minutes: 15)).toIso8601String(),
            'expiresInSeconds': 900,
          }),
          200,
        );
      });

      final mediaClient = MediaClient(
        client: mockHttpClient,
        baseUrl: 'https://api.test',
      );

      final res = await mediaClient.getDownloadUrl(uploadId: 'up-123');
      expect(res, isNotNull);
      expect(res!.uploadId, 'up-123');
      expect(res.downloadUrl, 'https://r2.test/presigned-get-signed');
      expect(res.expiresInSeconds, 900);
    });
  });
}
