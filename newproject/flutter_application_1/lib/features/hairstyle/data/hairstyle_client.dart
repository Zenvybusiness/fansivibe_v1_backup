import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';

import 'package:fansivibe/core/config/app_config.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_models.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';

/// HTTP client for the hairstyle recommendation API.
///
/// Override the endpoint with `--dart-define=ASSISTANT_BASE_URL=...`.
/// On failure it returns null so the caller can fall back to the offline
/// result — the flow never breaks when the server is unreachable.
class HairstyleClient {
  HairstyleClient({http.Client? client, Duration? pollInterval})
    : _client = client ?? http.Client(),
      _pollInterval = pollInterval ?? const Duration(milliseconds: 600);

  /// Canonical base URL — single source of truth is [AppConfig.apiBaseUrl].
  static const String baseUrl = AppConfig.apiBaseUrl;

  static const String _devTokenDefault = String.fromEnvironment(
    'FANSIVIBE_DEV_TOKEN',
    defaultValue: 'dev',
  );

  /// Session-first Bearer token (D-AUTH-1): the persisted session wins;
  /// the dart-define default covers logged-out/test behavior.
  static String get _devToken => AuthSession.effectiveToken(_devTokenDefault);

  final http.Client _client;
  static const Duration _timeout = Duration(seconds: 12);
  final Duration _pollInterval;

  /// Submits a hairstyle analysis, either for the authenticated user's
  /// stored style profile (profile-only pass, no request field) or for a
  /// real captured/selected image — never both at the transport level.
  ///
  /// Image upload sends the actual file bytes as a real multipart `image`
  /// part (`POST /v1/analysis/hairstyle`, `multipart/form-data`), never as a
  /// string/path field. The profile-only pass sends an empty multipart body
  /// (no fields); the backend resolves the authenticated user's
  /// `style_profile` by `user_id` (Phase 28: no face-profile reference).
  /// The backend remains authoritative for media
  /// validation (JPEG/PNG/WebP, 20 MB max, content checks); this client only
  /// derives the part content type from the filename for transport.
  ///
  /// Returns the submitted run id, or null when the backend is unreachable
  /// or rejects the request.
  Future<String?> submitHairstyleAnalysis({
    Uint8List? imageBytes,
    String? imageFilename,
    String? imageContentType,
  }) async {
    final bytes = imageBytes;
    if (bytes != null && bytes.isEmpty) {
      debugPrint('Hairstyle submit refused empty image bytes.');
      return null;
    }
    try {
      final request =
          http.MultipartRequest(
              'POST',
              Uri.parse('$baseUrl/v1/analysis/hairstyle'),
            )
            ..headers['Authorization'] = 'Bearer $_devToken';
      if (bytes != null) {
        final filename = imageFilename ?? 'face_scan.jpg';
        final contentType =
            imageContentType ?? _contentTypeForFilename(filename);
        request.files.add(
          http.MultipartFile.fromBytes(
            'image',
            bytes,
            filename: filename,
            contentType: MediaType.parse(contentType),
          ),
        );
      }
      // Profile-only pass: empty multipart body; backend resolves the
      // authenticated user's style_profile by user_id (no reference field).

      final streamed = await _client.send(request).timeout(_timeout);
      final response = await http.Response.fromStream(
        streamed,
      ).timeout(_timeout);

      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 202) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return decoded['run_id'] as String?;
      }
      debugPrint(
        'Hairstyle submit responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Hairstyle backend unreachable during submit: $error');
    }
    return null;
  }

  /// Derives the multipart part content type from the filename extension.
  ///
  /// Transport hint only — the backend validates the actual media type and
  /// content authoritatively.
  static String _contentTypeForFilename(String filename) {
    final lower = filename.toLowerCase();
    if (lower.endsWith('.png')) return 'image/png';
    if (lower.endsWith('.webp')) return 'image/webp';
    return 'image/jpeg';
  }

  /// Fetches an analysis run and polls until it is completed, failed, or times out.
  ///
  /// A terminal `failed` run is returned promptly (never polled to exhaustion)
  /// so the caller can surface the error instead of waiting. Returns the
  /// completed/failed run, or null when unreachable.
  Future<AnalysisRun?> pollAnalysisRun({required String runId}) async {
    try {
      for (var attempt = 0; attempt < 30; attempt++) {
        final run = await getAnalysisRun(runId: runId);
        if (run == null) {
          return null;
        }
        if (run.isCompleted || run.isFailed) {
          return run;
        }
        await Future<void>.delayed(_pollInterval);
      }
    } catch (error) {
      debugPrint('Hairstyle polling failed: $error');
    }
    return null;
  }

  Future<AnalysisRun?> getAnalysisRun({required String runId}) async {
    try {
      final response = await _client
          .get(
            Uri.parse('$baseUrl/v1/analysis/runs/$runId'),
            headers: {'Authorization': 'Bearer $_devToken'},
          )
          .timeout(_timeout);
      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return AnalysisRun.fromJson(decoded);
      }
      debugPrint(
        'Hairstyle fetch responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Hairstyle backend unreachable during fetch: $error');
    }
    return null;
  }

  /// Lists completed analysis runs (summary rows — no `result`).
  ///
  /// Returns null when the backend is unreachable.
  Future<AnalysisRunPage?> listRuns() async {
    try {
      final response = await _client
          .get(
            Uri.parse('$baseUrl/v1/analysis/runs'),
            headers: {'Authorization': 'Bearer $_devToken'},
          )
          .timeout(_timeout);
      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return AnalysisRunPage.fromJson(decoded);
      }
      debugPrint(
        'Hairstyle list responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Hairstyle backend unreachable during list: $error');
    }
    return null;
  }

  /// Saves a look with an idempotency key so retries never duplicate.
  ///
  /// Returns true when the save succeeded.
  Future<bool> saveLook({
    required String lookId,
    required String title,
    required Map<String, dynamic> snapshot,
    required String idempotencyKey,
  }) async {
    try {
      final payload = {
        'lookId': lookId,
        'title': title,
        'sourceContext': 'hairstyle',
        'snapshot': snapshot,
      };
      final response = await _client
          .post(
            Uri.parse('$baseUrl/v1/looks/saved'),
            headers: {
              'Content-Type': 'application/json; charset=UTF-8',
              'Authorization': 'Bearer $_devToken',
              'Idempotency-Key': idempotencyKey,
            },
            body: jsonEncode(payload),
          )
          .timeout(_timeout);
      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 201) {
        return true;
      }
      debugPrint(
        'Hairstyle save responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Hairstyle backend unreachable during save: $error');
    }
    return false;
  }

  /// Lists the user's saved looks (endpoint #24 `GET /v1/looks/saved`).
  ///
  /// Returns null when the backend is unreachable, matching the graceful
  /// null-on-failure pattern used elsewhere in this client.
  Future<SavedLookPage?> listSavedLooks({int page = 1, int pageSize = 50}) async {
    try {
      final response = await _client
          .get(
            Uri.parse('$baseUrl/v1/looks/saved?page=$page&page_size=$pageSize'),
            headers: {'Authorization': 'Bearer $_devToken'},
          )
          .timeout(_timeout);
      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return SavedLookPage.fromJson(decoded);
      }
      debugPrint(
        'Hairstyle list saved looks responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Hairstyle backend unreachable during saved-looks list: $error');
    }
    return null;
  }

  void dispose() => _client.close();
}
