import 'package:fansivibe/features/learning/data/models.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';

WardrobeItemData _toData(WardrobeEntry entry) => WardrobeItemData(
  id: entry.id,
  name: entry.name,
  category: entry.category,
  color: entry.color,
  material: entry.material,
  isFavorite: entry.isFavorite,
);

/// On-device wardrobe for guests (Phase 2.1, no account, no backend).
///
/// Implements the existing [WardrobeRepository] contract over the
/// already-persisted [LearningService] model (`LocalStore` shared_prefs
/// JSON), so guest screens run their normal list/detail/add/edit/delete
/// flows with zero API calls and zero new storage. IDs are
/// `local-<microseconds>` — deliberately NOT backend UUIDs, so the
/// existing UUID gate keeps hiding wear-logging (a server-history
/// action) without any extra check. Server intelligence has no
/// on-device equivalent: [getInsight] and [getWearSummary] return null
/// (callers already hide those slots) and [logWear] returns null
/// (unreachable behind the UUID gate). Photo `imageRef`s are dropped:
/// guest garment analysis is server-side, so local items are
/// imageless — the add-item form says so at the photo step.
class LocalWardrobeRepository implements WardrobeRepository {
  LocalWardrobeRepository({LearningService? service})
    : _service = service ?? LearningService.instance;

  final LearningService _service;

  /// Mints a device-local id. Microseconds make manual-add collisions
  /// practically impossible; no `uuid` dependency for one call site.
  static String newLocalId() =>
      'local-${DateTime.now().microsecondsSinceEpoch}';

  @override
  Future<List<WardrobeItemData>> listItems({
    String? category,
    String? color,
    String? sortBy,
    String? order,
    int page = 1,
    int pageSize = 20,
  }) async {
    Iterable<WardrobeEntry> entries = _service.wardrobe;
    if (category != null && category != 'all') {
      entries = entries.where((e) => e.category == category);
    }
    if (color != null && color.isNotEmpty) {
      entries = entries.where(
        (e) => e.color.toLowerCase() == color.toLowerCase(),
      );
    }
    final start = (page - 1) * pageSize;
    return entries.skip(start < 0 ? 0 : start).take(pageSize).map(_toData).toList();
  }

  @override
  Future<WardrobeItemData?> getItem({required String itemId}) async {
    for (final entry in _service.wardrobe) {
      if (entry.id == itemId) return _toData(entry);
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
  }) async {
    final entry = WardrobeEntry(
      id: newLocalId(),
      name: name,
      category: category,
      color: color,
      material: material,
    );
    _service.addItem(entry);
    return _toData(entry);
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
    WardrobeEntry? current;
    for (final entry in _service.wardrobe) {
      if (entry.id == itemId) current = entry;
    }
    if (current == null) return null;
    final updated = WardrobeEntry(
      id: current.id,
      name: name ?? current.name,
      category: category ?? current.category,
      color: color ?? current.color,
      material: material ?? current.material,
      isFavorite: isFavorite ?? current.isFavorite,
    );
    _service.updateItem(itemId, updated);
    return _toData(updated);
  }

  @override
  Future<bool?> deleteItem({required String itemId}) async {
    final existed = _service.wardrobe.any((e) => e.id == itemId);
    if (!existed) return false;
    _service.removeItem(itemId);
    return true;
  }

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
