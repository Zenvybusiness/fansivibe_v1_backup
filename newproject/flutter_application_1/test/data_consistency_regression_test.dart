import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:fansivibe/features/events/data/event_models.dart';
import 'package:fansivibe/features/events/data/events_client.dart';
import 'package:fansivibe/features/grooming/data/grooming_client.dart';
import 'package:fansivibe/features/grooming/data/grooming_models.dart';
import 'package:fansivibe/features/grooming/data/grooming_service.dart';
import 'package:fansivibe/features/learning/data/models.dart';
import 'package:fansivibe/features/learning/learning_repository.dart';
import 'package:fansivibe/features/outfit_builder/data/outfit_models.dart';
import 'package:fansivibe/features/outfit_builder/data/outfit_repository.dart';
import 'package:fansivibe/features/outfit_builder/presentation/outfit_generation_screen.dart';

/// DATA CONSISTENCY milestone regression tests (P5/P6/P0-P11).
///
/// - P6: backend `EventSummary` list cards (no createdAt/updatedAt) parse.
/// - P5: event context survives into the generation screen.
/// - P0/P11: grooming mock fallbacks are flagged, never silent success.

/// Backend `EventSummary` shape: id/title/eventType/eventDate/time only.
Map<String, dynamic> _summaryRow() => {
  'id': '78ff3686-c950-4cd6-84c3-7e18d6634dfa',
  'title': 'Company Gala',
  'eventType': 'formal',
  'eventDate': '2030-08-15',
  'time': '19:00',
};

class _FakeGroomingClient extends GroomingClient {
  String? submitResult;
  GroomingRun? pollResult;

  @override
  Future<String?> submitGroomingAnalysis() async => submitResult;

  @override
  Future<GroomingRun?> pollGroomingRun({required String runId}) async =>
      pollResult;
}

class _FakeLearning implements LearningRepository {
  _FakeLearning({this.faceProfile});

  final FaceProfile? faceProfile;

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
  List<LearningSignal> get signals => const [];

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
  void setStyleType(String value) {}

  @override
  void addSavedLook(String title) {}

  @override
  void addPreferredOccasion(String occasion) {}

  @override
  void recordSignal(String type, String label) {}
}

class _EmptyOutfitRepository implements OutfitBuilderRepository {
  @override
  Future<OutfitResult> generateOutfit({
    required String occasion,
    required String mood,
    required String fit,
    required String colorPalette,
    String? seed,
  }) async => const OutfitResult.noneAvailable();

  @override
  Future<SavedOutfit?> saveOutfit({
    String? lookId,
    required String title,
    required Map<String, dynamic> snapshot,
    required String idempotencyKey,
  }) async => null;
}

void main() {
  group('P6 events list-card shape', () {
    test('EventItem parses a summary row without timestamps', () {
      final item = EventItem.fromJson(_summaryRow());

      expect(item.id, '78ff3686-c950-4cd6-84c3-7e18d6634dfa');
      expect(item.title, 'Company Gala');
      expect(item.eventType, 'formal');
      expect(item.eventDate, '2030-08-15');
      expect(item.eventTime, '19:00');
      expect(item.location, isNull);
      expect(item.notes, isNull);
    });

    test('non-empty list page with summary rows parses (was null)', () async {
      final client = EventsClient(
        client: MockClient(
          (_) async => http.Response(
            jsonEncode({
              'items': [_summaryRow()],
              'page': 1,
              'page_size': 20,
              'total': 1,
            }),
            200,
          ),
        ),
      );

      final page = await client.listEvents();

      expect(page, isNotNull);
      expect(page!.isEmpty, isFalse);
      expect(page.items.single.title, 'Company Gala');
    });
  });

  group('P0/P11 grooming fail-closed provenance', () {
    test('no face profile flags mock instead of silent success', () async {
      final service = GroomingService(client: _FakeGroomingClient());
      addTearDown(service.dispose);

      final result = await service.runAnalysis();

      expect(result, GroomingAnalysisResult.mock);
      expect(service.isMockResult, isTrue);
      expect(service.analysisError, isNotNull);
      expect(service.result, isNotNull);
    });

    test('unreachable submit flags mock with an error', () async {
      final client = _FakeGroomingClient()..submitResult = null;
      final service = GroomingService(
        client: client,
        learning: _FakeLearning(
          faceProfile: const FaceProfile(faceShape: 'Oval'),
        ),
      );
      addTearDown(service.dispose);

      await service.runAnalysis();

      expect(service.isMockResult, isTrue);
      expect(service.analysisError, isNotNull);
    });
  });

  group('P5 event context reaches generation', () {
    testWidgets('shows Styling-for chip when eventTitle is passed', (
      tester,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: OutfitGenerationScreen(
            occasion: 'formal',
            mood: 'classic',
            fit: 'tailored',
            colorPalette: 'warm',
            eventId: '78ff3686-c950-4cd6-84c3-7e18d6634dfa',
            eventTitle: 'Company Gala',
            outfitRepository: _EmptyOutfitRepository(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.textContaining('Styling for: Company Gala'), findsWidgets);
    });
  });
}
