import 'dart:math';

import 'package:flutter/foundation.dart';

import 'package:fansivibe/features/hairstyle/data/hairstyle_client.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_mock_data.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_models.dart';
import 'package:fansivibe/features/hairstyle/domain/face_scan_votes.dart';
import 'package:fansivibe/features/learning/learning_repository.dart';
import 'package:fansivibe/shared/analytics/analytics_service.dart';

/// Orchestrates the hairstyle analysis flow.
///
/// Submits a hairstyle analysis for the user's face profile, polls until the
/// backend run completes, then exposes the result. When the server is
/// unreachable or no face profile exists yet, it falls back to the offline
/// mock result so the flow never breaks.
class HairstyleService extends ChangeNotifier {
  HairstyleService({HairstyleClient? client, LearningRepository? learning})
    : _client = client ?? HairstyleClient(),
      _learning = learning {
    _analytics = AnalyticsService.instance;
  }

  static final int totalStages = HairstyleProcessingStage.mockStages.length;

  final HairstyleClient _client;
  LearningRepository? _learning;
  late final AnalyticsService _analytics;
  final Random _random = Random();

  bool _isProcessing = false;
  bool get isProcessing => _isProcessing;

  int _completedStageCount = 0;
  int get completedStageCount => _completedStageCount;

  String? _analysisError;
  String? get analysisError => _analysisError;

  HairstyleAnalysisResult? _result;
  HairstyleAnalysisResult? get result => _result;

  bool _disposed = false;

  /// How the current analysis resolved — explicit REAL vs MOCK provenance.
  ///
  /// `false` only when the backend produced a real completed run; every
  /// fallback path (no face profile, unreachable, failed run) is `true`.
  bool _usedMockResult = false;
  bool get isMockResult => _usedMockResult;

  /// Terminal outcome of the last analysis ("offline" | "completed" |
  /// "failed" | "unreachable") used to report an honest run status.
  String _runOutcome = 'offline';

  /// The idempotency key last sent to `POST /v1/looks/saved` (authoritative
  /// value the `recommendation_saved` analytic must report).
  String? _lastIdempotencyKey;
  String? get lastIdempotencyKey => _lastIdempotencyKey;

  /// Whether the on-device `look_saved` signal was committed by the last save.
  bool _lastSavedSignalCommitted = false;
  bool get lastSavedSignalCommitted => _lastSavedSignalCommitted;

  /// Wire the learning repository so the analysis uses the user's stored face
  /// profile instead of falling back to the offline result.
  void attachLearning(LearningRepository learning) {
    _learning = learning;
  }

  /// Runs the analysis and returns the result.
  ///
  /// When [imageBytes] are supplied (real face-scan photo held in memory by
  /// the scan screen), they are uploaded as a real multipart `image` part and
  /// analyzed by the backend appearance analyzer. Otherwise the stored face
  /// profile path is used. Drives [completedStageCount] forward as real
  /// transitions happen: the pipeline completes when the backend run is
  /// finished (or when the offline fallback has produced its result). When
  /// the backend is reachable but the run ends in `failed`, [analysisError]
  /// is set so callers can surface the typed failure; the offline fallback
  /// still resolves so the flow never breaks (documented Stage 6-7 design
  /// decision). A backend-produced real analysis is never marked as mock.
  Future<HairstyleAnalysisResult> runAnalysis({
    Uint8List? imageBytes,
    String? imageFilename,
    String? imageContentType,
  }) async {
    _isProcessing = true;
    _completedStageCount = 0;
    _analysisError = null;
    _result = null;
    _runOutcome = 'offline';
    _safeNotify();

    HairstyleAnalysisResult resolved;
    if (imageBytes != null && imageBytes.isNotEmpty) {
      resolved = await _resolveBackendRun(
        _client.submitHairstyleAnalysis(
          imageBytes: imageBytes,
          imageFilename: imageFilename,
          imageContentType: imageContentType,
        ),
      );
    } else {
      final faceShape = _learning?.face?.faceShape;

      if (faceShape == null || faceShape.isEmpty) {
        _usedMockResult = true;
        resolved = HairstyleAnalysisResult.mock;
      } else {
        resolved = await _resolveBackendRun(
          _client.submitHairstyleAnalysis(),
        );
      }
    }

    // Emit appearance_scan_completed exactly once per analysis run with an
    // honest run status (offline mock resolution never reports "failed").
    _analytics.emitAppearanceScanCompleted(
      runStatus: _getRunStatus(),
      errorCode: _analysisError,
      pollAttempts: 0,
    );

    if (_disposed) return resolved;

    _result = resolved;
    _completedStageCount = totalStages;
    _isProcessing = false;
    _safeNotify();
    return resolved;
  }

