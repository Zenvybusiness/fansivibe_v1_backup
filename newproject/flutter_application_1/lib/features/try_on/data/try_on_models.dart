import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';

import 'package:fansivibe/features/media/domain/image_pipeline.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

/// Virtual try-on consent contract version pinned to the backend.
abstract final class TryOnConsentVersion {
  static const current = 'tryon-v1';
}

/// Outfit provenance accepted by `POST /v1/tryon/jobs`.
abstract final class TryOnOutfitSource {
  static const today = 'today';
  static const outfit = 'outfit';
  static const saved = 'saved';
  static const wardrobe = 'wardrobe';

  static const values = {today, outfit, saved, wardrobe};
}

/// Try-on job lifecycle states returned by `GET /v1/tryon/jobs/{job_id}`.
enum TryOnJobState { queued, processing, completed, failed, cancelled, unknown }

enum TryOnFailure {
  unauthorized,
  notFound,
  conflict,
  invalidInput,
  rateLimited,
  quotaExceeded,
  serviceUnavailable,
  networkError,
  timeout,
  unknown,
}

/// Backend-driven try-on capabilities (`GET /v1/tryon/capabilities`).
///
/// Defaults conservatively to single-garment + 10 MB when capabilities have
/// not yet loaded so the client never exceeds Genlook limits.
class TryOnCapabilities {
  const TryOnCapabilities({
    required this.enabled,
    required this.isMock,
    required this.maxGarments,
    required this.maxPersonImageBytes,
    required this.minImageEdge,
    required this.maxImageEdge,
    required this.maxImagePixels,
    required this.allowedMimeTypes,
    required this.consentVersion,
    required this.pollIntervalSeconds,
    required this.pollTimeoutSeconds,
    required this.aiDisclosureRequired,
  });

  static const TryOnCapabilities fallback = TryOnCapabilities(
    enabled: true,
    isMock: true,
    maxGarments: 1,
    maxPersonImageBytes: 10 * 1024 * 1024,
    minImageEdge: 64,
    maxImageEdge: 4096,
    maxImagePixels: 12000000,
    allowedMimeTypes: ['image/jpeg', 'image/png', 'image/webp'],
    consentVersion: TryOnConsentVersion.current,
    pollIntervalSeconds: 1.0,
    pollTimeoutSeconds: 120.0,
    aiDisclosureRequired: false,
  );

  final bool enabled;
  final bool isMock;
  final int maxGarments;
  final int maxPersonImageBytes;
  final int minImageEdge;
  final int maxImageEdge;
  final int maxImagePixels;
  final List<String> allowedMimeTypes;
  final String consentVersion;
  final double pollIntervalSeconds;
  final double pollTimeoutSeconds;
  final bool aiDisclosureRequired;

  Duration get pollInterval => Duration(
    milliseconds: (pollIntervalSeconds * 1000).round().clamp(250, 10000),
  );

  /// Add 15s headroom above backend poll timeout for response delivery.
  Duration get maxPollDuration => Duration(
    seconds: pollTimeoutSeconds.ceil().clamp(15, 600) + 15,
  );

  static TryOnCapabilities? fromJson(Map<String, dynamic> json) {
    final maxGarments = json['max_garments'];
    final maxBytes = json['max_person_image_bytes'];
    if (maxGarments is! int || maxBytes is! int) return null;
    final rawMimes = json['allowed_mime_types'];
    final mimes = rawMimes is List
        ? rawMimes.whereType<String>().toList()
        : fallback.allowedMimeTypes;
    return TryOnCapabilities(
      enabled: json['enabled'] != false,
      isMock: json['is_mock'] != false,
      maxGarments: maxGarments.clamp(1, 20),
      maxPersonImageBytes: maxBytes.clamp(1024, 50 * 1024 * 1024),
      minImageEdge: (json['min_image_edge'] as num?)?.toInt() ?? 64,
      maxImageEdge: (json['max_image_edge'] as num?)?.toInt() ?? 4096,
      maxImagePixels: (json['max_image_pixels'] as num?)?.toInt() ?? 12000000,
      allowedMimeTypes: mimes.isEmpty ? fallback.allowedMimeTypes : mimes,
      consentVersion:
          (json['consent_version'] as String?) ?? TryOnConsentVersion.current,
      pollIntervalSeconds:
          (json['poll_interval_seconds'] as num?)?.toDouble() ?? 1.0,
      pollTimeoutSeconds:
          (json['poll_timeout_seconds'] as num?)?.toDouble() ?? 120.0,
      aiDisclosureRequired: json['ai_disclosure_required'] == true,
    );
  }
}

