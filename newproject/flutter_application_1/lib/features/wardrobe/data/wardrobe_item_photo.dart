import 'dart:convert';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:fansivibe/features/learning/data/models.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart';

/// Photo bytes carried with a wardrobe item, and their persistence.
///
/// The backend image pipeline stores only an `imageRef` metadata envelope
/// (object key, media type, hash) and serves no image bytes back, so the
/// renderable photo lives with the item itself: [WardrobeItemData.imageBytes]
/// in memory, base64 under [WardrobeEntry.imageBase64] in the existing
/// on-device `LocalStore` JSON (guests), which doubles as the same-device
/// mirror for account items (the screens already mirror saves there).
/// No file paths are ever stored — picker/camera temp paths would go stale,
/// so only bytes travel. Manual entries stay null (existing empty well).
const int maxWardrobePhotoBytes = 512 * 1024;

/// Longest edge of a persisted wardrobe photo. Matches the existing
/// gallery-pick cap (1024) so camera captures obey the same policy.
const int maxWardrobePhotoEdge = 1024;

/// Encodes photo bytes for [WardrobeEntry.imageBase64]. Null/empty stays
/// null so imageless items serialize exactly as before.
String? encodeWardrobePhoto(Uint8List? bytes) {
  if (bytes == null || bytes.isEmpty) return null;
  return base64Encode(bytes);
}

/// Decodes [WardrobeEntry.imageBase64] back to bytes. Corrupt values fail
/// closed to null (safe fallback) instead of throwing into the list.
Uint8List? decodeWardrobePhoto(String? base64) {
  if (base64 == null || base64.isEmpty) return null;
  try {
    final bytes = base64Decode(base64);
    return bytes.isEmpty ? null : bytes;
  } catch (_) {
    return null;
  }
}

/// Bounds a captured/selected photo for persistence. Small photos pass
/// through untouched; oversized ones are downscaled (aspect preserved,
/// longest edge [maxWardrobePhotoEdge]) and PNG-encoded with stdlib
/// `dart:ui` only — no new dependency, web-safe. Any failure returns the
/// original bytes: a big photo beats no photo.
///
/// ponytail: PNG thumbnails bloat the single prefs blob (~100KB-1MB per
/// photo); move to a dedicated blob store or server thumbnails when photo
/// counts grow.
Future<Uint8List?> prepareWardrobePhoto(Uint8List? bytes) async {
  if (bytes == null || bytes.isEmpty) return null;
  if (bytes.length <= maxWardrobePhotoBytes) return bytes;
  try {
    final bounds = await _decodeBounds(bytes);
    if (bounds == null) return bytes;
    final longest = bounds.$1 > bounds.$2 ? bounds.$1 : bounds.$2;
    final scale = maxWardrobePhotoEdge / longest;
    if (scale >= 1) return bytes;
    final codec = await ui.instantiateImageCodec(
      bytes,
      targetWidth: (bounds.$1 * scale).round(),
      targetHeight: (bounds.$2 * scale).round(),
    );
    final frame = await codec.getNextFrame();
    final data = await frame.image.toByteData(format: ui.ImageByteFormat.png);
    return data == null ? bytes : data.buffer.asUint8List();
  } catch (_) {
    return bytes;
  }
}

Future<(int, int)?> _decodeBounds(Uint8List bytes) async {
  try {
    final codec = await ui.instantiateImageCodec(bytes);
    final frame = await codec.getNextFrame();
    return (frame.image.width, frame.image.height);
  } catch (_) {
    return null;
  }
}

/// Overlays the on-device photo for [item] by id. Backend list/get
/// responses carry metadata only, so account items rehydrate their
/// renderable bytes from the existing mirror; entries without a photo
/// (manual items, pre-fix rows) return unchanged.
WardrobeItemData attachLocalPhoto(WardrobeItemData item) {
  for (final entry in LearningService.instance.wardrobe) {
    if (entry.id != item.id) continue;
    final bytes = decodeWardrobePhoto(entry.imageBase64);
    if (bytes == null) return item;
    if (item.imageBytes != null && item.imageBytes!.isNotEmpty) return item;
    return item.copyWith(imageBytes: bytes);
  }
  return item;
}

/// Converts UI data to a mirror [WardrobeEntry], preserving the stored
/// photo when the incoming item carries no new bytes (edits must not wipe
/// the photo). New bytes win; both null stays imageless.
WardrobeEntry wardrobeEntryFromItem(WardrobeItemData item) {
  String? base64 = encodeWardrobePhoto(item.imageBytes);
  if (base64 == null) {
    for (final entry in LearningService.instance.wardrobe) {
      if (entry.id == item.id) {
        base64 = entry.imageBase64;
        break;
      }
    }
  }
  return WardrobeEntry(
    id: item.id,
    name: item.name,
    category: item.category,
    color: item.color,
    material: item.material,
    isFavorite: item.isFavorite,
    imageBase64: base64,
  );
}