  /// Runs guided multi-angle analysis (FRONT/LEFT/RIGHT).
  ///
  /// Each view is submitted through the existing single-image endpoint and
  /// polled to a terminal run; [aggregateFaceScanVotes] then picks the
  /// majority view deterministically. Returns the majority view's typed
  /// backend result, or null with [analysisError] set when too few views
  /// are valid or they disagree (explicit ambiguity — never a guess, never
  /// mock). Only safe metadata is logged (byte lengths, run ids, elapsed).
  Future<HairstyleAnalysisResult?> runMultiAngleAnalysis({
    required Uint8List frontBytes,
    String? frontName,
    required Uint8List leftBytes,
    String? leftName,
    required Uint8List rightBytes,
    String? rightName,
  }) async {
    _isProcessing = true;
    _completedStageCount = 0;
    _analysisError = null;
    _result = null;
    _runOutcome = 'offline';
    _safeNotify();

    final stopwatch = Stopwatch()..start();
    debugPrint(
      'Multi-angle submit: bytes(front=${frontBytes.length},'
      'left=${leftBytes.length},right=${rightBytes.length})',
    );
    final views = [
      (frontBytes, frontName ?? 'face_front.jpg'),
      (leftBytes, leftName ?? 'face_left.jpg'),
      (rightBytes, rightName ?? 'face_right.jpg'),
    ];
    final runs = <AnalysisRun?>[];
    for (final view in views) {
      final runId = await _client.submitHairstyleAnalysis(
        imageBytes: view.$1,
        imageFilename: view.$2,
      );
      if (runId == null) {
        runs.add(null);
        continue;
      }
      debugPrint('Multi-angle run accepted: run_id=$runId');
      runs.add(await _client.pollAnalysisRun(runId: runId));
    }
    stopwatch.stop();
    debugPrint(
      'Multi-angle polling done: elapsed_ms=${stopwatch.elapsedMilliseconds}',
    );

    final winner = aggregateFaceScanVotes(runs);
    if (winner == null) {
      _runOutcome = 'failed';
      _usedMockResult = true;
      _analysisError =
          'The three views didn\'t give a clear answer. Please retake '
          'them in good light, facing the guide.';
      _isProcessing = false;
      _safeNotify();
      return null;
    }
    final resolved = hairstyleResultFromRun(winner);
    _analytics.emitAppearanceScanCompleted(
      runStatus: 'completed',
      errorCode: null,
      pollAttempts: 0,
    );
    if (_disposed) return resolved;
    _result = resolved;
    _runOutcome = 'completed';
    _usedMockResult = false;
    _completedStageCount = totalStages;
    _isProcessing = false;
    _safeNotify();
    return resolved;
  }

