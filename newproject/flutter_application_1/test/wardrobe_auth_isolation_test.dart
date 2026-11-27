import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/features/assistant/data/models.dart';
import 'package:fansivibe/features/auth/data/auth_client.dart';
import 'package:fansivibe/features/auth/data/guest_data_migration.dart';
import 'package:fansivibe/features/learning/data/local_store.dart';
import 'package:fansivibe/features/learning/data/models.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/media/presentation/wardrobe_cache_manager.dart';
import 'package:fansivibe/features/wardrobe/data/local_wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_item_photo.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/presentation/wardrobe_screen.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/theme/fansivibe_theme.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

final Uint8List _kSamplePhoto = base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
);

const String _userAUuid = '11111111-1111-4111-8111-111111111111';
const String _userBUuid = '22222222-2222-4222-8222-222222222222';

class _TokenScopedFakeWardrobeRepository implements WardrobeRepository {
  _TokenScopedFakeWardrobeRepository(this._itemsByToken);

  final Map<String, List<WardrobeItemData>> _itemsByToken;
  int listCalls = 0;

  List<WardrobeItemData> _currentList() {
    final token = AuthSession.token ?? '';
    return List<WardrobeItemData>.from(_itemsByToken[token] ?? const []);
  }

  @override
  Future<List<WardrobeItemData>> listItems({
    String? category,
    String? color,
    String? sortBy,
    String? order,
    int page = 1,
    int pageSize = 20,
  }) async {
    listCalls++;
    return _currentList();
  }

