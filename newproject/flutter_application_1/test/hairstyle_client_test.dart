import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_client.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_mock_data.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_models.dart';

void main() {
  group('HairstyleClient.submitHairstyleAnalysis', () {
    test('returns run id on 202', () async {
      final client = HairstyleClient(
        client: MockClient((request) async {
          expect(request.url.path, '/v1/analysis/hairstyle');
          expect(request.headers['Authorization'], 'Bearer dev');
          expect(
            request.headers['Content-Type'],
            contains('multipart/form-data'),
          );
          expect(request.body, contains('faceProfileRef'));
          return http.Response('{"run_id": "run-123"}', 202);
        }),
      );

      final runId = await client.submitHairstyleAnalysis(
        faceProfileRef: 'profile-1',
      );

      expect(runId, 'run-123');
    });

    test('returns null when the backend rejects', () async {
      final client = HairstyleClient(
        client: MockClient(
          (request) async => http.Response('{"error":{}}', 422),
        ),
      );

      final runId = await client.submitHairstyleAnalysis(
        faceProfileRef: 'profile-1',
      );

      expect(runId, isNull);
    });

    test('returns null on network failure', () async {
      final client = HairstyleClient(
        client: MockClient(
          (request) async => throw http.ClientException('connection refused'),
        ),
      );

      final runId = await client.submitHairstyleAnalysis(
        faceProfileRef: 'profile-1',
      );

      expect(runId, isNull);
    });
  });

  group('HairstyleClient.getAnalysisRun', () {
    test('parses a completed run', () async {
      final client = HairstyleClient(
        client: MockClient((request) async {
          expect(request.url.path, '/v1/analysis/runs/run-1');
          return http.Response(
            jsonEncode({'run_id': 'run-1', 'status': 'completed'}),
            200,
          );
        }),
      );

      final run = await client.getAnalysisRun(runId: 'run-1');

      expect(run, isNotNull);
      expect(run!.runId, 'run-1');
      expect(run.isCompleted, isTrue);
    });

    test('parses a failed run with its error body', () async {
      final client = HairstyleClient(
        client: MockClient((request) async {
          expect(request.url.path, '/v1/analysis/runs/run-1');
          return http.Response(
            jsonEncode({
              'run_id': 'run-1',
              'status': 'failed',
              'error': {
                'code': 'PROCESSING_FAILURE',
                'message': "We couldn't finish this request.",
                'details': {'run_id': 'run-1'},
              },
            }),
            200,
          );
        }),
      );

      final run = await client.getAnalysisRun(runId: 'run-1');

      expect(run, isNotNull);
      expect(run!.isFailed, isTrue);
      expect(run.error?['code'], 'PROCESSING_FAILURE');
    });

    test('returns null on failure', () async {
      final client = HairstyleClient(
        client: MockClient((request) async => http.Response('', 500)),
      );

      final run = await client.getAnalysisRun(runId: 'run-1');

      expect(run, isNull);
    });
  });

  group('HairstyleClient.pollAnalysisRun', () {
    test('polls until completed', () async {
      var calls = 0;
      final client = HairstyleClient(
        client: MockClient((request) async {
          calls++;
          return http.Response(
            jsonEncode({'run_id': 'run-1', 'status': 'completed'}),
            200,
          );
        }),
      );

      final run = await client.pollAnalysisRun(runId: 'run-1');

      expect(run, isNotNull);
      expect(run!.isCompleted, isTrue);
      expect(calls, 1);
    });

    test('polls across pending responses', () async {
      var calls = 0;
      final client = HairstyleClient(
        client: MockClient((request) async {
          calls++;
          final status = calls == 1 ? 'pending' : 'completed';
          return http.Response(
            jsonEncode({'run_id': 'run-1', 'status': status}),
            200,
          );
        }),
      );

      final run = await client.pollAnalysisRun(runId: 'run-1');

      expect(run, isNotNull);
      expect(run!.isCompleted, isTrue);
      expect(calls, 2);
    });

    test('returns null when the run never completes', () async {
      final client = HairstyleClient(
        client: MockClient(
          (request) async => http.Response(
            jsonEncode({'run_id': 'run-1', 'status': 'pending'}),
            200,
          ),
        ),
        pollInterval: const Duration(milliseconds: 1),
      );

      final run = await client.pollAnalysisRun(runId: 'run-1');

      expect(run, isNull);
    });

    test('stops polling immediately on a failed run', () async {
      var calls = 0;
      final client = HairstyleClient(
        client: MockClient((request) async {
          calls++;
          return http.Response(
            jsonEncode({
              'run_id': 'run-1',
              'status': 'failed',
              'error': {'code': 'PROCESSING_FAILURE'},
            }),
            200,
          );
        }),
      );

      final run = await client.pollAnalysisRun(runId: 'run-1');

      expect(run, isNotNull);
      expect(run!.isFailed, isTrue);
      expect(calls, 1);
    });

    test('polls across pending responses then a failed run', () async {
      var calls = 0;
      final client = HairstyleClient(
        client: MockClient((request) async {
          calls++;
          final status = calls == 1 ? 'pending' : 'failed';
          return http.Response(
            jsonEncode({'run_id': 'run-1', 'status': status}),
            200,
          );
        }),
      );

      final run = await client.pollAnalysisRun(runId: 'run-1');

      expect(run, isNotNull);
      expect(run!.isFailed, isTrue);
      expect(calls, 2);
    });
  });

  group('HairstyleClient.listRuns', () {
    test('parses the list envelope', () async {
      final client = HairstyleClient(
        client: MockClient((request) async {
          expect(request.url.path, '/v1/analysis/runs');
          return http.Response(
            jsonEncode({
              'items': [
                {
                  'run_id': 'run-1',
                  'run_type': 'hairstyle',
                  'status': 'completed',
                  'created_at': '2026-08-11T10:00:00Z',
                },
                {
                  'run_id': 'run-2',
                  'run_type': 'hairstyle',
                  'status': 'pending',
                  'created_at': '2026-08-11T11:00:00Z',
                },
              ],
              'page': 1,
              'page_size': 20,
              'total': 2,
            }),
            200,
          );
        }),
      );

      final page = await client.listRuns();

      expect(page, isNotNull);
      expect(page!.items.length, 2);
      expect(page.items.first.runId, 'run-1');
      expect(page.items.first.isCompleted, isTrue);
      expect(page.items.last.isCompleted, isFalse);
      expect(page.total, 2);
    });

    test('returns null on failure', () async {
      final client = HairstyleClient(
        client: MockClient((request) async => http.Response('', 500)),
      );

      final page = await client.listRuns();

      expect(page, isNull);
    });
  });

  group('HairstyleClient.saveLook', () {
    test('returns true on 201 and sends idempotency key', () async {
      final client = HairstyleClient(
        client: MockClient((request) async {
          expect(request.url.path, '/v1/looks/saved');
          expect(request.headers['Idempotency-Key'], 'key-123');
          expect(request.headers['Authorization'], 'Bearer dev');
          expect(jsonDecode(request.body)['sourceContext'], 'hairstyle');
          return http.Response(
            '{"id": "saved-1", "look_id": "quiff", "title": "Textured Quiff"}',
            201,
          );
        }),
      );

      final ok = await client.saveLook(
        lookId: 'quiff',
        title: 'Textured Quiff',
        snapshot: const {'name': 'Textured Quiff'},
        idempotencyKey: 'key-123',
      );

      expect(ok, isTrue);
    });

    test('returns false on 409 conflict', () async {
      final client = HairstyleClient(
        client: MockClient(
          (request) async =>
              http.Response('{"error":{"code":"conflict"}}', 409),
        ),
      );

      final ok = await client.saveLook(
        lookId: 'quiff',
        title: 'Textured Quiff',
        snapshot: const {},
        idempotencyKey: 'key-123',
      );

      expect(ok, isFalse);
    });
  });

  group('HairstyleClient full flow', () {
    test('submits, polls across pending, and maps a completed run', () async {
      final calls = <String>[];
      final client = HairstyleClient(
        client: MockClient((request) async {
          calls.add(request.url.path);
          switch (request.url.path) {
            case '/v1/analysis/hairstyle':
              expect(request.headers['Authorization'], 'Bearer dev');
              expect(request.body, contains('faceProfileRef'));
              return http.Response('{"run_id": "run-1"}', 202);
            case '/v1/analysis/runs/run-1':
              final status = calls
                  .where((p) => p == '/v1/analysis/runs/run-1')
                  .length;
              final body = status == 1
                  ? {'run_id': 'run-1', 'status': 'pending'}
                  : {
                      'run_id': 'run-1',
                      'status': 'completed',
                      'result': {
                        'appearance': {
                          'faceShape': 'Round',
                          'skinTone': 'Cool Fair',
                        },
                        'recommendations': {
                          'top': {
                            'id': 'classic_pompadour',
                            'name': 'Classic Pompadour',
                            'matchScore': 0.91,
                            'reasons': ['Adds height'],
                            'stylingTips': 'Blow-dry up.',
                            'maintenance': 'High',
                            'bestFor': 'Round',
                          },
                          'alternatives': <Map<String, dynamic>>[],
                        },
                      },
                    };
              return http.Response(jsonEncode(body), 200);
            default:
              return http.Response('', 404);
          }
        }),
      );

      final runId = await client.submitHairstyleAnalysis(
        faceProfileRef: '00000000-0000-0000-0000-000000000001',
      );
      expect(runId, 'run-1');

      final run = await client.pollAnalysisRun(runId: runId!);
      expect(run, isNotNull);
      expect(run!.isCompleted, isTrue);

      final result = hairstyleResultFromRun(run);
      expect(result.faceShape, 'Round');
      expect(result.skinTone, 'Cool Fair');
      expect(result.topRecommendation.name, 'Classic Pompadour');
      expect(result.topRecommendation.matchScore, 0.91);
    });

    test('falls back to the offline result when the run failed', () async {
      final client = HairstyleClient(
        client: MockClient((request) async {
          if (request.url.path == '/v1/analysis/hairstyle') {
            return http.Response('{"run_id": "run-1"}', 202);
          }
          return http.Response(
            jsonEncode({
              'run_id': 'run-1',
              'status': 'failed',
              'error': {
                'code': 'PROCESSING_FAILURE',
                'message': "We couldn't finish this request.",
              },
            }),
            200,
          );
        }),
      );

      final runId = await client.submitHairstyleAnalysis(
        faceProfileRef: '00000000-0000-0000-0000-000000000001',
      );
      final run = await client.pollAnalysisRun(runId: runId!);

      expect(run, isNotNull);
      expect(run!.isFailed, isTrue);

      final result = hairstyleResultFromRun(run);
      expect(result.faceShape, HairstyleAnalysisResult.mock.faceShape);
    });
  });
}
