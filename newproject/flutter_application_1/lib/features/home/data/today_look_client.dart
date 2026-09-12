import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'package:fansivibe/features/home/data/today_look_models.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';

/// HTTP client for the M9 Today's Look surface (STEP 19.25).
///
/// Endpoints: #31 `GET /v1/looks/today`, #32 `POST /v1/looks/today`
/// (`?seed=`), #33 `POST /v1/looks/today/save`.
///
/// Override the endpoint with `--dart-define=ASSISTANT_BASE_URL=...`.
/// Fetches never throw: 200 parses into [TodayLookResult.available], 404
/// into [TodayLookResult.noneAvailable] (truthful empty state), and every
/// other status or transport error into [TodayLookResult.failure] so the
/// caller renders its honest loading/error states — the flow never
/// fabricates a look when the server is unreachable, never shows fake
/// successful content offline, and never recalculates occasions locally.
/// IDs pass through verbatim; local numeric IDs are never submitted.
///
/// Save (#33) hardcodes `sourceContext: "daily"` and sends the TodayLook
/// response [snapshot] verbatim with a caller-provided `Idempotency-Key`
/// (one fresh key per save attempt via [newTodayLookIdempotencyKey]).
/// Nothing here inserts saved-look records, writes learning signals, or
/// logs wear events — the backend response is the source of truth.
class TodayLookClient {
  /// Creates a [TodayLookClient] with an optional client for testing.
  TodayLookClient({http.Client? client}) : _client = client ?? http.Client();

  /// Backend base URL.
  static const String baseUrl = String.fromEnvironment(
    'ASSISTANT_BASE_URL',
    defaultValue: 'http://localhost:8000',
  );

  static const String _devTokenDefault = String.fromEnvironment(
    'FANSIVIBE_DEV_TOKEN',
    defaultValue: 'dev',
  );

  /// Session-first Bearer token (D-AUTH-1): the persisted session wins;
  /// the dart-define default covers logged-out/test behavior.
  static String get _devToken => AuthSession.effectiveToken(_devTokenDefault);

  final http.Client _client;
  static const Duration _timeout = Duration(seconds: 12);

  Map<String, String> get _headers => {'Authorization': 'Bearer $_devToken'};

  Map<String, String> get _jsonHeaders => {
    'Authorization': 'Bearer $_devToken',
    'Content-Type': 'application/json; charset=UTF-8',
  };

  /// Derives today's look (#31 `GET /v1/looks/today`, read/derive only).
  ///
  /// Never throws. Repeated calls over unchanged inputs are deterministic
  /// server-side.
  Future<TodayLookResult> getTodayLook() async {
    try {
      final response = await _client
          .get(Uri.parse('$baseUrl/v1/looks/today'), headers: _headers)
          .timeout(_timeout);
      return _decodeLookResponse(response, operation: 'get today look');
    } catch (error) {
      debugPrint('TodayLook backend unreachable during fetch: $error');
      return const TodayLookResult.failure(TodayLookFailure.networkError);
    }
  }

  /// Derives a fresh today's look (#32 `POST /v1/looks/today`).
  ///
  /// [seed] is an opaque 1..200 selector sent as `?seed=` (absent → the
  /// winner; same seed repeats the backend result). The seed is passed
  /// through verbatim — never randomized here. Never throws. Persists
  /// nothing and is never keyed.
  Future<TodayLookResult> regenerateTodayLook({String? seed}) async {
    try {
      final uri = seed == null
          ? Uri.parse('$baseUrl/v1/looks/today')
          : Uri.parse(
              '$baseUrl/v1/looks/today?seed=${Uri.encodeQueryComponent(seed)}',
            );
      final response = await _client
          .post(uri, headers: _headers)
          .timeout(_timeout);
      return _decodeLookResponse(response, operation: 'regenerate today look');
    } catch (error) {
      debugPrint('TodayLook backend unreachable during regenerate: $error');
      return const TodayLookResult.failure(TodayLookFailure.networkError);
    }
  }

