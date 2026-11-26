import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/stylist/presentation/stylist_screen.dart';
import 'package:fansivibe/features/wardrobe/data/garment_client.dart';
import 'package:fansivibe/features/wardrobe/data/garment_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_client.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_models.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';
import 'package:fansivibe/features/wardrobe/presentation/wardrobe_extraction_screen.dart';
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

  tearDown(() async {
    await AuthSession.clearSession();
    LocalStorage.savedLocally = false;
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
            expect((items.first as Map)['candidateId'], 'cand_top');
            return http.Response(
              jsonEncode({
                'runId': runId,
                'savedItems': [
                  {
                    'id': 'wardrobe-1',
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
          bytes: _kFakeJpeg,
          filename: 'shirt.jpg',
          contentType: 'image/jpeg',
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
          cropUrl: parsed.candidates.first.cropUrl!,
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
        bytes: Uint8List.fromList([1, 2, 3, 4]),
        filename: 'bad.gif',
        contentType: 'image/gif',
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
                              pickImage: () async => _kFakeJpeg,
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
          find.textContaining('Bounding box crop (mask unsupported)'),
          findsOneWidget,
        );

        // Close inspect sheet
        await tester.tap(find.text('Close'));
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
              initialImageBytes: _kFakeJpeg,
              initialFilename: 'outfit.jpg',
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
        expect(find.text('Saved'), findsOneWidget);
        expect(find.text('Save Selected to Wardrobe (1)'), findsOneWidget);

        // User abandons retry via "Try Another Photo" -> deletes remaining temp extraction assets
        await tester.tap(find.text('Try Another Photo'));
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

        expect(find.text('Extraction Failed'), findsOneWidget);
        expect(find.text('Try Another Photo'), findsOneWidget);
      },
    );
  });
}
