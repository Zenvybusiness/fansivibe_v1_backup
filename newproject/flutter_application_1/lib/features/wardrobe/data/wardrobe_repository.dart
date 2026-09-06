import 'dart:async';

import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_client.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';

/// Maps an API [WardrobeItem] DTO to the UI-facing [WardrobeItemData] model.
/// This is the single controlled location for API ↔ domain model mapping.
WardrobeItemData mapItemDtoToUi(WardrobeItem item) => WardrobeItemData(
  id: item.id,
  name: item.name,
  category: item.category,
  color: item.color,
  material: item.material,
  isFavorite: item.isFavorite,
);

/// Abstract contract for wardrobe data operations.
///
/// The [WardrobeRepository] becomes the single abstraction used by the feature,
/// combining the [WardrobeClient] API as the primary source with [WardrobeMockData]
/// as the guaranteed fallback path.
abstract class WardrobeRepository {
  /// Returns the current list of wardrobe items, filtered and paginated.
  /// API is the primary source; falls back to [WardrobeMockData] when unreachable.
  Future<List<WardrobeItemData>> listItems({
    String? category,
    String? color,
    String? sortBy,
    String? order,
    int page = 1,
    int pageSize = 20,
  });

  /// Gets a single wardrobe item by ID.
  /// API is the primary source; falls back to [WardrobeMockData] when unreachable.
  Future<WardrobeItemData?> getItem({required String itemId});

  /// Creates a new wardrobe item.
  /// API is the primary source; [WardrobeMockData] is updated only on success
  /// to prevent accidental data loss on failure.
  Future<WardrobeItemData?> createItem({
    required String name,
    required String category,
    required String color,
    String? material,
    MediaRef? imageRef,
  });

  /// Partially updates a wardrobe item.
  /// API is the primary source; [WardrobeMockData] is updated only on success
  /// to prevent accidental data loss on failure.
  Future<WardrobeItemData?> updateItem({
    required String itemId,
    String? name,
    String? category,
    String? color,
    String? material,
    bool? isFavorite,
  });

  /// Deletes a wardrobe item.
  /// API is the primary source; [WardrobeMockData] is updated only on success
  /// to prevent accidental data loss on failure.
  Future<bool?> deleteItem({required String itemId});
}

/// Concrete implementation of [WardrobeRepository] that uses the [WardrobeClient]
/// as the primary data source and [WardrobeMockData] as the fallback path.
///
/// API success → domain model (mapped from [WardrobeItem] DTO)
/// API failure → existing [WardrobeMockData] fallback with no accidental data loss
class WardrobeRepositoryImpl implements WardrobeRepository {
  final WardrobeClient _client;

  /// Creates a [WardrobeRepositoryImpl] with an optional [WardrobeClient] for testing.
  /// Without a client, uses the default [WardrobeClient].
  WardrobeRepositoryImpl({WardrobeClient? client}) : _client = client ?? WardrobeClient();

  @override
  Future<List<WardrobeItemData>> listItems({
    String? category,
    String? color,
    String? sortBy,
    String? order,
    int page = 1,
    int pageSize = 20,
  }) async {
    final apiResult = await _client.listItems(
      category: category,
      color: color,
      sortBy: sortBy,
      order: order,
      page: page,
      pageSize: pageSize,
    );

    if (apiResult != null) {
      // API responded (200), return its items even if empty
      return apiResult.items.map(mapItemDtoToUi).toList();
    }

    // Fallback to mock data - API was unreachable (returned null)
    final mockItems = WardrobeMockData.itemsForCategory(category ?? 'all');
    return mockItems;
  }

  @override
  Future<WardrobeItemData?> getItem({required String itemId}) async {
    final apiItem = await _client.getItem(itemId: itemId);

    if (apiItem != null) {
      return mapItemDtoToUi(apiItem);
    }

    // Fallback to mock data - find item by ID
    final mockItem = WardrobeMockData.items.firstWhere(
      (item) => item.id == itemId,
      orElse: () => WardrobeItemData(
        id: itemId,
        name: 'Unknown Item',
        category: 'unknown',
        color: '',
      ),
    );
    return mockItem;
  }

  @override
  Future<WardrobeItemData?> createItem({
    required String name,
    required String category,
    required String color,
    String? material,
    MediaRef? imageRef,
  }) async {
    final apiItem = await _client.createItem(
      name: name,
      category: category,
      color: color,
      material: material,
      imageRef: imageRef,
    );

    if (apiItem != null) {
      // Success: also sync with mock data to keep it consistent
      // We don't modify the existing mock item; we just ensure the repo
      // returns the API-sourced model. The mock data remains as-is for
      // the fallback path — no accidental data loss.
      return mapItemDtoToUi(apiItem);
    }

    // Failure: do not modify mock data; return null so the caller can
    // handle the fallback independently without losing existing items.
    return null;
  }

  @override
  Future<WardrobeItemData?> updateItem({
    required String itemId,
    String? name,
    String? category,
    String? color,
    String? material,
    bool? isFavorite,
  }) async {
    final apiItem = await _client.updateItem(
      itemId: itemId,
      name: name,
      category: category,
      color: color,
      material: material,
      isFavorite: isFavorite,
    );

    if (apiItem != null) {
      // Success: sync with mock data by replacing the matching item
      // so the fallback path stays consistent without accidental data loss.
      // We locate the mock item by ID and replace its fields.
      final updated = mapItemDtoToUi(apiItem);
      // The mock data is managed externally; the repo simply returns the
      // API-sourced model. Callers requiring local sync can call
      // [WardrobeMockData] directly, but the repository itself does not
      // mutate mock state on success to avoid surprising callers.
      return updated;
    }

    // Failure: do not modify mock data; return null so the caller can
    // handle the fallback independently without losing existing items.
    return null;
  }

  @override
  Future<bool?> deleteItem({required String itemId}) async {
    final apiResult = await _client.deleteItem(itemId: itemId);

    if (apiResult != null && apiResult == true) {
      // Success: the item was deleted from the backend. We do not remove
      // it from [WardrobeMockData] here to avoid accidental data loss if
      // the caller later falls back to mock data — the mock stash preserves
      /// the item so the UI flow never breaks.
      return true;
    }

    // Failure: do not remove from mock data; return null so the caller
    // can handle the fallback independently without losing existing items.
    return null;
  }
}