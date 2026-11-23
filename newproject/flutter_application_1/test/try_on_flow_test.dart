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

class FakeTryOnRepository implements TryOnRepository {
  FakeTryOnRepository({
    this.submitResult = const TryOnSubmitResult(
      job: TryOnJob(jobId: 'job-1', state: TryOnJobState.processing, isMock: true),
    ),
    this.pollResult = const TryOnJobStatus(
      jobId: 'job-1',
      state: TryOnJobState.completed,
      progress: 100,
      isMock: true,
    ),
  });

  int submits = 0;
  TryOnSubmitResult submitResult;
  TryOnJobStatus? pollResult;

  @override
  Future<TryOnSubmitResult> submitMockTryOn({
    required Uint8List personBytes,
    String personFilename = 'tryon_person.jpg',
    required String outfitSource,
    required List<String> garmentIds,
    required bool consentAccepted,
    required String idempotencyKey,
  }) async {
    submits++;
    return submitResult;
  }

  @override
  Future<TryOnJobStatus?> getJobStatus(String jobId) async => pollResult;

  @override
  Future<Uint8List?> getJobImage(String jobId) async =>
      Uint8List.fromList(<int>[1, 2, 3]);

  int retries = 0;
  int cancels = 0;
  int deletes = 0;

  @override
  Future<TryOnSubmitResult> retryJob(String jobId) async {
    retries++;
    return submitResult;
  }

  @override
  Future<TryOnJobStatus?> cancelJob(String jobId) async {
    cancels++;
    return const TryOnJobStatus(
      jobId: 'job-1',
      state: TryOnJobState.cancelled,
      progress: 0,
      isMock: true,
    );
  }

  @override
  Future<bool> deleteJob(String jobId) async {
    deletes++;
    return true;
  }
}

Future<XFile?> fakePickImage(ImageSource source) async {
  return XFile.fromData(
    Uint8List.fromList(List<int>.generate(64, (i) => i)),
    mimeType: 'image/jpeg',
    name: 'person.jpg',
  );
}

Future<void> pumpScreen(
  WidgetTester tester, {
  required FakeTryOnRepository repository,
  WardrobeRepository? wardrobeRepository,
  List<String> garmentIds = const <String>['wardrobe-1'],
}) async {
  await tester.pumpWidget(
    MaterialApp(
      home: TryOnScreen(
        outfitSource: 'today',
        garmentIds: garmentIds,
        title: 'Test Look',
        tryOnRepository: repository,
        wardrobeRepository: wardrobeRepository ?? FakeWardrobeRepository(),
        pickImage: fakePickImage,
      ),
    ),
  );
  await tester.pumpAndSettle();
}

/// Taps a button that may sit below the fold of the scroll view.
Future<void> tapVisible(WidgetTester tester, Finder finder) async {
  await tester.scrollUntilVisible(finder, 200);
  await tester.pumpAndSettle();
  await tester.tap(finder);
  await tester.pumpAndSettle();
}

