import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'package:fansivibe/core/config/app_config.dart';
import 'package:fansivibe/features/outfit_builder/data/outfit_models.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';

/// HTTP client for the M13 outfit builder surface (PHASE 2).
///
/// Endpoints: #41 `POST /v1/outfits/generate` (UC-28/29), #42
/// `POST /v1/outfits/saved` (UC-30, via M7).
///
/// Override the endpoint with `--dart-define=ASSISTANT_BASE_URL=...`.
/// Generation never throws: 200 parses into [OutfitResult.available],
/// 204 into [OutfitResult.noneAvailable] (truthful empty state), and
/// every other status or transport error into [OutfitResult.failure] so
/// the caller renders its honest loading/error states — the flow never
/// fabricates an outfit when the server is unreachable and never shows
/// fake successful content offline. IDs pass through verbatim; local
/// numeric IDs are never submitted.
///
/// Save (#42) hardcodes `sourceContext: "outfit"` and sends the outfit
/// response [snapshot] verbatim with a caller-provided `Idempotency-Key`
/// (one fresh key per save attempt via
/// [newOutfitBuilderIdempotencyKey]). Nothing here inserts saved-look
/// records, writes learning signals, or logs wear events — the backend
/// response is the source of truth.
class OutfitBuilderClient {
  /// Creates an [OutfitBuilderClient] with an optional client for testing.
  OutfitBuilderClient({http.Client? client})
    : _client = client ?? http.Client();

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

  Map<String, String> get _jsonHeaders => {
    'Authorization': 'Bearer $_devToken',
    'Content-Type': 'application/json; charset=UTF-8',
  };

  /// Derives one outfit (#41 `POST /v1/outfits/generate`, read/derive
  /// only, TRX-2).
  ///
  /// [seed] is the opaque UC-29 variety selector sent in the request
  /// body (absent → the winner; same seed repeats the backend result).
  /// The seed is passed through verbatim — never randomized here.
  /// Never throws. Persists nothing and is never keyed.
  Future<OutfitResult> generateOutfit({
    required String occasion,
    required String mood,
    required String fit,
    required String colorPalette,
    String? seed,
  }) async {
    try {
      final payload = <String, dynamic>{
        'occasion': occasion,
        'mood': mood,
        'fit': fit,
        'colorPalette': colorPalette,
        if (seed != null) 'seed': seed,
      };
      final response = await _client
          .post(
            Uri.parse('$baseUrl/v1/outfits/generate'),
            headers: _jsonHeaders,
            body: jsonEncode(payload),
          )
          .timeout(_timeout);
      if (response.statusCode == 200) {
        try {
          final decoded = jsonDecode(response.body) as Map<String, dynamic>;
          return OutfitResult.available(OutfitRecommendation.fromJson(decoded));
        } catch (error) {
          debugPrint('Outfit generate: malformed 200 body: $error');
          return const OutfitResult.failure(OutfitFailure.unknown);
        }
      }
      if (response.statusCode == 204) {
        // M11 P4: verbatim backend reason, never inferred locally.
        // Missing header (older backend) → null → generic empty copy.
        return OutfitResult.noneAvailable(
          emptyReason: response.headers['x-outfit-empty-reason'],
        );
      }
      debugPrint(
        'Outfit generate responded ${response.statusCode}: ${response.body}',
      );
      return OutfitResult.failure(_failureFor(response.statusCode));
    } catch (error) {
      debugPrint('Outfit backend unreachable during generate: $error');
      return const OutfitResult.failure(OutfitFailure.networkError);
    }
  }

  /// Freezes one derived outfit (#42 `POST /v1/outfits/saved`, via M7).
  ///
  /// Sends `sourceContext: "outfit"` (always — never parameterized),
  /// [title] (backend requires 1..200), and [snapshot] — the outfit
  /// response body verbatim, including its backend-UUID component IDs.
  /// [lookId] is omitted when null (outfit saves carry no catalog
  /// identity). [idempotencyKey] is required: one fresh key per save
  /// attempt (see [newOutfitBuilderIdempotencyKey]); an empty key fails
  /// closed with no network call.
  ///
  /// Returns the saved record on 201, or null when the backend rejects
  /// the request, on conflict, or when unreachable — an error is never
  /// turned into a fake success. Never logs a wear event.
  Future<SavedOutfit?> saveOutfit({
    String? lookId,
    required String title,
    required Map<String, dynamic> snapshot,
    required String idempotencyKey,
  }) async {
    if (idempotencyKey.isEmpty) {
      debugPrint('Outfit save refused: Idempotency-Key is required.');
      return null;
    }
    try {
      final payload = {
        if (lookId != null) 'lookId': lookId,
        'title': title,
        'sourceContext': 'outfit',
        'snapshot': snapshot,
      };
      final response = await _client
          .post(
            Uri.parse('$baseUrl/v1/outfits/saved'),
            headers: {..._jsonHeaders, 'Idempotency-Key': idempotencyKey},
            body: jsonEncode(payload),
          )
          .timeout(_timeout);
      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 201) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return SavedOutfit.fromJson(decoded);
      }
      debugPrint(
        'Outfit save responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Outfit backend unreachable during save: $error');
    }
    return null;
  }

  OutfitFailure _failureFor(int statusCode) {
    switch (statusCode) {
      case 401:
        AuthSession.notifyUnauthorized();
        return OutfitFailure.unauthorized;
      case 422:
        return OutfitFailure.invalidInput;
      case 429:
        return OutfitFailure.rateLimited;
      case 503:
        return OutfitFailure.serviceUnavailable;
      default:
        return OutfitFailure.unknown;
    }
  }

  /// Closes the underlying HTTP client.
  void dispose() => _client.close();
}

/// Generates a fresh v4-style client idempotency key for one outfit save
/// attempt.
///
/// Mirrors the assistant/wardrobe/today key helpers without importing
/// across features (feature-first boundary): 122 random bits formatted
/// as UUID text, no new dependency. The backend remains authoritative
/// for idempotency; Flutter only guarantees a fresh key per new
/// attempt — pass the same key to keep it stable across retries of the
/// SAME attempt.
String newOutfitBuilderIdempotencyKey() {
  final random = Random.secure();
  final bytes = List<int>.generate(16, (_) => random.nextInt(256));
  bytes[6] = (bytes[6] & 0x0F) | 0x40;
  bytes[8] = (bytes[8] & 0x3F) | 0x80;
  String hex(int v) => v.toRadixString(16).padLeft(2, '0');
  final h = bytes.map(hex).join();
  return '${h.substring(0, 8)}-${h.substring(8, 12)}-'
      '${h.substring(12, 16)}-${h.substring(16, 20)}-${h.substring(20)}';
}
