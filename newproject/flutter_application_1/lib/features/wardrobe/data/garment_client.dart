import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';

import 'package:fansivibe/core/config/app_config.dart';
import 'package:fansivibe/features/media/domain/image_pipeline.dart';
import 'package:fansivibe/features/wardrobe/data/garment_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';

/// One polled garment-analysis run (`GET /v1/analysis/runs/{run_id}`).
class GarmentAnalysisRun {
  const GarmentAnalysisRun({required this.statusCode, this.data});

  final int statusCode;
  final Map<String, dynamic>? data;

  bool get isCompleted => data?['status'] == 'completed';
  bool get isFailed => data?['status'] == 'failed';

  /// Completed-run observation snapshot, or null.
  Map<String, dynamic>? get result => data?['result'] as Map<String, dynamic>?;

  /// Persisted input-media metadata (key, mediaType, sizeBytes,
  /// contentHash, analyzer, uploadedAt) — the photo reference metadata.
  Map<String, dynamic>? get inputMedia =>
      data?['input_media'] as Map<String, dynamic>?;

  /// Typed failure reason (`details.reason`: no_garment_detected,
  /// low_confidence, analyzer_unavailable, invalid_image, …), or null.
  String? get failureReason {
    final error = data?['error'] as Map<String, dynamic>?;
    final details = error?['details'] as Map<String, dynamic>?;
    return details?['reason'] as String?;
  }
}

class SaveExtractedGarmentFailure {
  const SaveExtractedGarmentFailure({
    required this.candidateId,
    required this.name,
    required this.error,
  });

  final String candidateId;
  final String name;
  final String error;

  factory SaveExtractedGarmentFailure.fromJson(Map<String, dynamic> json) {
    return SaveExtractedGarmentFailure(
      candidateId: (json['candidateId'] as String?) ?? '',
      name: (json['name'] as String?) ?? 'Item',
      error: (json['error'] as String?) ?? 'Save failed',
    );
  }
}

class SaveExtractedGarmentsResult {
  const SaveExtractedGarmentsResult({
    this.savedItems = const [],
    this.failedItems = const [],
    this.cleanedUpAssets = false,
    this.errorMessage,
    this.isConflict = false,
    this.isUnauthorized = false,
  });

  final List<WardrobeItem> savedItems;
  final List<SaveExtractedGarmentFailure> failedItems;
  final bool cleanedUpAssets;
  final String? errorMessage;
  final bool isConflict;
  final bool isUnauthorized;

  bool get hasSavedItems => savedItems.isNotEmpty;
  bool get hasFailures => failedItems.isNotEmpty || errorMessage != null;
}

/// HTTP client for the M11 / P5.1 garment-analysis & extraction surface.
///
/// `POST /v1/analysis/garment` (multipart image → 202 `{run_id}`), then
/// `GET /v1/analysis/runs/{run_id}`, candidate crop retrieval, explicit save,
/// and temporary asset cleanup. Failures never fabricate garments.
class GarmentClient {
  GarmentClient({http.Client? client, Duration? pollInterval, String? baseUrl})
    : _client = client ?? http.Client(),
      _pollInterval = pollInterval ?? const Duration(seconds: 1),
      _baseUrl = baseUrl ?? AppConfig.apiBaseUrl;

  /// Canonical base URL — single source of truth is [AppConfig.apiBaseUrl].
  static const String baseUrl = AppConfig.apiBaseUrl;

  final String _baseUrl;

  static const String _devTokenDefault = String.fromEnvironment(
    'FANSIVIBE_DEV_TOKEN',
    defaultValue: 'dev',
  );

  /// Session-first Bearer token (D-AUTH-1): the persisted session wins;
  /// the dart-define default covers logged-out/test behavior.
  static String get _devToken => AuthSession.effectiveToken(_devTokenDefault);

  /// Client-side size guard mirroring the backend 20 MB contract so an
  /// oversized photo fails fast with a truthful message instead of an
  /// upload round-trip.
  static const int maxImageBytes = 20 * 1024 * 1024;

  final http.Client _client;
  final Duration _pollInterval;
  // Exceeds the 60s local vision inference budget + cropping overhead.
  static const Duration _timeout = Duration(seconds: 75);

