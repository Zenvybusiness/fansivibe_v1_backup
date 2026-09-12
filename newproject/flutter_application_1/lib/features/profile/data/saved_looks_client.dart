import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'package:fansivibe/features/profile/data/saved_looks_models.dart';

/// HTTP client for the saved-looks collection (DEC-013, STEP 18.4).
///
/// Override the endpoint with `--dart-define=ASSISTANT_BASE_URL=...`.
/// On failure it returns null so the caller keeps its rows and allows a
/// retry — the flow never fabricates success when the server is
/// unreachable. IDs pass through verbatim; local IDs are never submitted.
class SavedLooksClient {
  SavedLooksClient({http.Client? client}) : _client = client ?? http.Client();

  static const String baseUrl = String.fromEnvironment(
    'ASSISTANT_BASE_URL',
    defaultValue: 'http://localhost:8000',
  );

  static const String _devToken = String.fromEnvironment(
    'FANSIVIBE_DEV_TOKEN',
    defaultValue: 'dev',
  );

  final http.Client _client;
  static const Duration _timeout = Duration(seconds: 12);

  /// Lists the owner's saved looks (endpoint #24 `GET /v1/looks/saved`).
  ///
  /// Returns the decoded page on 200 (including an empty page), or null
  /// when the backend is unreachable or rejects the request.
  Future<SavedLookListPage?> listSavedLooks({
    int page = 1,
    int pageSize = 20,
  }) async {
    try {
      final uri = Uri.parse(
        '$baseUrl/v1/looks/saved?page=$page&page_size=$pageSize',
      );
      final response = await _client
          .get(uri, headers: {'Authorization': 'Bearer $_devToken'})
          .timeout(_timeout);
      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return SavedLookListPage.fromJson(decoded);
      }
      debugPrint(
        'Saved looks list responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Saved looks backend unreachable during list: $error');
    }
    return null;
  }

  /// Deletes one owned saved look (endpoint #25
  /// `DELETE /v1/looks/saved/{saved_look_id}`).
  ///
  /// Returns [SavedLookDeleteOutcome.deleted] on 204 and
  /// [SavedLookDeleteOutcome.alreadyGone] on 404. Returns null on any
  /// other status or when unreachable, so the caller retains the row.
  /// [id] is the backend saved-look UUID, sent verbatim.
  Future<SavedLookDeleteOutcome?> deleteSavedLook({required String id}) async {
    try {
      final response = await _client
          .delete(
            Uri.parse('$baseUrl/v1/looks/saved/$id'),
            headers: {'Authorization': 'Bearer $_devToken'},
          )
          .timeout(_timeout);
      if (response.statusCode == 204) {
        return SavedLookDeleteOutcome.deleted;
      }
      if (response.statusCode == 404) {
        return SavedLookDeleteOutcome.alreadyGone;
      }
      debugPrint(
        'Saved looks delete responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Saved looks backend unreachable during delete: $error');
    }
    return null;
  }

  void dispose() => _client.close();
}
