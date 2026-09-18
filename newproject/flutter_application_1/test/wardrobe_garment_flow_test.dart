import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:image_picker/image_picker.dart';

import 'package:fansivibe/features/wardrobe/data/garment_client.dart';
import 'package:fansivibe/features/wardrobe/data/garment_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_client.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart'
    show AddItemConfig, WardrobeInsightData, WardrobeItemData;
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/presentation/add_wardrobe_item_screen.dart';
import 'package:fansivibe/features/wardrobe/presentation/wardrobe_photo_screen.dart';

/// M11 P2 regression tests: garment data layer, photo screen, and the
/// add-item photo → analyze → confirm → save flow. No mocks pose as
/// backend data — fakes only stand in for transport boundaries.

/// 1x1 transparent PNG (valid image bytes for Image.memory in widgets).
final Uint8List kPng = base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
);

Map<String, dynamic> _garmentResult({
  Object? category = 'tops',
  Object? color = 'Black',
  Object? material = 'Cotton',
  Object? subcategory = 'T-Shirt',
}) => {
  'category': category,
  'subcategory': subcategory,
  'color': color,
  'pattern': 'solid',
  'material': material,
  'style': 'casual',
  'fit': 'regular',
  'confidence': 0.84,
  'needs_review': false,
  'sourceRunId': 'run-1',
};

Map<String, dynamic> _inputMedia() => {
  'key': 'users/u/scans/r/input.jpg',
  'mediaType': 'image/jpeg',
  'sizeBytes': kPng.length,
  'contentHash': 'abc123',
  'isGenerated': false,
  'uploadedAt': '2026-09-17T10:00:00Z',
  'analyzer': 'ollama-garment-v1',
};

class _ScriptedGarmentClient extends GarmentClient {
  String? runId = 'run-1';
  GarmentAnalysisRun? pollResult;
  int submitCalls = 0;

  @override
  Future<String?> submitGarmentAnalysisBytes(
    Uint8List bytes, {
    String filename = 'wardrobe_item.jpg',
  }) async {
    submitCalls++;
    return runId;
  }

  @override
  Future<GarmentAnalysisRun?> pollGarmentRun({
    required String runId,
    int attempts = 30,
  }) async => pollResult;
}

class _RecordingRepo implements WardrobeRepository {
  Map<String, dynamic>? savedPayload;

  @override
  Future<WardrobeItemData?> createItem({
    required String name,
    required String category,
    required String color,
    String? material,
    MediaRef? imageRef,
  }) async {
    savedPayload = {
      'name': name,
      'category': category,
      'color': color,
      'material': material,
      'imageRef': imageRef?.toJson(),
    };
    return WardrobeItemData(
      id: 'server-uuid',
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
  }) async => null;

  @override
  Future<bool?> deleteItem({required String itemId}) async => null;

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
}

