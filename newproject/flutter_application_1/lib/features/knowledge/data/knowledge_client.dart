import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'package:fansivibe/core/config/app_config.dart';
import 'package:fansivibe/features/knowledge/data/knowledge_api_models.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';

/// HTTP client for the M5 knowledge reads (#18–#22, STEP 19.5).
///
/// Override the endpoint with `--dart-define=ASSISTANT_BASE_URL=...`.
/// On failure it returns null so the caller can hide the surface — the
/// flow never breaks when the server is unreachable, and a failure is
/// never posed as catalog data (no mock success, no local fallback).
class KnowledgeClient {
  KnowledgeClient({http.Client? client}) : _client = client ?? http.Client();

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

  Map<String, String> get _headers => {'Authorization': 'Bearer $_devToken'};

  Uri _uri(String path, {int page = 1, int pageSize = 20}) {
    final queryParams = <String, String>{};
    if (page > 1) queryParams['page'] = page.toString();
    if (pageSize != 20) queryParams['page_size'] = pageSize.toString();
    return Uri.parse(
      '$baseUrl$path',
    ).resolveUri(Uri(queryParameters: queryParams));
  }

  /// Fetches the curated look catalog (#18).
  ///
  /// Returns the [KnowledgeLookList] on 200, or null when the backend is
  /// unreachable or rejects the request (including the honest 422 for
  /// unsupported occasion/style filters — never inferred client-side).
  Future<KnowledgeLookList?> listLooks({
    int page = 1,
    int pageSize = 20,
  }) async {
    try {
      final response = await _client
          .get(
            _uri('/v1/knowledge/looks', page: page, pageSize: pageSize),
            headers: _headers,
          )
          .timeout(_timeout);
      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return KnowledgeLookList.fromJson(decoded);
      }
      debugPrint(
        'Knowledge looks responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Knowledge backend unreachable during looks list: $error');
    }
    return null;
  }

  /// Fetches the canonical wardrobe-category vocabulary (#19).
  ///
  /// Returns the [KnowledgeVocabularyList] on 200, or null when unavailable.
  Future<KnowledgeVocabularyList?> listCategories({
    int page = 1,
    int pageSize = 20,
  }) async {
    return _listVocabulary(
      '/v1/knowledge/categories',
      page: page,
      pageSize: pageSize,
    );
  }

  /// Fetches the canonical color vocabulary (#20).
  ///
  /// Returns the [KnowledgeVocabularyList] on 200, or null when unavailable.
  Future<KnowledgeVocabularyList?> listColors({
    int page = 1,
    int pageSize = 20,
  }) async {
    return _listVocabulary(
      '/v1/knowledge/colors',
      page: page,
      pageSize: pageSize,
    );
  }

  /// Fetches the frozen 9-row occasion vocabulary (#21, DEC-014 P-1).
  ///
  /// Returns the [KnowledgeVocabularyList] on 200, or null when unavailable.
  Future<KnowledgeVocabularyList?> listOccasions({
    int page = 1,
    int pageSize = 20,
  }) async {
    return _listVocabulary(
      '/v1/knowledge/occasions',
      page: page,
      pageSize: pageSize,
    );
  }

  Future<KnowledgeVocabularyList?> _listVocabulary(
    String path, {
    required int page,
    required int pageSize,
  }) async {
    try {
      final response = await _client
          .get(
            _uri(path, page: page, pageSize: pageSize),
            headers: _headers,
          )
          .timeout(_timeout);
      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return KnowledgeVocabularyList.fromJson(decoded);
      }
      debugPrint(
        'Knowledge $path responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Knowledge backend unreachable during $path list: $error');
    }
    return null;
  }

  /// Fetches the system-owned item-type references (#22, DEC-014 P-2).
  ///
  /// Returns the [KnowledgeItemReferenceList] on 200 — including the valid
  /// empty catalog while the content gate holds — or null when unavailable.
  /// Null means unavailable; an empty non-null list means the server
  /// truthfully reports no reference content yet.
  Future<KnowledgeItemReferenceList?> listItems({
    int page = 1,
    int pageSize = 20,
  }) async {
    try {
      final response = await _client
          .get(
            _uri('/v1/knowledge/items', page: page, pageSize: pageSize),
            headers: _headers,
          )
          .timeout(_timeout);
      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return KnowledgeItemReferenceList.fromJson(decoded);
      }
      debugPrint(
        'Knowledge items responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Knowledge backend unreachable during items list: $error');
    }
    return null;
  }

  /// Fetches the FFO foundation schema index (`GET /v1/knowledge/ffo`).
  ///
  /// Returns the [FfoSchemaList] on 200, or null when unavailable.
  Future<FfoSchemaList?> listFfoSchemas({
    int page = 1,
    int pageSize = 20,
  }) async {
    try {
      final response = await _client
          .get(
            _uri('/v1/knowledge/ffo', page: page, pageSize: pageSize),
            headers: _headers,
          )
          .timeout(_timeout);
      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return FfoSchemaList.fromJson(decoded);
      }
      debugPrint(
        'Knowledge ffo responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Knowledge backend unreachable during ffo list: $error');
    }
    return null;
  }

  /// Fetches one FFO foundation schema verbatim (`GET /v1/knowledge/ffo/{name}`).
  ///
  /// Returns the raw schema JSON on 200, or null when unavailable —
  /// including the honest 404 for unknown names and empty names, which
  /// never leave the client.
  Future<Map<String, dynamic>?> getFfoSchema(String name) async {
    if (name.isEmpty) return null;
    try {
      final response = await _client
          .get(
            Uri.parse('$baseUrl/v1/knowledge/ffo/$name'),
            headers: _headers,
          )
          .timeout(_timeout);
      AuthSession.noteStatus(response.statusCode);
      if (response.statusCode == 200) {
        return jsonDecode(response.body) as Map<String, dynamic>;
      }
      debugPrint(
        'Knowledge ffo/$name responded ${response.statusCode}: ${response.body}',
      );
    } catch (error) {
      debugPrint('Knowledge backend unreachable during ffo get: $error');
    }
    return null;
  }
}
