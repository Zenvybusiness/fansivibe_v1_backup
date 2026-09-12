import 'dart:async';

import 'package:fansivibe/features/learning/data/learning_summary_client.dart';
import 'package:fansivibe/features/learning/data/learning_summary_models.dart';

/// Abstract contract for the M10 learning summary read (#34, STEP 19.16).
///
/// The backend is the single source of truth. There is deliberately NO
/// local recalculation and NO mock fallback here: a fabricated score or
/// streak would corrupt the Profile/Home surfaces, so any failure yields
/// null and the caller renders its honest loading/error states instead.
/// The zero-valued summary (score 60, streak 0, empty recents) is valid
/// server data and passes through as-is.
abstract class LearningSummaryRepository {
  /// Returns the caller's derived summary, or null when unavailable.
  Future<LearningSummary?> getSummary();
}

/// Concrete implementation of [LearningSummaryRepository] backed only by
/// the [LearningSummaryClient] — verbatim passthrough, no local math.
class LearningSummaryRepositoryImpl implements LearningSummaryRepository {
  /// Creates a [LearningSummaryRepositoryImpl] with an optional
  /// [LearningSummaryClient] for testing. Without a client, uses the
  /// default [LearningSummaryClient].
  LearningSummaryRepositoryImpl({LearningSummaryClient? client})
    : _client = client ?? LearningSummaryClient();

  final LearningSummaryClient _client;

  @override
  Future<LearningSummary?> getSummary() {
    // No score/streak recalculation, no mock merge: null means
    // unavailable — the caller renders its error state.
    return _client.getSummary();
  }
}
