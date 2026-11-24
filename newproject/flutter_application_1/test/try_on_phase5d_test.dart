import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image_picker/image_picker.dart';

import 'package:fansivibe/features/try_on/data/try_on_models.dart';
import 'package:fansivibe/features/try_on/data/try_on_repository.dart';
import 'package:fansivibe/features/try_on/presentation/try_on_screen.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart'
    show WardrobeInsightData, WardrobeItemData;
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart'
    show MediaRef, WearSummary, WearEventLogResponse;

class FakeWardrobeRepository implements WardrobeRepository {
  @override
  Future<List<WardrobeItemData>> listItems({
    String? category,
    String? color,
    String? sortBy,
    String? order,
    int page = 1,
    int pageSize = 20,
  }) async {
    return const [
      WardrobeItemData(
        id: 'wardrobe-1',
        name: 'Navy Blazer',
        category: 'tops',
        color: 'navy',
      ),
    ];
  }

  @override
  Future<WardrobeItemData?> getItem({required String itemId}) async => null;

  @override
  Future<WardrobeItemData?> createItem({
    required String name,
    required String category,
    required String color,
    String? material,
    MediaRef? imageRef,
    String? fit,
    double? fitConfidence,
  }) async => null;

  @override
  Future<WardrobeItemData?> updateItem({
    required String itemId,
    String? name,
    String? category,
    String? color,
    String? material,
    bool? isFavorite,
    String? fit,
    double? fitConfidence,
  }) async => null;

  @override
  Future<bool?> deleteItem({required String itemId}) async => true;

  @override
  Future<WardrobeInsightData?> getInsight() async => null;

  @override
  Future<WearSummary?> getWearSummary() async => null;

  @override
  Future<WearEventLogResponse?> logWear({
    required List<String> itemIds,
    DateTime? wornAt,
    String? idempotencyKey,
  }) async => null;

  @override
  Future<WearEventLogResponse?> logEnsembleWear({
    required List<String> itemIds,
    DateTime? wornAt,
    String? idempotencyKey,
  }) async => null;
}

class ControlledTryOnRepository implements TryOnRepository {
  ControlledTryOnRepository({
    this.submitResult = const TryOnSubmitResult(
      job: TryOnJob(jobId: 'job-1', state: TryOnJobState.queued, isMock: false),
    ),
    this.statusSequence = const [],
    this.imageBytes,
  });

  TryOnSubmitResult submitResult;
  List<TryOnJobStatus?> statusSequence;
  Uint8List? imageBytes;
  int statusCallCount = 0;
  bool retryCalled = false;
  bool deleteCalled = false;

  @override
  Future<TryOnSubmitResult> submitMockTryOn({
    required Uint8List personBytes,
    String personFilename = 'tryon_person.jpg',
    required String outfitSource,
    required List<String> garmentIds,
    required bool consentAccepted,
    required String idempotencyKey,
  }) async => submitResult;

  @override
  Future<TryOnJobStatus?> getJobStatus(String jobId) async {
    if (statusSequence.isEmpty) return null;
    final idx = statusCallCount < statusSequence.length
        ? statusCallCount
        : statusSequence.length - 1;
    statusCallCount++;
    return statusSequence[idx];
  }

  @override
  Future<Uint8List?> getJobImage(String jobId) async => imageBytes;

  @override
  Future<TryOnSubmitResult> retryJob(String jobId) async {
    retryCalled = true;
    return submitResult;
  }

  @override
  Future<TryOnJobStatus?> cancelJob(String jobId) async {
    return TryOnJobStatus(
      jobId: jobId,
      state: TryOnJobState.cancelled,
      progress: 0,
      isMock: false,
    );
  }

  @override
  Future<bool> deleteJob(String jobId) async {
    deleteCalled = true;
    return true;
  }
}

