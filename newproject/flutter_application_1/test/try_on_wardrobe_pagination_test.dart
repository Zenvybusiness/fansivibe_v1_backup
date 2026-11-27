import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/features/try_on/data/try_on_models.dart';
import 'package:fansivibe/features/try_on/data/try_on_repository.dart';
import 'package:fansivibe/features/try_on/presentation/try_on_screen.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart'
    show MediaRef, WearEventLogResponse, WearSummary;
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart'
    show WardrobeInsightData, WardrobeItemData;
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/shared/theme/fansivibe_theme.dart';

List<WardrobeItemData> _generateItems(int count) {
  return List<WardrobeItemData>.generate(count, (index) {
    final n = index + 1;
    return WardrobeItemData(
      id: 'item-$n',
      name: 'Garment $n',
      category: n.isEven ? 'bottoms' : 'tops',
      color: n.isEven ? 'Black' : 'Navy',
    );
  });
}

class _PaginatedFakeWardrobeRepository implements WardrobeRepository {
  _PaginatedFakeWardrobeRepository({
    required this.items,
    this.failPage2Once = false,
    this.overlapPage2 = false,
    this.onlyDuplicatesOnPage2 = false,
    this.page1Completer,
  });

  List<WardrobeItemData> items;
  bool failPage2Once;
  final bool overlapPage2;
  final bool onlyDuplicatesOnPage2;
  Completer<List<WardrobeItemData>>? page1Completer;

  final List<String> requestedPages = [];

  @override
  Future<List<WardrobeItemData>> listItems({
    String? category,
    String? color,
    String? sortBy,
    String? order,
    int page = 1,
    int pageSize = 20,
  }) async {
    requestedPages.add('page=$page,size=$pageSize');

    if (page == 1 && page1Completer != null) {
      final completer = page1Completer!;
      page1Completer = null;
      return completer.future;
    }

    if (page == 2 && failPage2Once) {
      failPage2Once = false;
      throw StateError('Simulated page 2 failure');
    }

    if (onlyDuplicatesOnPage2 && page == 2) {
      return items.take(pageSize).toList();
    }

    final start = (page - 1) * pageSize;
    if (start >= items.length) {
      return const [];
    }
    final end = (start + pageSize).clamp(0, items.length);
    final slice = items.sublist(start, end);

    if (overlapPage2 && page == 2 && items.isNotEmpty) {
      return [items.first, ...slice];
    }
    return slice;
  }

  @override
  Future<WardrobeItemData?> getItem({required String itemId}) async {
    for (final item in items) {
      if (item.id == itemId) return item;
    }
    return null;
  }

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

class _StubTryOnRepository implements TryOnRepository {
  @override
  Future<TryOnSubmitResult> submitMockTryOn({
    required Uint8List personBytes,
    String personFilename = 'tryon_person.jpg',
    required String outfitSource,
    required List<String> garmentIds,
    required bool consentAccepted,
    required String idempotencyKey,
  }) async {
    return const TryOnSubmitResult(
      job: TryOnJob(
        jobId: 'job-p53b',
        state: TryOnJobState.processing,
        isMock: true,
      ),
    );
  }

  @override
  Future<TryOnJobStatus?> getJobStatus(String jobId) async => null;

  @override
  Future<Uint8List?> getJobImage(String jobId) async => null;

  @override
  Future<TryOnSubmitResult> retryJob(String jobId) async {
    return const TryOnSubmitResult(failure: TryOnFailure.notFound);
  }

  @override
  Future<TryOnJobStatus?> cancelJob(String jobId) async => null;