  /// Saves a derived TodayLook (#33 `POST /v1/looks/today/save`, via M7).
  ///
  /// Sends `sourceContext: "daily"` (always — never parameterized),
  /// [title] (backend requires 1..200), and [snapshot] — the TodayLook
  /// response body verbatim, including its backend-UUID `selectedItemIds`.
  /// [lookId] is omitted when null (the backend derives identity from the
  /// snapshot). [idempotencyKey] is required: one fresh key per save
  /// attempt (see [newTodayLookIdempotencyKey]); an empty key fails closed
  /// with no network call.
  ///
  /// Returns the saved record on 201, or null when the backend rejects
  /// the request, on conflict, or when unreachable — an error is never
  /// turned into a fake success. Never logs a wear event.
  Future<SavedTodayLook?> saveTodayLook({
    String? lookId,
    required String title,
    required Map<String, dynamic> snapshot,
    required String idempotencyKey,
  }) async {
    if (idempotencyKey.isEmpty) {
      debugPrint('TodayLook save refused: Idempotency-Key is required.');
      return null;
    }
    try {
      final payload = {
        if (lookId != null) 'lookId': lookId,
        'title': title,
        'sourceContext': 'daily',
        'snapshot': snapshot,
      };
      final response = await _client
          .post(
            Uri.parse('$baseUrl/v1/looks/today/save'),
            headers: {..._jsonHeaders, 'Idempotency-Key': idempotencyKey},
            body: jsonEncode(payload),
          )
          .timeout(_timeout);
      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 201) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return SavedTodayLook.fromJson(decoded);
      }
      debugPrint(
        'TodayLook save responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('TodayLook backend unreachable during save: $error');
    }
    return null;
  }

  TodayLookResult _decodeLookResponse(
    http.Response response, {
    required String operation,
  }) {
    if (response.statusCode == 200) {
      try {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return TodayLookResult.available(TodayLook.fromJson(decoded));
      } catch (error) {
        debugPrint('TodayLook $operation: malformed 200 body: $error');
        return const TodayLookResult.failure(TodayLookFailure.unknown);
      }
    }
    if (response.statusCode == 404) {
      return const TodayLookResult.noneAvailable();
    }
    final failure = _failureFor(response.statusCode);
    debugPrint(
      'TodayLook $operation responded ${response.statusCode}: ${response.body}',
    );
    return TodayLookResult.failure(failure);
  }

  TodayLookFailure _failureFor(int statusCode) {
    switch (statusCode) {
      case 401:
        AuthSession.notifyUnauthorized();
        return TodayLookFailure.unauthorized;
      case 422:
        return TodayLookFailure.invalidInput;
      case 429:
        return TodayLookFailure.rateLimited;
      case 503:
        return TodayLookFailure.serviceUnavailable;
      default:
        return TodayLookFailure.unknown;
    }
  }

  /// Closes the underlying HTTP client.
  void dispose() => _client.close();
}

/// Generates a fresh v4-style client idempotency key for one save attempt.
///
/// Mirrors `newOutfitIdempotencyKey()` (assistant) / `newWearIdempotencyKey()`
/// (wardrobe) without importing across features (feature-first boundary):
/// 122 random bits formatted as UUID text, no new dependency. The backend
/// remains authoritative for idempotency; Flutter only guarantees a fresh
/// key per new attempt — pass the same key to keep it stable across
/// retries of the SAME attempt.
String newTodayLookIdempotencyKey() {
  final random = Random.secure();
  final bytes = List<int>.generate(16, (_) => random.nextInt(256));
  bytes[6] = (bytes[6] & 0x0F) | 0x40;
  bytes[8] = (bytes[8] & 0x3F) | 0x80;
  String hex(int v) => v.toRadixString(16).padLeft(2, '0');
  final h = bytes.map(hex).join();
  return '${h.substring(0, 8)}-${h.substring(8, 12)}-'
      '${h.substring(12, 16)}-${h.substring(16, 20)}-${h.substring(20)}';
}
