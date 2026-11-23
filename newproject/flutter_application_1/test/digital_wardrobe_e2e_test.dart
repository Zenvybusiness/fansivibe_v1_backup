import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image_picker/image_picker.dart';

import 'package:fansivibe/features/media/domain/image_pipeline.dart';
import 'package:fansivibe/features/wardrobe/data/garment_client.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart'
    show WardrobeInsightData, WardrobeItemData;
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/presentation/wardrobe_extraction_screen.dart';
import 'package:fansivibe/shared/theme/fansivibe_theme.dart';

/// Valid 1x1 transparent PNG bytes.
final Uint8List kTestPngBytes = base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
);

/// Valid JPEG header bytes (at least 3 bytes FF D8 FF).
final Uint8List kTestJpegBytes = Uint8List.fromList([
  0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
  0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
]);

/// Valid WebP header bytes (RIFF .... WEBP).
final Uint8List kTestWebPBytes = Uint8List.fromList([
  0x52, 0x49, 0x46, 0x46, // "RIFF"
  0x20, 0x00, 0x00, 0x00, // file size
  0x57, 0x45, 0x42, 0x50, // "WEBP"
  0x56, 0x50, 0x38, 0x20, // "VP8 "
]);

/// Mock recording repository for testing persistence behavior.
class _MockWardrobeRepository implements WardrobeRepository {
  final List<Map<String, dynamic>> createdItems = [];
  int createCalls = 0;

  @override
  Future<WardrobeItemData?> createItem({
    required String name,
    required String category,
    required String color,
    String? material,
    MediaRef? imageRef,
    String? fit,
    double? fitConfidence,
  }) async {
    createCalls++;
    final payload = {
      'name': name,
      'category': category,
      'color': color,
      'material': material,
      'imageRef': imageRef,
      'fit': fit,
      'fitConfidence': fitConfidence,
    };
    createdItems.add(payload);
    return WardrobeItemData(
      id: 'test-item-$createCalls',
      name: name,
      category: category,
      color: color,
      material: material,
    );
  }

  @override
  Future<List<WardrobeItemData>> listItems({
    String? category,
    String? color,
    String? sortBy,
    String? order,
    int page = 1,
    int pageSize = 20,
  }) async => const [];

  @override
  Future<WardrobeItemData?> getItem({required String itemId}) async => null;

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
  }) => logWear(
    itemIds: itemIds,
    wornAt: wornAt,
    idempotencyKey: idempotencyKey,
  );

  @override
  Future<WearSummary?> getWearSummary() async => null;
}

/// Scripted GarmentClient for testing extraction states.
class _ScriptedGarmentClient extends GarmentClient {
  String? runId = 'test-run-123';
  GarmentAnalysisRun? pollResult;
  int submitCalls = 0;
  int pollCalls = 0;

  @override
  Future<String?> submitGarmentAnalysisBytes(
    Uint8List bytes, {
    String filename = 'wardrobe_item.jpg',
    String? idempotencyKey,
  }) async {
    submitCalls++;
    return runId;
  }

  @override
  Future<GarmentAnalysisRun?> pollGarmentRun({
    required String runId,
    int attempts = 30,
  }) async {
    pollCalls++;
    return pollResult;
  }
}

Widget _wrapScreen({
  required Widget child,
}) {
  return MaterialApp(
    theme: FansivibeTheme.darkTheme,
    home: child,
  );
}

