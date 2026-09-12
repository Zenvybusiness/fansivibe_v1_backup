import 'package:fansivibe/features/discover/data/discover_client.dart';
import 'package:fansivibe/features/discover/data/discover_models.dart';

/// Abstract contract for M14 Discover data operations.
///
/// The [DiscoverRepository] is the single source consumed by the
/// Discover / Look Details surfaces: the backend `/v1/looks` collection
/// is authoritative. There is deliberately no local-service merge and no
/// mock fallback — a fabricated look would corrupt the code-addressed
/// detail surface. Failures travel as typed results; the caller keeps
/// its rows and allows a retry.
abstract class DiscoverRepository {
  /// Returns one cursor page of the ranked feed (#43 `GET /v1/looks`).
  ///
  /// Null filters are omitted (`all` selections); [cursor] is the opaque
  /// token from the previous page (null for the first page). Server
  /// order is never re-sorted in this layer.
  Future<DiscoverFeedResult> getLookFeed({
    String? occasion,
    String? style,
    String? fit,
    String? cursor,
    int? limit,
  });

  /// Returns one catalog look by its backend code (#44).
  ///
  /// [lookId] is the backend code verbatim — never a local mock ID.
  Future<LookDetailResult> getLookDetail({required String lookId});
}

/// Backend implementation of [DiscoverRepository].
class DiscoverRepositoryImpl implements DiscoverRepository {
  /// Creates a [DiscoverRepositoryImpl] with an optional client for
  /// testing. Without a client, uses the default [DiscoverClient].
  DiscoverRepositoryImpl({DiscoverClient? client})
    : _client = client ?? DiscoverClient();

  final DiscoverClient _client;

  @override
  Future<DiscoverFeedResult> getLookFeed({
    String? occasion,
    String? style,
    String? fit,
    String? cursor,
    int? limit,
  }) {
    // Verbatim passthrough: ranking, cursor windows, and envelope
    // semantics stay server-authoritative. Failures travel typed.
    return _client.getLookFeed(
      occasion: occasion,
      style: style,
      fit: fit,
      cursor: cursor,
      limit: limit,
    );
  }

  @override
  Future<LookDetailResult> getLookDetail({required String lookId}) {
    // Verbatim passthrough of the backend code: no ID translation, no
    // local mock IDs, no fabrication on failure.
    return _client.getLookDetail(lookId: lookId);
  }
}
