import 'dart:io';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import 'package:fansivibe/features/media/data/media_client.dart';
import 'package:fansivibe/features/media/domain/original_file_manager.dart';

/// Secure media cache manager for wardrobe images (Stage 2 P0-4 Gate 2 / Gate 5).
///
/// Features:
/// 1. Content-hash/key L1 (in-memory) and L2 (local disk) caching.
/// 2. Automatic presigned GET URL refresh on HTTP 403 or expired signature.
/// 3. Cross-account cache isolation: clearing on logout/account switch prevents
///    User A's images from ever leaking to User B.
/// 4. Does not delete local originals (preserves Decision Option B).
class WardrobeCacheManager {
  WardrobeCacheManager({
    http.Client? httpClient,
    MediaClient? mediaClient,
    String? cacheDirectoryPath,
  })  : _httpClient = httpClient ?? http.Client(),
        _mediaClient = mediaClient ?? MediaClient(),
        _cacheDirectoryPath = cacheDirectoryPath;

  final http.Client _httpClient;
  final MediaClient _mediaClient;
  final String? _cacheDirectoryPath;

  static WardrobeCacheManager? _instance;

  static WardrobeCacheManager get instance =>
      _instance ??= WardrobeCacheManager();

  /// L1 memory cache keyed by objectKey or content hash.
  final Map<String, Uint8List> _memoryCache = {};

  String get _cacheDir {
    if (_cacheDirectoryPath != null) return _cacheDirectoryPath;
    try {
      final tmp = Directory.systemTemp.path;
      return '$tmp/fansivibe_media_cache';
    } catch (_) {
      return '/tmp/fansivibe_media_cache';
    }
  }

  String _diskPathForKey(String key) {
    final sanitized = key.replaceAll(RegExp(r'[^a-zA-Z0-9_-]'), '_');
    return '$_cacheDir/$sanitized.webp';
  }

  /// Retrieves image bytes from L1 memory, L2 disk, or remote presigned URL.
  Future<Uint8List?> getImage({
    required String key,
    String? downloadUrl,
    String? uploadId,
    String? localOriginalPath,
  }) async {
    // 1. Check local original first if specified
    if (localOriginalPath != null && localOriginalPath.isNotEmpty) {
      final original =
          await OriginalFileManager.instance.loadOriginal(localOriginalPath);
      if (original != null && original.isNotEmpty) {
        return original;
      }
    }

    // 2. Check L1 memory cache
    if (_memoryCache.containsKey(key)) {
      return _memoryCache[key];
    }

    // 3. Check L2 disk cache
    try {
      final diskFile = File(_diskPathForKey(key));
      if (diskFile.existsSync()) {
        final bytes = await diskFile.readAsBytes();
        if (bytes.isNotEmpty) {
          _memoryCache[key] = bytes;
          return bytes;
        }
      }
    } catch (_) {}

    // 4. Download from remote URL if available
    var activeUrl = downloadUrl;
    if (activeUrl == null || activeUrl.isEmpty) {
      if (uploadId != null && uploadId.isNotEmpty) {
        final ref = await _mediaClient.getDownloadUrl(uploadId: uploadId);
        activeUrl = ref?.downloadUrl;
      }
    }

    if (activeUrl == null || activeUrl.isEmpty) {
      return null;
    }

    var bytes = await _fetchUrl(activeUrl);

    // If fetch failed due to expiration (401/403) and we have uploadId, refresh URL once
    if (bytes == null && uploadId != null && uploadId.isNotEmpty) {
      final fresh = await _mediaClient.getDownloadUrl(uploadId: uploadId);
      if (fresh != null && fresh.downloadUrl != activeUrl) {
        bytes = await _fetchUrl(fresh.downloadUrl);
      }
    }

    if (bytes != null && bytes.isNotEmpty) {
      _memoryCache[key] = bytes;
      _saveToDiskCache(key, bytes);
      return bytes;
    }

    return null;
  }

  Future<Uint8List?> _fetchUrl(String url) async {
    try {
      final response = await _httpClient
          .get(Uri.parse(url))
          .timeout(const Duration(seconds: 15));
      if (response.statusCode == 200) {
        return response.bodyBytes;
      }
    } catch (_) {}
    return null;
  }

  void _saveToDiskCache(String key, Uint8List bytes) {
    try {
      final dir = Directory(_cacheDir);
      if (!dir.existsSync()) {
        dir.createSync(recursive: true);
      }
      final file = File(_diskPathForKey(key));
      file.writeAsBytesSync(bytes, flush: true);
    } catch (_) {}
  }

  /// Invalidates a specific entry from memory and disk caches.
  void invalidate(String key) {
    _memoryCache.remove(key);
    try {
      final file = File(_diskPathForKey(key));
      if (file.existsSync()) {
        file.deleteSync();
      }
    } catch (_) {}
  }

  /// Clears all cached cloud derivatives across memory and disk on logout/account switch.
  /// Never touches local originals in `OriginalFileManager` (Option B).
  void clear() {
    _memoryCache.clear();
    try {
      final dir = Directory(_cacheDir);
      if (dir.existsSync()) {
        dir.deleteSync(recursive: true);
      }
    } catch (_) {}
  }
}
