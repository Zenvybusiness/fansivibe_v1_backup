import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/learning/data/models.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/stylist/presentation/stylist_screen.dart';
import 'package:fansivibe/features/wardrobe/data/garment_client.dart';
import 'package:fansivibe/features/wardrobe/data/garment_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_client.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart'
    show AddItemConfig, WardrobeItemData;
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/presentation/add_wardrobe_item_screen.dart';
import 'package:fansivibe/features/wardrobe/presentation/wardrobe_extraction_screen.dart';
import 'package:fansivibe/features/wardrobe/presentation/wardrobe_screen.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

/// Valid 1x1 PNG bytes so `Image.memory` renders cleanly in Flutter widget tests.
final Uint8List _kValidPng = Uint8List.fromList(const [
  0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, // PNG magic
  0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52, // IHDR
  0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
  0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4,
  0x89, 0x00, 0x00, 0x00, 0x0A, 0x49, 0x44, 0x41, // IDAT
  0x54, 0x78, 0x9C, 0x63, 0x00, 0x01, 0x00, 0x00,
  0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00,
  0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE, // IEND
  0x42, 0x60, 0x82,
]);

/// Distinct valid PNG byte sequences for verifying candidate-crop identity.
Uint8List _distinctPngCrop(int marker) =>
    Uint8List.fromList([..._kValidPng, marker & 0xFF, (marker >> 1) & 0xFF]);

/// Valid minimal JPEG header bytes (for upload MIME detection).
final Uint8List _kFakeJpeg = Uint8List.fromList([
  0xFF,
  0xD8,
  0xFF,
  0xE0,
  ..._kValidPng,
]);