/// Submitted try-on job (`202 Accepted`).
class TryOnJob {
  const TryOnJob({
    required this.jobId,
    required this.state,
    required this.isMock,
  });

  final String jobId;
  final TryOnJobState state;
  final bool isMock;

  static TryOnJob? fromJson(Map<String, dynamic> json) {
    final jobId = json['job_id'];
    if (jobId is! String || jobId.isEmpty) return null;
    return TryOnJob(
      jobId: jobId,
      state: _stateOf(json['status']),
      isMock: json['is_mock'] != false,
    );
  }

  static TryOnJobState _stateOf(Object? status) {
    switch (status) {
      case 'completed':
        return TryOnJobState.completed;
      case 'failed':
        return TryOnJobState.failed;
      case 'cancelled':
        return TryOnJobState.cancelled;
      case 'queued':
        return TryOnJobState.queued;
      case 'processing':
        return TryOnJobState.processing;
      default:
        return TryOnJobState.unknown;
    }
  }
}

/// Polled job status (`200 OK`) aligned with `TryOnJobStatus` schema.
class TryOnJobStatus {
  const TryOnJobStatus({
    required this.jobId,
    required this.state,
    required this.progress,
    required this.isMock,
    this.outfitSource,
    this.errorCode,
    this.errorMessage,
    this.retryCount = 0,
    this.createdAt,
    this.completedAt,
    this.garmentIds = const [],
    this.resultMediaRef,
  });

  final String jobId;
  final TryOnJobState state;
  final int progress;
  final bool isMock;
  final String? outfitSource;
  final String? errorCode;
  final String? errorMessage;
  final int retryCount;
  final String? createdAt;
  final String? completedAt;
  final List<String> garmentIds;
  final Map<String, dynamic>? resultMediaRef;

  static TryOnJobStatus? fromJson(Map<String, dynamic> json) {
    final jobId = json['job_id'];
    if (jobId is! String || jobId.isEmpty) return null;
    final progress = json['progress'];
    final rawGarments = json['garment_ids'];
    final garments = rawGarments is List
        ? rawGarments.whereType<String>().toList()
        : const <String>[];
    final rawMediaRef = json['result_media_ref'];
    return TryOnJobStatus(
      jobId: jobId,
      state: TryOnJob._stateOf(json['status']),
      progress: progress is int ? progress : 0,
      isMock: json['is_mock'] != false,
      outfitSource: json['outfit_source'] as String?,
      errorCode: json['error_code'] as String?,
      errorMessage: json['error_message'] as String?,
      retryCount: json['retry_count'] is int ? json['retry_count'] as int : 0,
      createdAt: json['created_at'] as String?,
      completedAt: json['completed_at'] as String?,
      garmentIds: garments,
      resultMediaRef: rawMediaRef is Map<String, dynamic>
          ? Map<String, dynamic>.from(rawMediaRef)
          : null,
    );
  }
}

/// Outcome of one submit or retry attempt.
class TryOnSubmitResult {
  const TryOnSubmitResult({
    this.job,
    this.failure,
    this.errorCode,
    this.errorMessage,
    this.statusCode,
  });

  final TryOnJob? job;
  final TryOnFailure? failure;
  final String? errorCode;
  final String? errorMessage;
  final int? statusCode;
}

/// Outcome of polling `GET /v1/tryon/jobs/{id}` with explicit failure context.
class TryOnStatusOutcome {
  const TryOnStatusOutcome({
    this.status,
    this.failure,
    this.errorMessage,
    this.statusCode,
  });

  final TryOnJobStatus? status;
  final TryOnFailure? failure;
  final String? errorMessage;
  final int? statusCode;
}

/// Outcome of fetching `GET /v1/tryon/jobs/{id}/image`.
class TryOnImageOutcome {
  const TryOnImageOutcome({
    this.bytes,
    this.contentType,
    this.failure,
    this.errorMessage,
    this.statusCode,
  });

  final Uint8List? bytes;
  final String? contentType;
  final TryOnFailure? failure;
  final String? errorMessage;
  final int? statusCode;
}

/// Result of client-side person image validation against backend constraints.
class TryOnPersonImageValidationResult {
  const TryOnPersonImageValidationResult.valid({
    required this.mimeType,
    required this.width,
    required this.height,
  }) : isValid = true,
       errorMessage = null;

