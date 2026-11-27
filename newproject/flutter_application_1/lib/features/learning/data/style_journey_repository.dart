import 'dart:async';

import 'package:fansivibe/features/learning/data/style_journey_client.dart';
import 'package:fansivibe/features/learning/data/style_journey_models.dart';

/// Abstract contract for SJ1/SJ2 Style Journey historical progress.
///
/// Backend is the sole source of truth — no local score/rank calculation
/// and no mock fallback.
abstract class StyleJourneyRepository {
  Future<StyleJourneyHistoryResult> getHistory({
    String? timezone,
    int limit = 12,
  });
}

/// Concrete [StyleJourneyRepository] backed by [StyleJourneyClient].
class StyleJourneyRepositoryImpl implements StyleJourneyRepository {
  StyleJourneyRepositoryImpl({StyleJourneyClient? client})
    : _client = client ?? StyleJourneyClient();

  final StyleJourneyClient _client;

  @override
  Future<StyleJourneyHistoryResult> getHistory({
    String? timezone,
    int limit = 12,
  }) {
    return _client.getHistory(timezone: timezone, limit: limit);
  }
}

