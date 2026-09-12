import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'package:fansivibe/features/learning/data/learning_summary_models.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';

/// HTTP client for the M10 learning summary read (#34, STEP 19.16).
///
/// Override the endpoint with `--dart-define=ASSISTANT_BASE_URL=...`.
/// On failure it returns null so the caller renders its honest
/// loading/error states — the flow never fabricates a score when the
/// server is unreachable, and a failure is never posed as summary data
/// (no mock fallback, no local recalculation).
class LearningSummaryClient {
  LearningSummaryClient({http.Client? client})
    : _client = client ?? http.Client();

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

  /// Fetches the caller's derived learning summary (#34).
  ///
  /// Returns the [LearningSummary] on 200 (including the zero-valued
  /// summary for a fresh user), or null when the backend is unreachable
  /// or rejects the request. Never throws.
  Future<LearningSummary?> getSummary() async {
    try {
      final response = await _client
          .get(
            Uri.parse('$baseUrl/v1/learning/summary'),
            headers: {'Authorization': 'Bearer $_devToken'},
          )
          .timeout(_timeout);
      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return LearningSummary.fromJson(decoded);
      }
      debugPrint(
        'Learning summary responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Learning backend unreachable during summary read: $error');
    }
    return null;
  }

  void dispose() => _client.close();
}
