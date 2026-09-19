import 'dart:async';
import 'dart:typed_data';

import 'package:fansivibe/features/hairstyle/data/hairstyle_mock_data.dart';
import 'package:fansivibe/features/hairstyle/domain/hairstyle_service.dart';

/// A [HairstyleService] whose analysis completes on demand, so widget tests
/// can control when the processing screen advances.
class ControllableHairstyleService extends HairstyleService {
  final Completer<HairstyleAnalysisResult> _completer =
      Completer<HairstyleAnalysisResult>();
  bool started = false;
  bool finished = false;

  /// Image bytes the processing screen handed over (null on skip).
  Uint8List? receivedImageBytes;

  @override
  Future<HairstyleAnalysisResult> runAnalysis({
    Uint8List? imageBytes,
    String? imageFilename,
    String? imageContentType,
  }) {
    started = true;
    receivedImageBytes = imageBytes;
    return _completer.future;
  }

  void finish() {
    finished = true;
    // A real (non-mock) parsed result so the processing screen forwards
    // it as genuine backend content (identical() must stay false).
    final real = HairstyleAnalysisResult.fromRunResult(const {
      'appearance': {
        'faceShape': 'Oval',
        'skinTone': 'Warm Medium',
        'styleType': 'Modern Classic',
      },
      'recommendations': {
        'top': {
          'id': 'textured_quiff',
          'name': 'Textured Quiff',
          'description': 'A real backend-derived recommendation.',
          'matchScore': 0.94,
          'reasons': ['Grounded reason'],
          'stylingTips': '',
          'maintenance': '',
          'bestFor': '',
        },
        'alternatives': <dynamic>[],
      },
    });
    completeWith(real);
    _completer.complete(real);
  }

  void failWith(String message) {
    finished = true;
    setAnalysisError(message);
    _completer.complete(HairstyleAnalysisResult.mock);
  }

  /// Multi-angle captures handed over by the processing screen.
  List<Uint8List>? receivedAngleBytes;

  /// Completed multi-angle calls.
  int multiAngleCalls = 0;

  @override
  Future<HairstyleAnalysisResult?> runMultiAngleAnalysis({
    required Uint8List frontBytes,
    String? frontName,
    required Uint8List leftBytes,
    String? leftName,
    required Uint8List rightBytes,
    String? rightName,
  }) async {
    multiAngleCalls++;
    receivedAngleBytes = [frontBytes, leftBytes, rightBytes];
    final real = HairstyleAnalysisResult.fromRunResult(const {
      'appearance': {'faceShape': 'Oval'},
      'recommendations': {
        'top': {'id': 'textured_quiff', 'name': 'Textured Quiff'},
        'alternatives': <dynamic>[],
      },
    });
    completeWith(real);
    return real;
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
