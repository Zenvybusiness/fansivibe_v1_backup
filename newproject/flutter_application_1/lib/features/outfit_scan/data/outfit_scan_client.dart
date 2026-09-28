import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';
import 'package:image_picker/image_picker.dart';

import 'package:fansivibe/core/config/app_config.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';

/// Response payload from an analysis run query.
class OutfitAnalysisRunResult {
  const OutfitAnalysisRunResult({
    required this.statusCode,
    this.data,
  });

  final int statusCode;
  final Map<String, dynamic>? data;

  bool get isCompleted => data?['status'] == 'completed';
  bool get isFailed => data?['status'] == 'failed';
  /// Human-readable failure detail, or null.
  ///
  /// Map-safe: backend `failed` runs carry a structured error
  /// (`{code, message, details: {reason}}`), mirroring
  /// `GarmentAnalysisRun.failureReason` — the typed `details.reason`
  /// wins, then `message`. A legacy plain-string error passes through.
  /// Non-string/non-map values yield null (never a crash, never a fake).
  String? get error {
    final raw = data?['error'];
    if (raw is String) return raw;
    if (raw is Map<String, dynamic>) {
      final details = raw['details'];
      if (details is Map<String, dynamic>) {
        final reason = details['reason'];
        if (reason is String) return reason;
      }
      final message = raw['message'];
      if (message is String) return message;
    }
    return null;
  }
}

/// Canonical API client for Outfit Scan operations.
class OutfitScanClient {
  OutfitScanClient({http.Client? client}) : _client = client ?? http.Client();

  /// Canonical base URL — single source of truth is [AppConfig.apiBaseUrl].
  static const String baseUrl = AppConfig.apiBaseUrl;

  static const String _devTokenDefault = String.fromEnvironment(
    'FANSIVIBE_DEV_TOKEN',
    defaultValue: 'dev',
  );

  /// Session-first Bearer token (D-AUTH-1): the persisted session wins;
  /// the dart-define default covers logged-out/test behavior.
  static String get devToken => AuthSession.effectiveToken(_devTokenDefault);

  final http.Client _client;
  // Phase 4A: 30s exceeds the backend 20s vision budget + overhead, so a
  // legitimate synchronous analysis never surfaces as a client timeout.
  static const Duration _timeout = Duration(seconds: 30);

  String? _activeIdempotencyKey;
  String? get activeIdempotencyKey => _activeIdempotencyKey;
  void resetIdempotencyKey() => _activeIdempotencyKey = null;

  /// Submits an outfit image for analysis (`POST /v1/analysis/outfit`).
  ///
  /// Web-safe: takes a cross-platform [XFile] (camera, gallery, or picked
  /// file) and uploads its bytes via multipart `fromBytes` — no `dart:io`
  /// `File` or `Platform` usage, so Chrome Web works from localhost
  /// (browser camera permission via `camera_web` / file input). Mobile
  /// behavior is preserved (`XFile` works on Android/iOS).
  ///
  /// Returns the accepted [run_id] on 202, or null when the backend rejects
  /// or is unreachable.
  Future<String?> submitOutfitAnalysis(
    XFile imageFile, {
    String? idempotencyKey,
  }) async {
    try {
      final bytes = await imageFile.readAsBytes();
      final filename = imageFile.name.isNotEmpty
          ? imageFile.name
          : 'outfit_scan.jpg';
      return await submitOutfitAnalysisBytes(
        bytes,
        filename: filename,
        idempotencyKey: idempotencyKey,
      );
    } catch (error) {
      debugPrint('Outfit scan backend unreachable during submit: $error');
      return null;
    }
  }

