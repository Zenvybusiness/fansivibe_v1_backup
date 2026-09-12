// Reaction DTOs for the M11 feedback surface (PHASE 2).
//
// Wire shapes follow the frozen contract exactly (camelCase):
// `FeedbackCreate {rating*, reason?, targetLookId?, targetSavedLookId?}`
// (FEEDBACK_LEARNING_API §5.1). `rating` is a tag string — the exact
// vocabulary is pending the feedback design (BC-38/39, PR-12), so this
// layer validates structure only, never a value allow-list. `reason`
// is optional free text (never echoed outside the submit pair).
// `targetLookId` is a catalog `looks.code`; `targetSavedLookId` is an
// owned `saved_looks.id` UUID. At most one target per reaction.
//
// IDs pass through verbatim; local numeric IDs are never produced,
// stored, or sent by this layer. Nothing here writes learning signals,
// marks styled days, logs wears, or mutates saves — the backend owns
// all side effects (exactly one `feedback_events` row per accepted
// submit).

/// Rating tags sent by the bundled reaction control.
///
/// The backend accepts any non-blank tag (vocabulary intentionally
/// unfrozen); these two spellings follow the contract's `like` example
/// and its natural counterpart.
abstract final class FeedbackRating {
  static const String like = 'like';
  static const String dislike = 'dislike';
}

/// How a feedback submit concluded (for truthful UI feedback — never
/// posed as recorded data).
enum FeedbackStatus {
  /// Backend accepted the reaction (201/204 ack, incl. idempotent replay).
  sent,

  /// Same key was already used with a different payload (409).
  conflict,

  /// Request rejected (422 — should not happen with bundled values).
  invalid,

  /// Authentication required (401).
  unauthorized,

  /// Throttled (429).
  rateLimited,

  /// Unreachable backend / transport error — truthful offline state.
  networkError,

  /// Any other status.
  unknown,
}

/// Outcome of `POST /v1/feedback`.
class FeedbackResult {
  const FeedbackResult._(this.status);

  /// Backend accepted the reaction (or acknowledged a replay).
  const FeedbackResult.sent() : this._(FeedbackStatus.sent);

  /// The submit failed in the given way. Safe to retry (with a fresh
  /// key for a new attempt, or the same key to replay it).
  const FeedbackResult.failure(FeedbackStatus status) : this._(status);

  final FeedbackStatus status;

  /// Whether the reaction landed (freshly or as a replay ack).
  bool get sent => status == FeedbackStatus.sent;
}
