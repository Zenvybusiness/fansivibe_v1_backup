import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/features/grooming/data/grooming_client.dart';
import 'package:fansivibe/features/grooming/data/grooming_models.dart';
import 'package:fansivibe/features/grooming/data/grooming_service.dart';
import 'package:fansivibe/features/learning/data/models.dart';
import 'package:fansivibe/features/learning/learning_repository.dart';

class _FakeGroomingClient extends GroomingClient {
  String? submitResult;
  GroomingRun? pollResult;
  int submitCalls = 0;

  @override
  Future<String?> submitGroomingAnalysis() async {
    submitCalls++;
    return submitResult;
  }

  @override
  Future<GroomingRun?> pollGroomingRun({required String runId}) async =>
      pollResult;
}

class _FakeLearningRepository implements LearningRepository {
  _FakeLearningRepository({this.faceProfile});

  final FaceProfile? faceProfile;
  final List<LearningSignal> recorded = [];

  @override
  FaceProfile? get face => faceProfile;

  @override
  List<WardrobeEntry> get wardrobe => const [];

  @override
  String? get styleType => null;

  @override
  List<String> get savedLooks => const [];

  @override
  List<String> get preferredOccasions => const [];

  @override
  List<LearningSignal> get signals => recorded;

  @override
  int get styleScore => 0;

  @override
  Future<void> load() async {}

  @override
  void updateItem(String itemId, WardrobeEntry item) {}

  @override
  void addItem(WardrobeEntry item) {}

  @override
  void setFace(FaceProfile face) {}

  @override
  void setStyleType(String styleType) {}

  @override
  void addSavedLook(String title) {}

  @override
  void addPreferredOccasion(String occasion) {}

  @override
  void recordSignal(String type, String label) {
    recorded.add(LearningSignal(type: type, label: label));
  }
}

void main() {
  group('GroomingService.runAnalysis (Phase 28: no face-profile reference)', () {
    test('falls back to mock without a stored face shape (no submit)', () async {
      final client = _FakeGroomingClient();
      final service = GroomingService(client: client);
      addTearDown(service.dispose);

      final result = await service.runAnalysis();

      expect(client.submitCalls, 0);
      expect(result, GroomingAnalysisResult.mock);
      expect(service.completedStageCount, GroomingService.totalStages);
    });

    test('submits with no reference field when style_profile exists', () async {
      final client = _FakeGroomingClient()
        ..submitResult = 'run-1'
        ..pollResult = const GroomingRun(
          runId: 'run-1',
          runType: 'grooming',
          status: 'failed',
          error: {'code': 'PROCESSING_FAILURE'},
        );
      final learning = _FakeLearningRepository(
        faceProfile: const FaceProfile(faceShape: 'Oval'),
      );
      final service = GroomingService(client: client, learning: learning);
      addTearDown(service.dispose);

      final result = await service.runAnalysis();

      // No fake ID exists on the wire — submit takes no arguments.
      expect(client.submitCalls, 1);
      // Failed run surfaces honest error and falls back to mock.
      expect(result, GroomingAnalysisResult.mock);
      expect(service.analysisError, isNotNull);
      expect(service.completedStageCount, GroomingService.totalStages);
    });

    test('falls back to mock when submit fails', () async {
      final client = _FakeGroomingClient()..submitResult = null;
      final learning = _FakeLearningRepository(
        faceProfile: const FaceProfile(faceShape: 'Oval'),
      );
      final service = GroomingService(client: client, learning: learning);
      addTearDown(service.dispose);

      final result = await service.runAnalysis();

      expect(client.submitCalls, 1);
      expect(result, GroomingAnalysisResult.mock);
    });
  });
}
