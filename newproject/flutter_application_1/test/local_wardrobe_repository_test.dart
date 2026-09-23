import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/wardrobe/data/local_wardrobe_repository.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

/// Unit tests for the guest on-device wardrobe (Phase 2.1).
///
/// The repository implements the existing backend contract over the
/// persisted [LearningService] model: no API, no fakes, no invented
/// intelligence. The singleton is reset to its 24-item seeded state
/// before each test and all assertions are relative to that baseline.
void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    LocalStorage.init(prefs: await SharedPreferences.getInstance());
    LearningService.instance.resetForTest();
  });

  test('listItems returns seeded entries mapped verbatim', () async {
    final repo = LocalWardrobeRepository();
    final items = await repo.listItems(pageSize: 100);

    expect(items.length, 24);
    expect(items.first.name, 'Merino Crew Neck');
    expect(items.first.isFavorite, isTrue);
  });

  test('listItems filters by category and color', () async {
    final repo = LocalWardrobeRepository();

    final tops = await repo.listItems(category: 'tops', pageSize: 100);
    expect(tops.length, 8);
    expect(tops.every((e) => e.category == 'tops'), isTrue);

    final black = await repo.listItems(color: 'Black', pageSize: 100);
    expect(black, isNotEmpty);
    expect(black.every((e) => e.color == 'Black'), isTrue);
  });

  test('createItem mints a non-UUID local id and persists', () async {
    final repo = LocalWardrobeRepository();
    final created = await repo.createItem(
      name: 'Guest Tee',
      category: 'tops',
      color: 'White',
    );

    expect(created, isNotNull);
    expect(created!.id.startsWith('local-'), isTrue);
    // Local ids must never satisfy the backend UUID gate, so the wear
    // action stays hidden for on-device rows without an extra check.
    expect(
      RegExp(
        r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-'
        r'[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$',
      ).hasMatch(created.id),
      isFalse,
    );
    expect(
      LearningService.instance.wardrobe.any((e) => e.id == created.id),
      isTrue,
    );
  });

  test('getItem round-trips, missing id returns null', () async {
    final repo = LocalWardrobeRepository();

    expect((await repo.getItem(itemId: '1'))?.name, 'Merino Crew Neck');
    expect(await repo.getItem(itemId: 'no-such-id'), isNull);
  });

  test('updateItem patches fields, missing id returns null', () async {
    final repo = LocalWardrobeRepository();

    final updated = await repo.updateItem(itemId: '2', isFavorite: true);
    expect(updated?.isFavorite, isTrue);
    expect(
      LearningService.instance.wardrobe
          .firstWhere((e) => e.id == '2')
          .isFavorite,
      isTrue,
    );
    expect(await repo.updateItem(itemId: 'no-such-id'), isNull);
  });

  test('deleteItem removes the row, missing id returns false', () async {
    final repo = LocalWardrobeRepository();

    expect(await repo.deleteItem(itemId: '2'), isTrue);
    expect(
      LearningService.instance.wardrobe.any((e) => e.id == '2'),
      isFalse,
    );
    expect(await repo.deleteItem(itemId: 'no-such-id'), isFalse);
  });

  test('server-only seams stay null (never fabricated)', () async {
    final repo = LocalWardrobeRepository();

    expect(await repo.getInsight(), isNull);
    expect(await repo.getWearSummary(), isNull);
    expect(
      await repo.logWear(itemIds: const ['1'], idempotencyKey: 'k'),
      isNull,
    );
  });
}