  const TryOnPersonImageValidationResult.invalid(this.errorMessage)
    : isValid = false,
      mimeType = null,
      width = null,
      height = null;

  final bool isValid;
  final String? errorMessage;
  final String? mimeType;
  final int? width;
  final int? height;
}

/// Pure-Dart header parser for JPEG, PNG, and WebP pixel dimensions.
/// Avoids decoding multi-megapixel images into RGBA buffers just to check bounds.
(int, int)? parseImageDimensions(Uint8List bytes) {
  final mime = detectImageMimeType(bytes);
  if (mime == 'image/png' && bytes.length >= 24) {
    final bd = ByteData.sublistView(bytes);
    final w = bd.getUint32(16, Endian.big);
    final h = bd.getUint32(20, Endian.big);
    return (w > 0 && h > 0) ? (w, h) : null;
  }
  if (mime == 'image/webp' && bytes.length >= 30) {
    final chunk = String.fromCharCodes(bytes.sublist(12, 16));
    if (chunk == 'VP8 ' && bytes.length >= 30) {
      final w = (bytes[26] | (bytes[27] << 8)) & 0x3FFF;
      final h = (bytes[28] | (bytes[29] << 8)) & 0x3FFF;
      return (w > 0 && h > 0) ? (w, h) : null;
    }
    if (chunk == 'VP8L' && bytes.length >= 25) {
      final b0 = bytes[21];
      final b1 = bytes[22];
      final b2 = bytes[23];
      final b3 = bytes[24];
      final w = 1 + (((b1 & 0x3F) << 8) | b0);
      final h = 1 + (((b3 & 0x0F) << 10) | (b2 << 2) | ((b1 & 0xC0) >> 6));
      return (w > 0 && h > 0) ? (w, h) : null;
    }
    if (chunk == 'VP8X' && bytes.length >= 30) {
      final w = 1 + (bytes[24] | (bytes[25] << 8) | (bytes[26] << 16));
      final h = 1 + (bytes[27] | (bytes[28] << 8) | (bytes[29] << 16));
      return (w > 0 && h > 0) ? (w, h) : null;
    }
  }
  if (mime == 'image/jpeg') {
    var i = 2;
    while (i + 3 < bytes.length) {
      if (bytes[i] != 0xFF) {
        i++;
        continue;
      }
      while (i < bytes.length && bytes[i] == 0xFF) {
        i++;
      }
      if (i >= bytes.length) break;
      final marker = bytes[i++];
      if (marker == 0xD8 || marker == 0xD9 || marker == 0x01 || (marker >= 0xD0 && marker <= 0xD7)) {
        continue;
      }
      if (i + 1 >= bytes.length) break;
      final segLen = (bytes[i] << 8) | bytes[i + 1];
      if (segLen < 2 || i + segLen > bytes.length) break;
      final isSof = (marker >= 0xC0 && marker <= 0xC3) ||
          (marker >= 0xC5 && marker <= 0xC7) ||
          (marker >= 0xC9 && marker <= 0xCB) ||
          (marker >= 0xCD && marker <= 0xCF);
      if (isSof && i + 6 < bytes.length) {
        final h = (bytes[i + 3] << 8) | bytes[i + 4];
        final w = (bytes[i + 5] << 8) | bytes[i + 6];
        return (w > 0 && h > 0) ? (w, h) : null;
      }
      i += segLen;
    }
  }
  return null;
}

