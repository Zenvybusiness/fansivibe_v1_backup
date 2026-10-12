import 'dart:math';

/// Stage F0 mock try-on wire models (typed, backend-verbatim).
///
/// Every result carries [isMock]: mock composites are test data for UI
/// development and must never be presented as genuine AI try-on output.
/// The single [TryOnConsentVersion.current] pins the backend consent
/// contract — a mismatch fails closed with [TryOnFailure.invalidInput].
abstract final class TryOnConsentVersion {
  static const current = 'tryon-v1';
}

/// Outfit provenance accepted by `POST /v1/tryon/jobs` (both product
/// paths share the one pipeline; IDs travel as labels only).
abstract final class TryOnOutfitSource {
  static const today = 'today';
  static const outfit = 'outfit';
  static const saved = 'saved';
  static const wardrobe = 'wardrobe';

  static const values = {today, outfit, saved, wardrobe};
}

/// Mock job lifecycle: submitted as `processing`, `completed` once the
/// mock SVG renders. `failed` is reserved for the real-provider stage.
enum TryOnJobState { processing, completed, failed, unknown }

enum TryOnFailure {
  unauthorized,
  invalidInput,
  rateLimited,
  quotaExceeded,
  serviceUnavailable,
  networkError,
  unknown,
}

/// Submitted mock job (202). Never throws on malformed input — null
/// means "not submitted", so the caller keeps truthful states.
class TryOnJob {
  const TryOnJob({
    required this.jobId,
    required this.state,
    required this.isMock,
  });

  final String jobId;
  final TryOnJobState state;
  final bool isMock;

  static TryOnJob? fromJson(Map<String, dynamic> json) {
    final jobId = json['job_id'];
    if (jobId is! String || jobId.isEmpty) return null;
    return TryOnJob(
      jobId: jobId,
      state: _stateOf(json['status']),
      isMock: json['is_mock'] != false,
    );
  }

  static TryOnJobState _stateOf(Object? status) {
    switch (status) {
      case 'completed':
        return TryOnJobState.completed;
      case 'failed':
        return TryOnJobState.failed;
      case 'processing':
        return TryOnJobState.processing;
      default:
        return TryOnJobState.unknown;
    }
  }
}

/// Polled mock job status (200). Progress is provider-reported (50 while
/// processing, 100 when completed).
class TryOnJobStatus {
  const TryOnJobStatus({
    required this.jobId,
    required this.state,
    required this.progress,
    required this.isMock,
  });

  final String jobId;
  final TryOnJobState state;
  final int progress;
  final bool isMock;

  static TryOnJobStatus? fromJson(Map<String, dynamic> json) {
    final jobId = json['job_id'];
    if (jobId is! String || jobId.isEmpty) return null;
    final progress = json['progress'];
    return TryOnJobStatus(
      jobId: jobId,
      state: TryOnJob._stateOf(json['status']),
      progress: progress is int ? progress : 0,
      isMock: json['is_mock'] != false,
    );
  }
}

/// Outcome of one submit attempt: either the accepted [job] or the
/// mapped [failure] (null failure with null job means transport
/// failure — the caller shows the network state).
class TryOnSubmitResult {
  const TryOnSubmitResult({this.job, this.failure});

  final TryOnJob? job;
  final TryOnFailure? failure;
}

/// Generates a fresh v4-style idempotency key for one try-on attempt.
///
/// Same convention as the TodayLook/outfit clients (122 random bits as
/// UUID text, no new dependency, no cross-feature import): fresh key per
/// new attempt, stable key across retries of the SAME attempt.
String newTryOnIdempotencyKey() {
  final random = Random.secure();
  final bytes = List<int>.generate(16, (_) => random.nextInt(256));
  bytes[6] = (bytes[6] & 0x0F) | 0x40;
  bytes[8] = (bytes[8] & 0x3F) | 0x80;
  String hex(int v) => v.toRadixString(16).padLeft(2, '0');
  final h = bytes.map(hex).join();
  return '${h.substring(0, 8)}-${h.substring(8, 12)}-'
      '${h.substring(12, 16)}-${h.substring(16, 20)}-${h.substring(20)}';
}
