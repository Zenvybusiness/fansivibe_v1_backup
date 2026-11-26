import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';

import 'package:fansivibe/core/config/app_config.dart';
import 'package:fansivibe/features/try_on/data/try_on_models.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';

/// HTTP client for the Fansivibe Virtual Try-On API (`/v1/tryon/*`).
///
/// Session-first Bearer auth (D-AUTH-1), client-side bounds mirroring the
/// backend contract, typed error parsing from FastAPI's `{"error": ...}`
/// envelope, and zero secret/image/signed-URL logging.
class TryOnClient {
  TryOnClient({http.Client? client, String? baseUrl})
      : _client = client ?? http.Client(),
        _baseUrl = baseUrl ?? AppConfig.apiBaseUrl;

  static const String baseUrl = AppConfig.apiBaseUrl;

  final String _baseUrl;

  static const String _devTokenDefault = String.fromEnvironment(
    'FANSIVIBE_DEV_TOKEN',
    defaultValue: 'dev',
  );

  static String get _devToken => AuthSession.effectiveToken(_devTokenDefault);

  /// Maximum general person image size (20 MB); Genlook caps at 10 MB.
  static const int maxImageBytes = 20 * 1024 * 1024;
  static const int genlookMaxImageBytes = 10 * 1024 * 1024;

  final http.Client _client;
  static const Duration _submitTimeout = Duration(seconds: 30);
  static const Duration _timeout = Duration(seconds: 12);

  Map<String, String> get _authHeaders => {
    'Authorization': 'Bearer $_devToken',
  };

  static String _contentTypeFor(String filename, [String? explicitMime]) {
    if (explicitMime != null &&
        (explicitMime == 'image/jpeg' ||
            explicitMime == 'image/png' ||
            explicitMime == 'image/webp')) {
      return explicitMime;
    }
    final lower = filename.toLowerCase();
    if (lower.endsWith('.png')) return 'image/png';
    if (lower.endsWith('.webp')) return 'image/webp';
    return 'image/jpeg';
  }

  static ({String? code, String? message}) _parseApiError(String body) {
    if (body.isEmpty) return (code: null, message: null);
    try {
      final decoded = jsonDecode(body);
      if (decoded is Map<String, dynamic>) {
        final err = decoded['error'];
        if (err is Map<String, dynamic>) {
          final code = err['code'] as String?;
          final msg = err['message'] as String?;
          final details = err['details'];
          if (details is Map<String, dynamic>) {
            final fieldErrors = details['field_errors'];
            if (fieldErrors is List && fieldErrors.isNotEmpty) {
              final first = fieldErrors.first;
              if (first is Map<String, dynamic>) {
                final field = first['field']?.toString() ?? '';
                final errText = first['error']?.toString() ?? '';
                if (errText.isNotEmpty) {
                  return (
                    code: code,
                    message: field.isNotEmpty ? '$field: $errText' : errText,
                  );
                }
              }
            }
          }
          return (code: code, message: msg);
        }
      }
    } catch (_) {}
    return (code: null, message: null);
  }

  static TryOnFailure _failureOf(int statusCode, [String? message]) {
    switch (statusCode) {
      case 401:
        return TryOnFailure.unauthorized;
      case 404:
        return TryOnFailure.notFound;
      case 409:
        return TryOnFailure.conflict;
      case 422:
        return TryOnFailure.invalidInput;
      case 429:
        final lower = (message ?? '').toLowerCase();
        if (lower.contains('daily') || lower.contains('quota')) {
          return TryOnFailure.quotaExceeded;
        }
        return TryOnFailure.rateLimited;
      case 503:
        return TryOnFailure.serviceUnavailable;
      case 504:
        return TryOnFailure.timeout;
      default:
        return TryOnFailure.unknown;
    }
  }

