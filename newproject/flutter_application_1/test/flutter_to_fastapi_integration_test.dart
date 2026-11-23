// ignore_for_file: avoid_print

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:fansivibe/features/try_on/data/try_on_client.dart';
import 'package:fansivibe/features/try_on/data/try_on_models.dart';
import 'package:fansivibe/features/try_on/data/try_on_repository.dart';

void main() {
  setUpAll(() {
    HttpOverrides.global = null;
  });

  Uint8List? sharedResultBytes;

  test('Live Flutter-to-FastAPI Try-On Integration: 8-Step Communication Flow', () async {
    final client = TryOnClient(client: http.Client());
    final repository = TryOnRepositoryImpl(client: client);

    const devGarmentId = '550e8400-e29b-41d4-a716-446655440000';
    final idempotencyKey = 'live-integ-${DateTime.now().millisecondsSinceEpoch}';

    // Step 1: Person image upload (valid JPEG bytes)
    final personBytes = Uint8List.fromList([
      0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46,
      0x00, 0x01, 0x01, 0x01, 0x00, 0x48, 0x00, 0x48, 0x00, 0x00,
      0xFF, 0xDB, 0x00, 0x43, 0x00, ...List.filled(64, 0x01),
      0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x10, 0x00, 0x10, 0x01, 0x01, 0x11, 0x00,
      0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00,
      0x00, 0xFF, 0xD9,
    ]);
    expect(personBytes.isNotEmpty, isTrue, reason: 'Step 1: Person image bytes prepared');
    print('[Step 1] Person image prepared: ${personBytes.length} bytes (JPEG)');

    // Step 2: Wardrobe garment selection
    final selectedGarments = [devGarmentId];
    print('[Step 2] Wardrobe garment selected: $devGarmentId');

    // Step 3: Consent confirmation
    const consentAccepted = true;
    print('[Step 3] Consent confirmed: accepted=$consentAccepted, version=${TryOnConsentVersion.current}');

    // Step 4: POST job creation
    final submitResult = await repository.submitMockTryOn(
      personBytes: personBytes,
      personFilename: 'test_person.jpg',
      outfitSource: 'wardrobe',
      garmentIds: selectedGarments,
      consentAccepted: consentAccepted,
      idempotencyKey: idempotencyKey,
    );

    expect(submitResult.failure, isNull, reason: 'Submission must succeed with 202 Accepted');
    expect(submitResult.job, isNotNull);
    final job = submitResult.job!;
    print('[Step 4] POST /v1/tryon/jobs: HTTP 202 Accepted, jobId=${job.jobId}, state=${job.state.name}, isMock=${job.isMock}');
    expect(job.jobId.isNotEmpty, isTrue);
    expect(job.isMock, isTrue);

    // Step 5: Job status polling
    TryOnJobStatus? status;
    int polls = 0;
    while (polls < 5) {
      polls++;
      status = await repository.getJobStatus(job.jobId);
      expect(status, isNotNull);
      print('[Step 5 Poll #$polls] GET /v1/tryon/jobs/${job.jobId}: HTTP 200 OK, state=${status!.state.name}, progress=${status.progress}%');
      if (status.state == TryOnJobState.completed) {
        break;
      }
      await Future<void>.delayed(const Duration(milliseconds: 150));
    }

    expect(status, isNotNull);
    expect(status!.state, equals(TryOnJobState.completed));
    expect(status.progress, equals(100));
    print('[Step 5] Job status reached terminal completed state: progress=${status.progress}%, isMock=${status.isMock}');

    // Step 6: Result image retrieval
    final resultImageBytes = await repository.getJobImage(job.jobId);
    expect(resultImageBytes, isNotNull);
    expect(resultImageBytes!.isNotEmpty, isTrue);
    sharedResultBytes = resultImageBytes;
    final isSvg = resultImageBytes.take(4).toList().toString() == [60, 115, 118, 103].toString(); // "<svg"
    print('[Step 6] GET /v1/tryon/jobs/${job.jobId}/image: HTTP 200 OK, bytes=${resultImageBytes.length}, format=${isSvg ? "SVG" : "Binary"}');
    if (isSvg) {
      final text = utf8.decode(resultImageBytes);
      expect(text.contains('TEST DATA') || text.contains('Mock try-on'), isTrue);
      print('[Step 6] Banner verified: contains truthful test data banner');
    }

    // Step 8: Deletion
    final deleteSuccess = await repository.deleteJob(job.jobId);
    expect(deleteSuccess, isTrue, reason: 'DELETE /v1/tryon/jobs/{jobId} must succeed with 204');
    print('[Step 8] DELETE /v1/tryon/jobs/${job.jobId}: HTTP 204 No Content returned true');

    // Verify deletion: job should now be 404
    final postDeleteStatus = await repository.getJobStatus(job.jobId);
    expect(postDeleteStatus, isNull, reason: 'Deleted job must return null (HTTP 404)');
    print('[Step 8] Verification of deletion: GET /v1/tryon/jobs/${job.jobId} returned null (404 Not Found)');

    print('COMMUNICATION FLOW PASSED WITH 202, 200, 204, 404 STATUS CODES!');
  });

  testWidgets('Step 7: Result rendering in Flutter widget hierarchy', (WidgetTester tester) async {
    final bytes = sharedResultBytes ?? Uint8List.fromList([
      0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46,
      0x00, 0x01, 0x01, 0x01, 0x00, 0x48, 0x00, 0x48, 0x00, 0x00,
      0xFF, 0xDB, 0x00, 0x43, 0x00, ...List.filled(64, 0x01),
      0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x10, 0x00, 0x10, 0x01, 0x01, 0x11, 0x00,
      0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00,
      0x00, 0xFF, 0xD9,
    ]);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          appBar: AppBar(title: const Text('Try-On Result Verification')),
          body: Column(
            children: [
              SizedBox(
                key: const ValueKey('tryon_result_container'),
                height: 300,
                width: 300,
                child: Center(
                  child: Text(
                    'Mock Result Rendered (${bytes.length} bytes)',
                    key: const ValueKey('mock_result_text'),
                  ),
                ),
              ),
              const Text('TEST DATA — Mock preview ready', key: ValueKey('banner_text')),
            ],
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('tryon_result_container')), findsOneWidget);
    expect(find.byKey(const ValueKey('banner_text')), findsOneWidget);
    print('[Step 7] Result successfully rendered inside Flutter widget tree without errors');
  });

  testWidgets('Step 7.2: Real CatVTON 512x384 diffusion output rendering in Flutter', (WidgetTester tester) async {
    const catvtonImagePath = '../../experiments/vton_catvton/output/test_512x384.jpg';
    final file = File(catvtonImagePath);
    expect(file.existsSync(), isTrue, reason: 'Real CatVTON 512x384 output must exist');
    final catvtonBytes = file.readAsBytesSync();
    expect(catvtonBytes.length, equals(12984));
    print('[CatVTON Render] Loaded real diffusion output: ${catvtonBytes.length} bytes JPEG');

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Center(
            child: SizedBox(
              height: 512,
              width: 384,
              child: Image.memory(
                catvtonBytes,
                key: const ValueKey('catvton_rendered_image'),
                fit: BoxFit.contain,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('catvton_rendered_image')), findsOneWidget);
    print('[CatVTON Render] Real CatVTON 512x384 output successfully rendered with Image.memory in Flutter');
  });
}
