import 'dart:math';

import 'package:flutter/foundation.dart';

import 'package:fansivibe/features/hairstyle/data/hairstyle_client.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_mock_data.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_models.dart';
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

  /// Dev-only face profile reference until profile creation is wired.
  static const String _devFaceProfileRef =
      '00000000-0000-0000-0000-000000000001';

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
  String? _lastRunId;

  /// Wire the learning repository so the analysis uses the user's stored face
  /// profile instead of falling back to the offline result.
  void attachLearning(LearningRepository learning) {
    _learning = learning;
  }

  /// Runs the analysis and returns the result.
  ///
  /// Drives [completedStageCount] forward as real transitions happen: the
  /// pipeline completes when the backend run is finished (or when the offline
  /// fallback has produced its result). When the backend is reachable but the
  /// run ends in `failed`, [analysisError] is set so callers can surface the
  /// typed failure; the offline fallback still resolves so the flow never
  /// breaks (documented Stage 6-7 design decision).
  Future<HairstyleAnalysisResult> runAnalysis() async {
    _isProcessing = true;
    _completedStageCount = 0;
    _analysisError = null;
    _result = null;
    _lastRunId = null;
    _safeNotify();

    HairstyleAnalysisResult resolved;
    final faceShape = _learning?.face?.faceShape;

    if (faceShape == null || faceShape.isEmpty) {
      resolved = HairstyleAnalysisResult.mock;
    } else {
      final runId = await _client.submitHairstyleAnalysis(
        faceProfileRef: _devFaceProfileRef,
      );
      _lastRunId = runId;
      if (runId == null) {
        resolved = HairstyleAnalysisResult.mock;
      } else {
        final run = await _client.pollAnalysisRun(runId: runId);
        if (run != null && run.isFailed) {
          _analysisError = _describeError(run.error);
          resolved = HairstyleAnalysisResult.mock;
        } else if (run != null) {
          resolved = hairstyleResultFromRun(run);
        } else {
          resolved = HairstyleAnalysisResult.mock;
        }
      }
    }

    // Emit appearance_scan_completed exactly once per analysis run
    _analytics.emitAppearanceScanCompleted(
      runStatus: _getRunStatus(_lastRunId, _analysisError),
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

  String _getRunStatus(String? runId, String? analysisError) {
    // If we don't have a runId or there was an error, it's either failed or mock
    if (runId == null || analysisError != null) {
      return 'failed';
    }
    return 'completed';
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

  /// Saves a recommendation to the user's saved looks.
  ///
  /// Uses an idempotency key so retries never create duplicates. Returns true
  /// when the backend accepted the save.
  Future<bool> saveLook({
    required HairstyleRecommendation recommendation,
    required String title,
  }) async {
    final idempotencyKey =
        '${DateTime.now().microsecondsSinceEpoch}-${_random.nextInt(1 << 32)}';
    final ok = await _client.saveLook(
      lookId: recommendation.id,
      title: title,
      snapshot: recommendation.toJson(),
      idempotencyKey: idempotencyKey,
    );
    if (ok) {
      _learning?.recordSignal('look_saved', recommendation.name);
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
    _result = result;
    _completedStageCount = totalStages;
    _isProcessing = false;
    _safeNotify();
  }

  /// Test-only hook: simulate a backend `failed` run.
  @visibleForTesting
  void setAnalysisError(String message) {
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