  /// Fetches backend try-on capabilities (`GET /v1/tryon/capabilities`).
  /// Returns null when the endpoint is unavailable (caller uses conservative fallback).
  Future<TryOnCapabilities?> getCapabilities() async {
    try {
      final response = await _client
          .get(
            Uri.parse('$_baseUrl/v1/tryon/capabilities'),
            headers: _authHeaders,
          )
          .timeout(_timeout);
      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body);
        if (decoded is Map<String, dynamic>) {
          return TryOnCapabilities.fromJson(decoded);
        }
      } else if (response.statusCode == 401) {
        AuthSession.notifyUnauthorized();
      }
    } catch (error) {
      debugPrint('TryOn capabilities unavailable: $error');
    }
    return null;
  }

  /// Submits one try-on job (`POST /v1/tryon/jobs`, 202 Accepted).
  Future<TryOnSubmitResult> submitMockTryOn({
    required Uint8List personBytes,
    String personFilename = 'tryon_person.jpg',
    String? personContentType,
    required String outfitSource,
    required List<String> garmentIds,
    String consentVersion = TryOnConsentVersion.current,
    required bool consentAccepted,
    required String idempotencyKey,
    int maxBytes = maxImageBytes,
  }) async {
    if (personBytes.isEmpty || personBytes.length > maxBytes) {
      debugPrint('TryOn submit refused image (${personBytes.length} bytes).');
      return const TryOnSubmitResult(
        failure: TryOnFailure.invalidInput,
        errorMessage: 'Selected photo is empty or exceeds the maximum file size.',
      );
    }
    if (idempotencyKey.isEmpty) {
      debugPrint('TryOn submit refused: Idempotency-Key is required.');
      return const TryOnSubmitResult(failure: TryOnFailure.invalidInput);
    }
    try {
      final mime = _contentTypeFor(personFilename, personContentType);
      final request = http.MultipartRequest(
        'POST',
        Uri.parse('$_baseUrl/v1/tryon/jobs'),
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
            contentType: MediaType.parse(mime),
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
        if (job != null) return TryOnSubmitResult(job: job, statusCode: 202);
        return const TryOnSubmitResult(
          failure: TryOnFailure.unknown,
          statusCode: 202,
        );
      }
      if (response.statusCode == 401) AuthSession.notifyUnauthorized();
      final parsedErr = _parseApiError(response.body);
      debugPrint(
        'TryOn submit responded ${response.statusCode} (${parsedErr.code ?? "unknown"}).',
      );
      return TryOnSubmitResult(
        failure: _failureOf(response.statusCode, parsedErr.message),
        errorCode: parsedErr.code,
        errorMessage: parsedErr.message,
        statusCode: response.statusCode,
      );
    } on TimeoutException catch (error) {
      debugPrint('TryOn submit timed out: $error');
      return const TryOnSubmitResult(
        failure: TryOnFailure.timeout,
        errorMessage:
            'Request timed out before confirmation. Tap Try Again to check or retry safely without creating a duplicate job.',
      );
    } catch (error) {
      debugPrint('TryOn backend unreachable during submit: $error');
      return const TryOnSubmitResult(failure: TryOnFailure.networkError);
    }
  }

  /// Polls one job and returns full status + HTTP failure distinction.
  Future<TryOnStatusOutcome> getJobStatusOutcome(String jobId) async {
    if (jobId.isEmpty) {
      return const TryOnStatusOutcome(failure: TryOnFailure.invalidInput);
    }
    try {
      final response = await _client
          .get(
            Uri.parse('$_baseUrl/v1/tryon/jobs/$jobId'),
            headers: _authHeaders,
          )
          .timeout(_timeout);
      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body);
        if (decoded is Map<String, dynamic>) {
          final parsed = TryOnJobStatus.fromJson(decoded);
          if (parsed != null) {
            return TryOnStatusOutcome(status: parsed, statusCode: 200);
          }
        }
        return const TryOnStatusOutcome(
          failure: TryOnFailure.unknown,
          statusCode: 200,
        );
      }
      if (response.statusCode == 401) AuthSession.notifyUnauthorized();
      final parsedErr = _parseApiError(response.body);
      return TryOnStatusOutcome(
        failure: _failureOf(response.statusCode, parsedErr.message),
        errorMessage: parsedErr.message,
        statusCode: response.statusCode,
      );
    } catch (error) {
      debugPrint('TryOn backend unreachable during poll: $error');
      return const TryOnStatusOutcome(failure: TryOnFailure.networkError);
    }
  }

  /// Polls one job. Null means transport/non-200 failure.
  Future<TryOnJobStatus?> getJobStatus(String jobId) async {
    final outcome = await getJobStatusOutcome(jobId);
    return outcome.status;
  }

  /// Fetches the generated image bytes with explicit status/failure info.
  Future<TryOnImageOutcome> getJobImageOutcome(String jobId) async {
    if (jobId.isEmpty) {
      return const TryOnImageOutcome(failure: TryOnFailure.invalidInput);
    }
    try {
      final response = await _client
          .get(
            Uri.parse('$_baseUrl/v1/tryon/jobs/$jobId/image'),
            headers: _authHeaders,
          )
          .timeout(_timeout);
      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 200) {
        return TryOnImageOutcome(
          bytes: response.bodyBytes,
          contentType: response.headers['content-type'],
          statusCode: 200,
        );
      }
      if (response.statusCode == 401) AuthSession.notifyUnauthorized();
      final parsedErr = _parseApiError(response.body);
      debugPrint('TryOn image responded ${response.statusCode}.');
      return TryOnImageOutcome(
        failure: _failureOf(response.statusCode, parsedErr.message),
        errorMessage: parsedErr.message,
        statusCode: response.statusCode,
      );
    } catch (error) {
      debugPrint('TryOn backend unreachable during image fetch: $error');
      return const TryOnImageOutcome(failure: TryOnFailure.networkError);
    }
  }

  /// Fetches the composite image bytes (completed jobs only).
  Future<Uint8List?> getJobImage(String jobId) async {
    final outcome = await getJobImageOutcome(jobId);
    return outcome.bytes;
  }

  /// Retries an eligible failed or cancelled try-on job.
  Future<TryOnSubmitResult> retryJob(String jobId) async {
    if (jobId.isEmpty) {
      return const TryOnSubmitResult(failure: TryOnFailure.invalidInput);
    }
    try {
      final response = await _client
          .post(
            Uri.parse('$_baseUrl/v1/tryon/jobs/$jobId/retry'),
            headers: _authHeaders,
          )
          .timeout(_submitTimeout);
      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 202) {
        final decoded = jsonDecode(response.body);
        final job = decoded is Map<String, dynamic>
            ? TryOnJob.fromJson(decoded)
            : null;
        if (job != null) return TryOnSubmitResult(job: job, statusCode: 202);
        return const TryOnSubmitResult(
          failure: TryOnFailure.unknown,
          statusCode: 202,
        );
      }
      if (response.statusCode == 401) AuthSession.notifyUnauthorized();
      final parsedErr = _parseApiError(response.body);
      return TryOnSubmitResult(
        failure: _failureOf(response.statusCode, parsedErr.message),
        errorCode: parsedErr.code,
        errorMessage: parsedErr.message,
        statusCode: response.statusCode,
      );
    } on TimeoutException catch (error) {
      debugPrint('TryOn retry timed out: $error');
      return const TryOnSubmitResult(
        failure: TryOnFailure.timeout,
        errorMessage:
            'Retry request timed out. Tap Try Again to safely re-check status.',
      );
    } catch (error) {
      debugPrint('TryOn backend unreachable during retry: $error');
      return const TryOnSubmitResult(failure: TryOnFailure.networkError);
    }
  }

  /// Cancels an in-progress try-on job.
  Future<TryOnJobStatus?> cancelJob(String jobId) async {
    if (jobId.isEmpty) return null;
    try {
      final response = await _client
          .post(
            Uri.parse('$_baseUrl/v1/tryon/jobs/$jobId/cancel'),
            headers: _authHeaders,
          )
          .timeout(_timeout);
      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body);
        if (decoded is Map<String, dynamic>) {
          return TryOnJobStatus.fromJson(decoded);
        }
      }
      if (response.statusCode == 401) AuthSession.notifyUnauthorized();
    } catch (error) {
      debugPrint('TryOn backend unreachable during cancel: $error');
    }
    return null;
  }

  /// Deletes a try-on job and associated media.
  Future<bool> deleteJob(String jobId) async {
    if (jobId.isEmpty) return false;
    try {
      final response = await _client
          .delete(
            Uri.parse('$_baseUrl/v1/tryon/jobs/$jobId'),
            headers: _authHeaders,
          )
          .timeout(_timeout);
      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 204 || response.statusCode == 200) {
        return true;
      }
      if (response.statusCode == 401) AuthSession.notifyUnauthorized();
    } catch (error) {
      debugPrint('TryOn backend unreachable during delete: $error');
    }
    return false;
  }
}
