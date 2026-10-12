import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';

import 'package:fansivibe/core/config/app_config.dart';
import 'package:fansivibe/features/try_on/data/try_on_models.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';

/// HTTP client for the Stage F0 mock try-on surface.
///
/// Endpoints: `POST /v1/tryon/jobs` (multipart person photo + outfit
/// refs, 202), `GET /v1/tryon/jobs/{id}` (poll), `GET
/// /v1/tryon/jobs/{id}/image` (mock SVG bytes).
///
/// Same conventions as the garment client: session-first Bearer token,
/// 20 MB client-side guard mirroring the backend contract, 30s timeout
/// for the multipart submit, 12s for polls/reads. Calls never throw —
/// result objects let the caller render honest states. The client never
/// talks to a real AI provider (DEC-003): `mock` is the only provider
/// in F0 and every response is labelled test data.
class TryOnClient {
  TryOnClient({http.Client? client}) : _client = client ?? http.Client();

  static const String baseUrl = AppConfig.apiBaseUrl;

  static const String _devTokenDefault = String.fromEnvironment(
    'FANSIVIBE_DEV_TOKEN',
    defaultValue: 'dev',
  );

  /// Session-first Bearer token (D-AUTH-1).
  static String get _devToken => AuthSession.effectiveToken(_devTokenDefault);

  /// Client-side size guard mirroring the backend 20 MB contract.
  static const int maxImageBytes = 20 * 1024 * 1024;

  final http.Client _client;
  static const Duration _submitTimeout = Duration(seconds: 30);
  static const Duration _timeout = Duration(seconds: 12);

  Map<String, String> get _authHeaders => {
    'Authorization': 'Bearer $_devToken',
  };

  static String _contentTypeFor(String filename) {
    final lower = filename.toLowerCase();
    if (lower.endsWith('.png')) return 'image/png';
    if (lower.endsWith('.webp')) return 'image/webp';
    return 'image/jpeg';
  }

  static TryOnFailure _failureOf(int statusCode) {
    switch (statusCode) {
      case 401:
        return TryOnFailure.unauthorized;
      case 422:
        return TryOnFailure.invalidInput;
      case 429:
        return TryOnFailure.quotaExceeded;
      case 503:
        return TryOnFailure.serviceUnavailable;
      default:
        return TryOnFailure.unknown;
    }
  }

  /// Submits one mock try-on job.
  ///
  /// [garmentIds] are labels only (the backend cannot retrieve wardrobe
  /// pixels — audit finding); the person photo is hashed and discarded
  /// server-side. One network call maps to one [TryOnSubmitResult]:
  /// accepted job on 202, typed failure on rejection, null job + null
  /// failure on transport failure (caller shows the network state).
  Future<TryOnSubmitResult> submitMockTryOn({
    required Uint8List personBytes,
    String personFilename = 'tryon_person.jpg',
    required String outfitSource,
    required List<String> garmentIds,
    String consentVersion = TryOnConsentVersion.current,
    required bool consentAccepted,
    required String idempotencyKey,
  }) async {
    if (personBytes.isEmpty || personBytes.length > maxImageBytes) {
      debugPrint('TryOn submit refused image (${personBytes.length} bytes).');
      return const TryOnSubmitResult(failure: TryOnFailure.invalidInput);
    }
    if (idempotencyKey.isEmpty) {
      debugPrint('TryOn submit refused: Idempotency-Key is required.');
      return const TryOnSubmitResult(failure: TryOnFailure.invalidInput);
    }
    try {
      final request = http.MultipartRequest(
        'POST',
        Uri.parse('$baseUrl/v1/tryon/jobs'),
      )
        ..headers['Authorization'] = 'Bearer $_devToken'
        ..headers['Idempotency-Key'] = idempotencyKey
        ..fields['outfit_source'] = outfitSource
        ..fields['garment_ids'] = jsonEncode(garmentIds)
        ..fields['consent_version'] = consentVersion
        ..fields['consent_accepted'] = consentAccepted.toString()
        ..files.add(
          http.MultipartFile.fromBytes(
            'person_image',
            personBytes,
            filename: personFilename,
            contentType: MediaType.parse(_contentTypeFor(personFilename)),
          ),
        );
      final streamed = await _client.send(request).timeout(_submitTimeout);
      final response = await http.Response.fromStream(
        streamed,
      ).timeout(_submitTimeout);
      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 202) {
        final decoded = jsonDecode(response.body);
        final job = decoded is Map<String, dynamic>
            ? TryOnJob.fromJson(decoded)
            : null;
        if (job != null) return TryOnSubmitResult(job: job);
        return const TryOnSubmitResult(failure: TryOnFailure.unknown);
      }
      if (response.statusCode == 401) AuthSession.notifyUnauthorized();
      debugPrint(
        'TryOn submit responded ${response.statusCode}: ${response.body}',
      );
      return TryOnSubmitResult(failure: _failureOf(response.statusCode));
    } catch (error) {
      debugPrint('TryOn backend unreachable during submit: $error');
      return const TryOnSubmitResult();
    }
  }

  /// Polls one mock job. Null means "still unknown" (transport failure
  /// or unparseable body) — the caller keeps polling or shows retry.
  Future<TryOnJobStatus?> getJobStatus(String jobId) async {
    if (jobId.isEmpty) return null;
    try {
      final response = await _client
          .get(
            Uri.parse('$baseUrl/v1/tryon/jobs/$jobId'),
            headers: _authHeaders,
          )
          .timeout(_timeout);
      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body);
        if (decoded is Map<String, dynamic>) {
          return TryOnJobStatus.fromJson(decoded);
        }
      } else if (response.statusCode == 401) {
        AuthSession.notifyUnauthorized();
      }
    } catch (error) {
      debugPrint('TryOn backend unreachable during poll: $error');
    }
    return null;
  }

  /// Fetches the mock composite bytes (completed jobs only). The bytes
  /// are a labelled SVG — test data, never AI output.
  Future<Uint8List?> getJobImage(String jobId) async {
    if (jobId.isEmpty) return null;
    try {
      final response = await _client
          .get(
            Uri.parse('$baseUrl/v1/tryon/jobs/$jobId/image'),
            headers: _authHeaders,
          )
          .timeout(_timeout);
      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 200) return response.bodyBytes;
      if (response.statusCode == 401) AuthSession.notifyUnauthorized();
      debugPrint('TryOn image responded ${response.statusCode}.');
    } catch (error) {
      debugPrint('TryOn backend unreachable during image fetch: $error');
    }
    return null;
  }
}
