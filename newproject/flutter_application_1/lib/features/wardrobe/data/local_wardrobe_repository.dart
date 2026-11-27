import 'dart:typed_data';

import 'package:fansivibe/features/learning/data/models.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_item_photo.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';

WardrobeItemData _toData(WardrobeEntry entry) => WardrobeItemData(
  id: entry.id,
  name: entry.name,
  category: entry.category,
  color: entry.color,
  material: entry.material,
  isFavorite: entry.isFavorite,
  fit: entry.fit,
  fitConfidence: entry.fitConfidence,
  sourceRunId: entry.sourceRunId,
  candidateId: entry.candidateId,
  extractionConfidence: entry.extractionConfidence,
  imageBytes: decodeWardrobePhoto(entry.imageBase64),
  createdAt: entry.createdAt,
  updatedAt: entry.updatedAt,
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
/// (unreachable behind the UUID gate). Photos persist as bounded bytes
/// on the entry itself (see the wardrobe photo helper); manual entries
/// stay imageless.
class LocalWardrobeRepository implements WardrobeRepository {
  LocalWardrobeRepository({LearningService? service})
    : _service = service ?? LearningService.instance;

  final LearningService _service;

  static int _lastIdMicros = 0;

  /// Mints a device-local id. Monotonic microseconds prevent collisions when
  /// saving multiple extracted garments in a tight loop.
  static String newLocalId() {
    final now = DateTime.now().microsecondsSinceEpoch;
    _lastIdMicros = now > _lastIdMicros ? now : _lastIdMicros + 1;
    return 'local-$_lastIdMicros';
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
    Iterable<WardrobeEntry> entries = _service.wardrobe.where(
      (e) => e.isGuestLocal,
    );
    if (category != null && category != 'all') {
      entries = entries.where((e) => e.category == category);
    }
    if (color != null && color.isNotEmpty) {
      entries = entries.where(
        (e) => e.color.toLowerCase() == color.toLowerCase(),
      );
    }
    final start = (page - 1) * pageSize;
    return entries
        .skip(start < 0 ? 0 : start)
        .take(pageSize)
        .map(_toData)
        .toList();
  }

  @override
  Future<WardrobeItemData?> getItem({required String itemId}) async {
    for (final entry in _service.wardrobe) {
      if (entry.id == itemId && entry.isGuestLocal) return _toData(entry);
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
    final now = DateTime.now().toUtc();
    final entry = WardrobeEntry(
      id: newLocalId(),
      name: name,
      category: category,
      color: color,
      material: material,
      fit: fit,
      fitConfidence: fitConfidence,
      sourceRunId: imageRef?.sourceRunId,
      candidateId: imageRef?.candidateId,
      extractionConfidence: imageRef?.extractionConfidence,
      isAuthenticatedMirror: false,
      createdAt: now,
      updatedAt: now,
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
    String? fit,
    double? fitConfidence,
  }) => updateItemDetailsDirect(
    itemId: itemId,
    name: name,
    category: category,
    color: color,
    material: material,
    isFavorite: isFavorite,
    fit: fit,
    fitConfidence: fitConfidence,
  );

  Future<WardrobeItemData?> updateItemDetailsDirect({
    required String itemId,
    String? name,
    String? category,
    String? color,
    String? material,
    bool clearMaterial = false,
    bool? isFavorite,
    String? fit,
    bool clearFit = false,
    double? fitConfidence,
    MediaRef? imageRef,
    bool clearImageRef = false,
    Uint8List? imageBytes,
  }) async {
    WardrobeEntry? current;
    for (final entry in _service.wardrobe) {
      if (entry.id == itemId && entry.isGuestLocal) {
        current = entry;
        break;
      }
    }
    if (current == null) return null;
    final String? nextImageBase64;
    if (clearImageRef) {
      nextImageBase64 = null;
    } else if (imageBytes != null && imageBytes.isNotEmpty) {
      nextImageBase64 = encodeWardrobePhoto(imageBytes);
    } else {
      nextImageBase64 = current.imageBase64;
    }
    final updated = WardrobeEntry(
      id: current.id,
      name: name ?? current.name,
      category: category ?? current.category,
      color: color ?? current.color,
      material: clearMaterial ? null : (material ?? current.material),
      isFavorite: isFavorite ?? current.isFavorite,
      fit: clearFit ? null : (fit ?? current.fit),
      fitConfidence: fitConfidence ?? current.fitConfidence,
      sourceRunId: current.sourceRunId,
      candidateId: current.candidateId,
      extractionConfidence: current.extractionConfidence,
      imageBase64: nextImageBase64,
      isAuthenticatedMirror: false,
      createdAt: current.createdAt,
      updatedAt: DateTime.now().toUtc(),
    );
    _service.updateItem(itemId, updated);
    return _toData(updated);
  }

  @override
  Future<bool?> deleteItem({required String itemId}) async {
    final existed = _service.wardrobe.any(
      (e) => e.id == itemId && e.isGuestLocal,
    );
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

  @override
  Future<WearEventLogResponse?> logEnsembleWear({
    required List<String> itemIds,
    DateTime? wornAt,
    String? idempotencyKey,
  }) async => null;
}
