import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/features/learning/data/models.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/media/data/media_client.dart';
import 'package:fansivibe/features/media/presentation/wardrobe_cache_manager.dart';
import 'package:fansivibe/features/wardrobe/data/garment_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_client.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_item_photo.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/presentation/add_wardrobe_item_screen.dart';
import 'package:fansivibe/features/wardrobe/presentation/wardrobe_item_details_screen.dart';
import 'package:fansivibe/features/wardrobe/presentation/wardrobe_screen.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/theme/fansivibe_theme.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

/// Minimal valid 1x1 JPEG bytes (SOI + APP0 + SOF0 + EOI) passing
/// `detectImageMimeType` and `getImageDimensions` without real image I/O.
Uint8List _validJpegBytes({int markerByte = 0x01}) => Uint8List.fromList([
  0xFF, 0xD8, // SOI
  0xFF, 0xE0, 0x00, 0x10, // APP0
  0x4A, 0x46, 0x49, 0x46, 0x00, 0x01, 0x01, 0x00,
  0x00, 0x01, 0x00, 0x01, 0x00, 0x00,
  0xFF, 0xC0, 0x00, 0x0B, 0x08, // SOF0
  0x00, 0x10, 0x00, 0x10, // 16x16
  0x01, 0x01, 0x11, 0x00,
  0xFF, 0xFE, 0x00, 0x03, markerByte, // COM marker to vary sha256
  0xFF, 0xD9, // EOI
]);

class _FakeWardrobeBackend {
  _FakeWardrobeBackend({
    required Map<String, Map<String, dynamic>> items,
    this.failPage2Once = false,
    this.overlapPage2 = false,
    this.failNextPatch = false,
    this.patchCompleter,
  }) : _items = items;

  final Map<String, Map<String, dynamic>> _items;
  bool failPage2Once;
  bool overlapPage2;
  bool failNextPatch;
  Completer<void>? patchCompleter;

  int listCalls = 0;
  int patchCalls = 0;
  final List<Map<String, dynamic>> patchPayloads = [];
  final List<String> requestedPages = [];

