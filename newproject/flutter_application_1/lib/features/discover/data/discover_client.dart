import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'package:fansivibe/features/discover/data/discover_models.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';

/// HTTP client for the M14 Discover surface.
///
/// Endpoints: #43 `GET /v1/looks` (`?occasion=&style=&fit=&cursor=&limit=`,
/// cursor envelope) and #44 `GET /v1/looks/{look_id}` (bare detail).
///
/// Override the endpoint with `--dart-define=ASSISTANT_BASE_URL=...`.
/// Fetches never throw: 200 parses into the typed result, 404 on detail
/// into [LookDetailResult.notFound] (truthful empty state), 422 into
/// [DiscoverFailure.invalidInput] (e.g. a filter the current catalog
/// cannot honor, or a bad cursor/limit), and every other status or
/// transport error into a typed failure so the caller renders its honest
/// loading/error states — the flow never fabricates a look when the
/// server is unreachable and never shows fake content offline.
///
/// Look IDs are backend catalog codes (PR-3 strings, not UUIDs) passed
/// through verbatim; local mock IDs (`fy_*`/`tr_*`) are never submitted.
/// Nothing here derives scores, reorders the feed, logs wears, or writes
/// learning signals — the backend response is the source of truth.
class DiscoverClient {
  /// Creates a [DiscoverClient] with an optional client for testing.
  DiscoverClient({http.Client? client}) : _client = client ?? http.Client();

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

  /// Fetches one cursor page of the ranked feed (#43 `GET /v1/looks`).
  ///
  /// Null filters are omitted (the screen passes null for its `all`
  /// selections); non-null filters travel verbatim and the backend
  /// truthfully 422s values the current catalog cannot honor. [cursor]
  /// is the opaque token from the previous page (null for the first
  /// page); [limit] is the page size when set. Never throws.
  Future<DiscoverFeedResult> getLookFeed({
    String? occasion,
    String? style,
    String? fit,
    String? cursor,
    int? limit,
  }) async {
    try {
      final query = <String, String>{
        if (occasion != null) 'occasion': occasion,
        if (style != null) 'style': style,
        if (fit != null) 'fit': fit,
        if (cursor != null) 'cursor': cursor,
        if (limit != null) 'limit': '$limit',
      };
      final uri = Uri.parse(
        '$baseUrl/v1/looks',
      ).replace(queryParameters: query.isEmpty ? null : query);
      final response = await _client
          .get(uri, headers: _headers)
          .timeout(_timeout);
      if (response.statusCode == 200) {
        try {
          final decoded = jsonDecode(response.body) as Map<String, dynamic>;
          return DiscoverFeedResult.page(LookFeedPage.fromJson(decoded));
        } catch (error) {
          debugPrint('Discover feed: malformed 200 body: $error');
          return const DiscoverFeedResult.failure(DiscoverFailure.networkError);
        }
      }
      final failure = _failureFor(response.statusCode);
      debugPrint(
        'Discover feed responded ${response.statusCode}: ${response.body}',
      );
      return DiscoverFeedResult.failure(failure);
    } catch (error) {
      debugPrint('Discover backend unreachable during feed fetch: $error');
      return const DiscoverFeedResult.failure(DiscoverFailure.networkError);
    }
  }

  /// Fetches one catalog look by its backend code (#44).
  ///
  /// [lookId] travels verbatim as the path segment (never translated to
  /// a local ID). Unknown codes 404 into [LookDetailResult.notFound].
  /// Never throws.
  Future<LookDetailResult> getLookDetail({required String lookId}) async {
    try {
      // Path-segment construction (never string interpolation): the
      // backend code travels verbatim and is never treated as a route.
      final base = Uri.parse(baseUrl);
      final uri = base.replace(
        pathSegments: [...base.pathSegments, 'v1', 'looks', lookId],
      );
      final response = await _client
          .get(uri, headers: _headers)
          .timeout(_timeout);
      if (response.statusCode == 200) {
        try {
          final decoded = jsonDecode(response.body) as Map<String, dynamic>;
          return LookDetailResult.available(LookDetail.fromJson(decoded));
        } catch (error) {
          debugPrint('Discover detail: malformed 200 body: $error');
          return const LookDetailResult.failure(DiscoverFailure.networkError);
        }
      }
      if (response.statusCode == 404) {
        return const LookDetailResult.notFound();
      }
      final failure = _failureFor(response.statusCode);
      debugPrint(
        'Discover detail responded ${response.statusCode}: ${response.body}',
      );
      return LookDetailResult.failure(failure);
    } catch (error) {
      debugPrint('Discover backend unreachable during detail fetch: $error');
      return const LookDetailResult.failure(DiscoverFailure.networkError);
    }
  }

  DiscoverFailure _failureFor(int statusCode) {
    switch (statusCode) {
      case 401:
        AuthSession.notifyUnauthorized();
        return DiscoverFailure.unauthorized;
      case 422:
        return DiscoverFailure.invalidInput;
      case 429:
        return DiscoverFailure.rateLimited;
      default:
        return DiscoverFailure.unknown;
    }
  }

  /// Closes the underlying HTTP client.
  void dispose() => _client.close();
}
