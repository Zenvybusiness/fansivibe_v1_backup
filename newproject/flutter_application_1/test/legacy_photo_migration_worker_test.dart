import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:fansivibe/features/learning/data/models.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/media/data/media_client.dart';
import 'package:fansivibe/features/media/domain/original_file_manager.dart';
import 'package:fansivibe/features/wardrobe/data/legacy_photo_migration_worker.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_item_photo.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

final Uint8List kTestPhoto = base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
);

class _TestWardrobeRepo implements WardrobeRepository {
  _TestWardrobeRepo();

  final Map<String, WardrobeItemData> items = {};
  bool failUpdate = false;

  Future<WardrobeItemData?> updateItemMediaDirect({
    required String itemId,
    MediaRef? imageRef,
    bool clearImageRef = false,
  }) async {
    if (failUpdate) return null;
    final item = WardrobeItemData(
      id: itemId,
      name: 'Item $itemId',
      category: 'tops',
      color: 'Black',
      imageRef: imageRef,
    );
    items[itemId] = item;
    return item;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('LegacyPhotoMigrationWorker', () {
    late Directory tempDir;

    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();
      LocalStorage.init(prefs: prefs);
      tempDir = Directory.systemTemp.createTempSync('fansivibe_mig_test_');
      await AuthSession.saveSession('test-token');
      LearningService.instance.resetForTest();
    });

    tearDown(() {
      AuthSession.clearSession();
      LearningService.instance.resetForTest();
      LocalStorage.resetForTest();
      if (tempDir.existsSync()) {
        tempDir.deleteSync(recursive: true);
      }
    });

    test('skips migration if unauthenticated', () async {
      AuthSession.clearSession();
      final worker = LegacyPhotoMigrationWorker();
      final summary = await worker.runMigration();
      expect(summary.totalEligible, 0);
      expect(summary.migratedCount, 0);
    });

    test('migrates legacy Base64 item end-to-end and preserves local original', () async {
      final base64Photo = encodeWardrobePhoto(kTestPhoto);
      final entry = WardrobeEntry(
        id: 'legacy-item-1',
        name: 'Vintage Tee',
        category: 'tops',
        color: 'Black',
        imageBase64: base64Photo,
      );
      LearningService.instance.addItem(entry);

      final fakeRepo = _TestWardrobeRepo();

      final mockHttp = MockClient((request) async {
        if (request.url.path == '/v1/media/uploads') {
          return http.Response(
            jsonEncode({
              'uploadId': 'up-111',
              'uploadUrl': 'https://r2.test/put-111',
              'stagingKey': 'users/u/staging/up-111.webp',
              'expiresAt': DateTime.now().add(const Duration(minutes: 15)).toIso8601String(),
              'expiresInSeconds': 900,
            }),
            201,
          );
        }
        if (request.method == 'PUT' && request.url.toString() == 'https://r2.test/put-111') {
          return http.Response('', 200);
        }
        if (request.url.path == '/v1/media/uploads/up-111/complete') {
          return http.Response(
            jsonEncode({
              'uploadId': 'up-111',
              'objectKey': 'users/u/wardrobe/up-111/att_1.webp',
              'mediaType': 'image/webp',
              'width': 1,
              'height': 1,
              'sizeBytes': kTestPhoto.length,
              'contentHash': 'a' * 64,
              'uploadedAt': DateTime.now().toIso8601String(),
              'status': 'ready',
            }),
            200,
          );
        }
        return http.Response('Not Found', 404);
      });

      final mediaClient = MediaClient(
        client: mockHttp,
        baseUrl: 'https://api.test',
      );

      final worker = LegacyPhotoMigrationWorker(
        wardrobeRepository: fakeRepo,
        mediaClient: mediaClient,
      );

      final summary = await worker.runMigration();
      expect(summary.totalEligible, 1);
      expect(summary.migratedCount, 1);
      expect(summary.failedCount, 0);

      // Verify server association took place
      expect(fakeRepo.items.containsKey('legacy-item-1'), isTrue);
      expect(fakeRepo.items['legacy-item-1']!.imageRef, isNotNull);
      expect(fakeRepo.items['legacy-item-1']!.imageRef!.uploadId, 'up-111');

      // Verify local Base64 copy was safely removed from LearningService
      final localEntry = LearningService.instance.wardrobe.firstWhere((e) => e.id == 'legacy-item-1');
      expect(localEntry.imageBase64, isNull);

      // Verify local original photograph is preserved in storage (Option B)
      final localOrig = await OriginalFileManager.instance.loadOriginal('legacy-item-1');
      expect(localOrig, isNotNull);
      expect(localOrig!.length, greaterThan(0));
    });

    test('failure on backend association preserves local Base64 intact', () async {
      final base64Photo = encodeWardrobePhoto(kTestPhoto);
      final entry = WardrobeEntry(
        id: 'legacy-item-fail',
        name: 'Jacket',
        category: 'outerwear',
        color: 'Navy',
        imageBase64: base64Photo,
      );
      LearningService.instance.addItem(entry);

      final fakeRepo = _TestWardrobeRepo()..failUpdate = true; // Simulate failure

      final mockHttp = MockClient((request) async {
        if (request.url.path == '/v1/media/uploads') {
          return http.Response(
            jsonEncode({
              'uploadId': 'up-222',
              'uploadUrl': 'https://r2.test/put-222',
              'stagingKey': 'users/u/staging/up-222.webp',
              'expiresAt': DateTime.now().add(const Duration(minutes: 15)).toIso8601String(),
            }),
            201,
          );
        }
        if (request.method == 'PUT') return http.Response('', 200);
        if (request.url.path == '/v1/media/uploads/up-222/complete') {
          return http.Response(
            jsonEncode({
              'uploadId': 'up-222',
              'objectKey': 'users/u/wardrobe/up-222/att_1.webp',
              'mediaType': 'image/webp',
              'width': 1,
              'height': 1,
              'sizeBytes': kTestPhoto.length,
              'contentHash': 'b' * 64,
              'uploadedAt': DateTime.now().toIso8601String(),
              'status': 'ready',
            }),
            200,
          );
        }
        return http.Response('Not Found', 404);
      });

      final mediaClient = MediaClient(
        client: mockHttp,
        baseUrl: 'https://api.test',
      );

      final worker = LegacyPhotoMigrationWorker(
        wardrobeRepository: fakeRepo,
        mediaClient: mediaClient,
      );

      final summary = await worker.runMigration();
      expect(summary.totalEligible, 1);
      expect(summary.migratedCount, 0);
      expect(summary.failedCount, 1);

      // CRITICAL SAFETY CHECK: Local Base64 must NOT be wiped if association failed!
      final localEntry = LearningService.instance.wardrobe.firstWhere((e) => e.id == 'legacy-item-fail');
      expect(localEntry.imageBase64, equals(base64Photo));
    });

    test('worker can be cancelled', () async {
      final worker = LegacyPhotoMigrationWorker();
      worker.cancel();
      final summary = await worker.runMigration(explicitEntries: [
        WardrobeEntry(
          id: 'item-cancelled',
          name: 'Pants',
          category: 'bottoms',
          color: 'Blue',
          imageBase64: encodeWardrobePhoto(kTestPhoto),
        ),
      ]);
      expect(summary.isCancelled, isTrue);
    });
  });
}
