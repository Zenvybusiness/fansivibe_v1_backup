import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image_picker/image_picker.dart';

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

/// Valid 1x1 JPEG bytes.
final Uint8List kTestJpegBytes = base64Decode(
  '/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoHBwYIDAoMDAsKCwsNDhIQDQ4RDgsLEBYQERMUFRUVDA8XGBYUGBIUFRT/wAALCAABAAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAAA//aAAgBAQAAPwA3/9k=',
);

/// Test WebP header bytes.
final Uint8List kTestWebPBytes = Uint8List.fromList([
  0x52, 0x49, 0x46, 0x46, // "RIFF"
  0x20, 0x00, 0x00, 0x00, // file size
  0x57, 0x45, 0x42, 0x50, // "WEBP"
  0x56, 0x50, 0x38, 0x20, // "VP8 "
]);

class _MockWardrobeRepository implements WardrobeRepository {
  final List<Map<String, dynamic>> createdItems = [];
  int createCalls = 0;
  bool shouldFailOnItem = false;
  String? failCategory;

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
    if (shouldFailOnItem && category == failCategory) {
      return null;
    }
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
      id: 'item-$createCalls',
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

class _MockGarmentClient extends GarmentClient {
  String? runId = 'test-run-phase4';
  GarmentAnalysisRun? pollResult;
  int submitCalls = 0;
  int pollCalls = 0;
  Completer<String?>? submitCompleter;

