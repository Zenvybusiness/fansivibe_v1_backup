import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'package:fansivibe/core/config/app_config.dart';
import 'package:fansivibe/features/trending/data/trending_models.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';

/// HTTP client for M14 Trending (`GET /v1/trending`, `GET /v1/trending/{id}`).
///
/// Backend is authoritative: no score derivation, no reordering, no mock
/// fallback. Fetches never throw — failures travel as typed results so
/// the caller renders honest loading/error states. Credentials never
/// leave the backend; this client sends only the session Bearer token.
class TrendingClient {
  /// Creates a [TrendingClient] with an optional client for testing.
  TrendingClient({http.Client? client}) : _client = client ?? http.Client();

  /// Backend base URL — single source of truth is [AppConfig.apiBaseUrl].
  static const String baseUrl = AppConfig.apiBaseUrl;

  static const String _devTokenDefault = String.fromEnvironment(
    'FANSIVIBE_DEV_TOKEN',
    defaultValue: 'dev',
  );

  /// Session-first Bearer token (D-AUTH-1): persisted session wins.
  static String get _devToken => AuthSession.effectiveToken(_devTokenDefault);

  final http.Client _client;
  static const Duration _timeout = Duration(seconds: 12);

  Map<String, String> get _headers => {'Authorization': 'Bearer $_devToken'};

  /// Fetches the ranked trend feed (`GET /v1/trending`). Never throws.
  Future<TrendingFeedResult> getTrendingFeed({String? region, int? limit}) async {
    try {
      final query = <String, String>{
        if (region != null) 'region': region,
        if (limit != null) 'limit': '$limit',
      };
      final uri = Uri.parse(
        '$baseUrl/v1/trending',
      ).replace(queryParameters: query.isEmpty ? null : query);
      final response = await _client.get(uri, headers: _headers).timeout(_timeout);
      if (response.statusCode == 200) {
        try {
          final decoded = jsonDecode(response.body) as Map<String, dynamic>;
          return TrendingFeedResult.page(TrendingFeed.fromJson(decoded));
        } catch (error) {
          debugPrint('Trending feed: malformed 200 body: $error');
          return const TrendingFeedResult.failure(TrendingFailure.networkError);
        }
      }
      final failure = _failureFor(response.statusCode);
      debugPrint('Trending feed responded ${response.statusCode}: ${response.body}');
      return TrendingFeedResult.failure(failure);
    } catch (error) {
      debugPrint('Trending backend unreachable during feed fetch: $error');
      return const TrendingFeedResult.failure(TrendingFailure.networkError);
    }
  }

  /// Fetches one trend by ID (`GET /v1/trending/{trend_id}`). Never throws.
  Future<TrendingDetailResult> getTrendDetail({required String trendId}) async {
    try {
      final base = Uri.parse(baseUrl);
      final uri = base.replace(
        pathSegments: [...base.pathSegments, 'v1', 'trending', trendId],
      );
      final response = await _client.get(uri, headers: _headers).timeout(_timeout);
      if (response.statusCode == 200) {
        try {
          final decoded = jsonDecode(response.body) as Map<String, dynamic>;
          return TrendingDetailResult.available(TrendingItem.fromJson(decoded));
        } catch (error) {
          debugPrint('Trending detail: malformed 200 body: $error');
          return const TrendingDetailResult.failure(TrendingFailure.networkError);
        }
      }
      if (response.statusCode == 404) {
        return const TrendingDetailResult.notFound();
      }
      final failure = _failureFor(response.statusCode);
      debugPrint('Trending detail responded ${response.statusCode}: ${response.body}');
      return TrendingDetailResult.failure(failure);
    } catch (error) {
      debugPrint('Trending backend unreachable during detail fetch: $error');
      return const TrendingDetailResult.failure(TrendingFailure.networkError);
    }
  }

  TrendingFailure _failureFor(int statusCode) {
    switch (statusCode) {
      case 401:
        AuthSession.notifyUnauthorized();
        return TrendingFailure.unauthorized;
      default:
        return TrendingFailure.unknown;
    }
  }

  /// Closes the underlying HTTP client.
  void dispose() => _client.close();
}