  /// Submits [submitFuture] then polls to a terminal run, mapping the
  /// outcome to a result with honest mock provenance. Shared by the image
  /// and profile-reference submit paths so polling/failed handling stays
  /// identical (30 attempts, 600 ms interval live in the client).
  Future<HairstyleAnalysisResult> _resolveBackendRun(
    Future<String?> submitFuture,
  ) async {
    final runId = await submitFuture;
    if (runId == null) {
      _runOutcome = 'unreachable';
      _usedMockResult = true;
      return HairstyleAnalysisResult.mock;
    }
    final run = await _client.pollAnalysisRun(runId: runId);
    if (run != null && run.isFailed) {
      _runOutcome = 'failed';
      _usedMockResult = true;
      _analysisError = _describeError(run.error);
      return HairstyleAnalysisResult.mock;
    } else if (run != null) {
      _runOutcome = 'completed';
      _usedMockResult = false;
      return hairstyleResultFromRun(run);
    } else {
      _runOutcome = 'unreachable';
      _usedMockResult = true;
      return HairstyleAnalysisResult.mock;
    }
  }

  String _getRunStatus() {
    switch (_runOutcome) {
      case 'failed':
      case 'unreachable':
        return 'failed';
      case 'completed':
      case 'offline':
        return 'completed';
      default:
        return 'completed';
    }
  }

  String _describeError(Map<String, dynamic>? error) {
    if (error == null) return 'Hairstyle analysis failed. Please try again.';
    final message = error['message'] as String?;
    final code = error['code'] as String?;
    if (message != null && message.isNotEmpty) return message;
    if (code != null && code.isNotEmpty) return code;
    return 'Hairstyle analysis failed. Please try again.';
  }

  /// Lists the user's analysis runs (summary rows).
  ///
  /// Returns an empty list when the backend is unreachable.
  Future<List<AnalysisRun>> listRuns() async {
    final page = await _client.listRuns();
    return page?.items ?? const [];
  }

  /// Lists the user's saved looks (endpoint #24).
  ///
  /// Returns an empty list when the backend is unreachable, matching the
  /// app-wide graceful fallback behavior.
  Future<List<SavedLook>> listSavedLooks() async {
    final page = await _client.listSavedLooks();
    return page?.items ?? const [];
  }

  /// Saves a recommendation to the user's saved looks.
  ///
  /// Uses an idempotency key so retries never create duplicates. Returns true
  /// when the backend accepted the save. The authoritative key and whether the
  /// on-device `look_saved` signal committed are exposed via
  /// [lastIdempotencyKey] and [lastSavedSignalCommitted] so analytics can
  /// report the actual save outcome.
  Future<bool> saveLook({
    required HairstyleRecommendation recommendation,
    required String title,
  }) async {
    final idempotencyKey =
        '${DateTime.now().microsecondsSinceEpoch}-${_random.nextInt(1 << 32)}';
    _lastIdempotencyKey = idempotencyKey;
    _lastSavedSignalCommitted = false;
    final ok = await _client.saveLook(
      lookId: recommendation.id,
      title: title,
      snapshot: recommendation.toJson(),
      idempotencyKey: idempotencyKey,
    );
    if (ok) {
      _learning?.addSavedLook(recommendation.name);
      _lastSavedSignalCommitted = _learning != null;
    }
    return ok;
  }

  void _safeNotify() {
    if (_disposed) return;
    notifyListeners();
  }

  /// Test-only hook: mark the pipeline finished with [result].
  @visibleForTesting
  void completeWith(HairstyleAnalysisResult result) {
    _usedMockResult = identical(result, HairstyleAnalysisResult.mock);
    _runOutcome = _usedMockResult ? 'offline' : 'completed';
    _result = result;
    _completedStageCount = totalStages;
    _isProcessing = false;
    _safeNotify();
  }

  /// Test-only hook: simulate a backend `failed` run.
  @visibleForTesting
  void setAnalysisError(String message) {
    _runOutcome = 'failed';
    _usedMockResult = true;
    _analysisError = message;
    _completedStageCount = totalStages;
    _isProcessing = false;
    _safeNotify();
  }

  @override
  void dispose() {
    _disposed = true;
    _client.dispose();
    super.dispose();
  }
}