  MockClient createClient() => MockClient((request) async {
    final path = request.url.path;
    if (request.method == 'GET' && path == '/v1/wardrobe/items') {
      listCalls++;
      final page =
          int.tryParse(request.url.queryParameters['page'] ?? '1') ?? 1;
      final pageSize =
          int.tryParse(request.url.queryParameters['page_size'] ?? '20') ?? 20;
      requestedPages.add('page=$page,size=$pageSize');

      if (page == 2 && failPage2Once) {
        failPage2Once = false;
        return http.Response('{"error":"temporary"}', 503);
      }

      final all = _items.values.toList();
      final start = (page - 1) * pageSize;
      var slice = start >= all.length
          ? <Map<String, dynamic>>[]
          : all.skip(start).take(pageSize).toList();
      if (overlapPage2 && page == 2 && all.isNotEmpty) {
        slice = [all.first, ...slice];
      }
      return http.Response(
        jsonEncode({
          'items': slice,
          'page': page,
          'page_size': pageSize,
          'total': all.length,
        }),
        200,
      );
    }

    if (request.method == 'GET' && path.startsWith('/v1/wardrobe/items/')) {
      final id = path.split('/').last;
      final item = _items[id];
      if (item == null) {
        return http.Response('{"error":"not_found"}', 404);
      }
      return http.Response(jsonEncode(item), 200);
    }

    if (request.method == 'PATCH' && path.startsWith('/v1/wardrobe/items/')) {
      patchCalls++;
      if (patchCompleter != null) {
        await patchCompleter!.future;
      }
      if (failNextPatch) {
        failNextPatch = false;
        return http.Response('{"error":"server_error"}', 500);
      }
      final id = path.split('/').last;
      final existing = _items[id];
      if (existing == null) {
        return http.Response('{"error":"not_found"}', 404);
      }
      final body = jsonDecode(request.body) as Map<String, dynamic>;
      patchPayloads.add(body);
      final updated = Map<String, dynamic>.from(existing);
      if (body.containsKey('name')) updated['name'] = body['name'];
      if (body.containsKey('category')) updated['category'] = body['category'];
      if (body.containsKey('color')) updated['color'] = body['color'];
      if (body.containsKey('material')) updated['material'] = body['material'];
      if (body.containsKey('isFavorite')) {
        updated['isFavorite'] = body['isFavorite'];
      }
      if (body.containsKey('fit')) updated['fit'] = body['fit'];
      if (body.containsKey('fitConfidence')) {
        updated['fitConfidence'] = body['fitConfidence'];
      }
      if (body.containsKey('imageRef')) {
        if (body['imageRef'] == null) {
          updated['imageRef'] = null;
          updated['imageUrl'] = null;
        } else {
          final ref = Map<String, dynamic>.from(
            body['imageRef'] as Map<String, dynamic>,
          );
          ref['downloadUrl'] ??=
              'https://cdn.example.com/${ref['objectKey'] ?? 'replaced.webp'}';
          updated['imageRef'] = ref;
          updated['imageUrl'] = ref['downloadUrl'];
        }
      }
      updated['updatedAt'] = '2026-11-27T02:00:00Z';
      _items[id] = updated;
      return http.Response(jsonEncode(updated), 200);
    }

    if (request.method == 'GET' && path == '/v1/wardrobe/insight') {
      return http.Response('', 204);
    }
    if (request.method == 'GET' && path == '/v1/wardrobe/wear-summary') {
      return http.Response(
        jsonEncode({
          'totalWears': 0,
          'wearCounts': <String, int>{},
          'lastWorn': <String, String>{},
          'mostWornItemIds': <String>[],
          'leastWornItemIds': <String>[],
          'unwornItemIds': <String>[],
          'recentlyWornItemIds': <String>[],
          'wearsByCategory': <String, int>{},
        }),
        200,
      );
    }
    return http.Response('{"error":"unhandled"}', 404);
  });
}

class _FakeMediaStorage {
  _FakeMediaStorage({this.failUpload = false});

  bool failUpload;
  int authorizeCalls = 0;
  int putCalls = 0;
  int completeCalls = 0;
  final Map<String, Uint8List> objects = {};

  MediaClient createClient() => MediaClient(
    baseUrl: 'https://api.example.com',
    client: MockClient((request) async {
      final path = request.url.path;
      if (request.method == 'POST' && path == '/v1/media/uploads') {
        authorizeCalls++;
        return http.Response(
          jsonEncode({
            'uploadId': 'upl-new-1',
            'stagingKey': 'staging/u1/upl-new-1.jpg',
            'uploadUrl': 'https://r2.example.com/upload/upl-new-1',
            'expiresAt': '2026-11-27T03:00:00Z',
          }),
          200,
        );
      }
      if (request.method == 'PUT' && path.startsWith('/upload/')) {
        putCalls++;
        if (failUpload) {
          return http.Response('error', 500);
        }
        objects[path] = request.bodyBytes;
        return http.Response('', 200);
      }
      if (request.method == 'POST' &&
          path == '/v1/media/uploads/upl-new-1/complete') {
        completeCalls++;
        return http.Response(
          jsonEncode({
            'uploadId': 'upl-new-1',
            'objectKey': 'users/u1/wardrobe/upl-new-1.webp',
            'mediaType': 'image/webp',
            'sizeBytes': 40,
            'width': 16,
            'height': 16,
            'contentHash': 'newhash123',
            'uploadedAt': '2026-11-27T02:00:00Z',
            'status': 'published',
          }),
          200,
        );
      }
      return http.Response('', 404);
    }),
  );
}

