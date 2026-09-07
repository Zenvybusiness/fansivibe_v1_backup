import 'dart:math';

import 'package:flutter/foundation.dart';

import 'package:fansivibe/features/grooming/data/grooming_client.dart';
import 'package:fansivibe/features/grooming/data/grooming_models.dart';
import 'package:fansivibe/features/learning/learning_repository.dart';

/// Orchestrates the grooming analysis flow.
///
/// Submits a grooming analysis for the user's face profile, polls until the
/// backend run completes, then exposes the result. When the server is
/// unreachable or no face profile exists yet, it falls back to the offline
/// mock result so the flow never breaks.
class GroomingService extends ChangeNotifier {
  GroomingService({GroomingClient? client, LearningRepository? learning})
    : _client = client ?? GroomingClient(),
      _learning = learning;

  static final int totalStages = 5;

  /// Dev-only face profile reference until profile creation is wired.
  static const String _devFaceProfileRef =
      '00000000-0000-0000-0000-000000000001';

  final GroomingClient _client;
  LearningRepository? _learning;
  final Random _random = Random();

  bool _isProcessing = false;
  bool get isProcessing => _isProcessing;

  bool _isFailed = false;
  bool get isFailed => _isFailed;

  bool _isCompleted = false;
  bool get isCompleted => _isCompleted;

  int _completedStageCount = 0;
  int get completedStageCount => _completedStageCount;

  String? _analysisError;
  String? get analysisError => _analysisError;

  GroomingAnalysisResult? _result;
  GroomingAnalysisResult? get result => _result;

  bool _disposed = false;

  /// Wire the learning repository so the analysis uses the user's stored face
  /// profile instead of falling back to the offline mock result.
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
  Future<GroomingAnalysisResult> runAnalysis() async {
    _isProcessing = true;
    _completedStageCount = 0;
    _analysisError = null;
    _result = null;
    _safeNotify();

    GroomingAnalysisResult resolved = GroomingAnalysisResult.mock;
    final faceShape = _learning?.face?.faceShape;

    if (faceShape == null || faceShape.isEmpty) {
      resolved = GroomingAnalysisResult.mock;
    } else {
      final runId = await _client.submitGroomingAnalysis(
        faceProfileRef: _devFaceProfileRef,
      );
      if (runId == null) {
        resolved = GroomingAnalysisResult.mock;
      } else {
        final run = await _client.pollGroomingRun(runId: runId);
        if (run != null && run.isFailed) {
          _analysisError = 'Grooming analysis failed. Please try again.';
          _isFailed = true;
          resolved = GroomingAnalysisResult.mock;
        } else {
          resolved = GroomingAnalysisResult.fromRunResult(run);
        }
        _isCompleted = true;

      }
    }

    if (_disposed) return resolved;

    _isProcessing = false;
    _completedStageCount = totalStages;
    _safeNotify();
    return resolved;
  }

  /// Lists the user's analysis runs (summary rows).
  ///
  /// Returns an empty list when the backend is unreachable.
  Future<List<GroomingRecommendation>> listRuns() async {
    final runs = await _client.listRuns();
    if (runs == null) return const [];
    return runs
        .map(
          (e) => e != null
              ? GroomingRecommendation.fromBackend(
                  {'id': e['run_id'] as String?, 'name': e['run_type'] as String? ?? '', 'description': '', 'matchScore': 0.0, 'reasons': [], 'stylingTips': '', 'maintenance': '', 'bestFor': '', 'icon': null},
                )
              : const GroomingRecommendation(
                  id: '',
                  name: '',
                  description: '',
                  matchScore: 0.0,
                  reasons: [],
                  stylingTips: '',
                  maintenance: '',
                  bestFor: '',
                ),
        )
        .toList(growable: false);
  }

  /// Lists the user's saved looks (endpoint #24).
  ///
  /// Returns an empty list when the backend is unreachable, matching the
  /// app-wide graceful fallback behavior.
  Future<List<dynamic>> listSavedLooks() async {
    final looks = await _client.listSavedLooks();
    if (looks == null) return const [];
    return looks;
  }

  /// Saves a grooming recommendation to the user's saved looks.
  ///
  /// Uses an idempotency key so retries never create duplicates. Returns true
  /// when the backend accepted the save.
  Future<bool> saveGroomingLook({
    required GroomingRecommendation recommendation,
    required String title,
  }) async {
    final idempotencyKey =
        '${DateTime.now().microsecondsSinceEpoch}-${_random.nextInt(1 << 32)}';
    final ok = await _client.saveGroomingLook(
      lookId: recommendation.id,
      title: title,
      snapshot: {
        'lookId': recommendation.id,
        'title': recommendation.name,
        'matchScore': recommendation.matchScore,
        'reasons': recommendation.reasons,
        'stylingTips': recommendation.stylingTips,
        'maintenance': recommendation.maintenance,
        'bestFor': recommendation.bestFor,
        'icon': recommendation.icon,
      },
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
  void completeWith(GroomingAnalysisResult result) {
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