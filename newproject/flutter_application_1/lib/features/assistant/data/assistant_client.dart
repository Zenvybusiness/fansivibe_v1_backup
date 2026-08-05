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

  void dispose() => _client.close();
}