  /// Web-safe bytes upload (used by [submitOutfitAnalysis] and directly
  /// by callers holding in-memory bytes, e.g. camera capture on Web).
  Future<String?> submitOutfitAnalysisBytes(
    Uint8List bytes, {
    String filename = 'outfit_scan.jpg',
    String? idempotencyKey,
  }) async {
    if (bytes.isEmpty) {
      debugPrint('Outfit scan submit refused empty image bytes.');
      return null;
    }
    final effectiveKey =
        idempotencyKey ?? (_activeIdempotencyKey ??= newOutfitScanIdempotencyKey());
    try {
      final uri = Uri.parse('$baseUrl/v1/analysis/outfit');
      final request = http.MultipartRequest('POST', uri)
        ..headers['Authorization'] = 'Bearer $devToken'
        ..headers['Idempotency-Key'] = effectiveKey;

      final contentType = _contentTypeForFilename(filename);

      request.files.add(
        http.MultipartFile.fromBytes(
          'image',
          bytes,
          filename: filename,
          contentType: MediaType.parse(contentType),
        ),
      );

      final streamed = await _client.send(request).timeout(_timeout);
      final response =
          await http.Response.fromStream(streamed).timeout(_timeout);

      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 202) {
        _activeIdempotencyKey = null;
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return decoded['run_id'] as String?;
      }
      debugPrint(
        'Outfit scan submit responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Outfit scan backend unreachable during submit: $error');
    }
    return null;
  }

  /// Polls the analysis run status (`GET /v1/analysis/runs/{run_id}`).
  ///
  /// Returns an [OutfitAnalysisRunResult] with the status code and decoded data.
  Future<OutfitAnalysisRunResult> getAnalysisRun(String runId) async {
    try {
      final uri = Uri.parse('$baseUrl/v1/analysis/runs/$runId');
      final response = await _client
          .get(
            uri,
            headers: {'Authorization': 'Bearer $devToken'},
          )
          .timeout(_timeout);

      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>?;
        return OutfitAnalysisRunResult(
          statusCode: 200,
          data: decoded,
        );
      }
      return OutfitAnalysisRunResult(statusCode: response.statusCode);
    } catch (error) {
      debugPrint('Outfit scan backend unreachable during poll: $error');
      return const OutfitAnalysisRunResult(statusCode: 0);
    }
  }

  static String _contentTypeForFilename(String filename) {
    final lower = filename.toLowerCase();
    if (lower.endsWith('.png')) return 'image/png';
    if (lower.endsWith('.webp')) return 'image/webp';
    return 'image/jpeg';
  }

  /// Submits a guest image for synchronous ephemeral analysis
  /// (`POST /v1/analysis/outfit/ephemeral`, D-01).
  ///
  /// Guest-only transport: NO `Authorization` header (the endpoint is
  /// unauthenticated), NO `Idempotency-Key` (no run row exists to
  /// deduplicate), NO `user_id` field. Returns the engine snapshot
  /// verbatim on 200 — the same map shape the analysis screen already
  /// renders — never a run id. The snapshot's `sourceRunId` is a
  /// transient correlation id (callers must strip it before any
  /// authenticated save).
  Future<({Map<String, dynamic>? snapshot, String? failureReason})>
  submitOutfitEphemeralBytes(
    Uint8List bytes, {
    String filename = 'outfit_scan.jpg',
  }) async {
    if (bytes.isEmpty) {
      debugPrint('Outfit ephemeral refused empty image bytes.');
      return (snapshot: null, failureReason: 'empty_image');
    }
    try {
      final uri = Uri.parse('$baseUrl/v1/analysis/outfit/ephemeral');
      final request = http.MultipartRequest('POST', uri);

      final contentType = _contentTypeForFilename(filename);

      request.files.add(
        http.MultipartFile.fromBytes(
          'image',
          bytes,
          filename: filename,
          contentType: MediaType.parse(contentType),
        ),
      );

      final streamed = await _client.send(request).timeout(_timeout);
      final response =
          await http.Response.fromStream(streamed).timeout(_timeout);

      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return (snapshot: decoded, failureReason: null);
      }
      debugPrint(
        'Outfit ephemeral responded ${response.statusCode}: ${response.body}',
      );
      return (
        snapshot: null,
        failureReason: _ephemeralFailureReason(response),
      );
    } catch (error) {
      debugPrint('Outfit ephemeral unreachable: $error');
      return (snapshot: null, failureReason: 'unreachable');
    }
  }

  /// Maps an ephemeral failure response to a stable reason string.
  ///
  /// 429/503 keep their transport meaning; a 422 surfaces the backend's
  /// typed field reason verbatim. Unknown shapes degrade to
  /// `request_failed` — never a crash, never a fake result.
  static String _ephemeralFailureReason(http.Response response) {
    if (response.statusCode == 429) return 'rate_limited';
    if (response.statusCode == 503) return 'service_unavailable';
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
}

/// Generates a fresh v4-style client idempotency key for one outfit analysis attempt.
String newOutfitScanIdempotencyKey() {
  final random = Random.secure();
  final bytes = List<int>.generate(16, (_) => random.nextInt(256));
  bytes[6] = (bytes[6] & 0x0F) | 0x40;
  bytes[8] = (bytes[8] & 0x3F) | 0x80;
  String hex(int v) => v.toRadixString(16).padLeft(2, '0');
  final h = bytes.map(hex).join();
  return '${h.substring(0, 8)}-${h.substring(8, 12)}-'
      '${h.substring(12, 16)}-${h.substring(16, 20)}-${h.substring(20)}';
}
