import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:fansivibe/features/media/data/media_client.dart';
import 'package:fansivibe/features/media/domain/original_file_manager.dart';
import 'package:fansivibe/features/media/presentation/wardrobe_cache_manager.dart';

void main() {
  group('WardrobeCacheManager', () {
    late Directory tempDir;

    setUp(() {
      tempDir = Directory.systemTemp.createTempSync('fansivibe_cache_test_');
    });

    tearDown(() {
      if (tempDir.existsSync()) {
        tempDir.deleteSync(recursive: true);
      }
    });

    test('retrieves image from remote URL and caches to L1 and L2', () async {
      var fetchCount = 0;
      final mockHttp = MockClient((request) async {
        fetchCount++;
        return http.Response.bytes([10, 20, 30, 40], 200);
      });

      final cacheManager = WardrobeCacheManager(
        httpClient: mockHttp,
        cacheDirectoryPath: '${tempDir.path}/cache',
      );

      // First call fetches from URL
      final bytes1 = await cacheManager.getImage(
        key: 'item_1_key',
        downloadUrl: 'https://r2.test/download-1',
      );
      expect(bytes1, equals(Uint8List.fromList([10, 20, 30, 40])));
      expect(fetchCount, 1);

      // Second call served from memory (L1) without network fetch
      final bytes2 = await cacheManager.getImage(
        key: 'item_1_key',
        downloadUrl: 'https://r2.test/download-1',
      );
      expect(bytes2, equals(bytes1));
      expect(fetchCount, 1);
    });

    test('prefers local original if localOriginalPath exists (Option B)', () async {
      final originalPath = await OriginalFileManager.instance.saveOriginal(
        idOrHash: 'item_orig_1',
        bytes: Uint8List.fromList([99, 98, 97]),
      );

      var networkHit = false;
      final mockHttp = MockClient((request) async {
        networkHit = true;
        return http.Response.bytes([1, 2], 200);
      });

      final cacheManager = WardrobeCacheManager(
        httpClient: mockHttp,
        cacheDirectoryPath: '${tempDir.path}/cache',
      );

      final bytes = await cacheManager.getImage(
        key: 'item_orig_1',
        downloadUrl: 'https://r2.test/download',
        localOriginalPath: originalPath,
      );

      expect(bytes, equals(Uint8List.fromList([99, 98, 97])));
      expect(networkHit, isFalse);
    });

    test('refreshes expired URL when HTTP fetch fails', () async {
      var fetchAttempt = 0;
      final mockHttp = MockClient((request) async {
        fetchAttempt++;
        if (request.url.toString() == 'https://r2.test/expired-url') {
          return http.Response('Forbidden', 403);
        }
        if (request.url.toString() == 'https://r2.test/fresh-url') {
          return http.Response.bytes([5, 6, 7], 200);
        }
        return http.Response('Not Found', 404);
      });

      final mockMediaClientHttp = MockClient((request) async {
        return http.Response(
          '''{
            "uploadId": "up-456",
            "objectKey": "users/u1/wardrobe/up-456/item.webp",
            "downloadUrl": "https://r2.test/fresh-url",
            "expiresAt": "${DateTime.now().add(const Duration(minutes: 15)).toIso8601String()}",
            "expiresInSeconds": 900
          }''',
          200,
        );
      });

      final mediaClient = MediaClient(
        client: mockMediaClientHttp,
        baseUrl: 'https://api.test',
      );

      final cacheManager = WardrobeCacheManager(
        httpClient: mockHttp,
        mediaClient: mediaClient,
        cacheDirectoryPath: '${tempDir.path}/cache',
      );

      final bytes = await cacheManager.getImage(
        key: 'item_refresh_test',
        downloadUrl: 'https://r2.test/expired-url',
        uploadId: 'up-456',
      );

      expect(bytes, equals(Uint8List.fromList([5, 6, 7])));
      expect(fetchAttempt, 2);
    });

    test('clear() purges cache on logout without deleting local originals', () async {
      final originalPath = await OriginalFileManager.instance.saveOriginal(
        idOrHash: 'preserved_item',
        bytes: Uint8List.fromList([1, 1, 1]),
      );

      final mockHttp = MockClient((request) async {
        return http.Response.bytes([2, 2, 2], 200);
      });

      final cacheDir = '${tempDir.path}/cache';
      final cacheManager = WardrobeCacheManager(
        httpClient: mockHttp,
        cacheDirectoryPath: cacheDir,
      );

      await cacheManager.getImage(
        key: 'cached_key',
        downloadUrl: 'https://r2.test/cached',
      );

      expect(Directory(cacheDir).existsSync(), isTrue);

      // Logout / clear session
      cacheManager.clear();

      // Cache directory removed
      expect(Directory(cacheDir).existsSync(), isFalse);

      // Local original MUST still exist intact (Option B)
      expect(File(originalPath).existsSync(), isTrue);
    });
  });
}
