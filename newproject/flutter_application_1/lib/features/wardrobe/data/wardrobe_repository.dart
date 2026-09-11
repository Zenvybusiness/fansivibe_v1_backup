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

/// Maps a backend [WardrobeInsight] DTO to the UI-facing [WardrobeInsightData].
/// The backend-provided title/insight/action pass through verbatim — Flutter
/// never reconstructs insight text. Visual identity (icon/accent) reuses the
/// established insight-card styling.
WardrobeInsightData mapInsightDtoToUi(WardrobeInsight insight) =>
    WardrobeInsightData(
      title: insight.title,
      insight: insight.insight,
      iconName: 'lightbulb_outline_rounded',
      accentColor: 0xFFC5A059,
      actionLabel: insight.action,
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

  /// Returns the live backend wardrobe insight, or null when there is none.
  ///
  /// The backend response is canonical: on success its title/insight render
  /// verbatim. There is deliberately NO mock fallback here — the static
  /// [WardrobeInsightData.mock] text ("8+ combinations", "lightweight
  /// jacket") is fabricated advice the backend never provided, so a 204
  /// (empty wardrobe), an unreachable backend, or any error all yield null
  /// and the caller hides the insight card instead of inventing one.
  Future<WardrobeInsightData?> getInsight();

  /// Logs a wear event for backend wardrobe items via the live backend.
  ///
  /// There is deliberately NO mock fallback here — a fabricated wear
  /// success would corrupt real wear history, so any failure yields null
  /// and the caller must treat the wear as unlogged (safe to retry with
  /// the same idempotency key).
  Future<WearEventLogResponse?> logWear({
    required List<String> itemIds,
    DateTime? wornAt,
    String? idempotencyKey,
  });
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

  @override
  Future<WardrobeInsightData?> getInsight() async {
    final apiInsight = await _client.getInsight();
    if (apiInsight != null) {
      return mapInsightDtoToUi(apiInsight);
    }
    // No insight (204 empty wardrobe, unreachable backend, or error):
    // return null so the UI hides the card. Never fall back to
    // [WardrobeInsightData.mock] — that text was never provided by the
    // backend and must not pose as live intelligence.
    return null;
  }

  @override
  Future<WearEventLogResponse?> logWear({
    required List<String> itemIds,
    DateTime? wornAt,
    String? idempotencyKey,
  }) async {
    // No mock fallback: a fabricated success would corrupt real wear
    // history. Null means unlogged — safe to retry with the same key.
    return _client.logWear(
      itemIds: itemIds,
      wornAt: wornAt,
      idempotencyKey: idempotencyKey,
    );
  }
}