/// Validates a person photo before upload using magic bytes, file size,
/// dimensions, and total pixel count matching the backend contract.
Future<TryOnPersonImageValidationResult> validateTryOnPersonImage(
  Uint8List bytes, {
  TryOnCapabilities capabilities = TryOnCapabilities.fallback,
  (int, int)? decodedDimensions,
}) async {
  if (bytes.isEmpty) {
    return const TryOnPersonImageValidationResult.invalid(
      'Selected image file is empty.',
    );
  }
  if (bytes.length > capabilities.maxPersonImageBytes) {
    final maxMb = (capabilities.maxPersonImageBytes / (1024 * 1024)).round();
    return TryOnPersonImageValidationResult.invalid(
      'Photo exceeds the $maxMb MB maximum size limit.',
    );
  }
  final mime = detectImageMimeType(bytes);
  if (mime == null || !capabilities.allowedMimeTypes.contains(mime)) {
    return const TryOnPersonImageValidationResult.invalid(
      'Unsupported image format. Please choose a JPEG, PNG, or WebP photo.',
    );
  }
  final dims =
      decodedDimensions ?? parseImageDimensions(bytes) ?? await getImageDimensions(bytes);
  if (dims == null) {
    return const TryOnPersonImageValidationResult.invalid(
      'Image file appears corrupted or unreadable.',
    );
  }
  final (width, height) = dims;
  if (width < capabilities.minImageEdge || height < capabilities.minImageEdge) {
    return TryOnPersonImageValidationResult.invalid(
      'Photo is too small (minimum ${capabilities.minImageEdge}×${capabilities.minImageEdge} px).',
    );
  }
  if (width > capabilities.maxImageEdge || height > capabilities.maxImageEdge) {
    return TryOnPersonImageValidationResult.invalid(
      'Photo dimensions exceed ${capabilities.maxImageEdge}×${capabilities.maxImageEdge} px.',
    );
  }
  if (width * height > capabilities.maxImagePixels) {
    final maxMp = (capabilities.maxImagePixels / 1000000).round();
    return TryOnPersonImageValidationResult.invalid(
      'Photo resolution exceeds the $maxMp megapixel limit.',
    );
  }
  return TryOnPersonImageValidationResult.valid(
    mimeType: mime,
    width: width,
    height: height,
  );
}

/// Opaque persisted reference for active/recent try-on recovery across
/// navigation and app restarts. Never stores person bytes, tokens, or URLs.
class TryOnSavedJobRef {
  const TryOnSavedJobRef({
    required this.jobId,
    required this.outfitSource,
    required this.garmentIds,
    required this.title,
    required this.isMock,
    required this.savedAtIso,
  });

  final String jobId;
  final String outfitSource;
  final List<String> garmentIds;
  final String title;
  final bool isMock;
  final String savedAtIso;

  Map<String, dynamic> toJson() => {
    'jobId': jobId,
    'outfitSource': outfitSource,
    'garmentIds': garmentIds,
    'title': title,
    'isMock': isMock,
    'savedAtIso': savedAtIso,
  };

  static TryOnSavedJobRef? fromJson(Map<String, dynamic> json) {
    final jobId = json['jobId'];
    if (jobId is! String || jobId.isEmpty) return null;
    final rawIds = json['garmentIds'];
    final ids = rawIds is List
        ? rawIds.whereType<String>().toList()
        : const <String>[];
    return TryOnSavedJobRef(
      jobId: jobId,
      outfitSource: (json['outfitSource'] as String?) ?? TryOnOutfitSource.wardrobe,
      garmentIds: ids,
      title: (json['title'] as String?) ?? 'Virtual Try-On',
      isMock: json['isMock'] != false,
      savedAtIso: (json['savedAtIso'] as String?) ?? '',
    );
  }
}

/// Null-safe persistence wrapper over [LocalStorage.activeTryOnJob].
abstract final class TryOnJobPersistence {
  static void save(TryOnSavedJobRef ref) {
    if (!LocalStorage.isInitialized) return;
    LocalStorage.activeTryOnJob = jsonEncode(ref.toJson());
  }

  static TryOnSavedJobRef? load() {
    if (!LocalStorage.isInitialized) return null;
    final raw = LocalStorage.activeTryOnJob;
    if (raw == null || raw.isEmpty) return null;
    try {
      final decoded = jsonDecode(raw);
      if (decoded is Map<String, dynamic>) {
        final ref = TryOnSavedJobRef.fromJson(decoded);
        if (ref == null) {
          clear();
          return null;
        }
        final savedAt = DateTime.tryParse(ref.savedAtIso);
        if (savedAt != null &&
            DateTime.now().toUtc().difference(savedAt.toUtc()).inHours >= 72) {
          clear();
          return null;
        }
        return ref;
      }
    } catch (_) {
      clear();
    }
    return null;
  }

  static void clear() {
    if (!LocalStorage.isInitialized) return;
    LocalStorage.activeTryOnJob = null;
  }
}

/// Generates a fresh v4-style idempotency key for one try-on attempt.
String newTryOnIdempotencyKey() {
  final random = Random.secure();
  final bytes = List<int>.generate(16, (_) => random.nextInt(256));
  bytes[6] = (bytes[6] & 0x0F) | 0x40;
  bytes[8] = (bytes[8] & 0x3F) | 0x80;
  String hex(int v) => v.toRadixString(16).padLeft(2, '0');
  final h = bytes.map(hex).join();
  return '${h.substring(0, 8)}-${h.substring(8, 12)}-'
      '${h.substring(12, 16)}-${h.substring(16, 20)}-${h.substring(20)}';
}
