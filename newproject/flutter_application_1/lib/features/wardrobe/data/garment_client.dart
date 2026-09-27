import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';

import 'package:fansivibe/core/config/app_config.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';

/// One polled garment-analysis run (`GET /v1/analysis/runs/{run_id}`).
class GarmentAnalysisRun {
  const GarmentAnalysisRun({required this.statusCode, this.data});

  final int statusCode;
  final Map<String, dynamic>? data;

  bool get isCompleted => data?['status'] == 'completed';
  bool get isFailed => data?['status'] == 'failed';

  /// Completed-run observation snapshot, or null.
  Map<String, dynamic>? get result =>
      data?['result'] as Map<String, dynamic>?;

  /// Persisted input-media metadata (key, mediaType, sizeBytes,
  /// contentHash, analyzer, uploadedAt) — the photo reference the
  /// wardrobe save persists as `imageRef`.
  Map<String, dynamic>? get inputMedia =>
      data?['input_media'] as Map<String, dynamic>?;

  /// Typed failure reason (`details.reason`: no_garment_detected,
  /// low_confidence, analyzer_unavailable, …), or null.
  String? get failureReason {
    final error = data?['error'] as Map<String, dynamic>?;
    final details = error?['details'] as Map<String, dynamic>?;
    return details?['reason'] as String?;
  }
}

/// HTTP client for the M11 garment-analysis surface.
///
/// `POST /v1/analysis/garment` (multipart image → 202 `{run_id}`), then
/// the existing run endpoint. Web-safe bytes upload (`fromBytes`, no
/// `dart:io`), same Bearer convention as every other client. Failures
/// return null — never a fabricated garment.
class GarmentClient {
  GarmentClient({http.Client? client, Duration? pollInterval})
    : _client = client ?? http.Client(),
      _pollInterval = pollInterval ?? const Duration(seconds: 1);

  /// Canonical base URL — single source of truth is [AppConfig.apiBaseUrl].
  static const String baseUrl = AppConfig.apiBaseUrl;

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
  // Phase 4A: 30s exceeds the backend 20s vision budget + overhead, so a
  // legitimate synchronous analysis never surfaces as a client timeout.
  static const Duration _timeout = Duration(seconds: 30);

  String? _activeIdempotencyKey;
  String? get activeIdempotencyKey => _activeIdempotencyKey;
  void resetIdempotencyKey() => _activeIdempotencyKey = null;

  /// Submits a garment photo for analysis.
  ///
  /// Returns the accepted `run_id` on 202, or null when the image is
  /// empty/oversized, the backend rejects it, or it is unreachable.
  Future<String?> submitGarmentAnalysisBytes(
    Uint8List bytes, {
    String filename = 'wardrobe_item.jpg',
    String? idempotencyKey,
  }) async {
    if (bytes.isEmpty || bytes.length > maxImageBytes) {
      debugPrint('Garment submit refused image (${bytes.length} bytes).');
      return null;
    }
    final effectiveKey =
        idempotencyKey ?? (_activeIdempotencyKey ??= newGarmentIdempotencyKey());
    try {
      final uri = Uri.parse('$baseUrl/v1/analysis/garment');
      final request = http.MultipartRequest('POST', uri)
        ..headers['Authorization'] = 'Bearer $_devToken'
        ..headers['Idempotency-Key'] = effectiveKey;
      request.files.add(
        http.MultipartFile.fromBytes(
          'image',
          bytes,
          filename: filename,
          contentType: MediaType.parse(_contentTypeFor(filename)),
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
        'Garment submit responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Garment backend unreachable during submit: $error');
    }
    return null;
  }

  /// Fetches one garment run (200 with data, other statuses bare, 0 when
  /// unreachable — never throws).
  Future<GarmentAnalysisRun> getGarmentRun({required String runId}) async {
    try {
      final response = await _client
          .get(
            Uri.parse('$baseUrl/v1/analysis/runs/$runId'),
            headers: {'Authorization': 'Bearer $_devToken'},
          )
          .timeout(_timeout);
      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>?;
        return GarmentAnalysisRun(statusCode: 200, data: decoded);
      }
      return GarmentAnalysisRun(statusCode: response.statusCode);
    } catch (error) {
      debugPrint('Garment backend unreachable during poll: $error');
      return const GarmentAnalysisRun(statusCode: 0);
    }
  }

  /// Polls until the run is completed/failed, the run disappears, or
  /// [attempts] exhaust. A terminal `failed` run returns promptly (never
  /// polled to exhaustion). Returns null when unreachable or timed out so
  /// the caller can offer a retry — retrying a timed-out poll is a fresh
  /// read, never a duplicate analysis.
  Future<GarmentAnalysisRun?> pollGarmentRun({
    required String runId,
    int attempts = 30,
  }) async {
    try {
      for (var attempt = 0; attempt < attempts; attempt++) {
        final run = await getGarmentRun(runId: runId);
        // Unreachable (0) and missing (404) stop promptly. A 401 also
        // stops: the session was already cleared via AuthSession.noteStatus
        // in getGarmentRun, so further polls are a doomed loop — the
        // caller surfaces its honest retry state instead.
        if (run.statusCode == 0 ||
            run.statusCode == 404 ||
            run.statusCode == 401) {
          return null;
        }
        if (run.isCompleted || run.isFailed) return run;
        await Future<void>.delayed(_pollInterval);
      }
    } catch (error) {
      debugPrint('Garment polling failed: $error');
    }
    return null;
  }

  static String _contentTypeFor(String filename) {
    final lower = filename.toLowerCase();
    if (lower.endsWith('.png')) return 'image/png';
    if (lower.endsWith('.webp')) return 'image/webp';
    return 'image/jpeg';
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
