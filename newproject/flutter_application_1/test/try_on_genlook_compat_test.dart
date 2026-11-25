import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:image_picker/image_picker.dart';

import 'package:fansivibe/features/try_on/data/try_on_client.dart';
import 'package:fansivibe/features/try_on/data/try_on_models.dart';
import 'package:fansivibe/features/try_on/data/try_on_repository.dart';
import 'package:fansivibe/features/try_on/presentation/try_on_screen.dart';
import 'package:fansivibe/features/wardrobe/data/wardrobe_api_models.dart'
    show MediaRef, WearEventLogResponse, WearSummary;
import 'package:fansivibe/features/wardrobe/data/wardrobe_mock_data.dart'
    show WardrobeInsightData, WardrobeItemData;
import 'package:fansivibe/features/wardrobe/data/wardrobe_repository.dart';

// Minimal valid 1x1 transparent PNG bytes.
final Uint8List _validPng1x1 = base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=',
);

class _StubWardrobeRepository implements WardrobeRepository {
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
        id: '550e8400-e29b-41d4-a716-446655440000',
        name: 'Navy Wool Blazer',
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

void main() {
  group('Genlook Backend Wire Compatibility (Phase 5F)', () {
    test('TryOnClient parses non-mock Genlook job submission, status, and image bytes', () async {
      var pollCount = 0;
      final mockHttp = MockClient((request) async {
        if (request.method == 'POST' && request.url.path == '/v1/tryon/jobs') {
          return http.Response(
            jsonEncode({
              'job_id': 'job-genlook-1',
              'status': 'queued',
              'is_mock': false,
            }),
            202,
          );
        }
        if (request.method == 'GET' && request.url.path == '/v1/tryon/jobs/job-genlook-1') {
          pollCount++;
          if (pollCount == 1) {
            return http.Response(
              jsonEncode({
                'job_id': 'job-genlook-1',
                'status': 'processing',
                'progress': 50,
                'is_mock': false,
                'garment_ids': ['550e8400-e29b-41d4-a716-446655440000'],
              }),
              200,
            );
          }
          return http.Response(
            jsonEncode({
              'job_id': 'job-genlook-1',
              'status': 'completed',
              'progress': 100,
              'is_mock': false,
              'garment_ids': ['550e8400-e29b-41d4-a716-446655440000'],
              'result_media_ref': {
                'key': 'users/u1/tryon/job-genlook-1/result.png',
                'mediaType': 'image/png',
                'isMock': false,
                'provider': 'genlook',
                'creditsCharged': 1,
              },
            }),
            200,
          );
        }
        if (request.method == 'GET' && request.url.path == '/v1/tryon/jobs/job-genlook-1/image') {
          return http.Response.bytes(
            _validPng1x1,
            200,
            headers: {'content-type': 'image/png'},
          );
        }
        return http.Response('Not found', 404);
      });

      final client = TryOnClient(client: mockHttp);
      final submit = await client.submitMockTryOn(
        personBytes: _validPng1x1,
        personFilename: 'person.png',
        outfitSource: 'wardrobe',
        garmentIds: const ['550e8400-e29b-41d4-a716-446655440000'],
        consentAccepted: true,
        idempotencyKey: 'idem-flutter-gl-1',
      );
      expect(submit.job, isNotNull);
      expect(submit.job!.isMock, isFalse);
      expect(submit.job!.state, TryOnJobState.queued);

      final s1 = await client.getJobStatus('job-genlook-1');
      expect(s1, isNotNull);
      expect(s1!.state, TryOnJobState.processing);
      expect(s1.isMock, isFalse);

      final s2 = await client.getJobStatus('job-genlook-1');
      expect(s2, isNotNull);
      expect(s2!.state, TryOnJobState.completed);
      expect(s2.progress, 100);
      expect(s2.isMock, isFalse);

      final bytes = await client.getJobImage('job-genlook-1');
      expect(bytes, isNotNull);
      expect(bytes, equals(_validPng1x1));
    });

    testWidgets('TryOnScreen renders Genlook non-mock AI result and fit disclaimer', (tester) async {
      final mockHttp = MockClient((request) async {
        if (request.method == 'POST' && request.url.path == '/v1/tryon/jobs') {
          return http.Response(
            jsonEncode({
              'job_id': 'job-genlook-ui',
              'status': 'queued',
              'is_mock': false,
            }),
            202,
          );
        }
        if (request.method == 'GET' && request.url.path == '/v1/tryon/jobs/job-genlook-ui') {
          return http.Response(
            jsonEncode({
              'job_id': 'job-genlook-ui',
              'status': 'completed',
              'progress': 100,
              'is_mock': false,
              'garment_ids': ['550e8400-e29b-41d4-a716-446655440000'],
              'result_media_ref': {
                'key': 'users/u1/tryon/job-genlook-ui/result.png',
                'mediaType': 'image/png',
                'isMock': false,
                'provider': 'genlook',
              },
            }),
            200,
          );
        }
        if (request.method == 'GET' && request.url.path == '/v1/tryon/jobs/job-genlook-ui/image') {
          return http.Response.bytes(_validPng1x1, 200, headers: {'content-type': 'image/png'});
        }
        return http.Response('Not found', 404);
      });

      final repo = TryOnRepositoryImpl(client: TryOnClient(client: mockHttp));

      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 2.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await tester.pumpWidget(
        MaterialApp(
          home: TryOnScreen(
            outfitSource: 'wardrobe',
            garmentIds: const ['550e8400-e29b-41d4-a716-446655440000'],
            title: 'Genlook Try-On Compat',
            tryOnRepository: repo,
            wardrobeRepository: _StubWardrobeRepository(),
            pickImage: (_) async => XFile.fromData(
              _validPng1x1,
              name: 'person.png',
              mimeType: 'image/png',
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Choose Photo'));
      await tester.pumpAndSettle();
      await tester.tap(find.byType(Checkbox));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Preview Try-On (Test Data)'));
      await tester.pumpAndSettle(const Duration(seconds: 2));

      expect(find.text('AI Try-On Result'), findsOneWidget);
      expect(
        find.textContaining('does not represent physical garment sizing or fit'),
        findsOneWidget,
      );
      expect(find.text('TEST DATA — NOT AI TRY-ON'), findsNothing);
    });

    test('defaultMaxPollDuration aligns with backend 120s polling window', () {
      expect(
        TryOnScreen.defaultMaxPollDuration,
        greaterThanOrEqualTo(const Duration(seconds: 120)),
      );
    });

    testWidgets('client polling timeout preserves jobId, does not fail or resubmit, and Check Status completes', (tester) async {
      var submitCount = 0;
      var retryCount = 0;
      var pollCount = 0;
      var now = DateTime.utc(2026, 11, 26, 12, 0, 0);

      final mockHttp = MockClient((request) async {
        if (request.method == 'POST' && request.url.path == '/v1/tryon/jobs') {
          submitCount++;
          return http.Response(
            jsonEncode({
              'job_id': 'job-timeout-resume',
              'status': 'queued',
              'is_mock': false,
            }),
            202,
          );
        }
        if (request.method == 'POST' && request.url.path == '/v1/tryon/jobs/job-timeout-resume/retry') {
          retryCount++;
          return http.Response('Conflict', 409);
        }
        if (request.method == 'GET' && request.url.path == '/v1/tryon/jobs/job-timeout-resume') {
          pollCount++;
          if (pollCount <= 2) {
            return http.Response(
              jsonEncode({
                'job_id': 'job-timeout-resume',
                'status': 'processing',
                'progress': 50,
                'is_mock': false,
                'garment_ids': ['550e8400-e29b-41d4-a716-446655440000'],
              }),
              200,
            );
          }
          return http.Response(
            jsonEncode({
              'job_id': 'job-timeout-resume',
              'status': 'completed',
              'progress': 100,
              'is_mock': false,
              'garment_ids': ['550e8400-e29b-41d4-a716-446655440000'],
            }),
            200,
          );
        }
        if (request.method == 'GET' && request.url.path == '/v1/tryon/jobs/job-timeout-resume/image') {
          return http.Response.bytes(_validPng1x1, 200, headers: {'content-type': 'image/png'});
        }
        return http.Response('Not found', 404);
      });

      final repo = TryOnRepositoryImpl(client: TryOnClient(client: mockHttp));
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 2.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await tester.pumpWidget(
        MaterialApp(
          home: TryOnScreen(
            outfitSource: 'wardrobe',
            garmentIds: const ['550e8400-e29b-41d4-a716-446655440000'],
            title: 'Timeout Resume Test',
            tryOnRepository: repo,
            wardrobeRepository: _StubWardrobeRepository(),
            pollInterval: const Duration(milliseconds: 20),
            maxPollDuration: const Duration(seconds: 2),
            now: () => now,
            pickImage: (_) async => XFile.fromData(
              _validPng1x1,
              name: 'person.png',
              mimeType: 'image/png',
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Choose Photo'));
      await tester.pumpAndSettle();
      await tester.tap(find.byType(Checkbox));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Preview Try-On (Test Data)'));
      await tester.pump();

      // Advance clock past maxPollDuration on second poll while job is still processing
      await tester.pump(const Duration(milliseconds: 25));
      now = now.add(const Duration(seconds: 3));
      await tester.pump(const Duration(milliseconds: 25));
      await tester.pumpAndSettle();

      // Shows non-failure timedOut state, never calls retry or duplicate submit
      expect(find.text('Still processing'), findsOneWidget);
      expect(find.text('Check Status'), findsOneWidget);
      expect(find.text('Try Again'), findsNothing);
      expect(submitCount, 1);
      expect(retryCount, 0);

      // Tap Check Status -> polls the same jobId and completes cleanly
      await tester.tap(find.text('Check Status'));
      await tester.pump(const Duration(milliseconds: 25));
      await tester.pumpAndSettle();

      expect(submitCount, 1);
      expect(retryCount, 0);
      expect(find.text('AI Try-On Result'), findsOneWidget);
      expect(
        find.text('Virtual Try-On generation complete. Result saved privately to your profile.'),
        findsOneWidget,
      );
    });

    testWidgets('app backgrounding and resumption continues polling same job without duplicate submit', (tester) async {
      var submitCount = 0;
      var pollCount = 0;
      var allowComplete = false;
      final now = DateTime.utc(2026, 11, 26, 12, 0, 0);

      final mockHttp = MockClient((request) async {
        if (request.method == 'POST' && request.url.path == '/v1/tryon/jobs') {
          submitCount++;
          return http.Response(
            jsonEncode({
              'job_id': 'job-bg-resume',
              'status': 'queued',
              'is_mock': false,
            }),
            202,
          );
        }
        if (request.method == 'GET' && request.url.path == '/v1/tryon/jobs/job-bg-resume') {
          pollCount++;
          if (!allowComplete) {
            return http.Response(
              jsonEncode({
                'job_id': 'job-bg-resume',
                'status': 'processing',
                'progress': 50,
                'is_mock': false,
              }),
              200,
            );
          }
          return http.Response(
            jsonEncode({
              'job_id': 'job-bg-resume',
              'status': 'completed',
              'progress': 100,
              'is_mock': false,
            }),
            200,
          );
        }
        if (request.method == 'GET' && request.url.path == '/v1/tryon/jobs/job-bg-resume/image') {
          return http.Response.bytes(_validPng1x1, 200, headers: {'content-type': 'image/png'});
        }
        return http.Response('Not found', 404);
      });

      final repo = TryOnRepositoryImpl(client: TryOnClient(client: mockHttp));
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 2.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await tester.pumpWidget(
        MaterialApp(
          home: TryOnScreen(
            outfitSource: 'wardrobe',
            garmentIds: const ['550e8400-e29b-41d4-a716-446655440000'],
            title: 'Background Resume Test',
            tryOnRepository: repo,
            wardrobeRepository: _StubWardrobeRepository(),
            pollInterval: const Duration(milliseconds: 30),
            maxPollDuration: const Duration(seconds: 60),
            now: () => now,
            pickImage: (_) async => XFile.fromData(
              _validPng1x1,
              name: 'person.png',
              mimeType: 'image/png',
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Choose Photo'));
      await tester.pumpAndSettle();
      await tester.tap(find.byType(Checkbox));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Preview Try-On (Test Data)'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 35));
      expect(pollCount, greaterThanOrEqualTo(1));

      // Background app: polling pauses while paused
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      final pollsBeforeBg = pollCount;
      await tester.pump(const Duration(milliseconds: 100));
      expect(pollCount, pollsBeforeBg);

      // Resume app after backend finishes: immediate poll completes job
      allowComplete = true;
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pump(const Duration(milliseconds: 40));
      await tester.pumpAndSettle();

      expect(submitCount, 1);
      expect(find.text('AI Try-On Result'), findsOneWidget);
    });

    testWidgets('submit failure preserves Idempotency-Key across retry and cancel shows remote credit notice', (tester) async {
      final seenIdemKeys = <String>[];
      var attempt = 0;

      final mockHttp = MockClient((request) async {
        if (request.method == 'POST' && request.url.path == '/v1/tryon/jobs') {
          attempt++;
          seenIdemKeys.add(request.headers['Idempotency-Key'] ?? '');
          if (attempt == 1) {
            return http.Response('Gateway timeout', 504);
          }
          return http.Response(
            jsonEncode({
              'job_id': 'job-idem-cancel',
              'status': 'processing',
              'is_mock': false,
            }),
            202,
          );
        }
        if (request.method == 'GET' && request.url.path == '/v1/tryon/jobs/job-idem-cancel') {
          return http.Response(
            jsonEncode({
              'job_id': 'job-idem-cancel',
              'status': 'processing',
              'progress': 50,
              'is_mock': false,
            }),
            200,
          );
        }
        if (request.method == 'POST' && request.url.path == '/v1/tryon/jobs/job-idem-cancel/cancel') {
          return http.Response(
            jsonEncode({
              'job_id': 'job-idem-cancel',
              'status': 'cancelled',
              'progress': 0,
              'is_mock': false,
              'error_message':
                  'Cancelled locally. If the request was already submitted to the try-on provider, it may still consume a credit.',
            }),
            200,
          );
        }
        return http.Response('Not found', 404);
      });

      final repo = TryOnRepositoryImpl(client: TryOnClient(client: mockHttp));
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 2.0;
      addTearDown(() => tester.view.resetPhysicalSize());

      await tester.pumpWidget(
        MaterialApp(
          home: TryOnScreen(
            outfitSource: 'wardrobe',
            garmentIds: const ['550e8400-e29b-41d4-a716-446655440000'],
            title: 'Idem & Cancel Test',
            tryOnRepository: repo,
            wardrobeRepository: _StubWardrobeRepository(),
            pollInterval: const Duration(milliseconds: 50),
            pickImage: (_) async => XFile.fromData(
              _validPng1x1,
              name: 'person.png',
              mimeType: 'image/png',
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Choose Photo'));
      await tester.pumpAndSettle();
      await tester.tap(find.byType(Checkbox));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Preview Try-On (Test Data)'));
      await tester.pumpAndSettle();

      expect(find.text('Try Again'), findsOneWidget);
      await tester.tap(find.text('Try Again'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 60));

      expect(seenIdemKeys.length, 2);
      expect(seenIdemKeys[0], isNotEmpty);
      expect(seenIdemKeys[1], equals(seenIdemKeys[0]));

      await tester.tap(find.text('Cancel Request'));
      await tester.pumpAndSettle();

      expect(
        find.textContaining('may still consume a credit'),
        findsWidgets,
      );
    });
  });
}

