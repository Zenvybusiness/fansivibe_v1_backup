import 'dart:async';

import 'package:fansivibe/features/hairstyle/data/hairstyle_mock_data.dart';
import 'package:fansivibe/features/hairstyle/domain/hairstyle_service.dart';

/// A [HairstyleService] whose analysis completes on demand, so widget tests
/// can control when the processing screen advances.
class ControllableHairstyleService extends HairstyleService {
  final Completer<HairstyleAnalysisResult> _completer =
      Completer<HairstyleAnalysisResult>();
  bool started = false;
  bool finished = false;

  @override
  Future<HairstyleAnalysisResult> runAnalysis() {
    started = true;
    return _completer.future;
  }

  void finish() {
    finished = true;
    completeWith(HairstyleAnalysisResult.mock);
    _completer.complete(HairstyleAnalysisResult.mock);
  }

  void failWith(String message) {
    finished = true;
    setAnalysisError(message);
    _completer.complete(HairstyleAnalysisResult.mock);
  }
}

/// A [HairstyleService] whose [saveLook] returns a controllable result, so
/// widget tests can assert the save UI state update (success/failure snackbar).
class StubSaveHairstyleService extends HairstyleService {
  StubSaveHairstyleService({this.saveResult = true});

  bool saveResult;
  int saveCalls = 0;
  final List<String> savedLookIds = [];
  final List<String> savedTitles = [];

  @override
  Future<bool> saveLook({
    required HairstyleRecommendation recommendation,
    required String title,
  }) async {
    saveCalls++;
    savedLookIds.add(recommendation.id);
    savedTitles.add(title);
    return saveResult;
  }
}
