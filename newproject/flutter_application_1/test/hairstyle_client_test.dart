import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:fansivibe/features/hairstyle/data/hairstyle_client.dart';

void main() {
  group('HairstyleClient.submitHairstyleAnalysis', () {
    test('returns run id on 202', () async {
      final client = HairstyleClient(
        client: MockClient((request) async {
          expect(request.url.path, '/v1/analysis/hairstyle');
          expect(request.headers['Authorization'], 'Bearer dev');
          expect(request.headers['Content-Type'], contains('multipart/form-data'));
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
        client: MockClient((request) async => http.Response('{"error":{}}', 422)),
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
          expect(request.url.path, '/v1/analysis/run-1');
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
          (request) async =>
              http.Response(jsonEncode({'run_id': 'run-1', 'status': 'pending'}), 200),
        ),
        pollInterval: const Duration(milliseconds: 1),
      );

      final run = await client.pollAnalysisRun(runId: 'run-1');

      expect(run, isNull);
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
}