class _RecordingCreateRepo implements WardrobeRepository {
  final List<Map<String, dynamic>> created = [];

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
    created.add({
      'name': name,
      'category': category,
      'color': color,
      'material': material,
      'imageRef': imageRef,
      'fit': fit,
      'fitConfidence': fitConfidence,
    });
    return WardrobeItemData(
      id: 'created-1',
      name: name,
      category: category,
      color: color,
      material: material,
      fit: fit,
      fitConfidence: fitConfidence,
    );
  }

  @override
  Future<List<WardrobeItemData>> listItems({
    String? category,
    String? color,
    String? sortBy,
    String? order,
    int page = 1,
    int pageSize = 20,
  }) async => const [];

  @override
  Future<WardrobeItemData?> getItem({required String itemId}) async => null;

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

Future<void> _tapVisible(WidgetTester tester, Finder finder) async {
  await tester.ensureVisible(finder);
  await tester.pumpAndSettle();
  await tester.tap(finder);
}

Map<String, Map<String, dynamic>> _generateItems(int count) {
  final map = <String, Map<String, dynamic>>{};
  for (var i = 1; i <= count; i++) {
    final id = 'item-$i';
    map[id] = {
      'id': id,
      'name': 'Garment $i',
      'category': i % 2 == 0 ? 'tops' : 'bottoms',
      'color': 'Navy',
      'material': 'Cotton',
      'isFavorite': i <= 5,
      'createdAt': '2026-11-27T00:00:00Z',
      'updatedAt': '2026-11-27T00:00:00Z',
    };
  }
  return map;
}

