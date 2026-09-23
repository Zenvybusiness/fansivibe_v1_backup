import 'dart:async';

import 'package:fansivibe/features/knowledge/data/knowledge_api_models.dart';
import 'package:fansivibe/features/knowledge/data/knowledge_client.dart';

/// Abstract contract for M5 knowledge reads (#18–#22, STEP 19.5) plus the
/// additive FFO foundation reads (`GET /v1/knowledge/ffo*`).
///
/// The backend is the single source of truth. There is deliberately NO
/// mock fallback here: a fabricated vocabulary would corrupt validation
/// and selection surfaces, so any failure yields null and the caller
/// hides the surface instead of inventing one. A non-null empty list
/// (notably #22 while its content gate holds) is valid server data and
/// passes through as-is.
abstract class KnowledgeRepository {
  /// Returns the curated look catalog page, or null when unavailable.
  Future<KnowledgeLookList?> listLooks({int page = 1, int pageSize = 20});

  /// Returns the canonical wardrobe-category vocabulary, or null.
  Future<KnowledgeVocabularyList?> listCategories({
    int page = 1,
    int pageSize = 20,
  });

  /// Returns the canonical color vocabulary, or null.
  Future<KnowledgeVocabularyList?> listColors({
    int page = 1,
    int pageSize = 20,
  });

  /// Returns the frozen 9-row occasion vocabulary, or null.
  Future<KnowledgeVocabularyList?> listOccasions({
    int page = 1,
    int pageSize = 20,
  });

  /// Returns the system-owned item-type references, or null.
  ///
  /// Null means unavailable — hide the surface. A non-null empty list
  /// means the server truthfully reports no reference content yet
  /// (DEC-014 P-2 content gate) — render the honest empty state.
  Future<KnowledgeItemReferenceList?> listItems({
    int page = 1,
    int pageSize = 20,
  });

  /// Returns the FFO foundation schema index, or null when unavailable.
  Future<FfoSchemaList?> listFfoSchemas({int page = 1, int pageSize = 20});

  /// Returns one FFO foundation schema verbatim, or null when unavailable.
  ///
  /// Null covers unreachable backend, unknown names (server 404), and
  /// empty names (never requested) — the caller hides the surface.
  Future<Map<String, dynamic>?> getFfoSchema(String name);

  /// Submits a fashion reasoning query (`POST /v1/reasoning`).
  ///
  /// Returns the validated [FashionReasoningResponse] on 200, or null
  /// when the reasoning service is unavailable, times out, or fails.
  Future<FashionReasoningResponse?> reasonQuery(FashionReasoningRequest request);

  /// Submits a fashion reasoning query and returns a typed [ReasoningResult]
  /// preserving distinct technical failure categories (502, 503, 504, 422, etc.).
  Future<ReasoningResult> reasonQueryDetailed(FashionReasoningRequest request);
}

/// Concrete implementation of [KnowledgeRepository] backed only by the
/// [KnowledgeClient] — verbatim passthrough, no local substitution.
class KnowledgeRepositoryImpl implements KnowledgeRepository {
  /// Creates a [KnowledgeRepositoryImpl] with an optional [KnowledgeClient]
  /// for testing. Without a client, uses the default [KnowledgeClient].
  KnowledgeRepositoryImpl({KnowledgeClient? client})
    : _client = client ?? KnowledgeClient();

  final KnowledgeClient _client;

  @override
  Future<KnowledgeLookList?> listLooks({int page = 1, int pageSize = 20}) {
    // No mock fallback, no occasion/style inference: null means
    // unavailable — the caller hides the surface.
    return _client.listLooks(page: page, pageSize: pageSize);
  }

  @override
  Future<KnowledgeVocabularyList?> listCategories({
    int page = 1,
    int pageSize = 20,
  }) {
    return _client.listCategories(page: page, pageSize: pageSize);
  }

  @override
  Future<KnowledgeVocabularyList?> listColors({
    int page = 1,
    int pageSize = 20,
  }) {
    return _client.listColors(page: page, pageSize: pageSize);
  }

  @override
  Future<KnowledgeVocabularyList?> listOccasions({
    int page = 1,
    int pageSize = 20,
  }) {
    return _client.listOccasions(page: page, pageSize: pageSize);
  }

  @override
  Future<KnowledgeItemReferenceList?> listItems({
    int page = 1,
    int pageSize = 20,
  }) {
    // No placeholder rows: an empty non-null list is the honest gated
    // state and passes through untouched.
    return _client.listItems(page: page, pageSize: pageSize);
  }

  @override
  Future<FfoSchemaList?> listFfoSchemas({int page = 1, int pageSize = 20}) {
    return _client.listFfoSchemas(page: page, pageSize: pageSize);
  }

  @override
  Future<Map<String, dynamic>?> getFfoSchema(String name) {
    return _client.getFfoSchema(name);
  }

  @override
  Future<FashionReasoningResponse?> reasonQuery(FashionReasoningRequest request) {
    return _client.reasonQuery(request);
  }

  @override
  Future<ReasoningResult> reasonQueryDetailed(FashionReasoningRequest request) {
    return _client.reasonQueryDetailed(request);
  }
}

