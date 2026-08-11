import 'dart:math';

import 'package:flutter/foundation.dart';

import 'package:fansivibe/features/hairstyle/data/hairstyle_client.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_mock_data.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_models.dart';
import 'package:fansivibe/features/learning/learning_repository.dart';

/// Orchestrates the hairstyle analysis flow.
///
/// Submits a hairstyle analysis for the user's face profile, polls until the
/// backend run completes, then exposes the result. When the server is
/// unreachable or no face profile exists yet, it falls back to the offline
/// mock result so the flow never breaks.
class HairstyleService extends ChangeNotifier {
  HairstyleService({
    HairstyleClient? client,
    LearningRepository? learning,
  }) : _client = client ?? HairstyleClient(),
       _learning = learning;

  static final int totalStages = HairstyleProcessingStage.mockStages.length;

  /// Dev-only face profile reference until profile creation is wired.
  static const String _devFaceProfileRef =
      '00000000-0000-0000-0000-000000000001';

  final HairstyleClient _client;
  LearningRepository? _learning;
  final Random _random = Random();

  bool _isProcessing = false;
  bool get isProcessing => _isProcessing;

  int _completedStageCount = 0;
  int get completedStageCount => _completedStageCount;

  HairstyleAnalysisResult? _result;
  HairstyleAnalysisResult? get result => _result;

  bool _disposed = false;

  /// Wire the learning repository so the analysis uses the user's stored face
  /// profile instead of falling back to the offline result.
  void attachLearning(LearningRepository learning) {
    _learning = learning;
  }

  /// Runs the analysis and returns the result.
  ///
  /// Drives [completedStageCount] forward as real transitions happen: the
  /// pipeline completes when the backend run is finished (or when the offline
  /// fallback has produced its result).
  Future<HairstyleAnalysisResult> runAnalysis() async {
    _isProcessing = true;
    _completedStageCount = 0;
    _result = null;
    _safeNotify();

    HairstyleAnalysisResult resolved;
    final faceShape = _learning?.face?.faceShape;

    if (faceShape == null || faceShape.isEmpty) {
      resolved = HairstyleAnalysisResult.mock;
    } else {
      final runId = await _client.submitHairstyleAnalysis(
        faceProfileRef: _devFaceProfileRef,
      );
      if (runId == null) {
        resolved = HairstyleAnalysisResult.mock;
      } else {
        final run = await _client.pollAnalysisRun(runId: runId);
        resolved = run != null
            ? hairstyleResultFromRun(run)
            : HairstyleAnalysisResult.mock;
      }
    }

    if (_disposed) return resolved;

    _result = resolved;
    _completedStageCount = totalStages;
    _isProcessing = false;
    _safeNotify();
    return resolved;
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

  @override
  void dispose() {
    _disposed = true;
    _client.dispose();
    super.dispose();
  }
}