void main() {
  group('GarmentAnalysisResult parsing', () {
    test('parses a full backend observation verbatim', () {
      final result = GarmentAnalysisResult.fromJson(_garmentResult());

      expect(result.category, 'tops');
      expect(result.subcategory, 'T-Shirt');
      expect(result.color, 'Black');
      expect(result.pattern, 'solid');
      expect(result.material, 'Cotton');
      expect(result.confidence, 0.84);
      expect(result.needsReview, isFalse);
      expect(result.sourceRunId, 'run-1');
    });

    test('null fields stay null (Not detected), never defaulted', () {
      final result = GarmentAnalysisResult.fromJson({
        'category': 'footwear',
        'confidence': 0.9,
      });

      expect(result.category, 'footwear');
      expect(result.subcategory, isNull);
      expect(result.color, isNull);
      expect(result.material, isNull);
      expect(result.style, isNull);
      expect(result.needsReview, isTrue);
    });

    test('unknown category throws instead of posing as a garment', () {
      expect(
        () => GarmentAnalysisResult.fromJson(_garmentResult(category: 'shirt')),
        throwsFormatException,
      );
    });

    test('non-numeric confidence throws (never invented)', () {
      expect(
        () => GarmentAnalysisResult.fromJson(
          _garmentResult()..['confidence'] = 'high',
        ),
        throwsFormatException,
      );
      final omitted = _garmentResult()..remove('confidence');
      expect(
        GarmentAnalysisResult.fromJson(omitted).confidence,
        isNull,
      );
    });

    test('wrong attribute types throw', () {
      expect(
        () => GarmentAnalysisResult.fromJson(_garmentResult(color: 5)),
        throwsFormatException,
      );
    });
  });

  group('GarmentClient transport', () {
    test('202 resolves the run id', () async {
      final client = GarmentClient(
        client: MockClient(
          (_) async => http.Response('{"run_id": "run-1"}', 202),
        ),
      );
      addTearDown(client.dispose);

      expect(
        await client.submitGarmentAnalysisBytes(kPng),
        'run-1',
      );
    });

    test('rejection and empty/oversized bytes resolve null, never fake', () async {
      final rejecting = GarmentClient(
        client: MockClient((_) async => http.Response('{}', 500)),
      );
      addTearDown(rejecting.dispose);
      expect(await rejecting.submitGarmentAnalysisBytes(kPng), isNull);

      final any = GarmentClient(
        client: MockClient((_) async => http.Response('{"run_id": "x"}', 202)),
      );
      addTearDown(any.dispose);
      expect(await any.submitGarmentAnalysisBytes(Uint8List(0)), isNull);
      expect(
        await any.submitGarmentAnalysisBytes(
          Uint8List(GarmentClient.maxImageBytes + 1),
        ),
        isNull,
      );
    });

    test('poll returns completed runs with result and input media', () async {
      final client = GarmentClient(
        client: MockClient(
          (_) async => http.Response(
            jsonEncode({
              'run_id': 'run-1',
              'status': 'completed',
              'result': _garmentResult(),
              'input_media': _inputMedia(),
            }),
            200,
          ),
        ),
      );
      addTearDown(client.dispose);

      final run = await client.pollGarmentRun(runId: 'run-1');
      expect(run, isNotNull);
      expect(run!.isCompleted, isTrue);
      expect(run.result!['category'], 'tops');
      expect(run.inputMedia!['contentHash'], 'abc123');
      expect(run.failureReason, isNull);
    });

    test('poll surfaces typed failure reasons', () async {
      final client = GarmentClient(
        client: MockClient(
          (_) async => http.Response(
            jsonEncode({
              'run_id': 'run-1',
              'status': 'failed',
              'error': {
                'code': 'PROCESSING_FAILURE',
                'details': {'reason': 'no_garment_detected'},
              },
            }),
            200,
          ),
        ),
      );
      addTearDown(client.dispose);

      final run = await client.pollGarmentRun(runId: 'run-1');
      expect(run!.isFailed, isTrue);
      expect(run.failureReason, 'no_garment_detected');
    });

    test('poll timeout resolves null (retryable, no duplicate analysis)', () async {
      final client = GarmentClient(
        client: MockClient(
          (_) async => http.Response(
            jsonEncode({'run_id': 'run-1', 'status': 'pending'}),
            200,
          ),
        ),
        pollInterval: Duration.zero,
      );
      addTearDown(client.dispose);

      expect(await client.pollGarmentRun(runId: 'run-1', attempts: 2), isNull);
    });
  });

  group('WardrobePhotoScreen', () {
    testWidgets('shows Take Photo and Choose from Gallery', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(home: WardrobePhotoScreen()),
      );

      expect(find.text('Take Photo'), findsOneWidget);
      expect(find.text('Choose from Gallery'), findsOneWidget);
    });

    testWidgets('gallery photo previews with Retake and Use Photo', (
      tester,
    ) async {
      Future<XFile?> pick(ImageSource source) async =>
          XFile.fromData(kPng, name: 'shirt.jpg', mimeType: 'image/jpeg');
      await tester.pumpWidget(
        MaterialApp(home: WardrobePhotoScreen(pickImage: pick)),
      );

      await tester.tap(find.text('Choose from Gallery'));
      await tester.pumpAndSettle();

      expect(find.text('Retake'), findsOneWidget);
      expect(find.text('Use Photo'), findsOneWidget);
    });

    testWidgets('Use Photo pops the captured bytes', (tester) async {
      Future<XFile?> pick(ImageSource source) async =>
          XFile.fromData(kPng, name: 'shirt.jpg', mimeType: 'image/jpeg');
      WardrobePhoto? popped;
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => TextButton(
              onPressed: () async {
                popped = await Navigator.of(context).push<WardrobePhoto>(
                  MaterialPageRoute(
                    builder: (_) => WardrobePhotoScreen(pickImage: pick),
                  ),
                );
              },
              child: const Text('open'),
            ),
          ),
        ),
      );

      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Choose from Gallery'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Use Photo'));
      await tester.pumpAndSettle();

      expect(popped, isNotNull);
      expect(popped!.bytes, kPng);
    });
  });

  group('Add screen photo → analyze → confirm → save', () {
    late _RecordingRepo repo;
    late _ScriptedGarmentClient garments;

    setUp(() {
      repo = _RecordingRepo();
      garments = _ScriptedGarmentClient()
        ..pollResult = GarmentAnalysisRun(
          statusCode: 200,
          data: {
            'status': 'completed',
            'result': _garmentResult(),
            'input_media': _inputMedia(),
          },
        );
    });

    // ponytail: plain MaterialApp — FansivibeTheme.darkTheme trips a
    // pre-existing FansiButton.secondary TextStyle.lerp debug assertion
    // during route transitions (shared-component issue, not this flow).
    Future<void> pumpAdd(
      WidgetTester tester, {
      WardrobeRepository? repository,
    }) async {
      final category = AddItemConfig.categories.firstWhere(
        (c) => c.id == 'tops',
      );
      await tester.pumpWidget(
        MaterialApp(
          home: AddWardrobeItemScreen(
            category: category,
            repository: repository ?? repo,
            garmentClient: garments,
            photoGalleryPick: (source) async =>
                XFile.fromData(kPng, name: 'shirt.jpg', mimeType: 'image/jpeg'),
          ),
        ),
      );
    }

    Future<void> takePhoto(WidgetTester tester) async {
      await tester.scrollUntilVisible(
        find.text('Take Photo'),
        200.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Take Photo'));
      await tester.pumpAndSettle();
      // Both routes are in the tree after the push — scope to the top
      // (photo) route, which builds later.
      await tester.tap(find.text('Choose from Gallery').last);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Use Photo'));
      await tester.pumpAndSettle();
    }

    testWidgets('analyzed photo prefills chips and saves with imageRef', (
      tester,
    ) async {
      // Real repository + mock transport: proves vocab normalization and
      // imageRef serialization on the true production path.
      Map<String, dynamic>? postedBody;
      final liveRepo = WardrobeRepositoryImpl(
        client: WardrobeClient(
          client: MockClient((request) async {
            postedBody =
                jsonDecode(request.body) as Map<String, dynamic>;
            return http.Response(
              jsonEncode({
                'id': 'server-uuid',
                'name': 'Cotton T-Shirt',
                'category': 'tops',
                'color': 'black',
                'material': 'cotton',
                'isFavorite': false,
                'imageRef': postedBody!['imageRef'],
              }),
              201,
            );
          }),
        ),
      );
      await pumpAdd(tester, repository: liveRepo);
      await takePhoto(tester);

      await tester.scrollUntilVisible(
        find.text('Analyze Item'),
        200.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Analyze Item'));
      await tester.pumpAndSettle();

      // Single submit (no duplicate taps), real values rendered.
      expect(garments.submitCalls, 1);
      expect(
        find.text('AI suggestion — confirmed below, edit if needed'),
        findsOneWidget,
      );
      // Prefill proof: the test never taps Type/Color/Texture chips, yet
      // the save below carries the AI-matched values.

      // Save carries the confirmed values plus the run photo reference.
      await tester.scrollUntilVisible(
        find.text('Save Item'),
        200.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Save Item'));
      await tester.pumpAndSettle();

      final payload = postedBody!;
      expect(payload['category'], 'tops');
      expect(payload['color'], 'black');
      expect(payload['material'], 'cotton');
      final imageRef = payload['imageRef'] as Map<String, dynamic>?;
      expect(imageRef, isNotNull);
      expect(imageRef!['objectKey'], 'users/u/scans/r/input.jpg');
      expect(imageRef['contentHash'], 'abc123');
      expect(imageRef['sourceRunId'], 'run-1');
      // Screen popped with the server item.
      expect(find.text('Add Tops'), findsNothing);
    });

    testWidgets('failed analysis shows a truthful error, never mock data', (
      tester,
    ) async {
      garments.pollResult = const GarmentAnalysisRun(
        statusCode: 200,
        data: {
          'status': 'failed',
          'error': {
            'code': 'PROCESSING_FAILURE',
            'details': {'reason': 'no_garment_detected'},
          },
        },
      );
      await pumpAdd(tester);
      await takePhoto(tester);

      await tester.scrollUntilVisible(
        find.text('Analyze Item'),
        200.0,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('Analyze Item'));
      await tester.pumpAndSettle();

      expect(
        find.textContaining('No clothing item was detected'),
        findsOneWidget,
      );
      expect(find.textContaining('AI suggestion'), findsNothing);
    });
  });
}
