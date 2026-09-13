import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'package:fansivibe/core/config/app_config.dart';
import 'package:fansivibe/features/feedback/data/feedback_models.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';

/// HTTP client for the M11 feedback surface (PHASE 2).
///
/// Endpoint: #35 `POST /v1/feedback` (UC-32).
///
/// Override the endpoint with `--dart-define=ASSISTANT_BASE_URL=...`.
/// Submits never throw: 201/204 map to [FeedbackResult.sent] (an
/// idempotent replay acks the same way), 409 to conflict, and every
/// other status or transport error to a typed failure so the caller
/// renders truthful feedback — the flow never claims a reaction landed
/// when the server is unreachable. IDs pass through verbatim; local
/// numeric IDs are never submitted.
///
/// [idempotencyKey] is required: one fresh key per reaction attempt
/// (see [newFeedbackIdempotencyKey]); an empty key fails closed with no
/// network call. Nothing here writes learning signals, marks styled
/// days, or logs wears — the backend response is the source of truth.
class FeedbackClient {
  /// Creates a [FeedbackClient] with an optional client for testing.
  FeedbackClient({http.Client? client}) : _client = client ?? http.Client();

  /// Backend base URL.
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

  /// Submits one reaction (#35 `POST /v1/feedback`, tier-1 append).
  ///
  /// Sends `rating` (tag string), optional `reason` free text, and at
  /// most one of `targetLookId` (catalog code) / `targetSavedLookId`
  /// (owned saved-look UUID) — nulls are omitted from the body.
  /// Never throws.
  Future<FeedbackResult> submitFeedback({
    required String rating,
    String? reason,
    String? targetLookId,
    String? targetSavedLookId,
    required String idempotencyKey,
  }) async {
    if (idempotencyKey.isEmpty) {
      debugPrint('Feedback submit refused: Idempotency-Key is required.');
      return const FeedbackResult.failure(FeedbackStatus.invalid);
    }
    try {
      final payload = <String, dynamic>{
        'rating': rating,
        if (reason != null) 'reason': reason,
        if (targetLookId != null) 'targetLookId': targetLookId,
        if (targetSavedLookId != null) 'targetSavedLookId': targetSavedLookId,
      };
      final response = await _client
          .post(
            Uri.parse('$baseUrl/v1/feedback'),
            headers: {
              'Authorization': 'Bearer $_devToken',
              'Content-Type': 'application/json; charset=UTF-8',
              'Idempotency-Key': idempotencyKey,
            },
            body: jsonEncode(payload),
          )
          .timeout(_timeout);
      if (response.statusCode == 201 || response.statusCode == 204) {
        return const FeedbackResult.sent();
      }
      debugPrint(
        'Feedback submit responded ${response.statusCode}: ${response.body}',
      );
      return FeedbackResult.failure(_failureFor(response.statusCode));
    } catch (error) {
      debugPrint('Feedback backend unreachable during submit: $error');
      return const FeedbackResult.failure(FeedbackStatus.networkError);
    }
  }

  FeedbackStatus _failureFor(int statusCode) {
    switch (statusCode) {
      case 401:
        AuthSession.notifyUnauthorized();
        return FeedbackStatus.unauthorized;
      case 409:
        return FeedbackStatus.conflict;
      case 422:
        return FeedbackStatus.invalid;
      case 429:
        return FeedbackStatus.rateLimited;
      default:
        return FeedbackStatus.unknown;
    }
  }

  /// Closes the underlying HTTP client.
  void dispose() => _client.close();
}

/// Generates a fresh v4-style client idempotency key for one reaction
/// attempt.
///
/// Mirrors the save/wear key helpers without importing across features
/// (feature-first boundary): 122 random bits formatted as UUID text, no
/// new dependency. The backend remains authoritative for idempotency;
/// Flutter only guarantees a fresh key per new attempt — pass the same
/// key to keep it stable across retries of the SAME attempt.
String newFeedbackIdempotencyKey() {
  final random = Random.secure();
  final bytes = List<int>.generate(16, (_) => random.nextInt(256));
  bytes[6] = (bytes[6] & 0x0F) | 0x40;
  bytes[8] = (bytes[8] & 0x3F) | 0x80;
  String hex(int v) => v.toRadixString(16).padLeft(2, '0');
  final h = bytes.map(hex).join();
  return '${h.substring(0, 8)}-${h.substring(8, 12)}-'
      '${h.substring(12, 16)}-${h.substring(16, 20)}-${h.substring(20)}';
}
