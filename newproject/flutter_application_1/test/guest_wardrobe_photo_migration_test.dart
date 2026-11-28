import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/features/assistant/data/models.dart';
import 'package:fansivibe/features/auth/data/guest_data_migration.dart';
import 'package:fansivibe/features/learning/data/models.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/learning/learning_repository.dart';
import 'package:fansivibe/features/media/data/media_client.dart';
import 'package:fansivibe/features/wardrobe/data/local_wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

final Uint8List _kJpegBytes = Uint8List.fromList([
  0xFF,
  0xD8,
  0xFF,
  0xE0,
  0x00,
  0x10,
  0x4A,
  0x46,
  0x49,
  0x46,
  0x00,
  0x01,
  0x01,
  0x00,
  0x00,
  0x01,
  0x00,
  0x01,
  0x00,
  0x00,
  0xFF,
  0xDB,
  0x00,
  0x43,
]);

final Uint8List _kWebpBytes = Uint8List.fromList([
  0x52, 0x49, 0x46, 0x46, // RIFF
  0x20, 0x00, 0x00, 0x00,
  0x57, 0x45, 0x42, 0x50, // WEBP
  0x56, 0x50, 0x38, 0x20,
]);

final Uint8List _kPngBytes = Uint8List.fromList([
  0x89,
  0x50,
  0x4E,
  0x47,
  0x0D,
  0x0A,
  0x1A,
  0x0A,
  0x00,
  0x00,
  0x00,
  0x0D,
  0x49,
  0x48,
  0x44,
  0x52,
]);

class _CreatedRecord {
  const _CreatedRecord({
    required this.name,
    required this.category,
    required this.color,
    this.material,
    this.imageRef,
    this.fit,
    this.fitConfidence,
  });

  final String name;
  final String category;
  final String color;
  final String? material;
  final MediaRef? imageRef;
  final String? fit;
  final double? fitConfidence;
}

class _FakeWardrobeRepo implements WardrobeRepository {
  final List<WardrobeItemData> server = [];
  final List<_CreatedRecord> createdCalls = [];
  final Set<String> failNames = {};

  @override
  Future<List<WardrobeItemData>> listItems({
    String? category,
    String? color,
    String? sortBy,
    String? order,
    int page = 1,
    int pageSize = 20,
  }) async => List.of(server);

  @override
  Future<WardrobeItemData?> getItem({required String itemId}) async => null;

  @override
  Future<WardrobeItemData?> createItem({
    required String name,
    required String category,
    required String color,
    String? material,
    MediaRef? imageRef,
    String? fit,
    double? fitConfidence,
  }) async {
    if (failNames.contains(name)) return null;
    createdCalls.add(
      _CreatedRecord(
        name: name,
        category: category,
        color: color,
        material: material,
        imageRef: imageRef,
        fit: fit,
        fitConfidence: fitConfidence,
      ),
    );
    final item = WardrobeItemData(
      id: 'server-${createdCalls.length}',
      name: name,
      category: category,
      color: color,
      material: material,
      imageRef: imageRef,
    );
    server.add(item);
    return item;
  }

  @override
  Future<WardrobeItemData?> updateItem({
    required String itemId,
    String? name,
    String? category,
    String? color,
    String? material,
    bool? isFavorite,
    String? fit,
    double? fitConfidence,
  }) async => null;

  @override
  Future<bool?> deleteItem({required String itemId}) async => null;

  @override
  Future<WardrobeInsightData?> getInsight() async => null;

  @override
  Future<WearSummary?> getWearSummary() async => null;

  @override
  Future<WearEventLogResponse?> logWear({
    required List<String> itemIds,
    DateTime? wornAt,
    String? idempotencyKey,
  }) async => null;

  @override
  Future<WearEventLogResponse?> logEnsembleWear({
    required List<String> itemIds,
    DateTime? wornAt,
    String? idempotencyKey,
  }) async => null;
}

class _MutableLearning implements LearningRepository {
  _MutableLearning(this.wardrobe);

  @override
  List<WardrobeEntry> wardrobe;

  @override
  List<String> get preferredOccasions => const [];
  @override
  FaceProfile? get face => null;
  @override
  String? get styleType => null;
  @override
  List<String> get savedLooks => const [];
  @override
  List<LearningSignal> get signals => const [];
  @override
  int get styleScore => 60;
  @override
  Future<void> load() async {}
  @override
  void addItem(WardrobeEntry item) => wardrobe = [...wardrobe, item];
  @override
  void setFace(FaceProfile face) {}
  @override
  void setStyleType(String styleType) {}
  @override
  void addSavedLook(String title) {}
  @override
  void addPreferredOccasion(String occasion) {}
  @override
  void recordSignal(String type, String label) {}
  @override
  void updateItem(String itemId, WardrobeEntry item) {}
}

