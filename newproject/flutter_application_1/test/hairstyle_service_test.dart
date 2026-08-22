import 'package:flutter_test/flutter_test.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_client.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_mock_data.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_models.dart';
import 'package:fansivibe/features/hairstyle/domain/hairstyle_service.dart';
import 'package:fansivibe/features/learning/data/models.dart';
import 'package:fansivibe/features/learning/learning_repository.dart';

class _FakeHairstyleClient extends HairstyleClient {
  String? submitResult;
  AnalysisRun? pollResult;
  AnalysisRunPage? listResult;
  bool saveResult = true;
  int submitCalls = 0;
  int saveCalls = 0;
  int listCalls = 0;
  final List<String> savedLookIds = [];
  final List<String> savedTitles = [];

  @override
  Future<String?> submitHairstyleAnalysis({
    required String faceProfileRef,
  }) async {
    submitCalls++;
    return submitResult;
  }

  @override
  Future<AnalysisRun?> pollAnalysisRun({required String runId}) async =>
      pollResult;

  @override
  Future<AnalysisRunPage?> listRuns() async {
    listCalls++;
    return listResult;
  }

  @override
  Future<bool> saveLook({
    required String lookId,
    required String title,
    required Map<String, dynamic> snapshot,
    required String idempotencyKey,
  }) async {
    saveCalls++;
    savedLookIds.add(lookId);
    savedTitles.add(title);
    return saveResult;
  }
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
  void addItem(WardrobeEntry item) {}

  @override
  void setFace(FaceProfile face) {}

  @override
  void setStyleType(String styleType) {}

  @override
  void addSavedLook(String title) {
    recorded.add(LearningSignal(type: 'look_saved', label: title));
  }

  @override
  void addPreferredOccasion(String occasion) {}

  @override
  void recordSignal(String type, String label) {
    recorded.add(LearningSignal(type: type, label: label));
  }
}

Map<String, dynamic> _wireResult() => {
  'appearance': {'faceShape': 'Oval', 'skinTone': 'Warm Medium'},
  'recommendations': {
    'top': {
      'id': 'textured_quiff',
      'name': 'Textured Quiff',
      'description': 'A modern take on the classic quiff.',
      'matchScore': 0.94,
      'reasons': ['Adds volume'],
      'stylingTips': 'Blow-dry upward.',
      'maintenance': 'Medium',
      'bestFor': 'Oval',
    },
    'alternatives': <Map<String, dynamic>>[],
  },
};