void main() {
  group('Stage B: Image Pipeline MIME Type Detection', () {
    test('detects JPEG magic bytes correctly', () {
      expect(detectImageMimeType(kTestJpegBytes), 'image/jpeg');
    });

    test('detects PNG magic bytes correctly', () {
      expect(detectImageMimeType(kTestPngBytes), 'image/png');
    });

    test('detects WebP magic bytes correctly', () {
      expect(detectImageMimeType(kTestWebPBytes), 'image/webp');
    });

    test('returns null for unknown or corrupted magic bytes', () {
      final corrupt = Uint8List.fromList([0x00, 0x11, 0x22, 0x33, 0x44]);
      expect(detectImageMimeType(corrupt), isNull);
    });

    test('returns null for too-short byte array', () {
      final tooShort = Uint8List.fromList([0xFF, 0xD8]);
      expect(detectImageMimeType(tooShort), isNull);
    });
  });

  group('Stage C & D: Wardrobe Extraction & Candidate Selection UI', () {
    late _MockWardrobeRepository repository;
    late _ScriptedGarmentClient garmentClient;

    setUp(() {
      repository = _MockWardrobeRepository();
      garmentClient = _ScriptedGarmentClient();
    });

    testWidgets('renders initial upload screen with camera and gallery actions', (
      tester,
    ) async {
      await tester.pumpWidget(
        _wrapScreen(
          child: WardrobeExtractionScreen(
            repository: repository,
            garmentClient: garmentClient,
          ),
        ),
      );

      expect(find.text('Add via AI Extraction'), findsOneWidget);
      expect(find.text('Extract Garments with AI'), findsOneWidget);
      expect(find.text('Take Photo'), findsOneWidget);
      expect(find.text('Choose from Gallery'), findsOneWidget);
    });

    testWidgets('rejects empty image files with truthful error', (
      tester,
    ) async {
      await tester.pumpWidget(
        _wrapScreen(
          child: WardrobeExtractionScreen(
            repository: repository,
            garmentClient: garmentClient,
            takePhoto: () async => XFile.fromData(
              Uint8List(0),
              name: 'empty.jpg',
            ),
          ),
        ),
      );

      await tester.tap(find.text('Take Photo'));
      await tester.pumpAndSettle();

      expect(find.textContaining('selected image is empty'), findsOneWidget);
      expect(garmentClient.submitCalls, 0);
    });

    testWidgets('rejects unsupported image format', (tester) async {
      final unsupportedBytes = Uint8List.fromList([0x47, 0x49, 0x46, 0x38]); // GIF
      await tester.pumpWidget(
        _wrapScreen(
          child: WardrobeExtractionScreen(
            repository: repository,
            garmentClient: garmentClient,
            takePhoto: () async => XFile.fromData(
              unsupportedBytes,
              name: 'animation.gif',
            ),
          ),
        ),
      );

      await tester.tap(find.text('Take Photo'));
      await tester.pumpAndSettle();

      expect(find.textContaining('Unsupported image format'), findsOneWidget);
      expect(garmentClient.submitCalls, 0);
    });

    testWidgets(
      'displays extracted garment candidates without auto-saving them',
      (tester) async {
        garmentClient.pollResult = const GarmentAnalysisRun(
          statusCode: 200,
          data: {
            'status': 'completed',
            'result': {
              'category': 'tops',
              'subcategory': 'Oxford Shirt',
              'color': 'Blue',
              'material': 'Linen',
              'confidence': 0.95,
              'candidates': [
                {
                  'category': 'tops',
                  'subcategory': 'Oxford Shirt',
                  'color': 'Blue',
                  'material': 'Linen',
                  'fit': 'slim',
                  'confidence': 0.95,
                },
                {
                  'category': 'bottoms',
                  'subcategory': 'Chinos',
                  'color': 'Beige',
                  'material': 'Cotton',
                  'fit': 'regular',
                  'confidence': 0.91,
                },
              ],
            },
          },
        );

        await tester.pumpWidget(
          _wrapScreen(
            child: WardrobeExtractionScreen(
              initialImageBytes: kTestPngBytes,
              initialFilename: 'outfit.png',
              repository: repository,
              garmentClient: garmentClient,
            ),
          ),
        );

        // Advance through upload & poll
        await tester.pump();
        await tester.pumpAndSettle();

        // Verify both candidates are displayed
        expect(find.text('Extracted Garments (2)'), findsOneWidget);
        expect(find.text('Oxford Shirt'), findsOneWidget);
        expect(find.text('Chinos'), findsOneWidget);
        expect(find.text('Color: Blue'), findsOneWidget);
        expect(find.text('Color: Beige'), findsOneWidget);

        // INVARIANT CHECK: Extracting does NOT persist items to database!
        expect(repository.createCalls, 0);
        expect(repository.createdItems, isEmpty);
      },
    );

    testWidgets(
      'user can select/deselect candidates and confirm saving only selected items',
      (tester) async {
        garmentClient.pollResult = const GarmentAnalysisRun(
          statusCode: 200,
          data: {
            'status': 'completed',
            'result': {
              'category': 'tops',
              'candidates': [
                {
                  'category': 'tops',
                  'subcategory': 'Denim Jacket',
                  'color': 'Blue',
                  'material': 'Denim',
                  'confidence': 0.92,
                },
                {
                  'category': 'footwear',
                  'subcategory': 'White Sneakers',
                  'color': 'White',
                  'material': 'Leather',
                  'confidence': 0.88,
                },
              ],
            },
          },
        );

        await tester.pumpWidget(
          _wrapScreen(
            child: WardrobeExtractionScreen(
              initialImageBytes: kTestPngBytes,
              initialFilename: 'denim.png',
              repository: repository,
              garmentClient: garmentClient,
            ),
          ),
        );

        await tester.pump();
        await tester.pumpAndSettle();

        expect(find.text('Save Selected to Wardrobe (2)'), findsOneWidget);

        // Deselect the second candidate (White Sneakers)
        final checkboxes = find.byType(Checkbox);
        expect(checkboxes, findsNWidgets(2));

        await tester.tap(checkboxes.at(1));
        await tester.pumpAndSettle();

        // Button should now reflect 1 item selected
        expect(find.text('Save Selected to Wardrobe (1)'), findsOneWidget);

        // Tap Save Selected to Wardrobe
        await tester.tap(find.text('Save Selected to Wardrobe (1)'));
        await tester.pumpAndSettle();

        // Verify persistence: ONLY the selected item was saved!
        expect(repository.createCalls, 1);
        expect(repository.createdItems.length, 1);
        expect(repository.createdItems[0]['name'], 'Denim Jacket');
        expect(repository.createdItems[0]['category'], 'tops');
        expect(repository.createdItems[0]['color'], 'Blue');
        expect(repository.createdItems[0]['material'], 'Denim');
      },
    );

    testWidgets('user can edit candidate metadata before persisting', (
      tester,
    ) async {
      garmentClient.pollResult = const GarmentAnalysisRun(
        statusCode: 200,
        data: {
          'status': 'completed',
          'result': {
            'category': 'tops',
            'candidates': [
              {
                'category': 'tops',
                'subcategory': 'Oxford Shirt',
                'color': 'Blue',
                'material': 'Linen',
                'confidence': 0.95,
              },
            ],
          },
        },
      );

      await tester.pumpWidget(
        _wrapScreen(
          child: WardrobeExtractionScreen(
            initialImageBytes: kTestPngBytes,
            initialFilename: 'oxford.png',
            repository: repository,
            garmentClient: garmentClient,
          ),
        ),
      );

      await tester.pump();
      await tester.pumpAndSettle();

      expect(find.text('Oxford Shirt'), findsOneWidget);

      // Tap the edit icon button on the candidate card
      final editButton = find.byIcon(Icons.edit_outlined);
      expect(editButton, findsOneWidget);
      await tester.tap(editButton);
      await tester.pumpAndSettle();

      // Verify bottom sheet opened
      expect(find.text('Edit Candidate Details'), findsOneWidget);
      expect(find.text('Item Name'), findsOneWidget);

      // Change the name to "Bespoke Italian Shirt"
      final textField = find.byType(TextField);
      await tester.enterText(textField, 'Bespoke Italian Shirt');

      // Tap Done
      await tester.tap(find.text('Done'));
      await tester.pumpAndSettle();

      // Verify updated name on candidate card
      expect(find.text('Bespoke Italian Shirt'), findsOneWidget);

      // Now save
      await tester.tap(find.text('Save Selected to Wardrobe (1)'));
      await tester.pumpAndSettle();

      // Verify created item received edited name
      expect(repository.createCalls, 1);
      expect(repository.createdItems[0]['name'], 'Bespoke Italian Shirt');
      expect(repository.createdItems[0]['category'], 'tops');
      expect(repository.createdItems[0]['color'], 'Blue');
    });

    testWidgets('cancelling candidate selection does not persist anything', (
      tester,
    ) async {
      garmentClient.pollResult = const GarmentAnalysisRun(
        statusCode: 200,
        data: {
          'status': 'completed',
          'result': {
            'category': 'tops',
            'candidates': [
              {
                'category': 'tops',
                'subcategory': 'Silk Blouse',
                'color': 'Cream',
                'confidence': 0.94,
              },
            ],
          },
        },
      );

      await tester.pumpWidget(
        _wrapScreen(
          child: WardrobeExtractionScreen(
            initialImageBytes: kTestPngBytes,
            initialFilename: 'silk.png',
            repository: repository,
            garmentClient: garmentClient,
          ),
        ),
      );

      await tester.pump();
      await tester.pumpAndSettle();

      expect(find.text('Silk Blouse'), findsOneWidget);

      // Tap Cancel button
      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();

      // Zero items persisted
      expect(repository.createCalls, 0);
      expect(repository.createdItems, isEmpty);
    });

    testWidgets('shows truthful error when no garment is detected', (
      tester,
    ) async {
      garmentClient.pollResult = const GarmentAnalysisRun(
        statusCode: 200,
        data: {
          'status': 'failed',
          'error': {
            'code': 'PROCESSING_FAILURE',
            'details': {'reason': 'no_garment_detected'},
          },
        },
      );

      await tester.pumpWidget(
        _wrapScreen(
          child: WardrobeExtractionScreen(
            initialImageBytes: kTestPngBytes,
            initialFilename: 'landscape.png',
            repository: repository,
            garmentClient: garmentClient,
          ),
        ),
      );

      await tester.pump();
      await tester.pumpAndSettle();

      expect(
        find.textContaining('No clothing item was detected in this photo'),
        findsOneWidget,
      );
      expect(find.text('Try Another Photo'), findsOneWidget);

      // Tapping "Try Another Photo" resets to idle stage
      await tester.tap(find.text('Try Another Photo'));
      await tester.pumpAndSettle();

      expect(find.text('Extract Garments with AI'), findsOneWidget);
      expect(repository.createCalls, 0);
    });

    testWidgets('shows truthful timeout error when analysis times out', (
      tester,
    ) async {
      // Simulate timeout by returning null for poll result
      garmentClient.pollResult = null;

      await tester.pumpWidget(
        _wrapScreen(
          child: WardrobeExtractionScreen(
            initialImageBytes: kTestPngBytes,
            initialFilename: 'timeout_test.png',
            repository: repository,
            garmentClient: garmentClient,
          ),
        ),
      );

      await tester.pump();
      await tester.pumpAndSettle();

      expect(
        find.textContaining('Garment analysis timed out'),
        findsOneWidget,
      );
      expect(find.text('Try Another Photo'), findsOneWidget);
      expect(repository.createCalls, 0);
    });
  });
}