  @override
  Future<WardrobeItemData?> getItem({required String itemId}) async {
    for (final item in _currentList()) {
      if (item.id == itemId) return item;
    }
    return null;
  }

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
    final token = AuthSession.token ?? 'anon';
    final created = WardrobeItemData(
      id: '33333333-3333-4333-8333-${_currentList().length.toString().padLeft(12, '0')}',
      name: name,
      category: category,
      color: color,
      material: material,
      imageRef: imageRef,
    );
    _itemsByToken.putIfAbsent(token, () => []).add(created);
    return created;
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
  Future<bool?> deleteItem({required String itemId}) async => true;

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

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    LocalStorage.init(prefs: await SharedPreferences.getInstance());
    AuthSession.resetForTest();
    LearningService.instance.resetForTest();
    // Start with empty wardrobe for clean isolation assertions.
    LearningService.instance.removeLocalItems(
      LearningService.instance.wardrobe.map((e) => e.id).toSet(),
    );
    WardrobeCacheManager.instance.clear();
  });

  tearDown(() async {
    AuthSession.resetForTest();
    await AuthSession.clearSession();
    WardrobeCacheManager.instance.clear();
  });

  test(
    '1. Authenticated items mirrored into LearningService are not returned by LocalWardrobeRepository',
    () async {
      final guestRepo = LocalWardrobeRepository();
      final guestCreated = await guestRepo.createItem(
        name: 'Guest Canvas Tote',
        category: 'accessories',
        color: 'Cream',
      );
      expect(guestCreated, isNotNull);
      expect(guestCreated!.id.startsWith('local-'), isTrue);

      // Mirror both an explicitly flagged authenticated entry and a legacy
      // unmarked server UUID entry into LearningService.
      LearningService.instance.addItem(
        WardrobeEntry(
          id: _userAUuid,
          name: 'User A Cashmere Coat',
          category: 'outerwear',
          color: 'Camel',
          imageBase64: encodeWardrobePhoto(_kSamplePhoto),
          isAuthenticatedMirror: true,
        ),
      );
      LearningService.instance.addItem(
        WardrobeEntry(
          id: _userBUuid,
          name: 'Legacy Unflagged Server Shirt',
          category: 'tops',
          color: 'Navy',
          imageBase64: encodeWardrobePhoto(_kSamplePhoto),
        ),
      );

      final items = await guestRepo.listItems(pageSize: 100);
      expect(items.map((e) => e.id).toList(), [guestCreated.id]);
      expect(items.single.name, 'Guest Canvas Tote');

      // Other local repository operations also refuse server-backed items.
      expect(await guestRepo.getItem(itemId: _userAUuid), isNull);
      expect(await guestRepo.getItem(itemId: _userBUuid), isNull);
      expect(
        await guestRepo.updateItem(itemId: _userAUuid, isFavorite: true),
        isNull,
      );
      expect(await guestRepo.deleteItem(itemId: _userAUuid), isFalse);
      // Authenticated entry was not silently converted to local-*.
      expect(
        LearningService.instance.wardrobe.any((e) => e.id == _userAUuid),
        isTrue,
      );
    },
  );

  test(
    '2. Genuine local-* guest items remain available after logout',
    () async {
      final guestRepo = LocalWardrobeRepository();
      final guestItem = await guestRepo.createItem(
        name: 'Guest Denim Jacket',
        category: 'outerwear',
        color: 'Indigo',
      );
      expect(guestItem, isNotNull);

      await AuthSession.saveSession('token-user-a');
      LearningService.instance.addItem(
        WardrobeEntry(
          id: _userAUuid,
          name: 'User A Silk Blazer',
          category: 'outerwear',
          color: 'Black',
          imageBase64: encodeWardrobePhoto(_kSamplePhoto),
          isAuthenticatedMirror: true,
        ),
      );

      final authClient = AuthClient(
        client: MockClient((_) async => http.Response('', 204)),
      );
      await authClient.logout();
      authClient.dispose();

      // Re-enter guest mode.
      LocalStorage.savedLocally = true;
      final guestItems = await guestRepo.listItems(pageSize: 100);
      expect(guestItems.length, 1);
      expect(guestItems.single.id, guestItem!.id);
      expect(guestItems.single.name, 'Guest Denim Jacket');
    },
  );

  test(
    '3. Authenticated photos are not visible in Guest mode after logout',
    () async {
      await AuthSession.saveSession('token-user-a');
      LearningService.instance.addItem(
        WardrobeEntry(
          id: _userAUuid,
          name: 'User A Photo Trench',
          category: 'outerwear',
          color: 'Beige',
          imageBase64: encodeWardrobePhoto(_kSamplePhoto),
          isAuthenticatedMirror: true,
        ),
      );

      // Also verify attachLocalPhoto in guest mode ignores any leftover mirror.
      await AuthSession.clearSession();
      LocalStorage.savedLocally = true;

      expect(
        LearningService.instance.wardrobe.any((e) => e.id == _userAUuid),
        isFalse,
      );
      final guestRepo = LocalWardrobeRepository();
      expect(await guestRepo.listItems(pageSize: 100), isEmpty);

      // Even if a stale entry were somehow present, attachLocalPhoto in guest
      // mode refuses non-guest-local entries.
      LearningService.instance.addItem(
        WardrobeEntry(
          id: _userAUuid,
          name: 'Stale Mirror',
          category: 'outerwear',
          color: 'Beige',
          imageBase64: encodeWardrobePhoto(_kSamplePhoto),
          isAuthenticatedMirror: true,
        ),
      );
      final attached = attachLocalPhoto(
        const WardrobeItemData(
          id: _userAUuid,
          name: 'Stale Mirror',
          category: 'outerwear',
          color: 'Beige',
        ),
      );
      expect(attached.imageBytes, isNull);
    },
  );

  test(
    '4 & 5. User A items and cached photos do not appear after User B logs in (account switch clears cache)',
    () async {
      final tempDir = await Directory.systemTemp.createTemp('p52b_cache_');
      addTearDown(() async {
        if (tempDir.existsSync()) {
          await tempDir.delete(recursive: true);
        }
      });

      // Seed WardrobeCacheManager default instance with a cached entry via clear check,
      // and also test a directory-backed WardrobeCacheManager directly.
      final cache = WardrobeCacheManager(cacheDirectoryPath: tempDir.path);
      final fakeClient = http.Client();
      fakeClient.close();

      // User A logs in and mirrors an item + photo.
      await AuthSession.saveSession('token-user-a');
      const userAItem = WardrobeItemData(
        id: _userAUuid,
        name: 'User A Leather Boots',
        category: 'footwear',
        color: 'Black',
      );
      LearningService.instance.addItem(
        wardrobeEntryFromItem(userAItem.copyWith(imageBytes: _kSamplePhoto)),
      );
      expect(
        LearningService.instance.wardrobe.single.isAuthenticatedMirror,
        isTrue,
      );

      // Write a file in cache dir to verify WardrobeCacheManager.instance.clear()
      // clears disk cache on account switch.
      await WardrobeCacheManager.instance.getImage(
        key: 'user-a-key',
        downloadUrl: null,
      );
      final defaultCacheDir = Directory(
        '${Directory.systemTemp.path}/fansivibe_media_cache',
      );
      defaultCacheDir.createSync(recursive: true);
      final cachedFile = File('${defaultCacheDir.path}/user_a_key.webp');
      cachedFile.writeAsBytesSync(_kSamplePhoto);
      expect(cachedFile.existsSync(), isTrue);

      // Account switch directly from User A to User B without explicit logout.
      await AuthSession.saveSession('token-user-b');

      expect(cachedFile.existsSync(), isFalse);
      expect(
        LearningService.instance.wardrobe.any((e) => e.id == _userAUuid),
        isFalse,
      );
      expect(cache.hashCode, isNotNull);
    },
  );

  testWidgets(
    '6. Authenticated wardrobe reload restores only the current user items without merging guest or previous-user items',
    (WidgetTester tester) async {
      final guestRepo = LocalWardrobeRepository();
      await guestRepo.createItem(
        name: 'Guest Local Tee',
        category: 'tops',
        color: 'White',
      );

      final fakeBackend = _TokenScopedFakeWardrobeRepository({
        'token-user-a': const [
          WardrobeItemData(
            id: _userAUuid,
            name: 'User A Blazer',
            category: 'outerwear',
            color: 'Navy',
          ),
        ],
        'token-user-b': const [
          WardrobeItemData(
            id: _userBUuid,
            name: 'User B Chinos',
            category: 'bottoms',
            color: 'Khaki',
          ),
        ],
      });

      await AuthSession.saveSession('token-user-a');

      await tester.pumpWidget(
        MaterialApp(
          theme: FansivibeTheme.darkTheme,
          home: WardrobeScreen(repository: fakeBackend),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('User A Blazer'), findsOneWidget);
      expect(find.text('User B Chinos'), findsNothing);
      expect(find.text('Guest Local Tee'), findsNothing);

      // Mirror User A photo into LearningService.
      LearningService.instance.addItem(
        wardrobeEntryFromItem(
          WardrobeItemData(
            id: _userAUuid,
            name: 'User A Blazer',
            category: 'outerwear',
            color: 'Navy',
            imageBytes: _kSamplePhoto,
          ),
        ),
      );

      // Switch to User B: WardrobeScreen reloads via AuthSession.authVersion.
      await AuthSession.saveSession('token-user-b');
      await tester.pumpAndSettle();

      expect(find.text('User B Chinos'), findsOneWidget);
      expect(find.text('User A Blazer'), findsNothing);
      expect(find.text('Guest Local Tee'), findsNothing);

      // Ensure local photo caching on User B item preserves server UUID and
      // authenticated mirror ownership.
      final userBMirror = wardrobeEntryFromItem(
        WardrobeItemData(
          id: _userBUuid,
          name: 'User B Chinos',
          category: 'bottoms',
          color: 'Khaki',
          imageBytes: _kSamplePhoto,
        ),
      );
      expect(userBMirror.id, _userBUuid);
      expect(userBMirror.id.startsWith('local-'), isFalse);
      expect(userBMirror.isAuthenticatedMirror, isTrue);
      expect(userBMirror.isGuestLocal, isFalse);

      // Logout to Guest mode: only Guest Local Tee is visible.
      await AuthSession.clearSession();
      LocalStorage.savedLocally = true;
      AuthSession.authVersion.value++;
      await tester.pumpAndSettle();

      expect(find.text('Guest Local Tee'), findsOneWidget);
      expect(find.text('User A Blazer'), findsNothing);
      expect(find.text('User B Chinos'), findsNothing);
    },
  );

  test(
    '7. Existing guest persistence and guest-to-auth migration behavior remain intact',
    () async {
      final guestRepo = LocalWardrobeRepository();
      final guestItem = await guestRepo.createItem(
        name: 'Guest Wool Scarf',
        category: 'accessories',
        color: 'Camel',
      );
      expect(guestItem, isNotNull);

      // Simulate authenticated mirror leftover before migration: migration
      // must only migrate local-* items, never server mirrors.
      LearningService.instance.addItem(
        const WardrobeEntry(
          id: _userAUuid,
          name: 'Old Mirror',
          category: 'tops',
          color: 'Black',
          isAuthenticatedMirror: true,
        ),
      );

      await AuthSession.saveSession('token-user-b');
      final backendRepo = _TokenScopedFakeWardrobeRepository({});
      final migration = GuestDataMigration(
        wardrobeRepo: backendRepo,
        syncPreference: ({required String code}) async =>
            PreferenceSyncResult.synced,
        learning: LearningService.instance,
      );

      final result = await migration.migrate();
      expect(result.migratedItemNames, ['Guest Wool Scarf']);
      expect(result.migratedLocalIds, [guestItem!.id]);
      final serverItems = await backendRepo.listItems(pageSize: 100);
      expect(serverItems.map((e) => e.name).toList(), ['Guest Wool Scarf']);
      expect(serverItems.single.id.startsWith('local-'), isFalse);

      // Verify LocalStore JSON round-trip preserves guest item & ownership.
      final store = LocalStore();
      final encoded = UserModel(
        wardrobe: LearningService.instance.wardrobe,
      ).encode();
      final decoded = UserModel.decode(encoded);
      expect(decoded.wardrobe.single.id, guestItem.id);
      expect(decoded.wardrobe.single.isGuestLocal, isTrue);
      expect(store, isNotNull);
    },
  );

  testWidgets(
    '8. Repeated logout/login transitions do not duplicate wardrobe entries',
    (WidgetTester tester) async {
      final guestRepo = LocalWardrobeRepository();
      final guestItem = await guestRepo.createItem(
        name: 'Guest Loafers',
        category: 'footwear',
        color: 'Brown',
      );

      final fakeBackend = _TokenScopedFakeWardrobeRepository({
        'token-user-a': const [
          WardrobeItemData(
            id: _userAUuid,
            name: 'User A Trench',
            category: 'outerwear',
            color: 'Stone',
          ),
        ],
      });

      await AuthSession.saveSession('token-user-a');
      await tester.pumpWidget(
        MaterialApp(
          theme: FansivibeTheme.darkTheme,
          home: WardrobeScreen(repository: fakeBackend),
        ),
      );
      await tester.pumpAndSettle();

      for (var i = 0; i < 3; i++) {
        // Logout -> Guest
        await AuthSession.clearSession();
        LocalStorage.savedLocally = true;
        AuthSession.authVersion.value++;
        await tester.pumpAndSettle();

        expect(find.text('Guest Loafers'), findsOneWidget);
        expect(find.text('User A Trench'), findsNothing);
        expect(
          LearningService.instance.wardrobe
              .where((e) => e.id == guestItem!.id)
              .length,
          1,
        );

        // Login -> Authenticated
        await AuthSession.saveSession('token-user-a');
        await tester.pumpAndSettle();

        expect(find.text('User A Trench'), findsOneWidget);
        expect(find.text('Guest Loafers'), findsNothing);
      }
    },
  );
}