void main() {
  group('HairstyleService.runAnalysis', () {
    test('falls back to the offline result without a face profile', () async {
      final client = _FakeHairstyleClient();
      final service = HairstyleService(client: client);
      addTearDown(service.dispose);

      final result = await service.runAnalysis();

      expect(client.submitCalls, 0);
      expect(result.faceShape, HairstyleAnalysisResult.mock.faceShape);
      expect(service.completedStageCount, HairstyleService.totalStages);
      expect(service.isProcessing, isFalse);
    });

    test('submits and maps a completed run', () async {
      final client = _FakeHairstyleClient()
        ..submitResult = 'run-1'
        ..pollResult = AnalysisRun(
          runId: 'run-1',
          runType: 'hairstyle',
          status: 'completed',
          result: _wireResult(),
        );
      final learning = _FakeLearningRepository(
        faceProfile: const FaceProfile(faceShape: 'Oval'),
      );
      final service = HairstyleService(client: client, learning: learning);
      addTearDown(service.dispose);

      final result = await service.runAnalysis();

      expect(client.submitCalls, 1);
      expect(result.faceShape, 'Oval');
      expect(result.topRecommendation.name, 'Textured Quiff');
      expect(result.topRecommendation.matchScore, 0.94);
      expect(service.completedStageCount, HairstyleService.totalStages);
    });

    test('falls back to the offline result when submit fails', () async {
      final client = _FakeHairstyleClient()..submitResult = null;
      final learning = _FakeLearningRepository(
        faceProfile: const FaceProfile(faceShape: 'Oval'),
      );
      final service = HairstyleService(client: client, learning: learning);
      addTearDown(service.dispose);

      final result = await service.runAnalysis();

      expect(client.submitCalls, 1);
      expect(result.faceShape, HairstyleAnalysisResult.mock.faceShape);
    });

    test('falls back to the offline result when polling fails', () async {
      final client = _FakeHairstyleClient()
        ..submitResult = 'run-1'
        ..pollResult = null;
      final learning = _FakeLearningRepository(
        faceProfile: const FaceProfile(faceShape: 'Oval'),
      );
      final service = HairstyleService(client: client, learning: learning);
      addTearDown(service.dispose);

      final result = await service.runAnalysis();

      expect(result.faceShape, HairstyleAnalysisResult.mock.faceShape);
      expect(service.analysisError, isNull);
    });

    test('surfaces the typed error when the run failed', () async {
      final client = _FakeHairstyleClient()
        ..submitResult = 'run-1'
        ..pollResult = AnalysisRun(
          runId: 'run-1',
          runType: 'hairstyle',
          status: 'failed',
          error: const {
            'code': 'PROCESSING_FAILURE',
            'message': "We couldn't finish this request.",
            'details': {'run_id': 'run-1'},
          },
        );
      final learning = _FakeLearningRepository(
        faceProfile: const FaceProfile(faceShape: 'Oval'),
      );
      final service = HairstyleService(client: client, learning: learning);
      addTearDown(service.dispose);

      final result = await service.runAnalysis();

      expect(client.submitCalls, 1);
      expect(result.faceShape, HairstyleAnalysisResult.mock.faceShape);
      expect(service.analysisError, "We couldn't finish this request.");
    });

    test('clears the previous error when a new run starts', () async {
      final client = _FakeHairstyleClient()
        ..submitResult = 'run-1'
        ..pollResult = AnalysisRun(
          runId: 'run-1',
          runType: 'hairstyle',
          status: 'failed',
          error: const {
            'code': 'PROCESSING_FAILURE',
            'message': "We couldn't finish this request.",
          },
        );
      final learning = _FakeLearningRepository(
        faceProfile: const FaceProfile(faceShape: 'Oval'),
      );
      final service = HairstyleService(client: client, learning: learning);
      addTearDown(service.dispose);

      await service.runAnalysis();
      expect(service.analysisError, isNotNull);

      client.pollResult = AnalysisRun(
        runId: 'run-2',
        runType: 'hairstyle',
        status: 'completed',
        result: _wireResult(),
      );
      final second = await service.runAnalysis();

      expect(second.topRecommendation.name, 'Textured Quiff');
      expect(service.analysisError, isNull);
    });
  });

  group('HairstyleService.listRuns', () {
    test('returns the run list from the client', () async {
      final client = _FakeHairstyleClient()
        ..listResult = AnalysisRunPage(
          items: [
            AnalysisRun(
              runId: 'run-1',
              runType: 'hairstyle',
              status: 'completed',
            ),
          ],
          page: 1,
          pageSize: 20,
          total: 1,
        );
      final service = HairstyleService(client: client);
      addTearDown(service.dispose);

      final runs = await service.listRuns();

      expect(client.listCalls, 1);
      expect(runs.single.runId, 'run-1');
    });

    test('returns an empty list when the client fails', () async {
      final client = _FakeHairstyleClient()..listResult = null;
      final service = HairstyleService(client: client);
      addTearDown(service.dispose);

      final runs = await service.listRuns();

      expect(runs, isEmpty);
    });
  });

  group('HairstyleService.saveLook', () {
    test('saves and records a look_saved signal on success', () async {
      final client = _FakeHairstyleClient();
      final learning = _FakeLearningRepository();
      final service = HairstyleService(client: client, learning: learning);
      addTearDown(service.dispose);

      final ok = await service.saveLook(
        recommendation: HairstyleAnalysisResult.mock.topRecommendation,
        title: 'Textured Quiff',
      );

      expect(ok, isTrue);
      expect(client.saveCalls, 1);
      expect(client.savedLookIds, ['textured_quiff']);
      expect(client.savedTitles, ['Textured Quiff']);
      expect(learning.recorded.single.type, 'look_saved');
    });

    test('does not record a signal when the save fails', () async {
      final client = _FakeHairstyleClient()..saveResult = false;
      final learning = _FakeLearningRepository();
      final service = HairstyleService(client: client, learning: learning);
      addTearDown(service.dispose);

      final ok = await service.saveLook(
        recommendation: HairstyleAnalysisResult.mock.topRecommendation,
        title: 'Textured Quiff',
      );

      expect(ok, isFalse);
      expect(learning.recorded, isEmpty);
    });
  });
}
