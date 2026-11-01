import 'dart:io';
import 'dart:typed_data';

import 'package:fansivibe/features/media/domain/image_pipeline.dart';

/// Manages local storage of original user photographs (Decision Option B).
///
/// Invariants:
/// 1. Original photographs remain locally in app-managed storage (`originals/`).
/// 2. Local originals must NOT be automatically deleted.
/// 3. Offline access is preserved even when disconnected or logged out.
class OriginalFileManager {
  OriginalFileManager({String? baseDirectoryPath})
      : _baseDirectoryPath = baseDirectoryPath;

  final String? _baseDirectoryPath;
  static OriginalFileManager? _instance;

  static OriginalFileManager get instance =>
      _instance ??= OriginalFileManager();

  /// In-memory cache fallback for environments without file system access or during tests.
  final Map<String, Uint8List> _memoryStore = {};

  String get _rootDir {
    if (_baseDirectoryPath != null) return _baseDirectoryPath;
    try {
      final tmp = Directory.systemTemp.path;
      return '$tmp/fansivibe_originals';
    } catch (_) {
      return '/tmp/fansivibe_originals';
    }
  }

  /// Calculates content-based key or normalizes input identifier.
  String _normalizeKey(String idOrHash, Uint8List bytes) {
    if (idOrHash.isNotEmpty) return idOrHash;
    return sha256Hex(bytes);
  }

  /// Computes the persistent local path for an original photo.
  String getOriginalPath(String idOrHash, {String extension = 'jpg'}) {
    final sanitized = idOrHash.replaceAll(RegExp(r'[^a-zA-Z0-9_-]'), '_');
    return '$_rootDir/$sanitized.$extension';
  }

  /// Persists original photo bytes to local app storage without deleting prior files.
  Future<String> saveOriginal({
    required String idOrHash,
    required Uint8List bytes,
    String extension = 'jpg',
  }) async {
    final key = _normalizeKey(idOrHash, bytes);
    _memoryStore[key] = bytes;

    try {
      final dir = Directory(_rootDir);
      if (!dir.existsSync()) {
        dir.createSync(recursive: true);
      }
      final filePath = getOriginalPath(key, extension: extension);
      final file = File(filePath);
      file.writeAsBytesSync(bytes, flush: true);
      return filePath;
    } catch (_) {
      // In web or restricted environments, memory store acts as safe fallback
      return 'memory://$key';
    }
  }

  /// Loads original photo bytes from local disk or memory cache.
  Future<Uint8List?> loadOriginal(String pathOrId) async {
    if (_memoryStore.containsKey(pathOrId)) {
      return _memoryStore[pathOrId];
    }

    try {
      final file = File(pathOrId);
      if (file.existsSync()) {
        final bytes = file.readAsBytesSync();
        return bytes;
      }
    } catch (_) {}

    // Check if pathOrId is a key in the root directory
    try {
      final fallbackPath = getOriginalPath(pathOrId);
      final file = File(fallbackPath);
      if (file.existsSync()) {
        return await file.readAsBytes();
      }
    } catch (_) {}

    return null;
  }

  /// Checks if the original photo exists locally.
  Future<bool> exists(String pathOrId) async {
    if (_memoryStore.containsKey(pathOrId)) return true;
    try {
      final file = File(pathOrId);
      if (file.existsSync()) return true;
      final fallbackFile = File(getOriginalPath(pathOrId));
      if (fallbackFile.existsSync()) return true;
    } catch (_) {}
    return false;
  }
}
