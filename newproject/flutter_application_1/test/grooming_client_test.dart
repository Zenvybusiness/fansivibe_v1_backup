import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:fansivibe/features/grooming/data/grooming_client.dart';

void main() {
  group('GroomingClient.submitGroomingAnalysis wire contract', () {
    test('posts empty JSON to /v1/analysis/grooming (no face_profile_ref)', () async {
      final client = GroomingClient(
        client: MockClient((request) async {
          expect(request.method, 'POST');
          expect(request.url.path, '/v1/analysis/grooming');
          expect(request.headers['Authorization'], 'Bearer dev');
          expect(
            request.headers['Content-Type'],
            contains('application/json'),
          );
          // Phase 28: obsolete face_profile_ref removed — profile-only pass
          // sends empty JSON; backend resolves style_profile by user_id.
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          expect(body.containsKey('face_profile_ref'), isFalse);
          expect(body.containsKey('faceProfileRef'), isFalse);
          expect(body, isEmpty);
          return http.Response('{"run_id": "run-123"}', 202);
        }),
      );

      final runId = await client.submitGroomingAnalysis();

      expect(runId, 'run-123');
    });

    test('returns null when the backend rejects', () async {
      final client = GroomingClient(
        client: MockClient(
          (request) async => http.Response('{"error":{}}', 422),
        ),
      );

      final runId = await client.submitGroomingAnalysis();

      expect(runId, isNull);
    });

    test('returns null on network failure', () async {
      final client = GroomingClient(
        client: MockClient(
          (request) async => throw http.ClientException('connection refused'),
        ),
      );

      final runId = await client.submitGroomingAnalysis();

      expect(runId, isNull);
    });
  });

  group('GroomingClient.getGroomingRun', () {
    test('parses a completed run', () async {
      final client = GroomingClient(
        client: MockClient((request) async {
          expect(request.url.path, '/v1/analysis/runs/run-1');
          return http.Response(
            jsonEncode({'run_id': 'run-1', 'status': 'completed'}),
            200,
          );
        }),
      );

      final run = await client.getGroomingRun(runId: 'run-1');

      expect(run, isNotNull);
      expect(run!.runId, 'run-1');
      expect(run.isCompleted, isTrue);
    });

    test('returns null on failure', () async {
      final client = GroomingClient(
        client: MockClient((request) async => http.Response('', 500)),
      );

      final run = await client.getGroomingRun(runId: 'run-1');

      expect(run, isNull);
    });
  });

  group('GroomingClient.pollGroomingRun', () {
    test('stops polling immediately on a failed run', () async {
      var calls = 0;
      final client = GroomingClient(
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

      final run = await client.pollGroomingRun(runId: 'run-1');

      expect(run, isNotNull);
      expect(run!.isFailed, isTrue);
      expect(calls, 1);
    });
  });
}