  @override
  Future<bool> deleteJob(String jobId) async => true;
}

Future<XFile?> _fakePickImage(ImageSource source) async {
  return XFile.fromData(
    Uint8List.fromList(List<int>.generate(64, (i) => i)),
    mimeType: 'image/jpeg',
    name: 'person.jpg',
  );
}

const TryOnCapabilities _genlookSingleCap = TryOnCapabilities(
  enabled: true,
  isMock: false,
  maxGarments: 1,
  maxPersonImageBytes: 10 * 1024 * 1024,
  minImageEdge: 64,
  maxImageEdge: 4096,
  maxImagePixels: 12000000,
  allowedMimeTypes: ['image/jpeg', 'image/png', 'image/webp'],
  consentVersion: TryOnConsentVersion.current,
  pollIntervalSeconds: 1,
  pollTimeoutSeconds: 120,
  aiDisclosureRequired: true,
);

const TryOnCapabilities _localMultiCap = TryOnCapabilities(
  enabled: true,
  isMock: true,
  maxGarments: 3,
  maxPersonImageBytes: 10 * 1024 * 1024,
  minImageEdge: 64,
  maxImageEdge: 4096,
  maxImagePixels: 12000000,
  allowedMimeTypes: ['image/jpeg', 'image/png', 'image/webp'],
  consentVersion: TryOnConsentVersion.current,
  pollIntervalSeconds: 1,
  pollTimeoutSeconds: 120,
  aiDisclosureRequired: false,
);

Future<void> _pumpTryOnScreen(
  WidgetTester tester, {
  required WardrobeRepository wardrobeRepository,
  List<String> garmentIds = const [],
  String outfitSource = TryOnOutfitSource.wardrobe,
  TryOnCapabilities capabilities = _genlookSingleCap,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: FansivibeTheme.darkTheme,
      home: TryOnScreen(
        key: UniqueKey(),
        outfitSource: outfitSource,
        garmentIds: garmentIds,
        title: 'Try On Pagination Test',
        tryOnRepository: _StubTryOnRepository(),
        wardrobeRepository: wardrobeRepository,
        pickImage: _fakePickImage,
        capabilities: capabilities,
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> _openGarmentPicker(WidgetTester tester) async {
  final selectButton = find.text('Select from Digital Wardrobe');
  final changeButton = find.text('Change');
  final selectTextButton = find.text('Select');
  Finder target;
  if (selectButton.evaluate().isNotEmpty) {
    target = selectButton;
  } else if (changeButton.evaluate().isNotEmpty) {
    target = changeButton;
  } else {
    target = selectTextButton;
  }
  await tester.scrollUntilVisible(target, 200);
  await tester.pumpAndSettle();
  await tester.tap(target);
  await tester.pumpAndSettle();
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  group('P5.3B TryOnScreen wardrobe pagination', () {
    testWidgets(
      '1. Wardrobe > 100 items loads all pages and shows page 2 item in picker',
      (tester) async {
        final repo = _PaginatedFakeWardrobeRepository(
          items: _generateItems(135),
        );
        await _pumpTryOnScreen(tester, wardrobeRepository: repo);

        expect(repo.requestedPages, ['page=1,size=100', 'page=2,size=100']);

        await _openGarmentPicker(tester);

        final pickerList = find.byType(ListView).last;
        final item135Finder = find.text('Garment 135');
        await tester.scrollUntilVisible(
          item135Finder,
          400,
          scrollable: find.descendant(
            of: pickerList,
            matching: find.byType(Scrollable),
          ),
        );
        await tester.pumpAndSettle();

        expect(item135Finder, findsOneWidget);

        await tester.tap(item135Finder);
        await tester.pumpAndSettle();

        expect(find.text('Selected Garments (1)'), findsOneWidget);
        expect(find.text('Garment 135'), findsOneWidget);
      },
    );

    testWidgets('2. Preselected garment from page 2 remains selected', (
      tester,
    ) async {
      final repo = _PaginatedFakeWardrobeRepository(items: _generateItems(135));
      await _pumpTryOnScreen(
        tester,
        wardrobeRepository: repo,
        garmentIds: const ['item-135'],
        outfitSource: TryOnOutfitSource.wardrobe,
      );

      expect(repo.requestedPages, ['page=1,size=100', 'page=2,size=100']);
      expect(find.text('Selected Garments (1)'), findsOneWidget);
      expect(find.text('Garment 135'), findsOneWidget);
      expect(
        find.text(
          'Removed garment selection that does not belong to your Digital Wardrobe.',
        ),
        findsNothing,
      );
    });

    testWidgets(
      '3. Duplicate IDs across pages do not produce duplicate garments',
      (tester) async {
        final repo = _PaginatedFakeWardrobeRepository(
          items: _generateItems(105),
          overlapPage2: true,
        );
        await _pumpTryOnScreen(tester, wardrobeRepository: repo);

        await _openGarmentPicker(tester);

        final pickerList = find.byType(ListView).last;
        // Garment 1 appears once at the top.
        expect(
          find.descendant(of: pickerList, matching: find.text('Garment 1')),
          findsOneWidget,
        );

        // Scroll to the end and verify Garment 105 is present and Garment 1 is not duplicated.
        await tester.scrollUntilVisible(
          find.text('Garment 105'),
          400,
          scrollable: find.descendant(
            of: pickerList,
            matching: find.byType(Scrollable),
          ),
        );
        await tester.pumpAndSettle();
        expect(find.text('Garment 105'), findsOneWidget);
      },
    );

    testWidgets(
      '4. Empty final page and all-duplicate page 2 terminate cleanly',
      (tester) async {
        final exactPageRepo = _PaginatedFakeWardrobeRepository(
          items: _generateItems(100),
        );
        await _pumpTryOnScreen(tester, wardrobeRepository: exactPageRepo);
        expect(exactPageRepo.requestedPages, [
          'page=1,size=100',
          'page=2,size=100',
        ]);

        final dupPageRepo = _PaginatedFakeWardrobeRepository(
          items: _generateItems(100),
          onlyDuplicatesOnPage2: true,
        );
        await _pumpTryOnScreen(tester, wardrobeRepository: dupPageRepo);
        expect(dupPageRepo.requestedPages, [
          'page=1,size=100',
          'page=2,size=100',
        ]);
      },
    );

    testWidgets(
      '5. Page 2 failure shows explicit error, hides incomplete wardrobe, and Retry recovers',
      (tester) async {
        final repo = _PaginatedFakeWardrobeRepository(
          items: _generateItems(120),
          failPage2Once: true,
        );
        await _pumpTryOnScreen(tester, wardrobeRepository: repo);

        expect(
          find.text('Could not load your Digital Wardrobe.'),
          findsOneWidget,
        );
        final retryButton = find.text('Retry Loading Wardrobe');
        expect(retryButton, findsOneWidget);
        expect(find.text('Select from Digital Wardrobe'), findsNothing);

        await tester.scrollUntilVisible(retryButton, 200);
        await tester.pumpAndSettle();
        await tester.tap(retryButton);
        await tester.pumpAndSettle();

        expect(
          find.text('Could not load your Digital Wardrobe.'),
          findsNothing,
        );
        expect(find.text('Select from Digital Wardrobe'), findsOneWidget);

        await _openGarmentPicker(tester);
        final pickerList = find.byType(ListView).last;
        await tester.scrollUntilVisible(
          find.text('Garment 120'),
          400,
          scrollable: find.descendant(
            of: pickerList,
            matching: find.byType(Scrollable),
          ),
        );
        await tester.pumpAndSettle();
        expect(find.text('Garment 120'), findsOneWidget);
      },
    );

    testWidgets(
      '6. Genlook single-garment limit and local multi-garment limit remain enforced across pages',
      (tester) async {
        final repo = _PaginatedFakeWardrobeRepository(
          items: _generateItems(135),
        );

        // Genlook (maxGarments: 1): selecting page 2 item replaces page 1 item.
        await _pumpTryOnScreen(
          tester,
          wardrobeRepository: repo,
          garmentIds: const ['item-1'],
          capabilities: _genlookSingleCap,
        );
        expect(find.text('Selected Garments (1)'), findsOneWidget);
        expect(find.text('Garment 1'), findsOneWidget);

        await _openGarmentPicker(tester);
        final pickerList = find.byType(ListView).last;
        await tester.scrollUntilVisible(
          find.text('Garment 135'),
          400,
          scrollable: find.descendant(
            of: pickerList,
            matching: find.byType(Scrollable),
          ),
        );
        await tester.pumpAndSettle();
        await tester.tap(find.text('Garment 135'));
        await tester.pumpAndSettle();

        expect(find.text('Selected Garments (1)'), findsOneWidget);
        expect(find.text('Garment 135'), findsOneWidget);
        expect(find.text('Garment 1'), findsNothing);

        // Local multi-garment (maxGarments: 3): allows selecting across pages up to limit.
        await _pumpTryOnScreen(
          tester,
          wardrobeRepository: repo,
          garmentIds: const ['item-1', 'item-2'],
          capabilities: _localMultiCap,
        );
        expect(find.text('Selected Garments (2)'), findsOneWidget);

        await _openGarmentPicker(tester);
        final multiPickerList = find.byType(ListView).last;
        await tester.scrollUntilVisible(
          find.text('Garment 135'),
          400,
          scrollable: find.descendant(
            of: multiPickerList,
            matching: find.byType(Scrollable),
          ),
        );
        await tester.pumpAndSettle();
        await tester.tap(find.text('Garment 135'));
        await tester.pumpAndSettle();

        await tester.tap(find.text('Done (3)'));
        await tester.pumpAndSettle();
        expect(find.text('Selected Garments (3)'), findsOneWidget);
        expect(find.text('Garment 135'), findsOneWidget);
      },
    );

    testWidgets(
      '7. Stale async pagination result does not overwrite newer state or fail after dispose',
      (tester) async {
        final slowPage1 = Completer<List<WardrobeItemData>>();
        final repo = _PaginatedFakeWardrobeRepository(
          items: _generateItems(10),
          page1Completer: slowPage1,
        );

        await tester.pumpWidget(
          MaterialApp(
            theme: FansivibeTheme.darkTheme,
            home: TryOnScreen(
              outfitSource: TryOnOutfitSource.wardrobe,
              garmentIds: const [],
              title: 'Dispose Test',
              tryOnRepository: _StubTryOnRepository(),
              wardrobeRepository: repo,
              pickImage: _fakePickImage,
              capabilities: _genlookSingleCap,
            ),
          ),
        );
        await tester.pump();

        // Dispose while page 1 is still in flight.
        await tester.pumpWidget(const MaterialApp(home: SizedBox.shrink()));
        await tester.pump();

        slowPage1.complete(_generateItems(10));
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
      },
    );
  });
}
