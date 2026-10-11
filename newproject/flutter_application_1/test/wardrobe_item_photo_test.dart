import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/features/learning/data/models.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/wardrobe/data/local_wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_item_photo.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/presentation/add_wardrobe_item_screen.dart';
import 'package:fansivibe/features/wardrobe/presentation/widgets/wardrobe_widgets.dart';
import 'package:fansivibe/features/wardrobe/presentation/wardrobe_item_details_screen.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/components/fansi_image_well.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

/// Regression tests for the photo-to-wardrobe-image pipeline.
///
/// A photo taken/selected in the add flow must appear on the saved item's
/// card, survive the save/load cycle, and never break manual imageless
/// entries. Fakes stand in for transport only; photo bytes are real.
final Uint8List kPhoto = base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
);

WardrobeItemData photoItem({
  String id = 'photo-1',
  Uint8List? bytes,
}) => WardrobeItemData(
  id: id,
  name: 'Photo Tee',
  category: 'tops',
  color: 'Black',
  material: 'Cotton',
  imageBytes: bytes ?? kPhoto,
);

WardrobeItemData manualItem() => const WardrobeItemData(
  id: 'manual-1',
  name: 'Oxford Shirt',
  category: 'tops',
  color: 'White',
  material: 'Cotton',
);

class _RecordingRepo implements WardrobeRepository {
  WardrobeItemData? saved;

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
    saved = WardrobeItemData(
      id: 'server-uuid-1',
      name: name,
      category: category,
      color: color,
      material: material,
      imageRef: imageRef,
    );
    return saved;
  }

  @override
  Future<List<WardrobeItemData>> listItems({
    String? category,
    String? color,
    String? sortBy,
    String? order,
    int page = 1,
    int pageSize = 20,
  }) async => saved == null ? const [] : [saved!];

  @override
  Future<WardrobeItemData?> getItem({required String itemId}) async => saved;

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
  }) async => saved;

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
}

Future<void> resetEnv() async {
  // Fresh mock prefs per test (no LocalStorage.resetForTest after init:
  // it drops the prefs handle and silently discards session writes).
  SharedPreferences.setMockInitialValues({});
  LocalStorage.init(prefs: await SharedPreferences.getInstance());
  AuthSession.resetForTest();
  await AuthSession.clearSession();
  LearningService.instance.resetForTest();
}

MemoryImage singleMemoryImage(WidgetTester tester) {
  final image = tester.widget<Image>(find.byType(Image));
  return image.image as MemoryImage;
}