void main() {
  late Directory tempCacheDir;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    LocalStorage.init(prefs: await SharedPreferences.getInstance());
    AuthSession.resetForTest();
    await AuthSession.saveSession('p52f-auth-token');
    LearningService.instance.resetForTest();
    tempCacheDir = Directory.systemTemp.createTempSync('p52f_cache_');
  });

  tearDown(() async {
    AuthSession.resetForTest();
    await AuthSession.clearSession();
    LocalStorage.resetForTest();
    LearningService.instance.resetForTest();
    if (tempCacheDir.existsSync()) {
      tempCacheDir.deleteSync(recursive: true);
    }
  });

  testWidgets('1. Loading more than 100 garments paginates all pages', (
    tester,
  ) async {
    final backend = _FakeWardrobeBackend(items: _generateItems(135));
    final repo = WardrobeRepositoryImpl(
      client: WardrobeClient(client: backend.createClient()),
    );

    await tester.pumpWidget(
      MaterialApp(
        theme: FansivibeTheme.darkTheme,
        home: WardrobeScreen(repository: repo),
      ),
    );
    await tester.pumpAndSettle();

    expect(backend.requestedPages, ['page=1,size=100', 'page=2,size=100']);
    expect(find.text('135 items'), findsWidgets);

    // Category filter and counts reflect all 135 items (67 tops, 68 bottoms).
    await tester.tap(find.text('Tops'));
    await tester.pumpAndSettle();
    expect(find.text('67 items'), findsOneWidget);
  });

  testWidgets('2. Pagination failure shows error and recovers on retry', (
    tester,
  ) async {
    final backend = _FakeWardrobeBackend(
      items: _generateItems(120),
      failPage2Once: true,
    );
    final repo = WardrobeRepositoryImpl(
      client: WardrobeClient(client: backend.createClient()),
    );

    await tester.pumpWidget(
      MaterialApp(
        theme: FansivibeTheme.darkTheme,
        home: WardrobeScreen(repository: repo),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.text('Failed to load wardrobe. Please check your connection.'),
      findsOneWidget,
    );
    expect(find.text('0 items'), findsWidgets);

    await tester.tap(find.text('Retry'));
    await tester.pumpAndSettle();

    expect(find.text('120 items'), findsWidgets);
  });

  testWidgets('3. No duplicate items across pages', (tester) async {
    final backend = _FakeWardrobeBackend(
      items: _generateItems(105),
      overlapPage2: true,
    );
    final repo = WardrobeRepositoryImpl(
      client: WardrobeClient(client: backend.createClient()),
    );

    await tester.pumpWidget(
      MaterialApp(
        theme: FansivibeTheme.darkTheme,
        home: WardrobeScreen(repository: repo),
      ),
    );
    await tester.pumpAndSettle();

    // Even though page 2 duplicated item-1, total count remains 105.
    expect(find.text('105 items'), findsWidgets);
  });

  testWidgets('4. Clearing material sends explicit null and updates UI', (
    tester,
  ) async {
    const id = '11111111-1111-4111-8111-111111111111';
    final backend = _FakeWardrobeBackend(
      items: {
        id: {
          'id': id,
          'name': 'Oxford Shirt',
          'category': 'tops',
          'color': 'White',
          'material': 'Cotton',
          'isFavorite': false,
          'createdAt': '2026-11-27T00:00:00Z',
          'updatedAt': '2026-11-27T00:00:00Z',
        },
      },
    );
    final repo = WardrobeRepositoryImpl(
      client: WardrobeClient(client: backend.createClient()),
    );

    await tester.pumpWidget(
      MaterialApp(
        theme: FansivibeTheme.darkTheme,
        home: WardrobeItemDetailsScreen(itemId: id, repository: repo),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Cotton'), findsOneWidget);

    await _tapVisible(tester, find.text('Edit'));
    await tester.pumpAndSettle();

    final materialField = find.widgetWithText(TextFormField, 'Cotton');
    await tester.enterText(materialField, '');
    await tester.pumpAndSettle();

    await _tapVisible(tester, find.text('Save'));
    await tester.pumpAndSettle();

    expect(backend.patchPayloads.single.containsKey('material'), isTrue);
    expect(backend.patchPayloads.single['material'], isNull);
    expect(find.text('Not specified'), findsOneWidget);
  });

  testWidgets(
    '5. Editing fit preserves fitConfidence, extractionConfidence, sourceRunId, candidateId',
    (tester) async {
      const id = '22222222-2222-4222-8222-222222222222';
      final backend = _FakeWardrobeBackend(
        items: {
          id: {
            'id': id,
            'name': 'Denim Jacket',
            'category': 'outerwear',
            'color': 'Indigo',
            'material': 'Denim',
            'isFavorite': false,
            'fit': 'Regular',
            'fitConfidence': 0.74,
            'sourceRunId': 'run-abc',
            'candidateId': 'cand-2',
            'extractionConfidence': 0.91,
            'imageRef': {
              'objectKey': 'users/u1/wardrobe/222.webp',
              'mediaType': 'image/webp',
              'sourceRunId': 'run-abc',
              'candidateId': 'cand-2',
              'extractionConfidence': 0.91,
            },
            'createdAt': '2026-11-27T00:00:00Z',
            'updatedAt': '2026-11-27T00:00:00Z',
          },
        },
      );
      final repo = WardrobeRepositoryImpl(
        client: WardrobeClient(client: backend.createClient()),
      );

      await tester.pumpWidget(
        MaterialApp(
          theme: FansivibeTheme.darkTheme,
          home: WardrobeItemDetailsScreen(itemId: id, repository: repo),
        ),
      );
      await tester.pumpAndSettle();

      await _tapVisible(tester, find.text('Edit'));
      await tester.pumpAndSettle();

      await _tapVisible(tester, find.text('Regular').last);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Relaxed').last);
      await tester.pumpAndSettle();

      await _tapVisible(tester, find.text('Save'));
      await tester.pumpAndSettle();

      expect(backend.patchPayloads.single['fit'], 'Relaxed');
      expect(
        backend.patchPayloads.single.containsKey('fitConfidence'),
        isFalse,
      );

      final persisted = await repo.getItem(itemId: id);
      expect(persisted!.fit, 'Relaxed');
      expect(persisted.fitConfidence, 0.74);
      expect(persisted.extractionConfidence, 0.91);
      expect(persisted.sourceRunId, 'run-abc');
      expect(persisted.candidateId, 'cand-2');
    },
  );

  testWidgets(
    '6. Outfit Scan prefill never writes general detection confidence into fitConfidence',
    (tester) async {
      final repo = _RecordingCreateRepo();
      await tester.pumpWidget(
        MaterialApp(
          theme: FansivibeTheme.darkTheme,
          home: AddWardrobeItemScreen(
            category: AddItemConfig.categories.first,
            repository: repo,
            initialGarmentResult: const GarmentAnalysisResult(
              category: 'tops',
              subcategory: 'Button-Down',
              color: 'Navy',
              fit: 'Slim',
              confidence: 0.88,
              sourceRunId: 'outfit-scan-run-1',
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.text('Save Item'));
      await tester.tap(find.text('Save Item'));
      await tester.pumpAndSettle();

      expect(repo.created, hasLength(1));
      expect(repo.created.single['fit'], 'Slim');
      expect(repo.created.single['fitConfidence'], isNull);
    },
  );

  testWidgets(
    '7. Successful image replacement uploads, updates, and invalidates cache',
    (tester) async {
      const id = '33333333-3333-4333-8333-333333333333';
      final oldBytes = _validJpegBytes(markerByte: 0x01);
      final newBytes = _validJpegBytes(markerByte: 0x02);
      final cacheManager = WardrobeCacheManager(
        cacheDirectoryPath: tempCacheDir.path,
      );
      final backend = _FakeWardrobeBackend(
        items: {
          id: {
            'id': id,
            'name': 'Silk Scarf',
            'category': 'accessories',
            'color': 'Cream',
            'isFavorite': false,
            'imageRef': {
              'objectKey': 'users/u1/wardrobe/old.webp',
              'mediaType': 'image/webp',
              'contentHash': 'oldhash',
            },
            'createdAt': '2026-11-27T00:00:00Z',
            'updatedAt': '2026-11-27T00:00:00Z',
          },
        },
      );
      final media = _FakeMediaStorage();
      LearningService.instance.addItem(
        WardrobeEntry(
          id: id,
          name: 'Silk Scarf',
          category: 'accessories',
          color: 'Cream',
          imageBase64: encodeWardrobePhoto(oldBytes),
          isAuthenticatedMirror: true,
        ),
      );
      final repo = WardrobeRepositoryImpl(
        client: WardrobeClient(client: backend.createClient()),
      );

      await tester.pumpWidget(
        MaterialApp(
          theme: FansivibeTheme.darkTheme,
          home: WardrobeItemDetailsScreen(
            itemId: id,
            repository: repo,
            mediaClient: media.createClient(),
            cacheManager: cacheManager,
            photoGalleryPick: (_) async =>
                XFile.fromData(newBytes, name: 'new.jpg'),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await _tapVisible(tester, find.text('Edit'));
      await tester.pumpAndSettle();

      await _tapVisible(tester, find.text('Replace Photo'));
      await tester.pumpAndSettle();

      await _tapVisible(tester, find.text('Save'));
      await tester.pumpAndSettle();

      expect(media.authorizeCalls, 1);
      expect(media.putCalls, 1);
      expect(media.completeCalls, 1);
      expect(backend.patchPayloads.single['imageRef']['uploadId'], 'upl-new-1');

      final mirror = LearningService.instance.wardrobe.firstWhere(
        (e) => e.id == id,
      );
      expect(decodeWardrobePhoto(mirror.imageBase64), newBytes);
    },
  );

  testWidgets(
    '8. Failed image replacement preserves the old image and stays in edit mode',
    (tester) async {
      const id = '44444444-4444-4444-8444-444444444444';
      final oldBytes = _validJpegBytes(markerByte: 0x01);
      final newBytes = _validJpegBytes(markerByte: 0x02);
      final backend = _FakeWardrobeBackend(
        items: {
          id: {
            'id': id,
            'name': 'Wool Coat',
            'category': 'outerwear',
            'color': 'Charcoal',
            'isFavorite': false,
            'imageRef': {
              'objectKey': 'users/u1/wardrobe/old.webp',
              'mediaType': 'image/webp',
            },
            'createdAt': '2026-11-27T00:00:00Z',
            'updatedAt': '2026-11-27T00:00:00Z',
          },
        },
      );
      final media = _FakeMediaStorage(failUpload: true);
      LearningService.instance.addItem(
        WardrobeEntry(
          id: id,
          name: 'Wool Coat',
          category: 'outerwear',
          color: 'Charcoal',
          imageBase64: encodeWardrobePhoto(oldBytes),
          isAuthenticatedMirror: true,
        ),
      );
      final repo = WardrobeRepositoryImpl(
        client: WardrobeClient(client: backend.createClient()),
      );

      await tester.pumpWidget(
        MaterialApp(
          theme: FansivibeTheme.darkTheme,
          home: WardrobeItemDetailsScreen(
            itemId: id,
            repository: repo,
            mediaClient: media.createClient(),
            photoGalleryPick: (_) async =>
                XFile.fromData(newBytes, name: 'new.jpg'),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await _tapVisible(tester, find.text('Edit'));
      await tester.pumpAndSettle();

      await _tapVisible(tester, find.text('Replace Photo'));
      await tester.pumpAndSettle();

      await _tapVisible(tester, find.text('Save'));
      await tester.pumpAndSettle();

      expect(
        find.text('Failed to upload replacement photo. Please try again.'),
        findsOneWidget,
      );
      expect(find.text('Edit Wool Coat'), findsOneWidget);
      expect(backend.patchCalls, 0);

      final mirror = LearningService.instance.wardrobe.firstWhere(
        (e) => e.id == id,
      );
      expect(decodeWardrobePhoto(mirror.imageBase64), oldBytes);
    },
  );

  testWidgets('9. Image removal for authenticated users sends imageRef null', (
    tester,
  ) async {
    const id = '55555555-5555-4555-8555-555555555555';
    final oldBytes = _validJpegBytes(markerByte: 0x03);
    final backend = _FakeWardrobeBackend(
      items: {
        id: {
          'id': id,
          'name': 'Linen Shirt',
          'category': 'tops',
          'color': 'White',
          'isFavorite': false,
          'imageRef': {
            'objectKey': 'users/u1/wardrobe/555.webp',
            'mediaType': 'image/webp',
          },
          'createdAt': '2026-11-27T00:00:00Z',
          'updatedAt': '2026-11-27T00:00:00Z',
        },
      },
    );
    LearningService.instance.addItem(
      WardrobeEntry(
        id: id,
        name: 'Linen Shirt',
        category: 'tops',
        color: 'White',
        imageBase64: encodeWardrobePhoto(oldBytes),
        isAuthenticatedMirror: true,
      ),
    );
    final repo = WardrobeRepositoryImpl(
      client: WardrobeClient(client: backend.createClient()),
    );

    await tester.pumpWidget(
      MaterialApp(
        theme: FansivibeTheme.darkTheme,
        home: WardrobeItemDetailsScreen(itemId: id, repository: repo),
      ),
    );
    await tester.pumpAndSettle();

    await _tapVisible(tester, find.text('Edit'));
    await tester.pumpAndSettle();

    await _tapVisible(tester, find.text('Remove Photo'));
    await tester.pumpAndSettle();

    await _tapVisible(tester, find.text('Save'));
    await tester.pumpAndSettle();

    expect(backend.patchPayloads.single.containsKey('imageRef'), isTrue);
    expect(backend.patchPayloads.single['imageRef'], isNull);

    final mirror = LearningService.instance.wardrobe.firstWhere(
      (e) => e.id == id,
    );
    expect(mirror.imageBase64, isNull);
  });

  testWidgets(
    '10. Guest photo replacement and removal use local storage without media upload',
    (tester) async {
      AuthSession.resetForTest();
      await AuthSession.clearSession();
      LocalStorage.savedLocally = true;

      final oldBytes = _validJpegBytes(markerByte: 0x04);
      final newBytes = _validJpegBytes(markerByte: 0x05);
      const localId = 'local-guest-1';
      LearningService.instance.addItem(
        WardrobeEntry(
          id: localId,
          name: 'Guest Tee',
          category: 'tops',
          color: 'Black',
          imageBase64: encodeWardrobePhoto(oldBytes),
        ),
      );
      final media = _FakeMediaStorage();

      await tester.pumpWidget(
        MaterialApp(
          theme: FansivibeTheme.darkTheme,
          home: WardrobeItemDetailsScreen(
            itemId: localId,
            mediaClient: media.createClient(),
            photoGalleryPick: (_) async =>
                XFile.fromData(newBytes, name: 'g.jpg'),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Replace photo in guest mode
      await _tapVisible(tester, find.text('Edit'));
      await tester.pumpAndSettle();
      await _tapVisible(tester, find.text('Replace Photo'));
      await tester.pumpAndSettle();
      await _tapVisible(tester, find.text('Save'));
      await tester.pumpAndSettle();

      expect(media.authorizeCalls, 0);
      expect(media.putCalls, 0);
      expect(
        decodeWardrobePhoto(
          LearningService.instance.wardrobe
              .firstWhere((e) => e.id == localId)
              .imageBase64,
        ),
        newBytes,
      );

      // Remove photo in guest mode
      await _tapVisible(tester, find.text('Edit'));
      await tester.pumpAndSettle();
      await _tapVisible(tester, find.text('Remove Photo'));
      await tester.pumpAndSettle();
      await _tapVisible(tester, find.text('Save'));
      await tester.pumpAndSettle();

      expect(
        LearningService.instance.wardrobe
            .firstWhere((e) => e.id == localId)
            .imageBase64,
        isNull,
      );
    },
  );

  testWidgets(
    '11. Edit API failure keeps edit mode, preserves original item, and guards duplicate saves',
    (tester) async {
      const id = '66666666-6666-4666-8666-666666666666';
      final completer = Completer<void>();
      final backend = _FakeWardrobeBackend(
        items: {
          id: {
            'id': id,
            'name': 'Original Name',
            'category': 'tops',
            'color': 'Navy',
            'isFavorite': false,
            'createdAt': '2026-11-27T00:00:00Z',
            'updatedAt': '2026-11-27T00:00:00Z',
          },
        },
        failNextPatch: true,
        patchCompleter: completer,
      );
      final repo = WardrobeRepositoryImpl(
        client: WardrobeClient(client: backend.createClient()),
      );

      await tester.pumpWidget(
        MaterialApp(
          theme: FansivibeTheme.darkTheme,
          home: WardrobeItemDetailsScreen(itemId: id, repository: repo),
        ),
      );
      await tester.pumpAndSettle();

      await _tapVisible(tester, find.text('Edit'));
      await tester.pumpAndSettle();

      await tester.enterText(
        find.widgetWithText(TextFormField, 'Original Name'),
        'Updated Name',
      );
      await tester.pumpAndSettle();

      // Tap Save twice while first request is still in-flight
      await tester.ensureVisible(find.text('Save'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Save'));
      await tester.pump();
      await tester.tap(find.byIcon(Icons.save_rounded));
      await tester.pump();

      expect(backend.patchCalls, 1);

      completer.complete();
      await tester.pumpAndSettle();

      // Remained in edit mode and showed error
      expect(find.text('Edit Original Name'), findsOneWidget);
      expect(
        find.text('Failed to save changes. Please try again.'),
        findsOneWidget,
      );

      // Dismiss SnackBar so Cancel button is unobstructed, then cancel
      await tester.pump(const Duration(seconds: 5));
      await tester.pumpAndSettle();
      await _tapVisible(tester, find.text('Cancel'));
      await tester.pumpAndSettle();
      expect(find.text('Original Name'), findsWidgets);
    },
  );

  testWidgets(
    '12 & 13. Successful metadata edit preserves imageBytes and extraction provenance',
    (tester) async {
      const id = '77777777-7777-4777-8777-777777777777';
      final photoBytes = _validJpegBytes(markerByte: 0x07);
      final backend = _FakeWardrobeBackend(
        items: {
          id: {
            'id': id,
            'name': 'Extracted Blazer',
            'category': 'outerwear',
            'color': 'Black',
            'material': 'Wool',
            'isFavorite': false,
            'fit': 'Tailored',
            'fitConfidence': 0.81,
            'sourceRunId': 'run-ext-99',
            'candidateId': 'cand-9',
            'extractionConfidence': 0.94,
            'imageRef': {
              'objectKey': 'users/u1/wardrobe/777.webp',
              'mediaType': 'image/webp',
              'sourceRunId': 'run-ext-99',
              'candidateId': 'cand-9',
              'extractionConfidence': 0.94,
            },
            'createdAt': '2026-11-27T00:00:00Z',
            'updatedAt': '2026-11-27T00:00:00Z',
          },
        },
      );
      LearningService.instance.addItem(
        WardrobeEntry(
          id: id,
          name: 'Extracted Blazer',
          category: 'outerwear',
          color: 'Black',
          material: 'Wool',
          imageBase64: encodeWardrobePhoto(photoBytes),
          isAuthenticatedMirror: true,
        ),
      );
      final repo = WardrobeRepositoryImpl(
        client: WardrobeClient(client: backend.createClient()),
      );

      await tester.pumpWidget(
        MaterialApp(
          theme: FansivibeTheme.darkTheme,
          home: WardrobeItemDetailsScreen(itemId: id, repository: repo),
        ),
      );
      await tester.pumpAndSettle();

      await _tapVisible(tester, find.text('Edit'));
      await tester.pumpAndSettle();

      await tester.enterText(
        find.widgetWithText(TextFormField, 'Extracted Blazer'),
        'Tailored Black Blazer',
      );
      await tester.pumpAndSettle();

      await _tapVisible(tester, find.text('Save'));
      await tester.pumpAndSettle();

      expect(find.text('Tailored Black Blazer'), findsWidgets);

      final mirror = LearningService.instance.wardrobe.firstWhere(
        (e) => e.id == id,
      );
      expect(decodeWardrobePhoto(mirror.imageBase64), photoBytes);
      expect(mirror.sourceRunId, 'run-ext-99');
      expect(mirror.candidateId, 'cand-9');
      expect(mirror.extractionConfidence, 0.94);
      expect(mirror.fitConfidence, 0.81);
    },
  );

  testWidgets('14. Wardrobe reopening and persistence after edits', (
    tester,
  ) async {
    const id = '88888888-8888-4888-8888-888888888888';
    final backend = _FakeWardrobeBackend(
      items: {
        id: {
          'id': id,
          'name': 'Chinos',
          'category': 'bottoms',
          'color': 'Khaki',
          'material': 'Cotton',
          'isFavorite': false,
          'createdAt': '2026-11-27T00:00:00Z',
          'updatedAt': '2026-11-27T00:00:00Z',
        },
      },
    );
    final repo = WardrobeRepositoryImpl(
      client: WardrobeClient(client: backend.createClient()),
    );

    await tester.pumpWidget(
      MaterialApp(
        theme: FansivibeTheme.darkTheme,
        home: WardrobeItemDetailsScreen(itemId: id, repository: repo),
      ),
    );
    await tester.pumpAndSettle();

    await _tapVisible(tester, find.text('Edit'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Chinos'),
      'Pleated Chinos',
    );
    await tester.enterText(find.widgetWithText(TextFormField, 'Cotton'), '');
    await _tapVisible(tester, find.text('Save'));
    await tester.pumpAndSettle();

    // Reopen WardrobeScreen against the same backend
    await tester.pumpWidget(
      MaterialApp(
        theme: FansivibeTheme.darkTheme,
        home: WardrobeScreen(repository: repo),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Pleated Chinos'), findsOneWidget);
    final reloaded = await repo.getItem(itemId: id);
    expect(reloaded!.name, 'Pleated Chinos');
    expect(reloaded.material, isNull);
  });
}