Map<String, dynamic> _multiCandidateRunPayload(String runId) => {
  'run_id': runId,
  'run_type': 'garment',
  'status': 'completed',
  'result': {
    'sourceRunId': runId,
    'extraction_method': 'vlm_bounding_box_crop',
    'has_segmentation_mask': false,
    'mask': null,
    'segmentation': {
      'supported': false,
      'type': 'none',
      'reason': 'Local VLM provides 2D bounding-box localization only.',
    },
    'partial_failures': <dynamic>[],
    'candidates': [
      {
        'id': 'cand_top',
        'category': 'tops',
        'subcategory': 'oxford shirt',
        'color': 'light_blue',
        'secondary_colors': ['white'],
        'pattern': 'striped',
        'material': 'cotton',
        'fit': 'Regular',
        'confidence': 0.93,
        'needs_review': false,
        'extraction_method': 'vlm_bounding_box_crop',
        'has_segmentation_mask': false,
        'mask': null,
        'has_crop': true,
        'crop_key': 'users/u1/extractions/$runId/candidates/cand_top.webp',
        'crop_url': '/v1/analysis/runs/$runId/candidates/cand_top/image',
        'crop_width': 320,
        'crop_height': 280,
        'bounding_box': {
          'x1': 0.2,
          'y1': 0.1,
          'x2': 0.8,
          'y2': 0.48,
          'coord_space': 'normalized_0_1',
        },
      },
      {
        'id': 'cand_bottom',
        'category': 'bottoms',
        'subcategory': 'chino trousers',
        'color': 'beige',
        'secondary_colors': <String>[],
        'pattern': 'solid',
        'material': null,
        'fit': 'Slim',
        'confidence': 0.89,
        'needs_review': false,
        'extraction_method': 'vlm_bounding_box_crop',
        'has_segmentation_mask': false,
        'mask': null,
        'has_crop': true,
        'crop_key': 'users/u1/extractions/$runId/candidates/cand_bottom.webp',
        'crop_url': '/v1/analysis/runs/$runId/candidates/cand_bottom/image',
        'crop_width': 280,
        'crop_height': 340,
        'bounding_box': {
          'x1': 0.25,
          'y1': 0.5,
          'x2': 0.75,
          'y2': 0.92,
          'coord_space': 'normalized_0_1',
        },
      },
    ],
  },
};

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    LocalStorage.init(prefs: await SharedPreferences.getInstance());
    AuthSession.resetForTest();
    LocalStorage.savedLocally = false;
  });

  tearDown(() async {
    await AuthSession.clearSession();
    AuthSession.resetForTest();
    LocalStorage.savedLocally = false;
    LocalStorage.resetForTest();
  });

  group('P5.1 GarmentClient HTTP contract', () {
    test(
      'submits, polls crops, saves selected batch, handles 409 and cleanup',
      () async {
        await AuthSession.saveSession('p51-token');
        const runId = 'run-p51-1';
        final cleanupCalls = <String>[];
        var saveAttempts = 0;

        final mockHttp = MockClient((req) async {
          expect(req.headers['Authorization'], 'Bearer p51-token');

          if (req.method == 'POST' && req.url.path == '/v1/analysis/garment') {
            expect(req.headers['Idempotency-Key'], 'submit-key-1');
            return http.Response(jsonEncode({'run_id': runId}), 202);
          }
          if (req.method == 'GET' &&
              req.url.path == '/v1/analysis/runs/$runId') {
            return http.Response(
              jsonEncode(_multiCandidateRunPayload(runId)),
              200,
            );
          }
          if (req.method == 'GET' &&
              req.url.path ==
                  '/v1/analysis/runs/$runId/candidates/cand_top/image') {
            return http.Response.bytes(_kValidPng, 200);
          }
          if (req.method == 'POST' &&
              req.url.path == '/v1/analysis/garment/runs/$runId/save') {
            saveAttempts++;
            if (saveAttempts == 1) {
              return http.Response(jsonEncode({'detail': 'conflict'}), 409);
            }
            final body = jsonDecode(req.body) as Map<String, dynamic>;
            final items = body['items'] as List<dynamic>;
            expect(items.length, 1);
            final firstItem = items.first as Map<String, dynamic>;
            expect(firstItem['candidateId'], 'cand_top');
            expect(firstItem['extractionConfidence'], 0.93);
            expect(firstItem.containsKey('fitConfidence'), isFalse);
            return http.Response(
              jsonEncode({
                'runId': runId,
                'savedItems': [
                  {
                    'id': 'wardrobe-1',
                    'candidateId': 'cand_top',
                    'userId': 'u1',
                    'name': 'oxford shirt',
                    'category': 'tops',
                    'color': 'light_blue',
                    'material': 'cotton',
                    'extractionConfidence': 0.93,
                    'isFavorite': false,
                  },
                ],
                'failedItems': <dynamic>[],
                'cleanedUpAssets': true,
              }),
              200,
            );
          }
          if (req.method == 'DELETE' &&
              req.url.path == '/v1/analysis/garment/runs/$runId/assets') {
            cleanupCalls.add(req.url.path);
            return http.Response(
              jsonEncode({
                'runId': runId,
                'deletedCount': 2,
                'alreadyCleaned': false,
              }),
              200,
            );
          }
          return http.Response('Not found', 404);
        });

        final client = GarmentClient(
          client: mockHttp,
          pollInterval: Duration.zero,
          baseUrl: 'http://localhost:8000',
        );

        final returnedRunId = await client.submitGarmentAnalysisBytes(
          _kFakeJpeg,
          filename: 'shirt.jpg',
          idempotencyKey: 'submit-key-1',
        );
        expect(returnedRunId, runId);

        final polled = await client.pollGarmentRun(runId: runId);
        expect(polled?.isCompleted, isTrue);
        final parsed = GarmentAnalysisResult.fromJson(
          polled!.data!['result'] as Map<String, dynamic>,
        );
        expect(parsed.hasSegmentationMask, isFalse);
        expect(parsed.candidates.length, 2);
        expect(parsed.candidates.first.pattern, 'striped');
        expect(parsed.candidates.first.hasCrop, isTrue);
        expect(parsed.candidates.last.material, isNull);

        final cropBytes = await client.fetchCandidateCropBytes(
          runId: runId,
          candidateId: parsed.candidates.first.id!,
        );
        expect(cropBytes, _kValidPng);

        // 409 conflict reported cleanly
        final conflictRes = await client.saveExtractedGarments(
          runId: runId,
          candidates: [parsed.candidates.first],
          idempotencyKey: 'save-1',
        );
        expect(conflictRes?.isConflict, isTrue);

        // Retry succeeds with 1 selected candidate & triggers server cleanup
        final okRes = await client.saveExtractedGarments(
          runId: runId,
          candidates: [parsed.candidates.first],
          idempotencyKey: 'save-2',
        );
        expect(okRes?.savedItems.length, 1);
        expect(okRes?.savedItems.first.id, 'wardrobe-1');
        expect(okRes?.cleanedUpAssets, isTrue);

        final cleaned = await client.cleanupExtractionAssets(runId: runId);
        expect(cleaned, isTrue);
        expect(cleanupCalls, ['/v1/analysis/garment/runs/$runId/assets']);
      },
    );

    test('surfaces 422 validation message in lastSubmitError', () async {
      await AuthSession.saveSession('p51-token');
      final mockHttp = MockClient((req) async {
        return http.Response(
          jsonEncode({
            'error': {
              'code': 'VALIDATION_ERROR',
              'message': 'Validation failed',
              'details': {
                'field_errors': [
                  {'field': 'image', 'error': 'unsupported media type'},
                ],
              },
            },
          }),
          422,
        );
      });

      final client = GarmentClient(
        client: mockHttp,
        pollInterval: Duration.zero,
        baseUrl: 'http://localhost:8000',
      );
      final id = await client.submitGarmentAnalysisBytes(
        Uint8List.fromList([1, 2, 3, 4]),
        filename: 'bad.gif',
      );
      expect(id, isNull);
      expect(client.lastSubmitError, contains('unsupported media type'));
    });
  });

  group('P5.1 Complete Flutter Extraction User Journey', () {
    testWidgets(
      'StylistScreen navigates to WardrobeExtractionScreen via Extract Garments',
      (tester) async {
        final router = GoRouter(
          initialLocation: '/',
          routes: [
            GoRoute(
              path: '/',
              builder: (_, __) => const StylistScreen(),
              routes: [
                GoRoute(
                  path: 'extraction',
                  name: RouteNames.wardrobeExtraction,
                  builder: (_, __) => const Scaffold(
                    body: Center(child: Text('EXTRACTION_SCREEN_DEST')),
                  ),
                ),
              ],
            ),
          ],
        );

        await tester.pumpWidget(MaterialApp.router(routerConfig: router));
        await tester.pumpAndSettle();

        final cardFinder = find.text('Extract Garments');
        await tester.scrollUntilVisible(
          cardFinder,
          250,
          scrollable: find.byType(Scrollable).first,
        );
        expect(cardFinder, findsOneWidget);

        await tester.tap(cardFinder);
        await tester.pumpAndSettle();
        expect(find.text('EXTRACTION_SCREEN_DEST'), findsOneWidget);
      },
    );

    testWidgets(
      'extracts multiple garments, inspects crop & honest mask limitation, saves selected subset only',
      (tester) async {
        await AuthSession.saveSession('p51-auth-token');
        LocalStorage.savedLocally = false;

        const runId = 'run-ui-multi-1';
        List<dynamic>? savedPayloadItems;

        final mockHttp = MockClient((req) async {
          if (req.method == 'POST' && req.url.path == '/v1/analysis/garment') {
            return http.Response(jsonEncode({'run_id': runId}), 202);
          }
          if (req.method == 'GET' &&
              req.url.path == '/v1/analysis/runs/$runId') {
            return http.Response(
              jsonEncode(_multiCandidateRunPayload(runId)),
              200,
            );
          }
          if (req.method == 'GET' &&
              req.url.path.contains('/candidates/') &&
              req.url.path.endsWith('/image')) {
            return http.Response.bytes(_kValidPng, 200);
          }
          if (req.method == 'POST' &&
              req.url.path == '/v1/analysis/garment/runs/$runId/save') {
            final decoded = jsonDecode(req.body) as Map<String, dynamic>;
            savedPayloadItems = decoded['items'] as List<dynamic>;
            return http.Response(
              jsonEncode({
                'runId': runId,
                'savedItems': [
                  {
                    'id': 'saved-oxford-1',
                    'candidateId': 'cand_top',
                    'userId': 'u1',
                    'name': 'oxford shirt',
                    'category': 'tops',
                    'color': 'light_blue',
                    'material': 'cotton',
                    'isFavorite': false,
                  },
                ],
                'failedItems': <dynamic>[],
                'cleanedUpAssets': true,
              }),
              200,
            );
          }
          if (req.method == 'DELETE') {
            return http.Response(
              jsonEncode({
                'runId': runId,
                'deletedCount': 0,
                'alreadyCleaned': true,
              }),
              200,
            );
          }
          return http.Response('Not found', 404);
        });

        final garmentClient = GarmentClient(
          client: mockHttp,
          pollInterval: Duration.zero,
          baseUrl: 'http://localhost:8000',
        );
        final wardrobeRepo = WardrobeRepositoryImpl(
          client: WardrobeClient(
            client: mockHttp,
            baseUrl: 'http://localhost:8000',
          ),
        );

        List<WardrobeItemData>? poppedItems;
        await tester.pumpWidget(
          MaterialApp(
            home: Builder(
              builder: (context) => Scaffold(
                body: ElevatedButton(
                  onPressed: () async {
                    poppedItems = await Navigator.of(context)
                        .push<List<WardrobeItemData>>(
                          MaterialPageRoute(
                            builder: (_) => WardrobeExtractionScreen(
                              garmentClient: garmentClient,
                              repository: wardrobeRepo,
                              pickImage: (_) async => XFile.fromData(
                                _kValidPng,
                                name: 'outfit.png',
                              ),
                            ),
                          ),
                        );
                  },
                  child: const Text('Launch Extraction'),
                ),
              ),
            ),
          ),
        );

        await tester.tap(find.text('Launch Extraction'));
        await tester.pumpAndSettle();

        // Pick photo from Gallery -> triggers extraction
        await tester.tap(find.text('Choose from Gallery'));
        await tester.pumpAndSettle();

        // Both candidates rendered with pattern pills and count = 2
        expect(find.text('oxford shirt'), findsOneWidget);
        expect(find.text('chino trousers'), findsOneWidget);
        expect(find.text('Pattern: striped'), findsOneWidget);
        expect(find.text('Save Selected to Wardrobe (2)'), findsOneWidget);

        // Open inspect sheet for first candidate & verify honest mask disclosure
        await tester.tap(find.byTooltip('Inspect garment').first);
        await tester.pumpAndSettle();
        expect(find.text('Primary Color'), findsOneWidget);
        expect(
          find.textContaining('Extracted via bounding-box crop'),
          findsOneWidget,
        );
        expect(find.text('Not supported (crop only)'), findsOneWidget);

        // Close inspect sheet
        await tester.tap(find.byIcon(Icons.close_rounded));
        await tester.pumpAndSettle();

        // Deselect the second garment ("chino trousers") via checkbox
        final checkboxes = find.byType(Checkbox);
        expect(checkboxes, findsNWidgets(2));
        await tester.tap(checkboxes.last);
        await tester.pumpAndSettle();
        expect(find.text('Save Selected to Wardrobe (1)'), findsOneWidget);

        // Tap Save -> only cand_top sent to backend endpoint
        await tester.tap(find.text('Save Selected to Wardrobe (1)'));
        await tester.pumpAndSettle();

        expect(savedPayloadItems, isNotNull);
        expect(savedPayloadItems!.length, 1);
        expect((savedPayloadItems!.first as Map)['candidateId'], 'cand_top');
        expect(poppedItems, isNotNull);
        expect(poppedItems!.length, 1);
        expect(poppedItems!.first.name, 'oxford shirt');
      },
    );

    testWidgets(
      'partial save failure marks saved item and retries remaining without duplicating; Try Another cleans temp assets',
      (tester) async {
        await AuthSession.saveSession('p51-auth-token');
        LocalStorage.savedLocally = false;

        const runId = 'run-ui-partial-1';
        var cleanupCalled = false;
        var saveCallCount = 0;

        final mockHttp = MockClient((req) async {
          if (req.method == 'POST' && req.url.path == '/v1/analysis/garment') {
            return http.Response(jsonEncode({'run_id': runId}), 202);
          }
          if (req.method == 'GET' &&
              req.url.path == '/v1/analysis/runs/$runId') {
            return http.Response(
              jsonEncode(_multiCandidateRunPayload(runId)),
              200,
            );
          }
          if (req.method == 'GET' &&
              req.url.path.contains('/candidates/') &&
              req.url.path.endsWith('/image')) {
            return http.Response.bytes(_kValidPng, 200);
          }
          if (req.method == 'POST' &&
              req.url.path == '/v1/analysis/garment/runs/$runId/save') {
            saveCallCount++;
            return http.Response(
              jsonEncode({
                'runId': runId,
                'savedItems': [
                  {
                    'id': 'saved-oxford-1',
                    'candidateId': 'cand_top',
                    'userId': 'u1',
                    'name': 'oxford shirt',
                    'category': 'tops',
                    'color': 'light_blue',
                    'material': 'cotton',
                    'isFavorite': false,
                  },
                ],
                'failedItems': [
                  {
                    'candidateId': 'cand_bottom',
                    'name': 'chino trousers',
                    'error': 'Temporary crop missing',
                  },
                ],
                'cleanedUpAssets': false,
              }),
              200,
            );
          }
          if (req.method == 'DELETE' &&
              req.url.path == '/v1/analysis/garment/runs/$runId/assets') {
            cleanupCalled = true;
            return http.Response(
              jsonEncode({
                'runId': runId,
                'deletedCount': 1,
                'alreadyCleaned': false,
              }),
              200,
            );
          }
          return http.Response('Not found', 404);
        });

        final garmentClient = GarmentClient(
          client: mockHttp,
          pollInterval: Duration.zero,
          baseUrl: 'http://localhost:8000',
        );
        final wardrobeRepo = WardrobeRepositoryImpl(
          client: WardrobeClient(
            client: mockHttp,
            baseUrl: 'http://localhost:8000',
          ),
        );

        await tester.pumpWidget(
          MaterialApp(
            home: WardrobeExtractionScreen(
              initialImageBytes: _kValidPng,
              initialFilename: 'outfit.png',
              garmentClient: garmentClient,
              repository: wardrobeRepo,
            ),
          ),
        );
        await tester.pumpAndSettle();

        await tester.tap(find.text('Save Selected to Wardrobe (2)'));
        await tester.pumpAndSettle();

        expect(saveCallCount, 1);
        expect(find.textContaining('Saved 1 item(s)'), findsOneWidget);
        expect(find.textContaining('SAVED'), findsOneWidget);
        expect(find.text('Save Selected to Wardrobe (1)'), findsOneWidget);

        // User abandons retry via "Cancel" -> deletes remaining temp extraction assets
        await tester.tap(find.text('Cancel'));
        await tester.pumpAndSettle();
        expect(cleanupCalled, isTrue);
      },
    );

    testWidgets(
      'displays actionable error when AI fails or detects no garments',
      (tester) async {
        await AuthSession.saveSession('p51-auth-token');
        const runId = 'run-ui-fail-1';

        final mockHttp = MockClient((req) async {
          if (req.method == 'POST' && req.url.path == '/v1/analysis/garment') {
            return http.Response(jsonEncode({'run_id': runId}), 202);
          }
          if (req.method == 'GET' &&
              req.url.path == '/v1/analysis/runs/$runId') {
            return http.Response(
              jsonEncode({
                'run_id': runId,
                'run_type': 'garment',
                'status': 'failed',
                'error': {
                  'code': 'PROCESSING_FAILURE',
                  'details': {'reason': 'no_garment_detected'},
                },
              }),
              200,
            );
          }
          return http.Response('Not found', 404);
        });

        final garmentClient = GarmentClient(
          client: mockHttp,
          pollInterval: Duration.zero,
          baseUrl: 'http://localhost:8000',
        );

        await tester.pumpWidget(
          MaterialApp(
            home: WardrobeExtractionScreen(
              initialImageBytes: _kFakeJpeg,
              initialFilename: 'empty.jpg',
              garmentClient: garmentClient,
            ),
          ),
        );
        await tester.pumpAndSettle();

        expect(find.text('Analysis Issue'), findsOneWidget);
        expect(find.text('Try Another Photo'), findsOneWidget);
      },
    );

    testWidgets(
      'P5.1A: when candidate A fails and B, C succeed, maps crops & metadata by candidateId and retries A without overwriting B or C',
      (tester) async {
        await AuthSession.saveSession('p51a-auth-token');
        LocalStorage.savedLocally = false;

        const runId = 'run-p51a-3cand';
        final cropA = _distinctPngCrop(0xA1);
        final cropB = _distinctPngCrop(0xB2);
        final cropC = _distinctPngCrop(0xC3);
        final savePayloads = <List<Map<String, dynamic>>>[];
        var saveAttempt = 0;

        final mockHttp = MockClient((req) async {
          if (req.method == 'POST' && req.url.path == '/v1/analysis/garment') {
            return http.Response(jsonEncode({'run_id': runId}), 202);
          }
          if (req.method == 'GET' &&
              req.url.path == '/v1/analysis/runs/$runId') {
            return http.Response(
              jsonEncode({
                'run_id': runId,
                'run_type': 'garment',
                'status': 'completed',
                'result': {
                  'sourceRunId': runId,
                  'extraction_method': 'vlm_bounding_box_crop',
                  'has_segmentation_mask': false,
                  'mask': null,
                  'partial_failures': <dynamic>[],
                  'candidates': [
                    {
                      'id': 'cand_a',
                      'category': 'tops',
                      'subcategory': 'Candidate A Tee',
                      'color': 'white',
                      'fit': 'Regular',
                      'confidence': 0.71,
                      'has_crop': true,
                      'crop_url':
                          '/v1/analysis/runs/$runId/candidates/cand_a/image',
                    },
                    {
                      'id': 'cand_b',
                      'category': 'outerwear',
                      'subcategory': 'Candidate B Blazer',
                      'color': 'navy',
                      'fit': 'Tailored',
                      'confidence': 0.86,
                      'has_crop': true,
                      'crop_url':
                          '/v1/analysis/runs/$runId/candidates/cand_b/image',
                    },
                    {
                      'id': 'cand_c',
                      'category': 'bottoms',
                      'subcategory': 'Candidate C Chinos',
                      'color': 'beige',
                      'fit': 'Slim',
                      'confidence': 0.94,
                      'has_crop': true,
                      'crop_url':
                          '/v1/analysis/runs/$runId/candidates/cand_c/image',
                    },
                  ],
                },
              }),
              200,
            );
          }
          if (req.method == 'GET' &&
              req.url.path ==
                  '/v1/analysis/runs/$runId/candidates/cand_a/image') {
            return http.Response.bytes(cropA, 200);
          }
          if (req.method == 'GET' &&
              req.url.path ==
                  '/v1/analysis/runs/$runId/candidates/cand_b/image') {
            return http.Response.bytes(cropB, 200);
          }
          if (req.method == 'GET' &&
              req.url.path ==
                  '/v1/analysis/runs/$runId/candidates/cand_c/image') {
            return http.Response.bytes(cropC, 200);
          }
          if (req.method == 'POST' &&
              req.url.path == '/v1/analysis/garment/runs/$runId/save') {
            saveAttempt++;
            final decoded = jsonDecode(req.body) as Map<String, dynamic>;
            final items = (decoded['items'] as List<dynamic>)
                .cast<Map<String, dynamic>>();
            savePayloads.add(items);

            if (saveAttempt == 1) {
              // Candidate A fails; Candidates B & C succeed.
              return http.Response(
                jsonEncode({
                  'runId': runId,
                  'savedItems': [
                    {
                      'id': 'wardrobe-b',
                      'candidateId': 'cand_b',
                      'name': 'Candidate B Blazer',
                      'category': 'outerwear',
                      'color': 'navy',
                      'fit': 'Tailored',
                      'fitConfidence': null,
                      'extractionConfidence': 0.86,
                      'imageRef': {
                        'uploadId': 'u-b',
                        'objectKey': 'users/u1/wardrobe/u-b/canonical.webp',
                        'mediaType': 'image/webp',
                        'sourceRunId': runId,
                        'candidateId': 'cand_b',
                        'extractionConfidence': 0.86,
                      },
                      'isFavorite': false,
                    },
                    {
                      'id': 'wardrobe-c',
                      'candidateId': 'cand_c',
                      'name': 'Candidate C Chinos',
                      'category': 'bottoms',
                      'color': 'beige',
                      'fit': 'Slim',
                      'fitConfidence': null,
                      'extractionConfidence': 0.94,
                      'imageRef': {
                        'uploadId': 'u-c',
                        'objectKey': 'users/u1/wardrobe/u-c/canonical.webp',
                        'mediaType': 'image/webp',
                        'sourceRunId': runId,
                        'candidateId': 'cand_c',
                        'extractionConfidence': 0.94,
                      },
                      'isFavorite': false,
                    },
                  ],
                  'failedItems': [
                    {
                      'candidateId': 'cand_a',
                      'name': 'Candidate A Tee',
                      'error': 'Validation error on category',
                    },
                  ],
                  'cleanedUpAssets': false,
                }),
                200,
              );
            }

            // Retry attempt: only cand_a was sent, and even if response echoes
            // cand_b with altered data, already-saved cand_b must not be overwritten.
            return http.Response(
              jsonEncode({
                'runId': runId,
                'savedItems': [
                  {
                    'id': 'wardrobe-a',
                    'candidateId': 'cand_a',
                    'name': 'Candidate A Tee',
                    'category': 'tops',
                    'color': 'white',
                    'fit': 'Regular',
                    'fitConfidence': null,
                    'extractionConfidence': 0.71,
                    'imageRef': {
                      'uploadId': 'u-a',
                      'objectKey': 'users/u1/wardrobe/u-a/canonical.webp',
                      'mediaType': 'image/webp',
                      'sourceRunId': runId,
                      'candidateId': 'cand_a',
                      'extractionConfidence': 0.71,
                    },
                    'isFavorite': false,
                  },
                  {
                    'id': 'wardrobe-b-tampered',
                    'candidateId': 'cand_b',
                    'name': 'Tampered B',
                    'category': 'outerwear',
                    'color': 'black',
                    'isFavorite': false,
                  },
                ],
                'failedItems': <dynamic>[],
                'cleanedUpAssets': true,
              }),
              200,
            );
          }
          if (req.method == 'DELETE') {
            return http.Response(
              jsonEncode({
                'runId': runId,
                'deletedCount': 0,
                'alreadyCleaned': true,
              }),
              200,
            );
          }
          return http.Response('Not found', 404);
        });

        final garmentClient = GarmentClient(
          client: mockHttp,
          pollInterval: Duration.zero,
          baseUrl: 'http://localhost:8000',
        );
        final wardrobeRepo = WardrobeRepositoryImpl(
          client: WardrobeClient(
            client: mockHttp,
            baseUrl: 'http://localhost:8000',
          ),
        );

        List<WardrobeItemData>? poppedItems;
        await tester.pumpWidget(
          MaterialApp(
            home: Builder(
              builder: (context) => Scaffold(
                body: ElevatedButton(
                  onPressed: () async {
                    poppedItems = await Navigator.of(context)
                        .push<List<WardrobeItemData>>(
                          MaterialPageRoute(
                            builder: (_) => WardrobeExtractionScreen(
                              initialImageBytes: _kValidPng,
                              initialFilename: 'three.png',
                              garmentClient: garmentClient,
                              repository: wardrobeRepo,
                            ),
                          ),
                        );
                  },
                  child: const Text('Launch Extraction'),
                ),
              ),
            ),
          ),
        );

        await tester.tap(find.text('Launch Extraction'));
        await tester.pumpAndSettle();

        expect(find.text('Save Selected to Wardrobe (3)'), findsOneWidget);

        // First save attempt: A fails, B & C succeed
        await tester.tap(find.text('Save Selected to Wardrobe (3)'));
        await tester.pumpAndSettle();

        expect(saveAttempt, 1);
        expect(savePayloads[0].length, 3);
        // Verify confidence semantics on outbound request: extractionConfidence sent, fitConfidence absent.
        for (final itemPayload in savePayloads[0]) {
          expect(itemPayload.containsKey('fitConfidence'), isFalse);
          expect(itemPayload['extractionConfidence'], isNotNull);
        }

        // B & C are SAVED; A remains selected and retryable
        expect(find.text('TOPS'), findsOneWidget);
        expect(find.text('OUTERWEAR • SAVED'), findsOneWidget);
        await tester.scrollUntilVisible(
          find.text('BOTTOMS • SAVED'),
          200,
          scrollable: find.byType(Scrollable).first,
        );
        expect(find.text('BOTTOMS • SAVED'), findsOneWidget);
        expect(find.text('Save Selected to Wardrobe (1)'), findsOneWidget);
        expect(
          find.textContaining(
            'Saved 2 item(s). Failed to save: Candidate A Tee',
          ),
          findsOneWidget,
        );

        // Retry saving remaining failed candidate A
        await tester.tap(find.text('Save Selected to Wardrobe (1)'));
        await tester.pumpAndSettle();

        expect(saveAttempt, 2);
        expect(savePayloads[1].length, 1);
        expect(savePayloads[1].first['candidateId'], 'cand_a');

        // Screen popped with all 3 saved items, each mapped to its own candidate crop & metadata
        expect(poppedItems, isNotNull);
        expect(poppedItems!.length, 3);
        final byId = {for (final item in poppedItems!) item.id: item};

        expect(byId.containsKey('wardrobe-a'), isTrue);
        expect(byId.containsKey('wardrobe-b'), isTrue);
        expect(byId.containsKey('wardrobe-c'), isTrue);
        expect(byId.containsKey('wardrobe-b-tampered'), isFalse);

        expect(byId['wardrobe-a']!.name, 'Candidate A Tee');
        expect(byId['wardrobe-a']!.imageBytes, equals(cropA));
        expect(byId['wardrobe-a']!.imageRef?.candidateId, 'cand_a');
        expect(byId['wardrobe-a']!.imageRef?.extractionConfidence, 0.71);

        expect(byId['wardrobe-b']!.name, 'Candidate B Blazer');
        expect(byId['wardrobe-b']!.imageBytes, equals(cropB));
        expect(byId['wardrobe-b']!.imageRef?.candidateId, 'cand_b');
        expect(byId['wardrobe-b']!.imageRef?.extractionConfidence, 0.86);

        expect(byId['wardrobe-c']!.name, 'Candidate C Chinos');
        expect(byId['wardrobe-c']!.imageBytes, equals(cropC));
        expect(byId['wardrobe-c']!.imageRef?.candidateId, 'cand_c');
        expect(byId['wardrobe-c']!.imageRef?.extractionConfidence, 0.94);
      },
    );
  });

  group('P5.1B Complete Journey, Error Matrix & Edge Cases', () {
    test(
      'GarmentClient error matrix: 401, 409, 413, timeouts, backend unavailable, ephemeral',
      () async {
        await AuthSession.saveSession('p51b-token');

        // 1. 401 on submit clears session and sets UNAUTHORIZED
        final c401 = GarmentClient(
          client: MockClient(
            (_) async => http.Response('{"detail":"unauth"}', 401),
          ),
          pollInterval: Duration.zero,
          baseUrl: 'http://localhost:8000',
        );
        expect(await c401.submitGarmentAnalysisBytes(_kFakeJpeg), isNull);
        expect(c401.lastSubmitErrorCode, 'UNAUTHORIZED');
        expect(c401.lastSubmitError, contains('sign in'));
        expect(AuthSession.isAuthenticated, isFalse);

        await AuthSession.saveSession('p51b-token');

        // 2. 409 on submit sets CONFLICT
        final c409 = GarmentClient(
          client: MockClient(
            (_) async => http.Response('{"detail":"conflict"}', 409),
          ),
          pollInterval: Duration.zero,
          baseUrl: 'http://localhost:8000',
        );
        expect(await c409.submitGarmentAnalysisBytes(_kFakeJpeg), isNull);
        expect(c409.lastSubmitErrorCode, 'CONFLICT');

        // 3. 413 on submit sets PAYLOAD_TOO_LARGE
        final c413 = GarmentClient(
          client: MockClient((_) async => http.Response('too big', 413)),
          pollInterval: Duration.zero,
          baseUrl: 'http://localhost:8000',
        );
        expect(await c413.submitGarmentAnalysisBytes(_kFakeJpeg), isNull);
        expect(c413.lastSubmitErrorCode, 'PAYLOAD_TOO_LARGE');

        // 4. Submit TimeoutException & 503 unavailable
        final cTimeout = GarmentClient(
          client: MockClient((_) async => throw TimeoutException('slow')),
          pollInterval: Duration.zero,
          baseUrl: 'http://localhost:8000',
        );
        expect(await cTimeout.submitGarmentAnalysisBytes(_kFakeJpeg), isNull);
        expect(cTimeout.lastSubmitErrorCode, 'TIMEOUT');

        final c503 = GarmentClient(
          client: MockClient((_) async => http.Response('down', 503)),
          pollInterval: Duration.zero,
          baseUrl: 'http://localhost:8000',
        );
        expect(await c503.submitGarmentAnalysisBytes(_kFakeJpeg), isNull);
        expect(c503.lastSubmitErrorCode, 'SERVICE_UNAVAILABLE');

        // 5. Poll 401, 503, TimeoutException, and attempt exhaustion
        final pTimeout = GarmentClient(
          client: MockClient((_) async => throw TimeoutException('poll slow')),
          pollInterval: Duration.zero,
          baseUrl: 'http://localhost:8000',
        );
        expect(await pTimeout.pollGarmentRun(runId: 'r1'), isNull);
        expect(pTimeout.lastPollErrorCode, 'TIMEOUT');

        final p503 = GarmentClient(
          client: MockClient((_) async => http.Response('unavailable', 503)),
          pollInterval: Duration.zero,
          baseUrl: 'http://localhost:8000',
        );
        expect(await p503.pollGarmentRun(runId: 'r1'), isNull);
        expect(p503.lastPollErrorCode, 'SERVICE_UNAVAILABLE');

        final pInferenceTimeout = GarmentClient(
          client: MockClient(
            (_) async => http.Response(
              jsonEncode({'run_id': 'r1', 'status': 'running'}),
              200,
            ),
          ),
          pollInterval: Duration.zero,
          baseUrl: 'http://localhost:8000',
        );
        expect(
          await pInferenceTimeout.pollGarmentRun(runId: 'r1', attempts: 2),
          isNull,
        );
        expect(pInferenceTimeout.lastPollErrorCode, 'INFERENCE_TIMEOUT');

        // 6. Save 401, 503, TimeoutException, and cleanup failure
        const cand = GarmentCandidate(
          id: 'cand_1',
          category: 'tops',
          subcategory: 'Tee',
          color: 'White',
          confidence: 0.9,
        );
        final s401 = GarmentClient(
          client: MockClient((_) async => http.Response('{}', 401)),
          baseUrl: 'http://localhost:8000',
        );
        final res401 = await s401.saveExtractedGarments(
          runId: 'r1',
          candidates: [cand],
        );
        expect(res401?.isUnauthorized, isTrue);
        expect(res401?.hasSavedItems, isFalse);

        final sTimeout = GarmentClient(
          client: MockClient(
            (_) async => throw TimeoutException('save timeout'),
          ),
          baseUrl: 'http://localhost:8000',
        );
        final resTimeout = await sTimeout.saveExtractedGarments(
          runId: 'r1',
          candidates: [cand],
        );
        expect(resTimeout?.errorMessage, contains('timed out'));
        expect(resTimeout?.hasSavedItems, isFalse);

        final cleanFail = GarmentClient(
          client: MockClient((_) async => http.Response('err', 500)),
          baseUrl: 'http://localhost:8000',
        );
        expect(await cleanFail.cleanupExtractionAssets(runId: 'r1'), isFalse);

        // 7. Guest ephemeral oversized / 413 / timeout
        final ephClient = GarmentClient(
          client: MockClient((_) async => http.Response('too large', 413)),
          baseUrl: 'http://localhost:8000',
        );
        final ephOversized = await ephClient.submitGarmentEphemeralBytes(
          Uint8List(GarmentClient.maxImageBytes + 1),
        );
        expect(ephOversized.failureReason, 'oversized_image');
        final eph413 = await ephClient.submitGarmentEphemeralBytes(_kFakeJpeg);
        expect(eph413.failureReason, 'oversized_image');
      },
    );

    testWidgets(
      'single-garment extraction via Stylist -> Save -> Snackbar View -> Wardrobe route',
      (tester) async {
        await AuthSession.saveSession('p51b-single-token');
        LocalStorage.savedLocally = false;
        LearningService.instance.resetForTest();
        addTearDown(() => LearningService.instance.resetForTest());

        const runId = 'run-p51b-single';
        final mockHttp = MockClient((req) async {
          if (req.method == 'POST' && req.url.path == '/v1/analysis/garment') {
            return http.Response(jsonEncode({'run_id': runId}), 202);
          }
          if (req.method == 'GET' &&
              req.url.path == '/v1/analysis/runs/$runId') {
            return http.Response(
              jsonEncode({
                'run_id': runId,
                'run_type': 'garment',
                'status': 'completed',
                'result': {
                  'sourceRunId': runId,
                  'has_segmentation_mask': false,
                  'candidates': [
                    {
                      'id': 'cand_1',
                      'category': 'tops',
                      'subcategory': 'Merino Knit Polo',
                      'color': 'navy',
                      'material': 'wool',
                      'confidence': 0.91,
                      'has_crop': true,
                      'crop_url':
                          '/v1/analysis/runs/$runId/candidates/cand_1/image',
                    },
                  ],
                },
              }),
              200,
            );
          }
          if (req.method == 'GET' &&
              req.url.path ==
                  '/v1/analysis/runs/$runId/candidates/cand_1/image') {
            return http.Response.bytes(_kValidPng, 200);
          }
          if (req.method == 'POST' &&
              req.url.path == '/v1/analysis/garment/runs/$runId/save') {
            return http.Response(
              jsonEncode({
                'runId': runId,
                'savedItems': [
                  {
                    'id': 'wardrobe-single-1',
                    'candidateId': 'cand_1',
                    'userId': 'u1',
                    'name': 'Merino Knit Polo',
                    'category': 'tops',
                    'color': 'navy',
                    'material': 'wool',
                    'extractionConfidence': 0.91,
                    'isFavorite': false,
                  },
                ],
                'failedItems': <dynamic>[],
                'cleanedUpAssets': true,
              }),
              200,
            );
          }
          return http.Response('Not found', 404);
        });

        final garmentClient = GarmentClient(
          client: mockHttp,
          pollInterval: Duration.zero,
          baseUrl: 'http://localhost:8000',
        );
        final wardrobeRepo = WardrobeRepositoryImpl(
          client: WardrobeClient(
            client: mockHttp,
            baseUrl: 'http://localhost:8000',
          ),
        );

        final router = GoRouter(
          initialLocation: '/stylist',
          routes: [
            GoRoute(
              path: '/stylist',
              name: RouteNames.stylist,
              builder: (_, __) =>
                  StylistScreen(wardrobeRepository: wardrobeRepo),
            ),
            GoRoute(
              path: '/wardrobe/extraction',
              name: RouteNames.wardrobeExtraction,
              builder: (_, __) => WardrobeExtractionScreen(
                garmentClient: garmentClient,
                repository: wardrobeRepo,
                pickImage: (_) async =>
                    XFile.fromData(_kValidPng, name: 'polo.png'),
              ),
            ),
            GoRoute(
              path: '/wardrobe',
              name: RouteNames.wardrobe,
              builder: (_, __) => const Scaffold(
                body: Center(child: Text('WARDROBE_DESTINATION')),
              ),
            ),
          ],
        );

        await tester.pumpWidget(MaterialApp.router(routerConfig: router));
        await tester.pumpAndSettle();

        final extractCard = find.text('Extract Garments');
        await tester.scrollUntilVisible(
          extractCard,
          250,
          scrollable: find.byType(Scrollable).first,
        );
        await tester.tap(extractCard);
        await tester.pumpAndSettle();

        await tester.tap(find.text('Choose from Gallery'));
        await tester.pumpAndSettle();

        expect(find.text('Extracted Garments (1)'), findsOneWidget);
        expect(find.text('Merino Knit Polo'), findsOneWidget);
        expect(find.text('Color: navy'), findsOneWidget);
        expect(find.text('91% match'), findsOneWidget);
        expect(find.text('BBox crop • no mask'), findsOneWidget);

        await tester.tap(find.text('Save Selected to Wardrobe (1)'));
        await tester.pumpAndSettle();

        expect(
          find.text('1 garment saved to your Digital Wardrobe'),
          findsOneWidget,
        );
        await tester.tap(find.text('View'));
        await tester.pumpAndSettle();
        expect(find.text('WARDROBE_DESTINATION'), findsOneWidget);
      },
    );

    testWidgets(
      'validates image format and oversized image (>20MB) cleanly before upload',
      (tester) async {
        await AuthSession.saveSession('p51b-val-token');
        var submitCalled = false;
        final garmentClient = GarmentClient(
          client: MockClient((_) async {
            submitCalled = true;
            return http.Response('{}', 202);
          }),
          baseUrl: 'http://localhost:8000',
        );

        // 1. Unsupported format
        await tester.pumpWidget(
          MaterialApp(
            home: WardrobeExtractionScreen(
              garmentClient: garmentClient,
              pickImage: (_) async => XFile.fromData(
                Uint8List.fromList([
                  0x47,
                  0x49,
                  0x46,
                  0x38,
                  0x39,
                  0x61,
                  1,
                  2,
                  3,
                  4,
                  5,
                  6,
                ]),
                name: 'bad.gif',
              ),
            ),
          ),
        );
        await tester.tap(find.text('Choose from Gallery'));
        await tester.pumpAndSettle();
        expect(submitCalled, isFalse);
        expect(find.text('Analysis Issue'), findsOneWidget);
        expect(find.textContaining('Unsupported image format'), findsOneWidget);

        // 2. Oversized image (>20 MB)
        await tester.tap(find.text('Try Another Photo'));
        await tester.pumpAndSettle();
        expect(find.text('Take Photo'), findsOneWidget);

        await tester.pumpWidget(
          MaterialApp(
            home: WardrobeExtractionScreen(
              garmentClient: garmentClient,
              pickImage: (_) async => XFile.fromData(
                Uint8List(GarmentClient.maxImageBytes + 1),
                name: 'huge.jpg',
              ),
            ),
          ),
        );
        await tester.tap(find.text('Choose from Gallery'));
        await tester.pumpAndSettle();
        expect(submitCalled, isFalse);
        expect(find.textContaining('exceeds 20 MB'), findsOneWidget);
      },
    );

    testWidgets(
      'metadata edit updates candidate & save payload, rejects empty name, and handles 409 save retry',
      (tester) async {
        await AuthSession.saveSession('p51b-edit-token');
        LocalStorage.savedLocally = false;
        const runId = 'run-p51b-edit';
        var saveAttempt = 0;
        final saveIdempKeys = <String?>[];
        Map<String, dynamic>? savedItemPayload;

        final mockHttp = MockClient((req) async {
          if (req.method == 'POST' && req.url.path == '/v1/analysis/garment') {
            return http.Response(jsonEncode({'run_id': runId}), 202);
          }
          if (req.method == 'GET' &&
              req.url.path == '/v1/analysis/runs/$runId') {
            return http.Response(
              jsonEncode({
                'run_id': runId,
                'run_type': 'garment',
                'status': 'completed',
                'result': {
                  'sourceRunId': runId,
                  'candidates': [
                    {
                      'id': 'cand_1',
                      'category': 'tops',
                      'subcategory': 'Draft Shirt',
                      'color': 'light_blue',
                      'material': 'cotton',
                      'fit': 'Regular',
                      'confidence': 0.88,
                      'has_crop': true,
                    },
                  ],
                },
              }),
              200,
            );
          }
          if (req.method == 'GET' &&
              req.url.path ==
                  '/v1/analysis/runs/$runId/candidates/cand_1/image') {
            return http.Response.bytes(_kValidPng, 200);
          }
          if (req.method == 'POST' &&
              req.url.path == '/v1/analysis/garment/runs/$runId/save') {
            saveAttempt++;
            saveIdempKeys.add(req.headers['Idempotency-Key']);
            if (saveAttempt == 1) {
              return http.Response(jsonEncode({'detail': 'conflict'}), 409);
            }
            final decoded = jsonDecode(req.body) as Map<String, dynamic>;
            savedItemPayload =
                (decoded['items'] as List).first as Map<String, dynamic>;
            return http.Response(
              jsonEncode({
                'runId': runId,
                'savedItems': [
                  {
                    'id': 'wardrobe-edited-1',
                    'candidateId': 'cand_1',
                    'name': savedItemPayload!['name'],
                    'category': savedItemPayload!['category'],
                    'color': savedItemPayload!['color'],
                    'material': savedItemPayload!['material'],
                    'fit': savedItemPayload!['fit'],
                    'extractionConfidence': 0.88,
                    'isFavorite': false,
                  },
                ],
                'failedItems': <dynamic>[],
                'cleanedUpAssets': true,
              }),
              200,
            );
          }
          return http.Response('Not found', 404);
        });

        final garmentClient = GarmentClient(
          client: mockHttp,
          pollInterval: Duration.zero,
          baseUrl: 'http://localhost:8000',
        );
        final wardrobeRepo = WardrobeRepositoryImpl(
          client: WardrobeClient(
            client: mockHttp,
            baseUrl: 'http://localhost:8000',
          ),
        );

        List<WardrobeItemData>? poppedItems;
        await tester.pumpWidget(
          MaterialApp(
            home: Builder(
              builder: (context) => Scaffold(
                body: ElevatedButton(
                  onPressed: () async {
                    poppedItems = await Navigator.of(context)
                        .push<List<WardrobeItemData>>(
                          MaterialPageRoute(
                            builder: (_) => WardrobeExtractionScreen(
                              initialImageBytes: _kValidPng,
                              initialFilename: 'edit.png',
                              garmentClient: garmentClient,
                              repository: wardrobeRepo,
                            ),
                          ),
                        );
                  },
                  child: const Text('Open'),
                ),
              ),
            ),
          ),
        );

        await tester.tap(find.text('Open'));
        await tester.pumpAndSettle();

        await tester.tap(find.byTooltip('Edit garment'));
        await tester.pumpAndSettle();

        // Empty name shows validation error and does not close sheet
        await tester.enterText(find.byType(TextField).first, '   ');
        await tester.tap(find.text('Done'));
        await tester.pumpAndSettle();
        expect(find.text('Please enter an item name.'), findsOneWidget);

        // Enter valid edited name & change category to Outerwear
        await tester.enterText(
          find.byType(TextField).first,
          'Tailored Denim Overshirt',
        );
        await tester.tap(find.text('Tops').first);
        await tester.pumpAndSettle();
        await tester.tap(find.text('Outerwear').last);
        await tester.pumpAndSettle();

        await tester.tap(find.text('Done'));
        await tester.pumpAndSettle();

        expect(find.text('Tailored Denim Overshirt'), findsOneWidget);
        expect(find.text('OUTERWEAR'), findsOneWidget);

        await tester.tap(find.text('Save Selected to Wardrobe (1)'));
        await tester.pumpAndSettle();

        // 409 conflict triggered automatic retry with a new Idempotency-Key
        expect(saveAttempt, 2);
        expect(saveIdempKeys[0], isNotNull);
        expect(saveIdempKeys[1], isNotNull);
        expect(saveIdempKeys[1], isNot(equals(saveIdempKeys[0])));
        expect(savedItemPayload!['name'], 'Tailored Denim Overshirt');
        expect(savedItemPayload!['category'], 'outerwear');
        expect(savedItemPayload!['color'], 'Light Blue');
        expect(poppedItems?.single.name, 'Tailored Denim Overshirt');
      },
    );

    testWidgets(
      'guest mode extracts via ephemeral endpoint and saves multiple items locally with unique IDs',
      (tester) async {
        AuthSession.resetForTest();
        LocalStorage.savedLocally = true;
        LearningService.instance.resetForTest();
        addTearDown(() => LearningService.instance.resetForTest());

        var ephemeralCalls = 0;
        var authedCalls = 0;
        final mockHttp = MockClient((req) async {
          if (req.url.path == '/v1/analysis/garment/ephemeral') {
            ephemeralCalls++;
            return http.Response(
              jsonEncode({
                'sourceRunId': 'ephem-1',
                'has_segmentation_mask': false,
                'candidates': [
                  {
                    'id': 'cand_1',
                    'category': 'tops',
                    'subcategory': 'Guest Tee',
                    'color': 'white',
                    'confidence': 0.85,
                    'has_crop': false,
                  },
                  {
                    'id': 'cand_2',
                    'category': 'bottoms',
                    'subcategory': 'Guest Jeans',
                    'color': 'indigo',
                    'confidence': 0.82,
                    'has_crop': false,
                  },
                ],
              }),
              200,
            );
          }
          authedCalls++;
          return http.Response('Not found', 404);
        });

        final garmentClient = GarmentClient(
          client: mockHttp,
          baseUrl: 'http://localhost:8000',
        );

        List<WardrobeItemData>? poppedItems;
        await tester.pumpWidget(
          MaterialApp(
            home: Builder(
              builder: (context) => Scaffold(
                body: ElevatedButton(
                  onPressed: () async {
                    poppedItems = await Navigator.of(context)
                        .push<List<WardrobeItemData>>(
                          MaterialPageRoute(
                            builder: (_) => WardrobeExtractionScreen(
                              initialImageBytes: _kValidPng,
                              initialFilename: 'guest.png',
                              garmentClient: garmentClient,
                            ),
                          ),
                        );
                  },
                  child: const Text('Open Guest'),
                ),
              ),
            ),
          ),
        );

        await tester.tap(find.text('Open Guest'));
        await tester.pumpAndSettle();

        expect(ephemeralCalls, 1);
        expect(authedCalls, 0);
        expect(find.text('Extracted Garments (2)'), findsOneWidget);
        expect(find.text('No mask (photo ref)'), findsNWidgets(2));

        await tester.tap(find.text('Save Selected to Wardrobe (2)'));
        await tester.pumpAndSettle();

        expect(poppedItems, isNotNull);
        expect(poppedItems!.length, 2);
        expect(poppedItems![0].id, startsWith('local-'));
        expect(poppedItems![1].id, startsWith('local-'));
        expect(poppedItems![0].id, isNot(equals(poppedItems![1].id)));
        expect(poppedItems![0].sourceRunId, 'ephem-1');
        expect(poppedItems![0].candidateId, 'cand_1');
        expect(poppedItems![0].extractionConfidence, 0.85);
        expect(poppedItems![1].sourceRunId, 'ephem-1');
        expect(poppedItems![1].candidateId, 'cand_2');
        expect(poppedItems![1].extractionConfidence, 0.82);

        final storedItems = LearningService.instance.wardrobe
            .where((entry) => entry.isGuestLocal)
            .toList();
        expect(
          storedItems
              .singleWhere((entry) => entry.id == poppedItems![0].id)
              .sourceRunId,
          'ephem-1',
        );
        expect(
          storedItems
              .singleWhere((entry) => entry.id == poppedItems![1].id)
              .candidateId,
          'cand_2',
        );
      },
    );

    testWidgets(
      'crop unavailable falls back gracefully and allows inspect & save without crash',
      (tester) async {
        await AuthSession.saveSession('p51b-crop-fallback');
        LocalStorage.savedLocally = false;
        const runId = 'run-crop-404';

        final mockHttp = MockClient((req) async {
          if (req.method == 'POST' && req.url.path == '/v1/analysis/garment') {
            return http.Response(jsonEncode({'run_id': runId}), 202);
          }
          if (req.method == 'GET' &&
              req.url.path == '/v1/analysis/runs/$runId') {
            return http.Response(
              jsonEncode({
                'run_id': runId,
                'run_type': 'garment',
                'status': 'completed',
                'result': {
                  'sourceRunId': runId,
                  'candidates': [
                    {
                      'id': 'cand_1',
                      'category': 'outerwear',
                      'subcategory': 'Trench Coat',
                      'color': 'stone',
                      'confidence': 0.87,
                      'has_crop': true,
                      'crop_url':
                          '/v1/analysis/runs/$runId/candidates/cand_1/image',
                    },
                  ],
                },
              }),
              200,
            );
          }
          if (req.method == 'GET' && req.url.path.endsWith('/image')) {
            return http.Response('missing', 404);
          }
          if (req.method == 'POST' &&
              req.url.path == '/v1/analysis/garment/runs/$runId/save') {
            return http.Response(
              jsonEncode({
                'runId': runId,
                'savedItems': [
                  {
                    'id': 'wardrobe-nocrop-1',
                    'candidateId': 'cand_1',
                    'name': 'Trench Coat',
                    'category': 'outerwear',
                    'color': 'stone',
                    'isFavorite': false,
                  },
                ],
                'failedItems': <dynamic>[],
                'cleanedUpAssets': true,
              }),
              200,
            );
          }
          return http.Response('Not found', 404);
        });

        final garmentClient = GarmentClient(
          client: mockHttp,
          pollInterval: Duration.zero,
          baseUrl: 'http://localhost:8000',
        );
        final wardrobeRepo = WardrobeRepositoryImpl(
          client: WardrobeClient(
            client: mockHttp,
            baseUrl: 'http://localhost:8000',
          ),
        );

        await tester.pumpWidget(
          MaterialApp(
            home: WardrobeExtractionScreen(
              initialImageBytes: _kValidPng,
              initialFilename: 'coat.png',
              garmentClient: garmentClient,
              repository: wardrobeRepo,
            ),
          ),
        );
        await tester.pumpAndSettle();

        expect(find.text('Trench Coat'), findsOneWidget);
        expect(find.text('Crop unavailable • no mask'), findsOneWidget);

        await tester.tap(find.byTooltip('Inspect garment'));
        await tester.pumpAndSettle();
        expect(find.textContaining('Crop preview unavailable'), findsOneWidget);
      },
    );

    testWidgets(
      'retake cleans up previous run, cancel during extraction aborts polling & cleans up, and cleanup failure surfaces notice',
      (tester) async {
        await AuthSession.saveSession('p51b-cleanup-token');
        LocalStorage.savedLocally = false;

        final cleanupCalls = <String>[];
        var shouldFailCleanup = false;
        var submitCount = 0;
        var pollCount = 0;
        final pollGate = Completer<void>();

        final mockHttp = MockClient((req) async {
          if (req.method == 'POST' && req.url.path == '/v1/analysis/garment') {
            submitCount++;
            return http.Response(
              jsonEncode({'run_id': 'run-clean-$submitCount'}),
              202,
            );
          }
          if (req.method == 'GET' &&
              req.url.path == '/v1/analysis/runs/run-clean-1') {
            return http.Response(
              jsonEncode(_multiCandidateRunPayload('run-clean-1')),
              200,
            );
          }
          if (req.method == 'GET' &&
              req.url.path == '/v1/analysis/runs/run-clean-2') {
            pollCount++;
            await pollGate.future;
            return http.Response(
              jsonEncode({'run_id': 'run-clean-2', 'status': 'running'}),
              200,
            );
          }
          if (req.method == 'GET' && req.url.path.endsWith('/image')) {
            return http.Response.bytes(_kValidPng, 200);
          }
          if (req.method == 'DELETE' && req.url.path.endsWith('/assets')) {
            cleanupCalls.add(req.url.path);
            if (shouldFailCleanup) {
              return http.Response('storage error', 503);
            }
            return http.Response(jsonEncode({'deletedCount': 1}), 200);
          }
          return http.Response('Not found', 404);
        });

        final garmentClient = GarmentClient(
          client: mockHttp,
          pollInterval: Duration.zero,
          baseUrl: 'http://localhost:8000',
        );

        await tester.pumpWidget(
          MaterialApp(
            home: WardrobeExtractionScreen(
              initialImageBytes: _kValidPng,
              initialFilename: 'first.png',
              garmentClient: garmentClient,
              pickImage: (_) async =>
                  XFile.fromData(_kFakeJpeg, name: 'second.jpg'),
            ),
          ),
        );
        await tester.pumpAndSettle();

        expect(find.text('Extracted Garments (2)'), findsOneWidget);

        // Retake Photo -> cleans up run-clean-1 and returns to idle
        await tester.tap(find.text('Retake Photo'));
        await tester.pumpAndSettle();
        expect(
          cleanupCalls,
          contains('/v1/analysis/garment/runs/run-clean-1/assets'),
        );
        expect(find.text('Take Photo'), findsOneWidget);

        // Pick second photo -> starts extraction on run-clean-2 and pauses in poll
        await tester.tap(find.text('Choose from Gallery'));
        await tester.pump();
        await tester.pump();
        expect(find.text('Extracting garments with AI…'), findsOneWidget);
        expect(find.text('Cancel Extraction'), findsOneWidget);
        expect(pollCount, 1);

        // Simulate cleanup failure when cancelling in-flight extraction
        shouldFailCleanup = true;
        await tester.tap(find.text('Cancel Extraction'));
        pollGate.complete();
        await tester.pumpAndSettle();

        expect(
          cleanupCalls,
          contains('/v1/analysis/garment/runs/run-clean-2/assets'),
        );
        expect(find.text('Take Photo'), findsOneWidget);
        expect(
          find.textContaining('Could not remove temporary preview images'),
          findsOneWidget,
        );
      },
    );

    testWidgets(
      'navigating away and returning preserves state on shell branch and cleans up safely on pop',
      (tester) async {
        await AuthSession.saveSession('p51b-nav-token');
        LocalStorage.savedLocally = false;

        const runId = 'run-nav-1';
        final cleanupCalls = <String>[];
        final mockHttp = MockClient((req) async {
          if (req.method == 'POST' && req.url.path == '/v1/analysis/garment') {
            return http.Response(jsonEncode({'run_id': runId}), 202);
          }
          if (req.method == 'GET' &&
              req.url.path == '/v1/analysis/runs/$runId') {
            return http.Response(
              jsonEncode(_multiCandidateRunPayload(runId)),
              200,
            );
          }
          if (req.method == 'GET' && req.url.path.endsWith('/image')) {
            return http.Response.bytes(_kValidPng, 200);
          }
          if (req.method == 'DELETE' && req.url.path.endsWith('/assets')) {
            cleanupCalls.add(req.url.path);
            return http.Response(jsonEncode({'deletedCount': 2}), 200);
          }
          return http.Response('Not found', 404);
        });

        final garmentClient = GarmentClient(
          client: mockHttp,
          pollInterval: Duration.zero,
          baseUrl: 'http://localhost:8000',
        );

        final router = GoRouter(
          initialLocation: '/home',
          routes: [
            StatefulShellRoute.indexedStack(
              builder: (_, __, shell) => Scaffold(
                body: shell,
                bottomNavigationBar: BottomNavigationBar(
                  currentIndex: shell.currentIndex,
                  onTap: (idx) => shell.goBranch(idx),
                  items: const [
                    BottomNavigationBarItem(
                      icon: Icon(Icons.home),
                      label: 'TabHome',
                    ),
                    BottomNavigationBarItem(
                      icon: Icon(Icons.checkroom),
                      label: 'TabExtract',
                    ),
                  ],
                ),
              ),
              branches: [
                StatefulShellBranch(
                  routes: [
                    GoRoute(
                      path: '/home',
                      builder: (_, __) => const Center(child: Text('HOME_TAB')),
                    ),
                  ],
                ),
                StatefulShellBranch(
                  routes: [
                    GoRoute(
                      path: '/extract',
                      builder: (_, __) => WardrobeExtractionScreen(
                        initialImageBytes: _kValidPng,
                        initialFilename: 'nav.png',
                        garmentClient: garmentClient,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ],
        );

        await tester.pumpWidget(MaterialApp.router(routerConfig: router));
        await tester.pumpAndSettle();

        // Switch to extraction tab
        await tester.tap(find.text('TabExtract'));
        await tester.pumpAndSettle();
        expect(find.text('Extracted Garments (2)'), findsOneWidget);

        // Navigate away to Home tab and back -> state preserved, not cleaned up yet
        await tester.tap(find.text('TabHome'));
        await tester.pumpAndSettle();
        expect(find.text('HOME_TAB'), findsOneWidget);
        expect(cleanupCalls, isEmpty);

        await tester.tap(find.text('TabExtract'));
        await tester.pumpAndSettle();
        expect(find.text('Extracted Garments (2)'), findsOneWidget);

        // Dispose widget tree -> triggers cleanup safely
        await tester.pumpWidget(const SizedBox.shrink());
        await tester.pumpAndSettle();
        expect(cleanupCalls, ['/v1/analysis/garment/runs/$runId/assets']);
      },
    );

    testWidgets(
      'save failure on 401/503 never pops or treats failure as saved',
      (tester) async {
        await AuthSession.saveSession('p51b-savefail');
        LocalStorage.savedLocally = false;
        const runId = 'run-save-fail-1';

        final mockHttp = MockClient((req) async {
          if (req.method == 'POST' && req.url.path == '/v1/analysis/garment') {
            return http.Response(jsonEncode({'run_id': runId}), 202);
          }
          if (req.method == 'GET' &&
              req.url.path == '/v1/analysis/runs/$runId') {
            return http.Response(
              jsonEncode(_multiCandidateRunPayload(runId)),
              200,
            );
          }
          if (req.method == 'GET' && req.url.path.endsWith('/image')) {
            return http.Response.bytes(_kValidPng, 200);
          }
          if (req.method == 'POST' &&
              req.url.path == '/v1/analysis/garment/runs/$runId/save') {
            return http.Response(jsonEncode({'detail': 'unauthorized'}), 401);
          }
          return http.Response('Not found', 404);
        });

        final garmentClient = GarmentClient(
          client: mockHttp,
          pollInterval: Duration.zero,
          baseUrl: 'http://localhost:8000',
        );
        final wardrobeRepo = WardrobeRepositoryImpl(
          client: WardrobeClient(
            client: mockHttp,
            baseUrl: 'http://localhost:8000',
          ),
        );

        var popped = false;
        await tester.pumpWidget(
          MaterialApp(
            home: Builder(
              builder: (context) => Scaffold(
                body: ElevatedButton(
                  onPressed: () async {
                    await Navigator.of(context).push<List<WardrobeItemData>>(
                      MaterialPageRoute(
                        builder: (_) => WardrobeExtractionScreen(
                          initialImageBytes: _kValidPng,
                          initialFilename: 'unauth.png',
                          garmentClient: garmentClient,
                          repository: wardrobeRepo,
                        ),
                      ),
                    );
                    popped = true;
                  },
                  child: const Text('Launch'),
                ),
              ),
            ),
          ),
        );

        await tester.tap(find.text('Launch'));
        await tester.pumpAndSettle();

        await tester.tap(find.text('Save Selected to Wardrobe (2)'));
        await tester.pumpAndSettle();

        expect(popped, isFalse);
        expect(
          find.text('Please sign in to save garments to your wardrobe.'),
          findsOneWidget,
        );
        expect(find.text('Save Selected to Wardrobe (2)'), findsOneWidget);
      },
    );
  });

  group('P5.1D Legacy Add Wardrobe Unified Extraction', () {
    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      LocalStorage.init(prefs: await SharedPreferences.getInstance());
      await AuthSession.clearSession();
      LocalStorage.savedLocally = false;
      LearningService.instance.resetForTest();
    });

    testWidgets(
      'Legacy AddWardrobeItemScreen delegates Analyze Item to unified WardrobeExtractionScreen: crop retrieval, metadata editing, selected-only save, partial-save retry, cleanup, and no duplicate LearningService entries',
      (tester) async {
        await AuthSession.saveSession('p51d-token');
        const runId = 'run-p51d-legacy';
        final cropTop = _distinctPngCrop(0x31);
        final cropBottom = _distinctPngCrop(0x52);

        var cropTopRequests = 0;
        var cropBottomRequests = 0;
        var saveAttempt = 0;
        var cleanupCalls = 0;
        final savedRequestPayloads = <Map<String, dynamic>>[];

        final mockHttp = MockClient((request) async {
          if (request.url.path == '/v1/analysis/garment' &&
              request.method == 'POST') {
            return http.Response(jsonEncode({'run_id': runId}), 202);
          }
          if (request.url.path == '/v1/analysis/runs/$runId' &&
              request.method == 'GET') {
            return http.Response(
              jsonEncode(_multiCandidateRunPayload(runId)),
              200,
            );
          }
          if (request.url.path ==
              '/v1/analysis/runs/$runId/candidates/cand_top/image') {
            cropTopRequests++;
            return http.Response.bytes(cropTop, 200);
          }
          if (request.url.path ==
              '/v1/analysis/runs/$runId/candidates/cand_bottom/image') {
            cropBottomRequests++;
            return http.Response.bytes(cropBottom, 200);
          }
          if (request.url.path == '/v1/analysis/garment/runs/$runId/save' &&
              request.method == 'POST') {
            saveAttempt++;
            final body = jsonDecode(request.body) as Map<String, dynamic>;
            savedRequestPayloads.add(body);
            final items = (body['items'] as List<dynamic>)
                .cast<Map<String, dynamic>>();
            if (saveAttempt == 1) {
              // Partial save: cand_top fails, cand_bottom succeeds
              return http.Response(
                jsonEncode({
                  'savedItems': [
                    {
                      'id': 'wardrobe-uuid-bottom',
                      'candidateId': 'cand_bottom',
                      'name': items.firstWhere(
                        (i) => i['candidateId'] == 'cand_bottom',
                      )['name'],
                      'category': 'bottoms',
                      'color': 'beige',
                      'fit': 'Slim',
                      'isFavorite': false,
                      'createdAt': '2026-11-27T00:00:00Z',
                    },
                  ],
                  'failedItems': [
                    {
                      'candidateId': 'cand_top',
                      'name': 'Edited Oxford',
                      'error': 'Temporary server glitch',
                    },
                  ],
                  'cleanedUpAssets': false,
                }),
                200,
              );
            }
            // Retry succeeds for cand_top only
            return http.Response(
              jsonEncode({
                'savedItems': [
                  {
                    'id': 'wardrobe-uuid-top',
                    'candidateId': 'cand_top',
                    'name': items.first['name'],
                    'category': 'tops',
                    'color': 'light_blue',
                    'material': 'cotton',
                    'fit': 'Regular',
                    'isFavorite': false,
                    'createdAt': '2026-11-27T00:00:00Z',
                  },
                ],
                'failedItems': <dynamic>[],
                'cleanedUpAssets': true,
              }),
              200,
            );
          }
          if (request.url.path == '/v1/analysis/garment/runs/$runId/assets' &&
              request.method == 'DELETE') {
            cleanupCalls++;
            return http.Response(jsonEncode({'deleted': true}), 200);
          }
          return http.Response('Not found', 404);
        });

        final garmentClient = GarmentClient(
          client: mockHttp,
          pollInterval: Duration.zero,
          baseUrl: 'http://localhost:8000',
        );
        final wardrobeRepo = WardrobeRepositoryImpl(
          client: WardrobeClient(
            client: mockHttp,
            baseUrl: 'http://localhost:8000',
          ),
        );
        final topsCategory = AddItemConfig.categories.firstWhere(
          (c) => c.id == 'tops',
        );

        await tester.pumpWidget(
          MaterialApp(
            home: AddWardrobeItemScreen(
              category: topsCategory,
              garmentClient: garmentClient,
              repository: wardrobeRepo,
              photoGalleryPick: (_) async => XFile.fromData(
                _kFakeJpeg,
                name: 'outfit.jpg',
                mimeType: 'image/jpeg',
              ),
            ),
          ),
        );

        // 1. Legacy Add Wardrobe: Take Photo -> Choose from Gallery -> Use Photo
        await tester.scrollUntilVisible(
          find.text('Take Photo'),
          200.0,
          scrollable: find.byType(Scrollable).first,
        );
        await tester.tap(find.text('Take Photo'));
        await tester.pumpAndSettle();
        await tester.tap(find.text('Choose from Gallery').last);
        await tester.pumpAndSettle();
        await tester.tap(find.text('Use Photo'));
        await tester.pumpAndSettle();

        // 2. Tap Analyze Item -> opens unified WardrobeExtractionScreen
        await tester.scrollUntilVisible(
          find.text('Analyze Item'),
          200.0,
          scrollable: find.byType(Scrollable).first,
        );
        await tester.tap(find.text('Analyze Item'));
        await tester.pumpAndSettle();

        expect(find.text('Add via AI Extraction'), findsOneWidget);
        expect(find.text('Extracted Garments (2)'), findsOneWidget);

        // 3. Crop retrieval worked for both candidates
        expect(cropTopRequests, 1);
        expect(cropBottomRequests, 1);

        // 4. Metadata editing works on cand_top
        await tester.tap(find.byIcon(Icons.edit_outlined).first);
        await tester.pumpAndSettle();
        await tester.enterText(find.byType(TextField).first, 'Edited Oxford');
        await tester.tap(find.text('Done'));
        await tester.pumpAndSettle();
        expect(find.text('Edited Oxford'), findsOneWidget);

        // 5. Partial-save + retry: first attempt saves cand_bottom, fails cand_top
        await tester.tap(find.text('Save Selected to Wardrobe (2)'));
        await tester.pumpAndSettle();

        expect(saveAttempt, 1);
        expect(find.textContaining('Saved 1 item(s).'), findsOneWidget);
        expect(find.text('Save Selected to Wardrobe (1)'), findsOneWidget);

        // Retry saves only cand_top
        await tester.tap(find.text('Save Selected to Wardrobe (1)'));
        await tester.pumpAndSettle();

        expect(saveAttempt, 2);
        final retryItems = savedRequestPayloads[1]['items'] as List<dynamic>;
        expect(retryItems.length, 1);
        expect(retryItems.first['candidateId'], 'cand_top');
        expect(retryItems.first['name'], 'Edited Oxford');

        // 6. Returned cleanly to AddWardrobeItemScreen with post-save confirmation
        expect(find.text('Saved 2 items to your wardrobe.'), findsOneWidget);
        expect(find.text('Done'), findsOneWidget);

        // 7. No duplicate entries in LearningService
        expect(
          LearningService.instance.wardrobe
              .where((e) => e.id == 'wardrobe-uuid-bottom')
              .length,
          1,
        );
        expect(
          LearningService.instance.wardrobe
              .where((e) => e.id == 'wardrobe-uuid-top')
              .length,
          1,
        );
        expect(cleanupCalls, 0);
      },
    );

    testWidgets(
      'Legacy AddWardrobeItemScreen unified flow: selected-only save and cleanup on cancel/abandonment',
      (tester) async {
        await AuthSession.saveSession('p51d-token-2');
        const runId = 'run-p51d-cleanup';
        var cleanupCalls = 0;
        final savedPayloads = <Map<String, dynamic>>[];

        final mockHttp = MockClient((request) async {
          if (request.url.path == '/v1/analysis/garment' &&
              request.method == 'POST') {
            return http.Response(jsonEncode({'run_id': runId}), 202);
          }
          if (request.url.path == '/v1/analysis/runs/$runId' &&
              request.method == 'GET') {
            return http.Response(
              jsonEncode(_multiCandidateRunPayload(runId)),
              200,
            );
          }
          if (request.url.path.endsWith('/image')) {
            return http.Response.bytes(_kValidPng, 200);
          }
          if (request.url.path == '/v1/analysis/garment/runs/$runId/assets' &&
              request.method == 'DELETE') {
            cleanupCalls++;
            return http.Response(jsonEncode({'deleted': true}), 200);
          }
          if (request.url.path == '/v1/analysis/garment/runs/$runId/save' &&
              request.method == 'POST') {
            savedPayloads.add(jsonDecode(request.body) as Map<String, dynamic>);
            return http.Response(
              jsonEncode({
                'savedItems': [
                  {
                    'id': 'wardrobe-uuid-only-top',
                    'candidateId': 'cand_top',
                    'name': 'oxford shirt',
                    'category': 'tops',
                    'color': 'light_blue',
                    'isFavorite': false,
                    'createdAt': '2026-11-27T00:00:00Z',
                  },
                ],
                'failedItems': <dynamic>[],
                'cleanedUpAssets': true,
              }),
              200,
            );
          }
          return http.Response('Not found', 404);
        });

        final garmentClient = GarmentClient(
          client: mockHttp,
          pollInterval: Duration.zero,
          baseUrl: 'http://localhost:8000',
        );
        final wardrobeRepo = WardrobeRepositoryImpl(
          client: WardrobeClient(
            client: mockHttp,
            baseUrl: 'http://localhost:8000',
          ),
        );
        final topsCategory = AddItemConfig.categories.firstWhere(
          (c) => c.id == 'tops',
        );

        await tester.pumpWidget(
          MaterialApp(
            home: AddWardrobeItemScreen(
              category: topsCategory,
              garmentClient: garmentClient,
              repository: wardrobeRepo,
              photoGalleryPick: (_) async => XFile.fromData(
                _kFakeJpeg,
                name: 'outfit.jpg',
                mimeType: 'image/jpeg',
              ),
            ),
          ),
        );

        // Open photo and launch unified extraction
        await tester.scrollUntilVisible(
          find.text('Take Photo'),
          200.0,
          scrollable: find.byType(Scrollable).first,
        );
        await tester.tap(find.text('Take Photo'));
        await tester.pumpAndSettle();
        await tester.tap(find.text('Choose from Gallery').last);
        await tester.pumpAndSettle();
        await tester.tap(find.text('Use Photo'));
        await tester.pumpAndSettle();
        await tester.scrollUntilVisible(
          find.text('Analyze Item'),
          200.0,
          scrollable: find.byType(Scrollable).first,
        );
        await tester.tap(find.text('Analyze Item'));
        await tester.pumpAndSettle();

        // Cancel cleans up temporary assets
        await tester.tap(find.text('Cancel'));
        await tester.pumpAndSettle();
        expect(cleanupCalls, 1);
        expect(find.text('Add Tops'), findsOneWidget);

        // Re-launch and test selected-only saving (deselect second candidate)
        await tester.tap(find.text('Analyze Item'));
        await tester.pumpAndSettle();
        await tester.tap(find.byType(Checkbox).last);
        await tester.pumpAndSettle();
        expect(find.text('Save Selected to Wardrobe (1)'), findsOneWidget);

        await tester.tap(find.text('Save Selected to Wardrobe (1)'));
        await tester.pumpAndSettle();

        expect(savedPayloads.length, 1);
        final items = savedPayloads.first['items'] as List<dynamic>;
        expect(items.length, 1);
        expect(items.first['candidateId'], 'cand_top');
      },
    );

    testWidgets(
      'Legacy AddWardrobeItemScreen guest mode uses ephemeral extraction, saves locally with no private assets, and does not create duplicates',
      (tester) async {
        LocalStorage.savedLocally = true;
        var authedCalls = 0;
        var ephemeralCalls = 0;

        final mockHttp = MockClient((request) async {
          if (request.url.path == '/v1/analysis/garment/ephemeral') {
            ephemeralCalls++;
            return http.Response(
              jsonEncode({
                'candidates': [
                  {
                    'id': 'guest_cand_1',
                    'category': 'tops',
                    'subcategory': 'linen shirt',
                    'color': 'White',
                    'confidence': 0.91,
                  },
                ],
              }),
              200,
            );
          }
          authedCalls++;
          return http.Response('Unauthorized', 401);
        });

        final garmentClient = GarmentClient(
          client: mockHttp,
          pollInterval: Duration.zero,
          baseUrl: 'http://localhost:8000',
        );
        final topsCategory = AddItemConfig.categories.firstWhere(
          (c) => c.id == 'tops',
        );

        await tester.pumpWidget(
          MaterialApp(
            home: AddWardrobeItemScreen(
              category: topsCategory,
              garmentClient: garmentClient,
              photoGalleryPick: (_) async => XFile.fromData(
                _kFakeJpeg,
                name: 'guest.jpg',
                mimeType: 'image/jpeg',
              ),
            ),
          ),
        );

        await tester.scrollUntilVisible(
          find.text('Take Photo'),
          200.0,
          scrollable: find.byType(Scrollable).first,
        );
        await tester.tap(find.text('Take Photo'));
        await tester.pumpAndSettle();
        await tester.tap(find.text('Choose from Gallery').last);
        await tester.pumpAndSettle();
        await tester.tap(find.text('Use Photo'));
        await tester.pumpAndSettle();
        await tester.scrollUntilVisible(
          find.text('Analyze Item'),
          200.0,
          scrollable: find.byType(Scrollable).first,
        );
        await tester.tap(find.text('Analyze Item'));
        await tester.pumpAndSettle();

        expect(ephemeralCalls, 1);
        expect(authedCalls, 0);
        expect(
          find.textContaining('Guest mode: items save locally on this device.'),
          findsOneWidget,
        );

        await tester.tap(find.text('Save Selected to Wardrobe (1)'));
        await tester.pumpAndSettle();

        expect(authedCalls, 0);
        expect(
          find.text('Saved linen shirt to your wardrobe.'),
          findsOneWidget,
        );
        final guestItems = LearningService.instance.wardrobe
            .where((e) => e.name == 'linen shirt')
            .toList();
        expect(guestItems.length, 1);
        expect(guestItems.first.id.startsWith('local-'), isTrue);
      },
    );

    testWidgets(
      'WardrobeScreen avoids duplicate LearningService entries when WardrobeItemData is returned',
      (tester) async {
        await AuthSession.saveSession('p51d-token-3');
        const itemId = 'wardrobe-uuid-no-dup';
        const entry = WardrobeEntry(
          id: itemId,
          name: 'Silk Blouse',
          category: 'tops',
          color: 'Cream',
        );
        LearningService.instance.addItem(entry);
        expect(
          LearningService.instance.wardrobe.where((e) => e.id == itemId).length,
          1,
        );

        if (!LearningService.instance.wardrobe.any((e) => e.id == itemId)) {
          LearningService.instance.addItem(entry);
        }
        expect(
          LearningService.instance.wardrobe.where((e) => e.id == itemId).length,
          1,
        );
      },
    );

    testWidgets(
      'P5.1F Multiple-candidate AddWardrobeItemScreen contract: persists all, returns first, survives navigation and reload without duplicates',
      (tester) async {
        await AuthSession.saveSession('p51f-contract-token');
        const runId = 'run-p51f-contract';
        final serverItems = <Map<String, dynamic>>[];

        final mockHttp = MockClient((request) async {
          if (request.url.path == '/v1/analysis/garment' &&
              request.method == 'POST') {
            return http.Response(jsonEncode({'run_id': runId}), 202);
          }
          if (request.url.path == '/v1/analysis/runs/$runId' &&
              request.method == 'GET') {
            return http.Response(
              jsonEncode(_multiCandidateRunPayload(runId)),
              200,
            );
          }
          if (request.url.path.endsWith('/image')) {
            return http.Response.bytes(_kValidPng, 200);
          }
          if (request.url.path == '/v1/analysis/garment/runs/$runId/save' &&
              request.method == 'POST') {
            final savedList = [
              {
                'id': 'wardrobe-p51f-1',
                'candidateId': 'cand_top',
                'name': 'oxford shirt',
                'category': 'tops',
                'color': 'light_blue',
                'isFavorite': false,
                'createdAt': '2026-11-27T00:00:00Z',
              },
              {
                'id': 'wardrobe-p51f-2',
                'candidateId': 'cand_bottom',
                'name': 'chino trousers',
                'category': 'bottoms',
                'color': 'beige',
                'isFavorite': false,
                'createdAt': '2026-11-27T00:00:01Z',
              },
            ];
            serverItems
              ..clear()
              ..addAll(savedList);
            return http.Response(
              jsonEncode({
                'savedItems': savedList,
                'failedItems': <dynamic>[],
                'cleanedUpAssets': true,
              }),
              200,
            );
          }
          if (request.url.path == '/v1/wardrobe/items' &&
              request.method == 'GET') {
            return http.Response(jsonEncode({'items': serverItems}), 200);
          }
          if (request.url.path == '/v1/wardrobe/insights' &&
              request.method == 'GET') {
            return http.Response(
              jsonEncode({
                'totalItems': serverItems.length,
                'categoryCounts': {'tops': 1, 'bottoms': 1},
                'mostWornItem': null,
                'leastWornItem': null,
                'wearStreakDays': 0,
              }),
              200,
            );
          }
          if (request.url.path == '/v1/wardrobe/wear-summary' &&
              request.method == 'GET') {
            return http.Response(
              jsonEncode({
                'totalWears': 0,
                'uniqueItemsWorn': 0,
                'outfitsLogged': 0,
              }),
              200,
            );
          }
          return http.Response('Not found', 404);
        });

        final garmentClient = GarmentClient(
          client: mockHttp,
          pollInterval: Duration.zero,
          baseUrl: 'http://localhost:8000',
        );
        final repo1 = WardrobeRepositoryImpl(
          client: WardrobeClient(
            client: mockHttp,
            baseUrl: 'http://localhost:8000',
          ),
        );
        final topsCategory = AddItemConfig.categories.firstWhere(
          (c) => c.id == 'tops',
        );

        WardrobeItemData? poppedContractItem;
        final router = GoRouter(
          initialLocation: '/wardrobe',
          routes: [
            GoRoute(
              path: '/wardrobe',
              builder: (context, state) => WardrobeScreen(repository: repo1),
            ),
            GoRoute(
              path: '/wardrobe/add-category',
              name: RouteNames.wardrobeAddCategory,
              builder: (context, state) => AddWardrobeItemScreen(
                category: topsCategory,
                garmentClient: garmentClient,
                repository: repo1,
                photoGalleryPick: (_) async => XFile.fromData(
                  _kFakeJpeg,
                  name: 'multi.jpg',
                  mimeType: 'image/jpeg',
                ),
              ),
            ),
          ],
        );

        await tester.pumpWidget(MaterialApp.router(routerConfig: router));
        await tester.pumpAndSettle();

        // Navigate to AddWardrobeItemScreen and capture the Future<WardrobeItemData?> return
        unawaited(
          router
              .pushNamed<WardrobeItemData>(RouteNames.wardrobeAddCategory)
              .then((val) {
                poppedContractItem = val;
              }),
        );
        await tester.pumpAndSettle();

        await tester.scrollUntilVisible(
          find.text('Take Photo'),
          200.0,
          scrollable: find.byType(Scrollable).first,
        );
        await tester.tap(find.text('Take Photo'));
        await tester.pumpAndSettle();
        await tester.tap(find.text('Choose from Gallery').last);
        await tester.pumpAndSettle();
        await tester.tap(find.text('Use Photo'));
        await tester.pumpAndSettle();
        await tester.scrollUntilVisible(
          find.text('Analyze Item'),
          200.0,
          scrollable: find.byType(Scrollable).first,
        );
        await tester.tap(find.text('Analyze Item'));
        await tester.pumpAndSettle();

        // Save both candidates
        await tester.tap(find.text('Save Selected to Wardrobe (2)'));
        await tester.pumpAndSettle();

        expect(find.text('Saved 2 items to your wardrobe.'), findsOneWidget);

        // Tapping Done returns the first saved item per Future<WardrobeItemData?> contract
        await tester.scrollUntilVisible(
          find.text('Done'),
          200.0,
          scrollable: find.byType(Scrollable).first,
        );
        await tester.tap(find.text('Done'));
        await tester.pumpAndSettle();

        expect(poppedContractItem, isNotNull);
        expect(poppedContractItem!.id, 'wardrobe-p51f-1');
        expect(poppedContractItem!.name, 'oxford shirt');

        // Both saved garments are visible in WardrobeScreen
        expect(find.text('oxford shirt'), findsOneWidget);
        expect(find.text('chino trousers'), findsOneWidget);

        // Simulate app restart / repository reload with a fresh WardrobeRepositoryImpl
        final repo2 = WardrobeRepositoryImpl(
          client: WardrobeClient(
            client: mockHttp,
            baseUrl: 'http://localhost:8000',
          ),
        );
        await tester.pumpWidget(
          MaterialApp(home: WardrobeScreen(repository: repo2)),
        );
        await tester.pumpAndSettle();

        expect(find.text('oxford shirt'), findsOneWidget);
        expect(find.text('chino trousers'), findsOneWidget);

        // No duplicate IDs in LearningService
        final ids = LearningService.instance.wardrobe.map((e) => e.id).toList();
        expect(ids.where((id) => id == 'wardrobe-p51f-1').length, 1);
        expect(ids.where((id) => id == 'wardrobe-p51f-2').length, 1);
      },
    );

    testWidgets(
      'P5.1F Guest-to-authenticated transition does not silently duplicate or misrepresent guest local items',
      (tester) async {
        LocalStorage.savedLocally = true;
        final guestEntry = const WardrobeEntry(
          id: 'local-guest-1',
          name: 'Guest Linen Shirt',
          category: 'tops',
          color: 'White',
        );
        LearningService.instance.addItem(guestEntry);

        // Transition guest -> authenticated
        await AuthSession.saveSession('p51f-auth-after-guest');
        expect(LocalStorage.savedLocally, isFalse);

        final mockHttp = MockClient((request) async {
          if (request.url.path == '/v1/wardrobe/items') {
            return http.Response(jsonEncode({'items': <dynamic>[]}), 200);
          }
          if (request.url.path == '/v1/wardrobe/insights') {
            return http.Response(
              jsonEncode({
                'totalItems': 0,
                'categoryCounts': <String, int>{},
                'mostWornItem': null,
                'leastWornItem': null,
                'wearStreakDays': 0,
              }),
              200,
            );
          }
          if (request.url.path == '/v1/wardrobe/wear-summary') {
            return http.Response(
              jsonEncode({
                'totalWears': 0,
                'uniqueItemsWorn': 0,
                'outfitsLogged': 0,
              }),
              200,
            );
          }
          return http.Response('Not found', 404);
        });

        final authedRepo = WardrobeRepositoryImpl(
          client: WardrobeClient(
            client: mockHttp,
            baseUrl: 'http://localhost:8000',
          ),
        );

        await tester.pumpWidget(
          MaterialApp(home: WardrobeScreen(repository: authedRepo)),
        );
        await tester.pumpAndSettle();

        // Authenticated wardrobe shows empty backend wardrobe, not guest local item
        expect(find.text('Guest Linen Shirt'), findsNothing);
      },
    );

    testWidgets(
      'P5.1F Multiple-candidate AddWardrobeItemScreen contract: persists all, returns first, survives navigation and reload without duplicates',
      (tester) async {
        await AuthSession.saveSession('p51f-contract-token');
        const runId = 'run-p51f-contract';
        final serverItems = <Map<String, dynamic>>[];

        final mockHttp = MockClient((request) async {
          if (request.url.path == '/v1/analysis/garment' &&
              request.method == 'POST') {
            return http.Response(jsonEncode({'run_id': runId}), 202);
          }
          if (request.url.path == '/v1/analysis/runs/$runId' &&
              request.method == 'GET') {
            return http.Response(
              jsonEncode(_multiCandidateRunPayload(runId)),
              200,
            );
          }
          if (request.url.path.endsWith('/image')) {
            return http.Response.bytes(_kValidPng, 200);
          }
          if (request.url.path == '/v1/analysis/garment/runs/$runId/save' &&
              request.method == 'POST') {
            final savedList = [
              {
                'id': 'wardrobe-p51f-1',
                'candidateId': 'cand_top',
                'name': 'oxford shirt',
                'category': 'tops',
                'color': 'light_blue',
                'isFavorite': false,
                'createdAt': '2026-11-27T00:00:00Z',
              },
              {
                'id': 'wardrobe-p51f-2',
                'candidateId': 'cand_bottom',
                'name': 'chino trousers',
                'category': 'bottoms',
                'color': 'beige',
                'isFavorite': false,
                'createdAt': '2026-11-27T00:00:01Z',
              },
            ];
            serverItems
              ..clear()
              ..addAll(savedList);
            return http.Response(
              jsonEncode({
                'savedItems': savedList,
                'failedItems': <dynamic>[],
                'cleanedUpAssets': true,
              }),
              200,
            );
          }
          if (request.url.path == '/v1/wardrobe/items' &&
              request.method == 'GET') {
            return http.Response(jsonEncode({'items': serverItems}), 200);
          }
          if (request.url.path == '/v1/wardrobe/insights' &&
              request.method == 'GET') {
            return http.Response(
              jsonEncode({
                'totalItems': serverItems.length,
                'categoryCounts': {'tops': 1, 'bottoms': 1},
                'mostWornItem': null,
                'leastWornItem': null,
                'wearStreakDays': 0,
              }),
              200,
            );
          }
          if (request.url.path == '/v1/wardrobe/wear-summary' &&
              request.method == 'GET') {
            return http.Response(
              jsonEncode({
                'totalWears': 0,
                'uniqueItemsWorn': 0,
                'outfitsLogged': 0,
              }),
              200,
            );
          }
          return http.Response('Not found', 404);
        });

        final garmentClient = GarmentClient(
          client: mockHttp,
          pollInterval: Duration.zero,
          baseUrl: 'http://localhost:8000',
        );
        final repo1 = WardrobeRepositoryImpl(
          client: WardrobeClient(
            client: mockHttp,
            baseUrl: 'http://localhost:8000',
          ),
        );
        final topsCategory = AddItemConfig.categories.firstWhere(
          (c) => c.id == 'tops',
        );

        WardrobeItemData? poppedContractItem;
        final router = GoRouter(
          initialLocation: '/wardrobe',
          routes: [
            GoRoute(
              path: '/wardrobe',
              builder: (context, state) => WardrobeScreen(repository: repo1),
            ),
            GoRoute(
              path: '/wardrobe/add-category',
              name: RouteNames.wardrobeAddCategory,
              builder: (context, state) => AddWardrobeItemScreen(
                category: topsCategory,
                garmentClient: garmentClient,
                repository: repo1,
                photoGalleryPick: (_) async => XFile.fromData(
                  _kFakeJpeg,
                  name: 'multi.jpg',
                  mimeType: 'image/jpeg',
                ),
              ),
            ),
          ],
        );

        await tester.pumpWidget(MaterialApp.router(routerConfig: router));
        await tester.pumpAndSettle();

        // Navigate to AddWardrobeItemScreen and capture the Future<WardrobeItemData?> return
        unawaited(
          router
              .pushNamed<WardrobeItemData>(RouteNames.wardrobeAddCategory)
              .then((val) {
                poppedContractItem = val;
              }),
        );
        await tester.pumpAndSettle();

        await tester.scrollUntilVisible(
          find.text('Take Photo'),
          200.0,
          scrollable: find.byType(Scrollable).first,
        );
        await tester.tap(find.text('Take Photo'));
        await tester.pumpAndSettle();
        await tester.tap(find.text('Choose from Gallery').last);
        await tester.pumpAndSettle();
        await tester.tap(find.text('Use Photo'));
        await tester.pumpAndSettle();
        await tester.scrollUntilVisible(
          find.text('Analyze Item'),
          200.0,
          scrollable: find.byType(Scrollable).first,
        );
        await tester.tap(find.text('Analyze Item'));
        await tester.pumpAndSettle();

        // Save both candidates
        await tester.tap(find.text('Save Selected to Wardrobe (2)'));
        await tester.pumpAndSettle();

        expect(find.text('Saved 2 items to your wardrobe.'), findsOneWidget);

        // Tapping Done returns the first saved item per Future<WardrobeItemData?> contract
        await tester.scrollUntilVisible(
          find.text('Done'),
          200.0,
          scrollable: find.byType(Scrollable).first,
        );
        await tester.tap(find.text('Done'));
        await tester.pumpAndSettle();

        expect(poppedContractItem, isNotNull);
        expect(poppedContractItem!.id, 'wardrobe-p51f-1');
        expect(poppedContractItem!.name, 'oxford shirt');

        // Both saved garments are visible in WardrobeScreen
        expect(find.text('oxford shirt'), findsOneWidget);
        expect(find.text('chino trousers'), findsOneWidget);

        // Simulate app restart / repository reload with a fresh WardrobeRepositoryImpl
        final repo2 = WardrobeRepositoryImpl(
          client: WardrobeClient(
            client: mockHttp,
            baseUrl: 'http://localhost:8000',
          ),
        );
        await tester.pumpWidget(
          MaterialApp(home: WardrobeScreen(repository: repo2)),
        );
        await tester.pumpAndSettle();

        expect(find.text('oxford shirt'), findsOneWidget);
        expect(find.text('chino trousers'), findsOneWidget);

        // No duplicate IDs in LearningService
        final ids = LearningService.instance.wardrobe.map((e) => e.id).toList();
        expect(ids.where((id) => id == 'wardrobe-p51f-1').length, 1);
        expect(ids.where((id) => id == 'wardrobe-p51f-2').length, 1);
      },
    );

    testWidgets(
      'P5.1F Guest-to-authenticated transition does not silently duplicate or misrepresent guest local items',
      (tester) async {
        LocalStorage.savedLocally = true;
        final guestEntry = const WardrobeEntry(
          id: 'local-guest-1',
          name: 'Guest Linen Shirt',
          category: 'tops',
          color: 'White',
        );
        LearningService.instance.addItem(guestEntry);

        // Transition guest -> authenticated
        await AuthSession.saveSession('p51f-auth-after-guest');
        expect(LocalStorage.savedLocally, isFalse);

        final mockHttp = MockClient((request) async {
          if (request.url.path == '/v1/wardrobe/items') {
            return http.Response(jsonEncode({'items': <dynamic>[]}), 200);
          }
          if (request.url.path == '/v1/wardrobe/insights') {
            return http.Response(
              jsonEncode({
                'totalItems': 0,
                'categoryCounts': <String, int>{},
                'mostWornItem': null,
                'leastWornItem': null,
                'wearStreakDays': 0,
              }),
              200,
            );
          }
          if (request.url.path == '/v1/wardrobe/wear-summary') {
            return http.Response(
              jsonEncode({
                'totalWears': 0,
                'uniqueItemsWorn': 0,
                'outfitsLogged': 0,
              }),
              200,
            );
          }
          return http.Response('Not found', 404);
        });

        final authedRepo = WardrobeRepositoryImpl(
          client: WardrobeClient(
            client: mockHttp,
            baseUrl: 'http://localhost:8000',
          ),
        );

        await tester.pumpWidget(
          MaterialApp(home: WardrobeScreen(repository: authedRepo)),
        );
        await tester.pumpAndSettle();

        // Authenticated wardrobe shows empty backend wardrobe, not guest local item
        expect(find.text('Guest Linen Shirt'), findsNothing);
      },
    );
  });
}
