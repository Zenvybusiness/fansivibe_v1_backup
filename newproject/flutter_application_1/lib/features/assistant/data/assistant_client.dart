import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'package:fansivibe/features/assistant/data/models.dart';

/// HTTP client for the Fansivibe AI backend.
///
/// Override the endpoint with `--dart-define=ASSISTANT_BASE_URL=...`.
/// On failure it returns null so the caller can fall back to the offline
/// assistant — the app never breaks when the server is unreachable.
class AssistantClient {
  AssistantClient({http.Client? client}) : _client = client ?? http.Client();

  static const String baseUrl = String.fromEnvironment(
    'ASSISTANT_BASE_URL',
    defaultValue: 'http://localhost:8000',
  );

  final http.Client _client;
  static const Duration _timeout = Duration(seconds: 12);

  static const String _devToken = String.fromEnvironment(
    'FANSIVIBE_DEV_TOKEN',
    defaultValue: 'dev',
  );

  Map<String, String> get _authJsonHeaders => const {
    'Content-Type': 'application/json; charset=UTF-8',
    'Authorization': 'Bearer $_devToken',
  };

  Future<AssistantReply?> chat({
    required List<AssistantMessage> history,
    required AssistantUserContext context,
  }) async {
    try {
      final payload = {
        'messages': history
            .map((m) => {'role': m.role, 'content': m.text})
            .toList(),
        'user': context.toJson(),
      };
      final response = await _client
          .post(
            Uri.parse('$baseUrl/v1/assistant/chat'),
            headers: const {'Content-Type': 'application/json; charset=UTF-8'},
            body: jsonEncode(payload),
          )
          .timeout(_timeout);

      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return AssistantReply.fromJson(decoded);
      }
      debugPrint(
        'Assistant backend responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Assistant backend unreachable: $error');
    }
    return null;
  }

  /// Saves an Outfit via the existing contract `POST /v1/looks/saved`.
  ///
  /// Sends `lookId: null`, `title`, `snapshot`, `sourceContext: "outfit"`
  /// with the caller-provided [idempotencyKey] as the `Idempotency-Key`
  /// header. Returns the saved record on 200/201, null otherwise so the
  /// caller can leave the outfit unsaved and allow a retry.
  Future<SavedOutfitLook?> saveOutfitLook({
    required OutfitSaveRequest request,
    required String idempotencyKey,
  }) async {
    try {
      final response = await _client
          .post(
            Uri.parse('$baseUrl/v1/looks/saved'),
            headers: {
              'Content-Type': 'application/json; charset=UTF-8',
              'Idempotency-Key': idempotencyKey,
            },
            body: jsonEncode(request.toJson()),
          )
          .timeout(_timeout);

      if (response.statusCode == 200 || response.statusCode == 201) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        final dynamic nested =
            decoded['savedLook'] ?? decoded['saved_look'] ?? decoded['data'];
        final Map<String, dynamic> payload = nested is Map<String, dynamic>
            ? nested
            : nested is Map
            ? Map<String, dynamic>.from(nested)
            : decoded;
        return SavedOutfitLook.fromJson(payload);
      }
      debugPrint(
        'Save outfit backend responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Save outfit backend unreachable: $error');
    }
    return null;
  }

  /// Fetches the server-persisted `preferredOccasions` (`GET /v1/users/me`).
  ///
  /// Returns the authoritative `preferences.preferredOccasions` list — `[]`
  /// is a valid clear and is returned as such. Returns null on any failure
  /// or when the key is missing/malformed, so the caller keeps local state.
  /// Same timeout/error degradation conventions as [chat].
  Future<List<String>?> fetchPreferredOccasions() async {
    try {
      final response = await _client
          .get(Uri.parse('$baseUrl/v1/users/me'), headers: _authJsonHeaders)
          .timeout(_timeout);

      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        final preferences = decoded['preferences'];
        if (preferences is Map<String, dynamic>) {
          final raw = preferences['preferredOccasions'];
          if (raw is List && raw.every((e) => e is String)) {
            return List<String>.from(raw);
          }
        }
        debugPrint('User profile missing preferredOccasions.');
      } else {
        debugPrint(
          'User profile backend responded ${response.statusCode}: ${response.body}',
        );
      }
    } catch (error) {
      debugPrint('User profile backend unreachable: $error');
    }
    return null;
  }

  /// Persists `preferredOccasions` (`PATCH /v1/users/me`).
  ///
  /// Sends exactly `{"preferredOccasions": [...]}` (`[]` clears). Returns
  /// true only when the backend confirms (200). Same timeout/error
  /// degradation conventions as [chat]: false on any failure, never throws.
  Future<bool> updatePreferredOccasions(List<String> occasions) async {
    try {
      final response = await _client
          .patch(
            Uri.parse('$baseUrl/v1/users/me'),
            headers: _authJsonHeaders,
            body: jsonEncode({'preferredOccasions': occasions}),
          )
          .timeout(_timeout);

      if (response.statusCode == 200) return true;
      debugPrint(
        'Update preferences backend responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Update preferences backend unreachable: $error');
    }
    return false;
  }

  /// Reports a card interaction (`POST /v1/assistant/feedback`, #17/UC-23).
  ///
  /// Sends only the public interaction contract: `interactionType`
  /// (`opened`/`navigated`) plus the optional card reference. Never sends
  /// signal/action names — the backend owns that mapping. Returns true
  /// only when the backend confirms (204). Same timeout/error degradation
  /// conventions as [chat]: false on any failure, never throws, so
  /// feedback never blocks the assistant interaction.
  Future<bool> submitCardFeedback({
    String? cardId,
    String? cardTitle,
    required String interactionType,
  }) async {
    try {
      final body = <String, dynamic>{'interactionType': interactionType};
      if (cardId != null) body['cardId'] = cardId;
      if (cardTitle != null) body['cardTitle'] = cardTitle;
      final response = await _client
          .post(
            Uri.parse('$baseUrl/v1/assistant/feedback'),
            headers: _authJsonHeaders,
            body: jsonEncode(body),
          )
          .timeout(_timeout);

      if (response.statusCode == 204) return true;
      debugPrint(
        'Card feedback backend responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Card feedback backend unreachable: $error');
    }
    return false;
  }

  void dispose() => _client.close();
}
