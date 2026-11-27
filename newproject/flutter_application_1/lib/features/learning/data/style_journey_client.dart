import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'package:fansivibe/core/config/app_config.dart';
import 'package:fansivibe/features/learning/data/style_journey_models.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';

/// HTTP client for SJ1 Style Journey weekly progress history
/// (`GET /v1/learning/journey/history`).
///
/// Reuses [AuthSession] Bearer token and 401 handling, and classifies
/// network, auth, and server errors into [StyleJourneyFailure] instead of
/// fabricating historical data.
class StyleJourneyClient {
  StyleJourneyClient({http.Client? client}) : _client = client ?? http.Client();

  static const String baseUrl = AppConfig.apiBaseUrl;

  static const String _devTokenDefault = String.fromEnvironment(
    'FANSIVIBE_DEV_TOKEN',
    defaultValue: 'dev',
  );

  static String get _token => AuthSession.effectiveToken(_devTokenDefault);

  final http.Client _client;
  static const Duration _timeout = Duration(seconds: 12);

  Future<StyleJourneyHistoryResult> getHistory({
    String? timezone,
    int limit = 12,
  }) async {
    try {
      final queryParams = <String, String>{'limit': limit.toString()};
      if (timezone != null && timezone.trim().isNotEmpty) {
        queryParams['timezone'] = timezone.trim();
      }
      final uri = Uri.parse(
        '$baseUrl/v1/learning/journey/history',
      ).replace(queryParameters: queryParams);
      final response = await _client
          .get(uri, headers: {'Authorization': 'Bearer $_token'})
          .timeout(_timeout);
      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 200) {
        try {
          final decoded = jsonDecode(response.body) as Map<String, dynamic>;
          return StyleJourneyHistoryResult.success(
            StyleJourneyHistory.fromJson(decoded),
          );
        } catch (error) {
          debugPrint('Style Journey history malformed 200 body: $error');
          return const StyleJourneyHistoryResult.failure(
            StyleJourneyFailure.serverError,
          );
        }
      }
      debugPrint(
        'Style Journey history responded ${response.statusCode}: ${response.body}',
      );
      return StyleJourneyHistoryResult.failure(
        _failureForStatus(response.statusCode),
      );
    } on SocketException catch (error) {
      debugPrint('Style Journey backend unreachable: $error');
      return const StyleJourneyHistoryResult.failure(
        StyleJourneyFailure.networkError,
      );
    } on TimeoutException catch (error) {
      debugPrint('Style Journey backend timed out: $error');
      return const StyleJourneyHistoryResult.failure(
        StyleJourneyFailure.networkError,
      );
    } on http.ClientException catch (error) {
      debugPrint('Style Journey HTTP client error: $error');
      return const StyleJourneyHistoryResult.failure(
        StyleJourneyFailure.networkError,
      );
    } catch (error) {
      debugPrint('Style Journey unexpected error: $error');
      return const StyleJourneyHistoryResult.failure(
        StyleJourneyFailure.serverError,
      );
    }
  }

  static StyleJourneyFailure _failureForStatus(int statusCode) {
    if (statusCode == 401) return StyleJourneyFailure.unauthorized;
    if (statusCode == 429) return StyleJourneyFailure.rateLimited;
    if (statusCode == 503) return StyleJourneyFailure.serviceUnavailable;
    return StyleJourneyFailure.serverError;
  }

  void dispose() => _client.close();
}