void main() {
  group('TryOnScreen Stage F0', () {
    testWidgets('every view carries the TEST DATA banner', (tester) async {
      await pumpScreen(tester, repository: FakeTryOnRepository());
      expect(find.text('TEST DATA — NOT AI TRY-ON'), findsOneWidget);
    });

    testWidgets('submit without consent is blocked honestly', (tester) async {
      final repository = FakeTryOnRepository();
      await pumpScreen(tester, repository: repository);
      await tester.tap(find.text('Choose Photo'));
      await tester.pumpAndSettle();
      await tapVisible(tester, find.text('Preview Try-On (Test Data)'));
      expect(repository.submits, 0);
      expect(
        find.text('Please accept the test-preview consent first.'),
        findsOneWidget,
      );
    });

    testWidgets('consent + photo reaches done with mock label', (tester) async {
      await pumpScreen(tester, repository: FakeTryOnRepository());
      await tester.tap(find.text('Choose Photo'));
      await tester.pumpAndSettle();
      await tapVisible(tester, find.byType(Checkbox));
      await tapVisible(tester, find.text('Preview Try-On (Test Data)'));
      expect(find.text('TEST DATA — NOT AI TRY-ON'), findsOneWidget);
      expect(find.textContaining('not an AI-generated'), findsOneWidget);
      expect(find.text('Navy Blazer'), findsOneWidget);
      // No save/share/export path exists for mock output.
      expect(find.text('Save Look'), findsNothing);
      expect(find.text('Share'), findsNothing);
    });

    testWidgets('rejection shows failure with retry', (tester) async {
      final repository = FakeTryOnRepository(
        submitResult: const TryOnSubmitResult(
          failure: TryOnFailure.quotaExceeded,
        ),
      );
      await pumpScreen(tester, repository: repository);
      await tester.tap(find.text('Choose Photo'));
      await tester.pumpAndSettle();
      await tapVisible(tester, find.byType(Checkbox));
      await tapVisible(tester, find.text('Preview Try-On (Test Data)'));
      expect(find.text('Daily preview limit reached. Please try again tomorrow.'), findsOneWidget);
      expect(find.text('Try Again'), findsOneWidget);
      expect(find.text('TEST DATA — NOT AI TRY-ON'), findsOneWidget);
    });

    testWidgets('empty outfit fails closed', (tester) async {
      await pumpScreen(
        tester,
        repository: FakeTryOnRepository(),
        garmentIds: const <String>[],
      );
      expect(find.text('No outfit selected. Go back and pick a look.'), findsOneWidget);
      expect(find.text('Preview Try-On (Test Data)'), findsNothing);
    });

    testWidgets('done state displays delete result button and calls deleteJob', (tester) async {
      final repository = FakeTryOnRepository();
      await pumpScreen(tester, repository: repository);
      await tester.tap(find.text('Choose Photo'));
      await tester.pumpAndSettle();
      await tapVisible(tester, find.byType(Checkbox));
      await tapVisible(tester, find.text('Preview Try-On (Test Data)'));

      expect(find.text('Delete Result'), findsOneWidget);
      await tapVisible(tester, find.text('Delete Result'));
      expect(repository.deletes, 1);
    });

    testWidgets('non-mock completed job displays truthful AI banner', (tester) async {
      final repository = FakeTryOnRepository(
        submitResult: const TryOnSubmitResult(
          job: TryOnJob(jobId: 'job-real', state: TryOnJobState.processing, isMock: false),
        ),
        pollResult: const TryOnJobStatus(
          jobId: 'job-real',
          state: TryOnJobState.completed,
          progress: 100,
          isMock: false,
        ),
      );
      await pumpScreen(tester, repository: repository);
      await tester.tap(find.text('Choose Photo'));
      await tester.pumpAndSettle();
      await tapVisible(tester, find.byType(Checkbox));
      await tapVisible(tester, find.text('Preview Try-On (Test Data)'));

      expect(find.text('AI Try-On Result'), findsOneWidget);
      expect(find.textContaining('does not represent physical garment sizing'), findsOneWidget);
    });

    testWidgets('retry button in failure state triggers repository retryJob', (tester) async {
      final repository = FakeTryOnRepository(
        submitResult: const TryOnSubmitResult(
          job: TryOnJob(jobId: 'job-f', state: TryOnJobState.processing, isMock: true),
        ),
        pollResult: const TryOnJobStatus(
          jobId: 'job-f',
          state: TryOnJobState.failed,
          progress: 0,
          isMock: true,
          errorMessage: 'CUDA out of memory',
        ),
      );
      await pumpScreen(tester, repository: repository);
      await tester.tap(find.text('Choose Photo'));
      await tester.pumpAndSettle();
      await tapVisible(tester, find.byType(Checkbox));
      await tapVisible(tester, find.text('Preview Try-On (Test Data)'));

      expect(find.text('CUDA out of memory'), findsOneWidget);
      expect(find.text('Try Again'), findsOneWidget);

      await tapVisible(tester, find.text('Try Again'));
      expect(repository.retries, 1);
    });
  });
}