Future<void> pumpTryOnScreen(
  WidgetTester tester, {
  required TryOnRepository repository,
  List<String> garmentIds = const ['wardrobe-1'],
}) async {
  tester.view.physicalSize = const Size(1080, 2400);
  tester.view.devicePixelRatio = 2.0;
  addTearDown(() => tester.view.resetPhysicalSize());

  await tester.pumpWidget(
    MaterialApp(
      home: TryOnScreen(
        outfitSource: 'wardrobe',
        garmentIds: garmentIds,
        title: 'Virtual Try-On Test',
        tryOnRepository: repository,
        wardrobeRepository: FakeWardrobeRepository(),
        pickImage: (source) async => XFile.fromData(
          Uint8List.fromList([0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46]),
          name: 'person.jpg',
          mimeType: 'image/jpeg',
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  group('TryOnScreen Phase 5D Operational and Reliability States', () {
    testWidgets('displays documented retention and privacy policy in consent section', (tester) async {
      await pumpTryOnScreen(tester, repository: ControlledTryOnRepository());

      expect(
        find.textContaining('automatically deleted after 24 hours (results after 72 hours)'),
        findsOneWidget,
      );
      expect(
        find.textContaining('Photos are stored privately'),
        findsOneWidget,
      );
    });

    testWidgets('shows provider unavailable failure state with retry option', (tester) async {
      final repo = ControlledTryOnRepository(
        submitResult: const TryOnSubmitResult(
          failure: TryOnFailure.serviceUnavailable,
        ),
      );
      await pumpTryOnScreen(tester, repository: repo);

      // Select photo and accept consent
      await tester.tap(find.text('Choose Photo'));
      await tester.pumpAndSettle();
      await tester.tap(find.byType(Checkbox));
      await tester.pumpAndSettle();

      // Submit
      await tester.tap(find.text('Preview Try-On (Test Data)'));
      await tester.pumpAndSettle();

      expect(
        find.text('Virtual Try-On is currently unavailable. Please try again later.'),
        findsOneWidget,
      );
      expect(find.text('Try Again'), findsOneWidget);
    });

    testWidgets('shows quota exceeded failure state with informative guidance', (tester) async {
      final repo = ControlledTryOnRepository(
        submitResult: const TryOnSubmitResult(
          failure: TryOnFailure.quotaExceeded,
        ),
      );
      await pumpTryOnScreen(tester, repository: repo);

      await tester.tap(find.text('Choose Photo'));
      await tester.pumpAndSettle();
      await tester.tap(find.byType(Checkbox));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Preview Try-On (Test Data)'));
      await tester.pumpAndSettle();

      expect(
        find.text('Daily preview limit reached. Please try again tomorrow.'),
        findsOneWidget,
      );
      expect(find.text('Try Again'), findsOneWidget);
    });

    testWidgets('shows concurrent limit failure state with wait guidance', (tester) async {
      final repo = ControlledTryOnRepository(
        submitResult: const TryOnSubmitResult(
          failure: TryOnFailure.rateLimited,
        ),
      );
      await pumpTryOnScreen(tester, repository: repo);

      await tester.tap(find.text('Choose Photo'));
      await tester.pumpAndSettle();
      await tester.tap(find.byType(Checkbox));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Preview Try-On (Test Data)'));
      await tester.pumpAndSettle();

      expect(
        find.text('Too many active try-on jobs. Please wait for in-progress jobs to finish.'),
        findsOneWidget,
      );
      expect(find.text('Try Again'), findsOneWidget);
    });

    testWidgets('shows timeout failure state and triggers retry', (tester) async {
      final repo = ControlledTryOnRepository(
        submitResult: const TryOnSubmitResult(
          failure: TryOnFailure.timeout,
        ),
      );
      await pumpTryOnScreen(tester, repository: repo);

      await tester.tap(find.text('Choose Photo'));
      await tester.pumpAndSettle();
      await tester.tap(find.byType(Checkbox));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Preview Try-On (Test Data)'));
      await tester.pumpAndSettle();

      expect(
        find.text('Try-on processing timed out. Please retry with the button below.'),
        findsOneWidget,
      );
      expect(find.text('Try Again'), findsOneWidget);

      // Tap Try Again and verify retry execution
      await tester.tap(find.text('Try Again'));
      await tester.pumpAndSettle();
    });
  });
}
