import 'dart:async';

import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_client.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart'
    show WardrobeInsightData, WardrobeItemData;

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

/// Maps a backend [WearSummary] DTO to UI-facing [WardrobeInsightData]
/// copy following the accepted §10.5 rules (DEC-012, STEP 17.4).
///
/// Returns null when there is no usable wear history (`totalWears == 0`)
/// so the caller renders nothing — no claim beats an ungrounded one.
/// Otherwise counts-only sentences: logged totals, 30-day recency,
/// most/least-worn with ties named, unworn counts, and the top category.
/// Never item names (the summary carries backend UUIDs only, and UUIDs
/// are never user-facing prose), never favorites/saves/recommendations
/// inference, never banned language ("never wear", "neglected",
/// "should", "need", "balanced", rotation judgments). `actionLabel` is
/// always null so no CTA — and no dead navigation — is ever rendered.
WardrobeInsightData? mapWearSummaryToUi(WearSummary summary) {
  if (summary.totalWears == 0) return null;
  final parts = <String>[];
  final itemCount = summary.wearCounts.length;
  parts.add(
    'Logged ${summary.totalWears} '
    '${_plural(summary.totalWears, 'wear', 'wears')} '
    'across $itemCount ${_plural(itemCount, 'item', 'items')}.',
  );
  if (summary.recentlyWornItemIds.isNotEmpty) {
    final n = summary.recentlyWornItemIds.length;
    parts.add('$n ${_plural(n, 'item', 'items')} worn in the last 30 days.');
  }
  if (summary.mostWornItemIds.isNotEmpty) {
    final top = summary.wearCounts[summary.mostWornItemIds.first] ?? 0;
    final n = summary.mostWornItemIds.length;
    parts.add(
      'Most-worn: $n ${_plural(n, 'item', 'items')} at $top '
      '${_plural(top, 'wear', 'wears')}'
      '${n > 1 ? ' (tied)' : ''}.',
    );
  }
  if (summary.leastWornItemIds.isNotEmpty) {
    final floor = summary.wearCounts[summary.leastWornItemIds.first] ?? 0;
    final n = summary.leastWornItemIds.length;
    parts.add(
      'Least-worn: $n ${_plural(n, 'item', 'items')} at $floor '
      '${_plural(floor, 'wear', 'wears')}'
      '${n > 1 ? ' (tied)' : ''}.',
    );
  }
  if (summary.unwornItemIds.isNotEmpty) {
    final n = summary.unwornItemIds.length;
    parts.add('$n ${_plural(n, 'item', 'items')} not logged yet.');
  }
  final topCategory =
      _topCategoryLine(summary.wearsByCategory, summary.totalWears);
  if (topCategory.isNotEmpty) parts.add(topCategory);
  return WardrobeInsightData(
    title: 'Wear Summary',
    insight: parts.join(' '),
    iconName: 'insights_rounded',
    accentColor: 0xFFC5A059,
  );
}

String _plural(int n, String one, String many) => n == 1 ? one : many;

/// Counts-only top-category line, or empty when nothing is logged.
/// Ties are named; single winners are stated as facts, never judgments.
String _topCategoryLine(Map<String, int> byCategory, int total) {
  if (byCategory.isEmpty || total == 0) return '';
  var peak = 0;
  for (final count in byCategory.values) {
    if (count > peak) peak = count;
  }
  if (peak == 0) return '';
  final tops = [
    for (final entry in byCategory.entries)
      if (entry.value == peak) entry.key,
  ]..sort();
  if (tops.length == 1) {
    return 'Most logged category: ${tops.single} ($peak of $total wears).';
  }
  return 'Most logged categories (tied): ${tops.join(', ')} '
      '($peak of $total wears each).';
}

/// Normalizes a UI display value to a backend vocabulary code.
///
/// Backend `wardrobe_categories`/`colors`/`materials` are lowercase
/// snake_case (`light_blue`); the add-item UI offers display labels
/// (`Light Blue`). Already-canonical codes pass through unchanged.
// ponytail: case/space mapping only; labels outside backend vocab still
// 422 truthfully — add when backend publishes aliases or UI reads
// GET /v1/knowledge/* vocab.
String _vocabCode(String value) =>
    value.trim().toLowerCase().replaceAll(RegExp(r'\s+'), '_');

/// Abstract contract for wardrobe data operations.
///
/// The [WardrobeRepository] becomes the single abstraction used by the feature,
/// backed by the [WardrobeClient] API as the single source of truth.
/// There is deliberately NO mock fallback — missing or unavailable data
/// propagates truthfully to the UI.
abstract class WardrobeRepository {
  /// Returns the current list of wardrobe items, filtered and paginated.
  /// API is the primary source; propagates errors when unreachable.
  Future<List<WardrobeItemData>> listItems({
    String? category,
    String? color,
    String? sortBy,
    String? order,
    int page = 1,
    int pageSize = 20,
  });

  /// Gets a single wardrobe item by ID.
  /// API is the primary source; returns null when unreachable or not found.
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

  /// Returns the live backend wear summary, or null when unavailable.
  ///
  /// Simple pass-through of `WardrobeClient.getWearSummary` (W-9): the
  /// backend `WearSummary` DTO is returned verbatim — UUID strings
  /// untouched, no local-ID reconciliation, no mock fallback. A 200 zero
  /// object (empty wardrobe / no history) passes through as-is; the
  /// caller (via `mapWearSummaryToUi`) renders no claim for it. Null
  /// means unavailable — hide the summary surface, never fabricate one.
  Future<WearSummary?> getWearSummary();

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
/// as the primary and authoritative data source with zero mock fallback.
///
/// API success → domain model (mapped from [WardrobeItem] DTO)
/// API failure → truthful failure propagation (throw on listItems, null on getItem)
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

    // Backend unreachable / failed: propagate failure so WardrobeScreen
    // can display its loading/error/retry UI. Never fall back to mock data.
    throw StateError('Wardrobe backend unavailable');
  }

  @override
  Future<WardrobeItemData?> getItem({required String itemId}) async {
    final apiItem = await _client.getItem(itemId: itemId);

    if (apiItem != null) {
      return mapItemDtoToUi(apiItem);
    }

    // Backend unreachable or item not found: truthfully return null.
    // Never fall back to mock data.
    return null;
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
      category: _vocabCode(category),
      color: _vocabCode(color),
      material: material == null ? null : _vocabCode(material),
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
      category: category == null ? null : _vocabCode(category),
      color: color == null ? null : _vocabCode(color),
      material: material == null ? null : _vocabCode(material),
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
  Future<WearSummary?> getWearSummary() {
    // No mock fallback, no LearningService substitution, no ID
    // translation: a fabricated or remapped summary would corrupt the
    // read surface. Null means unavailable — the caller hides it.
    return _client.getWearSummary();
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