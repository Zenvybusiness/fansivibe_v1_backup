import 'dart:async';

import 'package:fansivibe/features/hairstyle/data/hairstyle_mock_data.dart';
import 'package:fansivibe/features/hairstyle/domain/hairstyle_service.dart';

/// A [HairstyleService] whose analysis completes on demand, so widget tests
/// can control when the processing screen advances.
class ControllableHairstyleService extends HairstyleService {
  final Completer<HairstyleAnalysisResult> _completer = Completer<
    HairstyleAnalysisResult
  >();
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
}