class _UploadTracker {
  int authorizeCalls = 0;
  int directPutCalls = 0;
  int completeCalls = 0;
  final List<String> authorizeMimeTypes = [];
  final List<String> idempotencyKeys = [];
  bool failAuthorize = false;
  bool failDirectPut = false;
  bool failComplete = false;
  bool failSecondAuthorize = false;

  MediaClient buildClient() {
    return MediaClient(
      baseUrl: 'https://api.test',
      client: MockClient((request) async {
        if (request.method == 'POST' &&
            request.url.path == '/v1/media/uploads') {
          authorizeCalls++;
          if (failAuthorize || (failSecondAuthorize && authorizeCalls >= 2)) {
            return http.Response('{"detail": "auth failed"}', 503);
          }
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          authorizeMimeTypes.add(body['contentType'] as String);
          idempotencyKeys.add(request.headers['Idempotency-Key'] ?? '');
          final uploadId = '00000000-0000-0000-0000-00000000000$authorizeCalls';
          return http.Response(
            jsonEncode({
              'uploadId': uploadId,
              'uploadUrl': 'https://r2.test/put/$uploadId',
              'stagingKey': 'staging/users/u1/wardrobe/$uploadId.webp',
              'expiresAt': DateTime.now()
                  .add(const Duration(minutes: 15))
                  .toIso8601String(),
            }),
            201,
          );
        }

        if (request.method == 'PUT' && request.url.host == 'r2.test') {
          directPutCalls++;
          if (failDirectPut) {
            return http.Response('PutFailed', 503);
          }
          return http.Response('', 200);
        }

        if (request.method == 'POST' &&
            request.url.path.startsWith('/v1/media/uploads/') &&
            request.url.path.endsWith('/complete')) {
          completeCalls++;
          if (failComplete) {
            return http.Response('{"detail": "complete failed"}', 503);
          }
          final segments = request.url.pathSegments;
          final uploadId = segments[segments.length - 2];
          return http.Response(
            jsonEncode({
              'uploadId': uploadId,
              'objectKey': 'users/u1/wardrobe/$uploadId/canonical.webp',
              'mediaType': 'image/webp',
              'width': 512,
              'height': 512,
              'sizeBytes': 1024,
              'contentHash': 'a' * 64,
              'uploadedAt': DateTime.now().toIso8601String(),
              'status': 'ready',
            }),
            200,
          );
        }

        return http.Response('Not found', 404);
      }),
    );
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    LocalStorage.init(prefs: await SharedPreferences.getInstance());
    AuthSession.resetForTest();
    await AuthSession.saveSession('token-user-a');
    LearningService.instance.resetForTest();
  });

  tearDown(() async {
    AuthSession.resetForTest();
    await AuthSession.clearSession();
    LocalStorage.resetForTest();
    LearningService.instance.resetForTest();
  });

  group('P5.2E Guest Wardrobe Photo Migration', () {
    test(
      '1. guest item without a photo migrates metadata-only successfully',
      () async {
        final repo = _FakeWardrobeRepo();
        final tracker = _UploadTracker();
        final learning = _MutableLearning([
          const WardrobeEntry(
            id: 'local-1',
            name: 'Plain Tee',
            category: 'tops',
            color: 'white',
          ),
        ]);

        final result = await GuestDataMigration(
          wardrobeRepo: repo,
          syncPreference: ({required String code}) async =>
              PreferenceSyncResult.synced,
          learning: learning,
          mediaClient: tracker.buildClient(),
          decodeDimensions: (_) async => (512, 512),
        ).migrate();

        expect(result.migratedLocalIds, ['local-1']);
        expect(result.failedItemNames, isEmpty);
        expect(tracker.authorizeCalls, 0);
        expect(repo.createdCalls, hasLength(1));
        expect(repo.createdCalls.single.imageRef, isNull);
      },
    );

    test(
      '2. guest item with valid JPEG migrates with non-null imageRef via 3-step media pipeline',
      () async {
        final repo = _FakeWardrobeRepo();
        final tracker = _UploadTracker();
        final learning = _MutableLearning([
          WardrobeEntry(
            id: 'local-2',
            name: 'Navy Jacket',
            category: 'outerwear',
            color: 'navy',
            imageBase64: base64Encode(_kJpegBytes),
          ),
        ]);

        final result = await GuestDataMigration(
          wardrobeRepo: repo,
          syncPreference: ({required String code}) async =>
              PreferenceSyncResult.synced,
          learning: learning,
          mediaClient: tracker.buildClient(),
          decodeDimensions: (_) async => (600, 800),
        ).migrate();

        expect(result.migratedLocalIds, ['local-2']);
        expect(result.failedItemNames, isEmpty);
        expect(tracker.authorizeCalls, 1);
        expect(tracker.directPutCalls, 1);
        expect(tracker.completeCalls, 1);
        expect(tracker.authorizeMimeTypes, ['image/jpeg']);

        expect(repo.createdCalls, hasLength(1));
        final ref = repo.createdCalls.single.imageRef;
        expect(ref, isNotNull);
        expect(ref!.objectKey, contains('users/u1/wardrobe/'));
        expect(ref.uploadId, isNotNull);
        expect(
          jsonEncode(ref.toJson()),
          isNot(contains(base64Encode(_kJpegBytes))),
        );
      },
    );

    test(
      'preserves fit and extraction provenance on migrated guest items',
      () async {
        final repo = _FakeWardrobeRepo();
        final tracker = _UploadTracker();
        final learning = _MutableLearning([
          WardrobeEntry(
            id: 'local-provenance',
            name: 'Analyzed Jacket',
            category: 'outerwear',
            color: 'navy',
            imageBase64: base64Encode(_kJpegBytes),
            fit: 'regular',
            fitConfidence: 0.9,
            sourceRunId: 'run-123',
            candidateId: 'candidate-1',
            extractionConfidence: 0.82,
          ),
        ]);

        final result = await GuestDataMigration(
          wardrobeRepo: repo,
          syncPreference: ({required String code}) async =>
              PreferenceSyncResult.synced,
          learning: learning,
          mediaClient: tracker.buildClient(),
          decodeDimensions: (_) async => (600, 800),
        ).migrate();

        expect(result.migratedLocalIds, ['local-provenance']);
        final created = repo.createdCalls.single;
        expect(created.fit, 'regular');
        expect(created.fitConfidence, 0.9);
        expect(created.imageRef?.sourceRunId, 'run-123');
        expect(created.imageRef?.candidateId, 'candidate-1');
        expect(created.imageRef?.extractionConfidence, 0.82);
      },
    );

    test(
      '3. guest item with WebP succeeds and PNG follows supported media rules (rejected)',
      () async {
        final repo = _FakeWardrobeRepo();
        final tracker = _UploadTracker();
        final learning = _MutableLearning([
          WardrobeEntry(
            id: 'local-webp',
            name: 'WebP Coat',
            category: 'outerwear',
            color: 'charcoal',
            imageBase64: base64Encode(_kWebpBytes),
          ),
          WardrobeEntry(
            id: 'local-png',
            name: 'PNG Shirt',
            category: 'tops',
            color: 'white',
            imageBase64: base64Encode(_kPngBytes),
          ),
        ]);

        final result = await GuestDataMigration(
          wardrobeRepo: repo,
          syncPreference: ({required String code}) async =>
              PreferenceSyncResult.synced,
          learning: learning,
          mediaClient: tracker.buildClient(),
          decodeDimensions: (_) async => (400, 400),
        ).migrate();

        expect(result.migratedLocalIds, ['local-webp']);
        expect(result.failedItemNames, ['PNG Shirt']);
        expect(tracker.authorizeMimeTypes, ['image/webp']);
        expect(repo.createdCalls, hasLength(1));
        expect(repo.createdCalls.single.name, 'WebP Coat');
        expect(repo.createdCalls.single.imageRef, isNotNull);
      },
    );

    test(
      '4. corrupt base64, invalid bytes, oversized bytes, and oversized dimensions are rejected safely',
      () async {
        final repo = _FakeWardrobeRepo();
        final tracker = _UploadTracker();
        final oversized = Uint8List(2 * 1024 * 1024 + 10);
        oversized.setRange(0, _kJpegBytes.length, _kJpegBytes);

        final learning = _MutableLearning([
          const WardrobeEntry(
            id: 'local-bad-b64',
            name: 'Bad Base64',
            category: 'tops',
            color: 'black',
            imageBase64: '!!!not-valid-base64!!!',
          ),
          WardrobeEntry(
            id: 'local-bad-magic',
            name: 'Bad Magic',
            category: 'tops',
            color: 'black',
            imageBase64: base64Encode([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]),
          ),
          WardrobeEntry(
            id: 'local-too-big',
            name: 'Too Big',
            category: 'tops',
            color: 'black',
            imageBase64: base64Encode(oversized),
          ),
          WardrobeEntry(
            id: 'local-bad-dims',
            name: 'Too Wide',
            category: 'tops',
            color: 'black',
            imageBase64: base64Encode(_kJpegBytes),
          ),
        ]);

        final result = await GuestDataMigration(
          wardrobeRepo: repo,
          syncPreference: ({required String code}) async =>
              PreferenceSyncResult.synced,
          learning: learning,
          mediaClient: tracker.buildClient(),
          decodeDimensions: (_) async => (5000, 5000),
        ).migrate();

        expect(result.migratedLocalIds, isEmpty);
        expect(result.failedItemNames, [
          'Bad Base64',
          'Bad Magic',
          'Too Big',
          'Too Wide',
        ]);
        expect(tracker.authorizeCalls, 0);
        expect(repo.createdCalls, isEmpty);
      },
    );

    test(
      '5. upload authorization failure preserves guest item and photo (never creates null-image item)',
      () async {
        final repo = _FakeWardrobeRepo();
        final tracker = _UploadTracker()..failAuthorize = true;
        final b64 = base64Encode(_kJpegBytes);
        final learning = _MutableLearning([
          WardrobeEntry(
            id: 'local-5',
            name: 'Auth Fail Item',
            category: 'tops',
            color: 'navy',
            imageBase64: b64,
          ),
        ]);

        final result = await GuestDataMigration(
          wardrobeRepo: repo,
          syncPreference: ({required String code}) async =>
              PreferenceSyncResult.synced,
          learning: learning,
          mediaClient: tracker.buildClient(),
          decodeDimensions: (_) async => (300, 300),
        ).migrate();

        expect(result.migratedLocalIds, isEmpty);
        expect(result.failedItemNames, ['Auth Fail Item']);
        expect(repo.createdCalls, isEmpty);
        expect(learning.wardrobe.single.imageBase64, b64);
        expect(LocalStorage.migratedGuestIds, isEmpty);
      },
    );

    test('6. direct upload failure preserves guest item and photo', () async {
      final repo = _FakeWardrobeRepo();
      final tracker = _UploadTracker()..failDirectPut = true;
      final b64 = base64Encode(_kJpegBytes);
      final learning = _MutableLearning([
        WardrobeEntry(
          id: 'local-6',
          name: 'Put Fail Item',
          category: 'tops',
          color: 'navy',
          imageBase64: b64,
        ),
      ]);

      final result = await GuestDataMigration(
        wardrobeRepo: repo,
        syncPreference: ({required String code}) async =>
            PreferenceSyncResult.synced,
        learning: learning,
        mediaClient: tracker.buildClient(),
        decodeDimensions: (_) async => (300, 300),
      ).migrate();

      expect(result.migratedLocalIds, isEmpty);
      expect(result.failedItemNames, ['Put Fail Item']);
      expect(tracker.authorizeCalls, 1);
      expect(tracker.directPutCalls, 1);
      expect(tracker.completeCalls, 0);
      expect(repo.createdCalls, isEmpty);
      expect(learning.wardrobe.single.imageBase64, b64);
    });

    test(
      '7 & 8. completeUpload then createItem failure is recoverable on retry without duplicate upload or duplicate item',
      () async {
        final repo = _FakeWardrobeRepo()..failNames.add('Recoverable Jacket');
        final tracker = _UploadTracker();
        final b64 = base64Encode(_kJpegBytes);
        final learning = _MutableLearning([
          WardrobeEntry(
            id: 'local-7',
            name: 'Recoverable Jacket',
            category: 'outerwear',
            color: 'navy',
            imageBase64: b64,
          ),
        ]);

        final first = await GuestDataMigration(
          wardrobeRepo: repo,
          syncPreference: ({required String code}) async =>
              PreferenceSyncResult.synced,
          learning: learning,
          mediaClient: tracker.buildClient(),
          decodeDimensions: (_) async => (300, 300),
        ).migrate();

        expect(first.failedItemNames, ['Recoverable Jacket']);
        expect(first.migratedLocalIds, isEmpty);
        expect(tracker.authorizeCalls, 1);
        expect(tracker.directPutCalls, 1);
        expect(tracker.completeCalls, 1);
        expect(
          LocalStorage.migratedGuestMediaRefs.containsKey('local-7'),
          isTrue,
        );

        // Recover wardrobe API and retry: must reuse cached MediaRef (no duplicate upload!)
        repo.failNames.clear();
        final second = await GuestDataMigration(
          wardrobeRepo: repo,
          syncPreference: ({required String code}) async =>
              PreferenceSyncResult.synced,
          learning: learning,
          mediaClient: tracker.buildClient(),
          decodeDimensions: (_) async => (300, 300),
        ).migrate();

        expect(second.failedItemNames, isEmpty);
        expect(second.migratedLocalIds, ['local-7']);
        expect(tracker.authorizeCalls, 1);
        expect(tracker.directPutCalls, 1);
        expect(tracker.completeCalls, 1);
        expect(repo.createdCalls, hasLength(1));
        expect(repo.createdCalls.single.imageRef, isNotNull);
        expect(LocalStorage.migratedGuestMediaRefs, isEmpty);

        // Third run (repeat migration): item is already in ledger -> skipped, 0 new items
        final third = await GuestDataMigration(
          wardrobeRepo: repo,
          syncPreference: ({required String code}) async =>
              PreferenceSyncResult.synced,
          learning: learning,
          mediaClient: tracker.buildClient(),
          decodeDimensions: (_) async => (300, 300),
        ).migrate();

        expect(third.migratedLocalIds, isEmpty);
        expect(third.skippedItemNames, ['Recoverable Jacket']);
        expect(repo.createdCalls, hasLength(1));
      },
    );

    test(
      '9. multiple guest items migrate remaining items when one item upload fails',
      () async {
        final repo = _FakeWardrobeRepo();
        final tracker = _UploadTracker()..failSecondAuthorize = true;
        final learning = _MutableLearning([
          WardrobeEntry(
            id: 'local-a',
            name: 'Item A',
            category: 'tops',
            color: 'navy',
            imageBase64: base64Encode(_kJpegBytes),
          ),
          WardrobeEntry(
            id: 'local-b',
            name: 'Item B',
            category: 'bottoms',
            color: 'charcoal',
            imageBase64: base64Encode(_kWebpBytes),
          ),
          const WardrobeEntry(
            id: 'local-c',
            name: 'Item C',
            category: 'footwear',
            color: 'white',
          ),
        ]);

        final result = await GuestDataMigration(
          wardrobeRepo: repo,
          syncPreference: ({required String code}) async =>
              PreferenceSyncResult.synced,
          learning: learning,
          mediaClient: tracker.buildClient(),
          decodeDimensions: (_) async => (300, 300),
        ).migrate();

        expect(result.migratedLocalIds, ['local-a', 'local-c']);
        expect(result.failedItemNames, ['Item B']);
        expect(repo.createdCalls.map((c) => c.name), ['Item A', 'Item C']);
        expect(repo.createdCalls.first.imageRef, isNotNull);
        expect(repo.createdCalls.last.imageRef, isNull);
      },
    );

    test(
      '10, 11 & 12. successful migration clears only migrated guest items and preserves isolation',
      () async {
        await LearningService.instance.load();
        LearningService.instance.removeLocalItems(
          LearningService.instance.wardrobe.map((e) => e.id).toSet(),
        );
        final b64A = base64Encode(_kJpegBytes);
        final b64B = base64Encode(_kWebpBytes);
        LearningService.instance.addItem(
          WardrobeEntry(
            id: 'local-keep-fail',
            name: 'Failed Photo Item',
            category: 'tops',
            color: 'navy',
            imageBase64: b64A,
          ),
        );
        LearningService.instance.addItem(
          WardrobeEntry(
            id: 'local-success-ok',
            name: 'Migrated Item',
            category: 'bottoms',
            color: 'beige',
            imageBase64: b64B,
          ),
        );

        final localRepo = LocalWardrobeRepository();
        expect((await localRepo.listItems()).length, 2);

        final repo = _FakeWardrobeRepo()..failNames.add('Failed Photo Item');
        final tracker = _UploadTracker();
        final result = await GuestDataMigration(
          wardrobeRepo: repo,
          syncPreference: ({required String code}) async =>
              PreferenceSyncResult.synced,
          learning: LearningService.instance,
          mediaClient: tracker.buildClient(),
          decodeDimensions: (_) async => (300, 300),
        ).migrate();

        expect(result.migratedLocalIds, ['local-success-ok']);
        expect(result.failedItemNames, ['Failed Photo Item']);

        // Simulate post_auth_flow removing only migratedLocalIds
        LearningService.instance.removeLocalItems(
          result.migratedLocalIds.toSet(),
        );

        final remaining = LearningService.instance.wardrobe;
        expect(remaining, hasLength(1));
        expect(remaining.single.id, 'local-keep-fail');
        expect(remaining.single.imageBase64, b64A);
        expect(remaining.single.isGuestLocal, isTrue);

        // Account switch to User B: authenticated mirrors cleared, guest-local remains separate
        await AuthSession.saveSession('token-user-b');
        expect(
          LearningService.instance.wardrobe.where(
            (e) => e.isAuthenticatedMirror,
          ),
          isEmpty,
        );
      },
    );
  });
}