  @override
  Future<String?> submitGarmentAnalysisBytes(
    Uint8List bytes, {
    String filename = 'wardrobe_item.jpg',
    String? idempotencyKey,
  }) async {
    submitCalls++;
    if (submitCompleter != null) {
      return submitCompleter!.future;
    }
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

Widget _wrap(Widget child) {
  return MaterialApp(
    theme: FansivibeTheme.darkTheme,
    home: child,
  );
}

void main() {
  group('Phase 4: Flutter Image Analysis End-to-End Tests', () {
    late _MockWardrobeRepository repository;
    late _MockGarmentClient garmentClient;

    setUp(() {
      repository = _MockWardrobeRepository();
      garmentClient = _MockGarmentClient();
    });

    testWidgets('Gallery image selection flow triggers extraction', (tester) async {
      garmentClient.pollResult = const GarmentAnalysisRun(
        statusCode: 200,
        data: {
          'status': 'completed',
          'result': {
            'category': 'tops',
            'items': [
              {
                'id': 'cand_1',
                'category': 'tops',
                'subcategory': 'White Oxford Shirt',
                'color': 'White',
                'material': 'Cotton',
                'confidence': 0.95,
              },
            ],
          },
        },
      );

      await tester.pumpWidget(
        _wrap(
          WardrobeExtractionScreen(
            repository: repository,
            garmentClient: garmentClient,
            pickImage: (source) async => XFile.fromData(
              kTestJpegBytes,
              name: 'shirt.jpg',
            ),
          ),
        ),
      );

      expect(find.text('Choose from Gallery'), findsOneWidget);
      await tester.tap(find.text('Choose from Gallery'));
      await tester.pumpAndSettle();

      expect(garmentClient.submitCalls, 1);
      expect(find.text('Extracted Garments (1)'), findsOneWidget);
      expect(find.text('White Oxford Shirt'), findsOneWidget);
    });

    testWidgets('Camera capture flow triggers extraction', (tester) async {
      garmentClient.pollResult = const GarmentAnalysisRun(
        statusCode: 200,
        data: {
          'status': 'completed',
          'result': {
            'category': 'bottoms',
            'items': [
              {
                'id': 'cand_1',
                'category': 'bottoms',
                'subcategory': 'Denim Jeans',
                'color': 'Navy',
                'material': 'Denim',
                'confidence': 0.92,
              },
            ],
          },
        },
      );

      await tester.pumpWidget(
        _wrap(
          WardrobeExtractionScreen(
            repository: repository,
            garmentClient: garmentClient,
            takePhoto: () async => XFile.fromData(
              kTestJpegBytes,
              name: 'camera_capture.jpg',
            ),
          ),
        ),
      );

      expect(find.text('Take Photo'), findsOneWidget);
      await tester.tap(find.text('Take Photo'));
      await tester.pumpAndSettle();

      expect(garmentClient.submitCalls, 1);
      expect(find.text('Extracted Garments (1)'), findsOneWidget);
      expect(find.text('Denim Jeans'), findsOneWidget);
    });

    testWidgets('Renders image thumbnail preview and loading state', (tester) async {
      final completer = Completer<String?>();
      garmentClient.submitCompleter = completer;

      await tester.pumpWidget(
        _wrap(
          WardrobeExtractionScreen(
            initialImageBytes: kTestJpegBytes,
            initialFilename: 'wardrobe.jpg',
            repository: repository,
            garmentClient: garmentClient,
          ),
        ),
      );

      await tester.pump();
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
      expect(find.text('Uploading photo…'), findsOneWidget);

      completer.complete(null);
      await tester.pumpAndSettle();
    });

    testWidgets('Renders multiple garment candidate cards with attributes', (tester) async {
      tester.view.physicalSize = const Size(800, 1400);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() {
        tester.view.resetPhysicalSize();
        tester.view.resetDevicePixelRatio();
      });

      garmentClient.pollResult = const GarmentAnalysisRun(
        statusCode: 200,
        data: {
          'status': 'completed',
          'result': {
            'category': 'tops',
            'items': [
              {
                'id': 'cand_1',
                'category': 'tops',
                'subcategory': 'Silk Blouse',
                'color': 'Cream',
                'secondary_colors': ['Gold'],
                'material': 'Silk',
                'fit': 'regular',
                'sleeve_type': 'long_sleeve',
                'confidence': 0.94,
              },
              {
                'id': 'cand_2',
                'category': 'bottoms',
                'subcategory': 'Pleated Skirt',
                'color': 'Navy',
                'material': 'Wool',
                'fit': 'relaxed',
                'confidence': 0.90,
              },
              {
                'id': 'cand_3',
                'category': 'accessories',
                'subcategory': 'Leather Belt',
                'color': 'Tan',
                'material': 'Leather',
                'confidence': 0.88,
              },
            ],
          },
        },
      );

      await tester.pumpWidget(
        _wrap(
          WardrobeExtractionScreen(
            initialImageBytes: kTestJpegBytes,
            repository: repository,
            garmentClient: garmentClient,
          ),
        ),
      );

      await tester.pump();
      await tester.pumpAndSettle();

      expect(find.text('Extracted Garments (3)'), findsOneWidget);
      expect(find.text('Silk Blouse'), findsOneWidget);
      expect(find.text('Pleated Skirt'), findsOneWidget);
      expect(find.text('Leather Belt'), findsOneWidget);
      expect(find.text('Color: Cream'), findsOneWidget);
      expect(find.text('Secondary: Gold'), findsOneWidget);
      expect(find.text('Material: Silk'), findsOneWidget);
      expect(find.text('Fit: regular'), findsOneWidget);
      expect(find.text('Sleeve: long_sleeve'), findsOneWidget);
      expect(find.text('Save Selected to Wardrobe (3)'), findsOneWidget);
    });

    testWidgets('Individual candidate selection and deselection updates save count', (tester) async {
      garmentClient.pollResult = const GarmentAnalysisRun(
        statusCode: 200,
        data: {
          'status': 'completed',
          'result': {
            'items': [
              {'id': 'cand_1', 'category': 'tops', 'subcategory': 'Shirt', 'color': 'White', 'confidence': 0.9},
              {'id': 'cand_2', 'category': 'bottoms', 'subcategory': 'Pants', 'color': 'Black', 'confidence': 0.9},
            ],
          },
        },
      );

      await tester.pumpWidget(
        _wrap(
          WardrobeExtractionScreen(
            initialImageBytes: kTestJpegBytes,
            repository: repository,
            garmentClient: garmentClient,
          ),
        ),
      );

      await tester.pump();
      await tester.pumpAndSettle();

      expect(find.text('Save Selected to Wardrobe (2)'), findsOneWidget);

      // Deselect the first candidate checkbox
      final checkboxes = find.byType(Checkbox);
      expect(checkboxes, findsNWidgets(2));
      await tester.tap(checkboxes.first);
      await tester.pumpAndSettle();

      // Count drops to 1
      expect(find.text('Save Selected to Wardrobe (1)'), findsOneWidget);

      // Deselect the second candidate
      await tester.tap(checkboxes.at(1));
      await tester.pumpAndSettle();

      // Count drops to 0, button disabled
      expect(find.text('Save Selected to Wardrobe (0)'), findsOneWidget);
    });

    testWidgets('User can edit candidate metadata before persistence', (tester) async {
      garmentClient.pollResult = const GarmentAnalysisRun(
        statusCode: 200,
        data: {
          'status': 'completed',
          'result': {
            'items': [
              {'id': 'cand_1', 'category': 'tops', 'subcategory': 'Unknown Top', 'color': 'Navy', 'confidence': 0.8},
            ],
          },
        },
      );

      await tester.pumpWidget(
        _wrap(
          WardrobeExtractionScreen(
            initialImageBytes: kTestJpegBytes,
            repository: repository,
            garmentClient: garmentClient,
          ),
        ),
      );

      await tester.pump();
      await tester.pumpAndSettle();

      expect(find.text('Unknown Top'), findsOneWidget);

      // Tap edit button
      await tester.tap(find.byIcon(Icons.edit_outlined));
      await tester.pumpAndSettle();

      expect(find.text('Edit Candidate Details'), findsOneWidget);

      // Edit item name
      await tester.enterText(find.byType(TextField).first, 'Custom Wool Blazer');
      await tester.tap(find.text('Done'));
      await tester.pumpAndSettle();

      // Verified updated title on candidate card
      expect(find.text('Custom Wool Blazer'), findsOneWidget);
    });

    testWidgets('Explicit confirmation saves only confirmed items', (tester) async {
      garmentClient.pollResult = const GarmentAnalysisRun(
        statusCode: 200,
        data: {
          'status': 'completed',
          'result': {
            'items': [
              {'id': 'cand_1', 'category': 'tops', 'subcategory': 'Confirmed Top', 'color': 'White', 'confidence': 0.95},
              {'id': 'cand_2', 'category': 'bottoms', 'subcategory': 'Unwanted Shorts', 'color': 'Khaki', 'confidence': 0.90},
            ],
          },
        },
      );

      await tester.pumpWidget(
        _wrap(
          WardrobeExtractionScreen(
            initialImageBytes: kTestJpegBytes,
            repository: repository,
            garmentClient: garmentClient,
          ),
        ),
      );

      await tester.pump();
      await tester.pumpAndSettle();

      // Uncheck second item (Unwanted Shorts)
      final checkboxes = find.byType(Checkbox);
      await tester.tap(checkboxes.at(1));
      await tester.pumpAndSettle();

      // Tap save
      await tester.tap(find.text('Save Selected to Wardrobe (1)'));
      await tester.pumpAndSettle();

      // Only the 1 confirmed item is persisted
      expect(repository.createCalls, 1);
      expect(repository.createdItems.length, 1);
      expect(repository.createdItems[0]['name'], 'Confirmed Top');
    });

    testWidgets('Partial save failure communicates which items failed and prevents duplicate save', (tester) async {
      repository.shouldFailOnItem = true;
      repository.failCategory = 'bottoms';

      garmentClient.pollResult = const GarmentAnalysisRun(
        statusCode: 200,
        data: {
          'status': 'completed',
          'result': {
            'items': [
              {'id': 'cand_1', 'category': 'tops', 'subcategory': 'Good Top', 'color': 'White', 'confidence': 0.95},
              {'id': 'cand_2', 'category': 'bottoms', 'subcategory': 'Bad Bottoms', 'color': 'Black', 'confidence': 0.90},
            ],
          },
        },
      );

      await tester.pumpWidget(
        _wrap(
          WardrobeExtractionScreen(
            initialImageBytes: kTestJpegBytes,
            repository: repository,
            garmentClient: garmentClient,
          ),
        ),
      );

      await tester.pump();
      await tester.pumpAndSettle();

      // Tap save both
      await tester.tap(find.text('Save Selected to Wardrobe (2)'));
      await tester.pumpAndSettle();

      // Partial save surfaced truthfully
      expect(find.textContaining('Saved 1 item(s). Failed to save: Bad Bottoms'), findsOneWidget);
      // The good top should now be deselected so retrying doesn't duplicate it
      expect(find.text('Save Selected to Wardrobe (1)'), findsOneWidget);
      expect(repository.createCalls, 2);
      expect(repository.createdItems.length, 1);
    });

    testWidgets('Retry button in error state re-triggers analysis', (tester) async {
      // First attempt fails
      garmentClient.pollResult = const GarmentAnalysisRun(
        statusCode: 200,
        data: {
          'status': 'failed',
          'error': {'details': {'reason': 'analyzer_timeout'}},
        },
      );

      await tester.pumpWidget(
        _wrap(
          WardrobeExtractionScreen(
            initialImageBytes: kTestJpegBytes,
            repository: repository,
            garmentClient: garmentClient,
          ),
        ),
      );

      await tester.pump();
      await tester.pumpAndSettle();

      expect(find.text('Analysis Issue'), findsOneWidget);
      expect(find.text('Retry Analysis'), findsOneWidget);
      expect(garmentClient.submitCalls, 1);

      // Fix client for retry
      garmentClient.pollResult = const GarmentAnalysisRun(
        statusCode: 200,
        data: {
          'status': 'completed',
          'result': {
            'items': [
              {'id': 'cand_1', 'category': 'tops', 'subcategory': 'Retried Shirt', 'color': 'Blue', 'confidence': 0.95},
            ],
          },
        },
      );

      // Tap retry
      await tester.tap(find.text('Retry Analysis'));
      await tester.pump();
      await tester.pumpAndSettle();

      expect(garmentClient.submitCalls, 2);
      expect(find.text('Extracted Garments (1)'), findsOneWidget);
      expect(find.text('Retried Shirt'), findsOneWidget);
    });
  });
}
