import 'package:fansivibe/features/feedback/data/feedback_client.dart';
import 'package:fansivibe/features/feedback/data/feedback_models.dart';

/// Abstract contract for M11 feedback operations (PHASE 2).
///
/// The [FeedbackRepository] is the single source consumed by reaction
/// UI: the backend `/v1/feedback` collection is authoritative. There is
/// deliberately no local-service merge and no mock fallback — a
/// fabricated ack would corrupt the append-only reaction history.
/// Anything but [FeedbackStatus.sent] means the reaction did not land
/// and is safe to retry.
abstract class FeedbackRepository {
  /// Submits one reaction (#35 `POST /v1/feedback`).
  ///
  /// At most one of [targetLookId] / [targetSavedLookId]; both null is
  /// a valid general rating. [idempotencyKey] is required — one fresh
  /// key per reaction attempt. Never throws.
  Future<FeedbackResult> submitFeedback({
    required String rating,
    String? reason,
    String? targetLookId,
    String? targetSavedLookId,
    required String idempotencyKey,
  });
}

/// Backend implementation of [FeedbackRepository].
class FeedbackRepositoryImpl implements FeedbackRepository {
  /// Creates a [FeedbackRepositoryImpl] with an optional client for
  /// testing. Without a client, uses the default [FeedbackClient].
  FeedbackRepositoryImpl({FeedbackClient? client})
    : _client = client ?? FeedbackClient();

  final FeedbackClient _client;

  @override
  Future<FeedbackResult> submitFeedback({
    required String rating,
    String? reason,
    String? targetLookId,
    String? targetSavedLookId,
    required String idempotencyKey,
  }) {
    // Verbatim passthrough: rating/reason/targets travel as given
    // under the caller's key. No local signal, no mock ack.
    return _client.submitFeedback(
      rating: rating,
      reason: reason,
      targetLookId: targetLookId,
      targetSavedLookId: targetSavedLookId,
      idempotencyKey: idempotencyKey,
    );
  }
}