void main() {
  setUp(resetEnv);

  group('photo bytes helpers', () {
    test('encode/decode round-trips the exact bytes', () {
      expect(decodeWardrobePhoto(encodeWardrobePhoto(kPhoto)), orderedEquals(kPhoto));
    });

    test('null and empty stay null (imageless shape unchanged)', () {
      expect(encodeWardrobePhoto(null), isNull);
      expect(encodeWardrobePhoto(Uint8List(0)), isNull);
      expect(decodeWardrobePhoto(null), isNull);
      expect(decodeWardrobePhoto(''), isNull);
    });

    test('corrupt base64 fails closed to null, never throws', () {
      expect(decodeWardrobePhoto('!!!not-base64!!!'), isNull);
    });

    test('prepare passes small photos through untouched', () async {
      expect(await prepareWardrobePhoto(kPhoto), orderedEquals(kPhoto));
      expect(await prepareWardrobePhoto(null), isNull);
      expect(await prepareWardrobePhoto(Uint8List(0)), isNull);
    });

    test('prepare never loses undecodable bytes', () async {
      final bigGarbage = Uint8List(maxWardrobePhotoBytes + 8);
      expect(await prepareWardrobePhoto(bigGarbage), same(bigGarbage));
    });
  });

  group('model persistence', () {
    test('entry JSON round-trips the photo (restart shape)', () {
      final entry = WardrobeEntry(
        id: 'photo-1',
        name: 'Photo Tee',
        category: 'tops',
        color: 'Black',
        imageBase64: encodeWardrobePhoto(kPhoto),
      );
      final revived = WardrobeEntry.fromJson(
        jsonDecode(jsonEncode(entry.toJson())) as Map<String, dynamic>,
      );
      expect(decodeWardrobePhoto(revived.imageBase64), orderedEquals(kPhoto));
    });

    test('old rows without the photo key still parse as imageless', () {
      final revived = WardrobeEntry.fromJson({
        'id': '1',
        'name': 'Merino Crew Neck',
        'category': 'tops',
        'color': 'Charcoal',
      });
      expect(revived.imageBase64, isNull);
    });

    test('imageless entries serialize exactly as before (no photo key)', () {
      final json = manualItem();
      expect(json.imageBytes, isNull);
      final entryJson = WardrobeEntry(
        id: json.id,
        name: json.name,
        category: json.category,
        color: json.color,
        material: json.material,
      ).toJson();
      expect(entryJson.containsKey('imageBase64'), isFalse);
    });

    test('DTO mapping preserves the backend imageRef verbatim', () {
      const ref = MediaRef(objectKey: 'users/u/scans/r/input.jpg', mediaType: 'image/jpeg');
      const dto = WardrobeItem(
        id: 'uuid-1',
        name: 'Tee',
        category: 'tops',
        color: 'black',
        imageRef: ref,
      );
      final ui = mapItemDtoToUi(dto);
      expect(ui.imageRef, isNotNull);
      expect(ui.imageRef!.objectKey, 'users/u/scans/r/input.jpg');
      expect(ui.imageRef!.mediaType, 'image/jpeg');
    });
  });

  group('guest save/load cycle', () {
    test('photo survives create/list/get through the local repository', () async {
      final repo = LocalWardrobeRepository();
      final created = await repo.createItem(
        name: 'Photo Tee',
        category: 'tops',
        color: 'Black',
        material: 'Cotton',
      );
      expect(created, isNotNull);
      // The add screen binds the photo to the saved id (real path).
      LearningService.instance.updateItem(
        created!.id,
        wardrobeEntryFromItem(created.copyWith(imageBytes: kPhoto)),
      );

      final listed = await repo.listItems(pageSize: 100);
      final reloaded = listed.firstWhere((e) => e.id == created.id);
      expect(reloaded.imageBytes, orderedEquals(kPhoto));

      final fetched = await repo.getItem(itemId: created.id);
      expect(fetched!.imageBytes, orderedEquals(kPhoto));
    });

    test('photo survives a JSON restart cycle', () async {
      final repo = LocalWardrobeRepository();
      final created = await repo.createItem(
        name: 'Photo Tee',
        category: 'tops',
        color: 'Black',
      );
      LearningService.instance.updateItem(
        created!.id,
        wardrobeEntryFromItem(created.copyWith(imageBytes: kPhoto)),
      );

      // Simulate restart: encode the persisted entries, decode fresh.
      final raw = LearningService.instance.wardrobe
          .map((e) => e.toJson())
          .toList();
      final revived = (jsonDecode(jsonEncode(raw)) as List)
          .map((e) => WardrobeEntry.fromJson(e as Map<String, dynamic>))
          .toList();
      final entry = revived.firstWhere((e) => e.id == created.id);
      expect(decodeWardrobePhoto(entry.imageBase64), orderedEquals(kPhoto));
    });

    test('edit preserves the photo, delete removes it', () async {
      final repo = LocalWardrobeRepository();
      final created = await repo.createItem(
        name: 'Photo Tee',
        category: 'tops',
        color: 'Black',
      );
      LearningService.instance.updateItem(
        created!.id,
        wardrobeEntryFromItem(created.copyWith(imageBytes: kPhoto)),
      );

      final updated = await repo.updateItem(
        itemId: created.id,
        isFavorite: true,
      );
      expect(updated!.imageBytes, orderedEquals(kPhoto));

      expect(await repo.deleteItem(itemId: created.id), isTrue);
      expect(await repo.getItem(itemId: created.id), isNull);
    });

    test('manual imageless entries keep working with the empty state', () async {
      final repo = LocalWardrobeRepository();
      final created = await repo.createItem(
        name: 'Oxford Shirt',
        category: 'tops',
        color: 'White',
      );
      expect(created!.imageBytes, isNull);
      expect((await repo.getItem(itemId: created.id))!.imageBytes, isNull);
    });
  });

  group('mirror overlay for account items', () {
    test('attaches stored bytes by id, leaves unknown ids alone', () {
      LearningService.instance.addItem(
        WardrobeEntry(
          id: 'server-uuid-1',
          name: 'Photo Tee',
          category: 'tops',
          color: 'Black',
          imageBase64: encodeWardrobePhoto(kPhoto),
        ),
      );
      const serverItem = WardrobeItemData(
        id: 'server-uuid-1',
        name: 'Photo Tee',
        category: 'tops',
        color: 'Black',
      );
      expect(
        attachLocalPhoto(serverItem).imageBytes,
        orderedEquals(kPhoto),
      );
      const unknown = WardrobeItemData(
        id: 'other-uuid',
        name: 'Tee',
        category: 'tops',
        color: 'Black',
      );
      expect(attachLocalPhoto(unknown).imageBytes, isNull);
    });

    test('entry merge preserves stored bytes across edits', () {
      LearningService.instance.addItem(
        WardrobeEntry(
          id: 'server-uuid-1',
          name: 'Photo Tee',
          category: 'tops',
          color: 'Black',
          imageBase64: encodeWardrobePhoto(kPhoto),
        ),
      );
      const edited = WardrobeItemData(
        id: 'server-uuid-1',
        name: 'Photo Tee Renamed',
        category: 'tops',
        color: 'Black',
      );
      final merged = wardrobeEntryFromItem(edited);
      expect(merged.name, 'Photo Tee Renamed');
      expect(
        decodeWardrobePhoto(merged.imageBase64),
        orderedEquals(kPhoto),
      );
    });
  });

  group('ClothingItemCard', () {
    testWidgets('photo item renders the exact image', (tester) async {
      await tester.pumpWidget(
        MaterialApp(home: Scaffold(body: ClothingItemCard(item: photoItem()))),
      );
      await tester.pumpAndSettle();

      expect(singleMemoryImage(tester).bytes, orderedEquals(kPhoto));
      expect(find.byType(FansiImageWell), findsNothing);
      // Card chrome is intact around the photo.
      expect(find.text('Photo Tee'), findsOneWidget);
      expect(find.text('Cotton'), findsOneWidget);
    });

    testWidgets('manual item shows the empty well without crashing', (
      tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(home: Scaffold(body: ClothingItemCard(item: manualItem()))),
      );
      await tester.pumpAndSettle();

      expect(find.byType(FansiImageWell), findsOneWidget);
      expect(find.byType(Image), findsNothing);
      expect(find.text('Oxford Shirt'), findsOneWidget);
    });

    testWidgets('undecodable bytes fall back safely, never crash', (
      tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ClothingItemCard(
              item: photoItem(bytes: Uint8List.fromList([0, 1, 2, 3])),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      expect(find.byType(FansiImageWell), findsOneWidget);
      expect(find.text('Photo Tee'), findsOneWidget);
    });
  });

  group('detail view', () {
    testWidgets('photo item shows the exact image hero', (tester) async {
      await AuthSession.saveSession('test-token');
      final repo = _RecordingRepo()..saved = photoItem(id: 'server-uuid-1');
      await tester.pumpWidget(
        MaterialApp(
          home: WardrobeItemDetailsScreen(
            itemId: 'server-uuid-1',
            repository: repo,
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(singleMemoryImage(tester).bytes, orderedEquals(kPhoto));
      expect(find.text('Photo Tee'), findsWidgets);
    });

    testWidgets('manual item keeps its existing imageless layout', (
      tester,
    ) async {
      await AuthSession.saveSession('test-token');
      final repo = _RecordingRepo()..saved = manualItem();
      await tester.pumpWidget(
        MaterialApp(
          home: WardrobeItemDetailsScreen(itemId: 'manual-1', repository: repo),
        ),
      );
      await tester.pumpAndSettle();

      // No photo: no hero at all — the pre-existing layout is untouched.
      expect(find.byType(Image), findsNothing);
      expect(find.byType(FansiImageWell), findsNothing);
      expect(find.text('Oxford Shirt'), findsWidgets);
    });
  });

  group('add flow binds the photo', () {
    Future<void> takePhotoWithoutAnalysis(WidgetTester tester) async {
      await tester.scrollUntilVisible(
        find.text('Take Photo'),
        200.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Take Photo'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Choose from Gallery').last);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Use Photo'));
      await tester.pumpAndSettle();
    }

    Future<void> fillAndSave(WidgetTester tester) async {
      await tester.tap(find.text('T-Shirt'));
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(
        find.text('Black'),
        200.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Black'));
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(
        find.text('Save Item'),
        300.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Save Item'));
      await tester.pumpAndSettle();
    }

    testWidgets('unanalyzed photo is bound to the saved item', (tester) async {
      final repo = _RecordingRepo();
      final category = AddItemConfig.categories.firstWhere(
        (c) => c.id == 'tops',
      );
      WardrobeItemData? popped;
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => TextButton(
              onPressed: () async {
                popped = await Navigator.of(context)
                    .push<WardrobeItemData>(
                      MaterialPageRoute(
                        builder: (_) => AddWardrobeItemScreen(
                          category: category,
                          repository: repo,
                          photoGalleryPick: (source) async =>
                              XFile.fromData(
                                kPhoto,
                                name: 'shirt.jpg',
                                mimeType: 'image/jpeg',
                              ),
                        ),
                      ),
                    );
              },
              child: const Text('open'),
            ),
          ),
        ),
      );

      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      await takePhotoWithoutAnalysis(tester);
      // Deliberately no analysis: the photo alone must still bind.
      await fillAndSave(tester);

      await tester.scrollUntilVisible(
        find.text('Done'),
        300.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Done'));
      await tester.pumpAndSettle();

      expect(popped, isNotNull);
      expect(popped!.imageBytes, orderedEquals(kPhoto));
    });

    testWidgets('guest photo persists on-device with the local repository', (
      tester,
    ) async {
      LocalStorage.savedLocally = true;
      final category = AddItemConfig.categories.firstWhere(
        (c) => c.id == 'tops',
      );
      await tester.pumpWidget(
        MaterialApp(
          home: AddWardrobeItemScreen(
            category: category,
            photoGalleryPick: (source) async => XFile.fromData(
              kPhoto,
              name: 'shirt.jpg',
              mimeType: 'image/jpeg',
            ),
          ),
        ),
      );

      await takePhotoWithoutAnalysis(tester);
      await fillAndSave(tester);
      expect(find.text('Done'), findsOneWidget);

      final items = await LocalWardrobeRepository().listItems(pageSize: 100);
      final saved = items.firstWhere((e) => e.name == 'T-Shirt');
      expect(saved.imageBytes, orderedEquals(kPhoto));
    });
  });
}
