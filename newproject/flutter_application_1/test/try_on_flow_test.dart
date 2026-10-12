import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image_picker/image_picker.dart';

import 'package:fansivibe/features/try_on/data/try_on_models.dart';
import 'package:fansivibe/features/try_on/data/try_on_repository.dart';
import 'package:fansivibe/features/try_on/presentation/try_on_screen.dart';

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
  List<String> garmentIds = const <String>['wardrobe-1'],
}) async {
  await tester.pumpWidget(
    MaterialApp(
      home: TryOnScreen(
        outfitSource: 'today',
        garmentIds: garmentIds,
        title: 'Test Look',
        tryOnRepository: repository,
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
      await tester.tap(find.byType(Checkbox));
      await tester.pumpAndSettle();
      await tapVisible(tester, find.text('Preview Try-On (Test Data)'));
      expect(find.text('TEST DATA — NOT AI TRY-ON'), findsOneWidget);
      expect(find.textContaining('not an AI-generated'), findsOneWidget);
      expect(find.text('wardrobe-1'), findsOneWidget);
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
      await tester.tap(find.byType(Checkbox));
      await tester.pumpAndSettle();
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
  });
}