  String? _activeIdempotencyKey;
  String? get activeIdempotencyKey => _activeIdempotencyKey;
  void resetIdempotencyKey() => _activeIdempotencyKey = null;

  String? lastSubmitError;
  String? lastSubmitErrorCode;
  String? lastPollError;
  String? lastPollErrorCode;
  bool _pollCancelled = false;

  /// Requests early cancellation of an in-flight [pollGarmentRun] loop.
  void cancelPolling() => _pollCancelled = true;

  /// Submits a garment photo for analysis.
  ///
  /// Returns the accepted `run_id` on 202, or null when the image is
  /// empty/oversized, the backend rejects it, or it is unreachable.
  Future<String?> submitGarmentAnalysisBytes(
    Uint8List bytes, {
    String filename = 'wardrobe_item.jpg',
    String? idempotencyKey,
  }) async {
    lastSubmitError = null;
    lastSubmitErrorCode = null;
    if (bytes.isEmpty || bytes.length > maxImageBytes) {
      lastSubmitError = bytes.isEmpty
          ? 'The selected image is empty.'
          : 'Image exceeds 20 MB size limit.';
      lastSubmitErrorCode = 'VALIDATION_ERROR';
      debugPrint('Garment submit refused image (${bytes.length} bytes).');
      return null;
    }
    final effectiveKey =
        idempotencyKey ??
        (_activeIdempotencyKey ??= newGarmentIdempotencyKey());
    try {
      final uri = Uri.parse('$_baseUrl/v1/analysis/garment');
      final request = http.MultipartRequest('POST', uri)
        ..headers['Authorization'] = 'Bearer $_devToken'
        ..headers['Idempotency-Key'] = effectiveKey;
      request.files.add(
        http.MultipartFile.fromBytes(
          'image',
          bytes,
          filename: filename,
          contentType: MediaType.parse(_contentTypeFor(filename, bytes)),
        ),
      );
      final streamed = await _client.send(request).timeout(_timeout);
      final response = await http.Response.fromStream(
        streamed,
      ).timeout(_timeout);
      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 202) {
        _activeIdempotencyKey = null;
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return decoded['run_id'] as String?;
      }
      _captureSubmitError(response);
      debugPrint(
        'Garment submit responded ${response.statusCode}: ${response.body}',
      );
    } on TimeoutException {
      lastSubmitError =
          'Garment extraction timed out while contacting the server. Please try again.';
      lastSubmitErrorCode = 'TIMEOUT';
    } catch (error) {
      lastSubmitError =
          'Could not upload photo for analysis. Please check your connection.';
      lastSubmitErrorCode = 'UNREACHABLE';
      debugPrint('Garment backend unreachable during submit: $error');
    }
    return null;
  }

  void _captureSubmitError(http.Response response) {
    if (response.statusCode == 401) {
      lastSubmitError = 'Please sign in to extract garments.';
      lastSubmitErrorCode = 'UNAUTHORIZED';
      return;
    }
    if (response.statusCode == 409) {
      lastSubmitError =
          'This request key was already used for another photo. Please try again.';
      lastSubmitErrorCode = 'CONFLICT';
      return;
    }
    if (response.statusCode == 413) {
      lastSubmitError = 'Image exceeds the maximum allowed upload size.';
      lastSubmitErrorCode = 'PAYLOAD_TOO_LARGE';
      return;
    }
    if (response.statusCode == 504) {
      lastSubmitError =
          'Garment extraction timed out while contacting the server. Please try again.';
      lastSubmitErrorCode = 'TIMEOUT';
      return;
    }
    if (response.statusCode == 502 || response.statusCode == 503) {
      lastSubmitError =
          'AI extraction service is currently unavailable. Please try again.';
      lastSubmitErrorCode = 'SERVICE_UNAVAILABLE';
      return;
    }
    try {
      final decoded = jsonDecode(response.body) as Map<String, dynamic>?;
      final error = decoded?['error'];
      if (error is Map<String, dynamic>) {
        lastSubmitErrorCode = error['code'] as String?;
        final details = error['details'];
        if (details is Map<String, dynamic>) {
          final fieldErrors = details['field_errors'];
          if (fieldErrors is List && fieldErrors.isNotEmpty) {
            final first = fieldErrors.first;
            if (first is Map<String, dynamic> && first['error'] is String) {
              lastSubmitError = first['error'] as String;
              return;
            }
          }
        }
        if (error['message'] is String &&
            (error['message'] as String).isNotEmpty) {
          lastSubmitError = error['message'] as String;
          return;
        }
      }
    } catch (_) {}
    lastSubmitError =
        'Garment upload failed (HTTP ${response.statusCode}). Please try again.';
  }

  /// Fetches one garment run (200 with data, other statuses bare, 0 when
  /// unreachable — never throws).
  Future<GarmentAnalysisRun> getGarmentRun({required String runId}) async {
    lastPollError = null;
    lastPollErrorCode = null;
    try {
      final response = await _client
          .get(
            Uri.parse('$_baseUrl/v1/analysis/runs/$runId'),
            headers: {'Authorization': 'Bearer $_devToken'},
          )
          .timeout(_timeout);
      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>?;
        return GarmentAnalysisRun(statusCode: 200, data: decoded);
      }
      if (response.statusCode == 401) {
        lastPollError = 'Please sign in again to continue garment extraction.';
        lastPollErrorCode = 'UNAUTHORIZED';
      } else if (response.statusCode == 404) {
        lastPollError =
            'This extraction run could not be found. Please try again.';
        lastPollErrorCode = 'NOT_FOUND';
      } else if (response.statusCode == 504) {
        lastPollError = 'Garment analysis timed out. Please try again.';
        lastPollErrorCode = 'TIMEOUT';
      } else if (response.statusCode == 502 || response.statusCode == 503) {
        lastPollError =
            'AI extraction service is currently unavailable. Please try again.';
        lastPollErrorCode = 'SERVICE_UNAVAILABLE';
      } else if (response.statusCode >= 500) {
        lastPollError =
            'Garment extraction failed on the server (HTTP ${response.statusCode}). Please try again.';
        lastPollErrorCode = 'SERVER_ERROR';
      }
      return GarmentAnalysisRun(statusCode: response.statusCode);
    } on TimeoutException {
      lastPollError =
          'Garment analysis timed out while contacting the server. Please try again.';
      lastPollErrorCode = 'TIMEOUT';
      return const GarmentAnalysisRun(statusCode: 0);
    } catch (error) {
      lastPollError =
          'Could not reach the server while checking extraction progress. Please try again.';
      lastPollErrorCode = 'UNREACHABLE';
      debugPrint('Garment backend unreachable during poll: $error');
      return const GarmentAnalysisRun(statusCode: 0);
    }
  }

  /// Polls until the run is completed/failed, the run disappears, [cancelPolling]
  /// is called, or [attempts] exhaust. A terminal `failed` run returns promptly.
  Future<GarmentAnalysisRun?> pollGarmentRun({
    required String runId,
    int attempts = 30,
  }) async {
    _pollCancelled = false;
    lastPollError = null;
    lastPollErrorCode = null;
    try {
      for (var attempt = 0; attempt < attempts; attempt++) {
        if (_pollCancelled) {
          lastPollErrorCode = 'CANCELLED';
          return null;
        }
        final run = await getGarmentRun(runId: runId);
        if (_pollCancelled) {
          lastPollErrorCode = 'CANCELLED';
          return null;
        }
        if (run.statusCode == 0 ||
            run.statusCode == 404 ||
            run.statusCode == 401 ||
            run.statusCode >= 500) {
          return null;
        }
        if (run.isCompleted || run.isFailed) return run;
        await Future<void>.delayed(_pollInterval);
      }
      lastPollError = 'Garment analysis timed out. Please try again.';
      lastPollErrorCode = 'INFERENCE_TIMEOUT';
    } catch (error) {
      lastPollError ??=
          'Could not reach the server while checking extraction progress. Please try again.';
      lastPollErrorCode ??= 'UNREACHABLE';
      debugPrint('Garment polling failed: $error');
    }
    return null;
  }

  /// Fetches private cropped candidate image bytes using authenticated Bearer token.
  Future<Uint8List?> fetchCandidateCropBytes({
    required String runId,
    required String candidateId,
  }) async {
    try {
      final uri = Uri.parse(
        '$_baseUrl/v1/analysis/runs/$runId/candidates/$candidateId/image',
      );
      final response = await _client
          .get(uri, headers: {'Authorization': 'Bearer $_devToken'})
          .timeout(const Duration(seconds: 15));
      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 200 && response.bodyBytes.isNotEmpty) {
        return response.bodyBytes;
      }
    } catch (error) {
      debugPrint('Candidate crop fetch failed: $error');
    }
    return null;
  }

  /// Explicitly saves user-selected garment candidates to Digital Wardrobe
  /// (`POST /v1/analysis/garment/runs/{runId}/save`).
  Future<SaveExtractedGarmentsResult?> saveExtractedGarments({
    required String runId,
    required List<GarmentCandidate> candidates,
    String? idempotencyKey,
  }) async {
    if (candidates.isEmpty) return null;
    try {
      final uri = Uri.parse('$_baseUrl/v1/analysis/garment/runs/$runId/save');
      final payload = {
        'items': candidates.map((c) {
          final name = (c.subcategory?.trim().isNotEmpty ?? false)
              ? c.subcategory!.trim()
              : '${c.color ?? ''} ${c.category ?? 'Garment'}'.trim();
          return {
            'candidateId': c.id ?? 'cand_1',
            'name': name.length > 100 ? name.substring(0, 100) : name,
            'category': c.category ?? 'tops',
            'color': c.color ?? 'black',
            if (c.material != null) 'material': c.material,
            if (c.fit != null) 'fit': c.fit,
            if (c.confidence != null) 'extractionConfidence': c.confidence,
            'isFavorite': false,
          };
        }).toList(),
      };
      final headers = <String, String>{
        'Authorization': 'Bearer $_devToken',
        'Content-Type': 'application/json; charset=UTF-8',
        if (idempotencyKey != null && idempotencyKey.isNotEmpty)
          'Idempotency-Key': idempotencyKey,
      };
      final response = await _client
          .post(uri, headers: headers, body: jsonEncode(payload))
          .timeout(_timeout);
      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        final rawSaved = decoded['savedItems'] as List<dynamic>? ?? const [];
        final rawFailed = decoded['failedItems'] as List<dynamic>? ?? const [];
        return SaveExtractedGarmentsResult(
          savedItems: rawSaved
              .whereType<Map<String, dynamic>>()
              .map(WardrobeItem.fromJson)
              .toList(),
          failedItems: rawFailed
              .whereType<Map<String, dynamic>>()
              .map(SaveExtractedGarmentFailure.fromJson)
              .toList(),
          cleanedUpAssets: decoded['cleanedUpAssets'] as bool? ?? false,
        );
      }
      if (response.statusCode == 401) {
        return const SaveExtractedGarmentsResult(
          errorMessage: 'Please sign in to save garments to your wardrobe.',
          isUnauthorized: true,
        );
      }
      if (response.statusCode == 409) {
        return const SaveExtractedGarmentsResult(
          errorMessage:
              'Selection changed for an existing save key. Retrying with fresh key.',
          isConflict: true,
        );
      }
      if (response.statusCode == 413) {
        return const SaveExtractedGarmentsResult(
          errorMessage:
              'Selected garment data exceeds the maximum allowed size.',
        );
      }
      String msg = response.statusCode == 504
          ? 'Saving garments timed out. Please retry.'
          : (response.statusCode == 502 || response.statusCode == 503)
          ? 'Wardrobe service is temporarily unavailable. Please try again.'
          : 'Could not save selected garments (HTTP ${response.statusCode}).';
      try {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>?;
        final err = decoded?['error'];
        if (err is Map<String, dynamic> && err['message'] is String) {
          msg = err['message'] as String;
        }
      } catch (_) {}
      return SaveExtractedGarmentsResult(errorMessage: msg);
    } on TimeoutException {
      return const SaveExtractedGarmentsResult(
        errorMessage: 'Saving garments timed out. Please retry.',
      );
    } catch (error) {
      debugPrint('Save extracted garments failed: $error');
      return const SaveExtractedGarmentsResult(
        errorMessage: 'Could not reach server while saving garments.',
      );
    }
  }

  /// Cleans up temporary extraction crops when discarding/cancelling a run.
  Future<bool> cleanupExtractionAssets({required String runId}) async {
    try {
      final uri = Uri.parse('$_baseUrl/v1/analysis/garment/runs/$runId/assets');
      final response = await _client
          .delete(uri, headers: {'Authorization': 'Bearer $_devToken'})
          .timeout(const Duration(seconds: 10));
      AuthSession.noteStatus(response.statusCode);
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  static String _contentTypeFor(String filename, [Uint8List? bytes]) {
    if (bytes != null && bytes.length >= 12) {
      final detected = detectImageMimeType(bytes);
      if (detected != null) return detected;
    }
    final lower = filename.toLowerCase();
    if (lower.endsWith('.png')) return 'image/png';
    if (lower.endsWith('.webp')) return 'image/webp';
    return 'image/jpeg';
  }

  /// Submits a guest garment photo for synchronous ephemeral observation
  /// (`POST /v1/analysis/garment/ephemeral`, D-01).
  Future<({Map<String, dynamic>? snapshot, String? failureReason})>
  submitGarmentEphemeralBytes(
    Uint8List bytes, {
    String filename = 'wardrobe_item.jpg',
  }) async {
    if (bytes.isEmpty) {
      debugPrint('Garment ephemeral refused empty image.');
      return (snapshot: null, failureReason: 'empty_image');
    }
    if (bytes.length > maxImageBytes) {
      debugPrint(
        'Garment ephemeral refused oversized image (${bytes.length} bytes).',
      );
      return (snapshot: null, failureReason: 'oversized_image');
    }
    try {
      final uri = Uri.parse('$_baseUrl/v1/analysis/garment/ephemeral');
      final request = http.MultipartRequest('POST', uri);
      request.files.add(
        http.MultipartFile.fromBytes(
          'image',
          bytes,
          filename: filename,
          contentType: MediaType.parse(_contentTypeFor(filename, bytes)),
        ),
      );
      final streamed = await _client.send(request).timeout(_timeout);
      final response = await http.Response.fromStream(
        streamed,
      ).timeout(_timeout);
      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return (snapshot: decoded, failureReason: null);
      }
      debugPrint(
        'Garment ephemeral responded ${response.statusCode}: ${response.body}',
      );
      return (snapshot: null, failureReason: _ephemeralFailureReason(response));
    } on TimeoutException {
      return (snapshot: null, failureReason: 'analyzer_timeout');
    } catch (error) {
      debugPrint('Garment ephemeral unreachable: $error');
      return (snapshot: null, failureReason: 'unreachable');
    }
  }

  static String _ephemeralFailureReason(http.Response response) {
    if (response.statusCode == 413) return 'oversized_image';
    if (response.statusCode == 429) return 'rate_limited';
    if (response.statusCode == 504) return 'analyzer_timeout';
    if (response.statusCode == 502 || response.statusCode == 503) {
      return 'service_unavailable';
    }
    try {
      final decoded = jsonDecode(response.body) as Map<String, dynamic>?;
      final error = decoded?['error'];
      if (error is Map<String, dynamic>) {
        final details = error['details'];
        if (details is Map<String, dynamic>) {
          final fieldErrors = details['field_errors'];
          if (fieldErrors is List && fieldErrors.isNotEmpty) {
            final first = fieldErrors.first;
            if (first is Map<String, dynamic>) {
              final reason = first['error'];
              if (reason is String && reason.isNotEmpty) return reason;
            }
          }
        }
        final message = error['message'];
        if (message is String && message.isNotEmpty) return message;
      }
    } catch (_) {}
    return 'request_failed';
  }

  void dispose() => _client.close();
}

/// Generates a fresh v4-style client idempotency key for one garment analysis attempt.
String newGarmentIdempotencyKey() {
  final random = Random.secure();
  final bytes = List<int>.generate(16, (_) => random.nextInt(256));
  bytes[6] = (bytes[6] & 0x0F) | 0x40;
  bytes[8] = (bytes[8] & 0x3F) | 0x80;
  String hex(int v) => v.toRadixString(16).padLeft(2, '0');
  final h = bytes.map(hex).join();
  return '${h.substring(0, 8)}-${h.substring(8, 12)}-'
      '${h.substring(12, 16)}-${h.substring(16, 20)}-${h.substring(20)}';
}
