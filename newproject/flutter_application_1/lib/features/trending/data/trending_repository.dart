import 'package:fansivibe/features/trending/data/trending_client.dart';
import 'package:fansivibe/features/trending/data/trending_models.dart';

/// Abstract contract for M14 Trending data operations.
///
/// The [TrendingRepository] is the single source consumed by Trending
/// surfaces: the backend `/v1/trending` collection is authoritative.
/// Verbatim passthrough — no local scoring, no reordering, no mock
/// fallback. Failures travel as typed results.
abstract class TrendingRepository {
  /// Returns the ranked trend feed (`GET /v1/trending`).
  Future<TrendingFeedResult> getTrendingFeed({String? region, int? limit});

  /// Returns one trend by ID (`GET /v1/trending/{trend_id}`).
  Future<TrendingDetailResult> getTrendDetail({required String trendId});
}

/// Backend implementation of [TrendingRepository].
class TrendingRepositoryImpl implements TrendingRepository {
  /// Creates a [TrendingRepositoryImpl] with an optional client for testing.
  TrendingRepositoryImpl({TrendingClient? client}) : _client = client ?? TrendingClient();

  final TrendingClient _client;

  @override
  Future<TrendingFeedResult> getTrendingFeed({String? region, int? limit}) {
    // Verbatim passthrough: ranking and envelope stay server-authoritative.
    return _client.getTrendingFeed(region: region, limit: limit);
  }

  @override
  Future<TrendingDetailResult> getTrendDetail({required String trendId}) {
    // Verbatim passthrough of the trend ID — never translated, never faked.
    return _client.getTrendDetail(trendId: trendId);
  }
}
