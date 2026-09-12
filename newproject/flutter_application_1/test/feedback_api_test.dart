import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:fansivibe/features/feedback/data/feedback_client.dart';
import 'package:fansivibe/features/feedback/data/feedback_models.dart';
import 'package:fansivibe/features/feedback/data/feedback_repository.dart';

const String _savedId = '78ff3686-c950-4cd6-84c3-7e18d6634dfa';

void main() {
  group('FeedbackClient submit path', () {
    test('submit posts the exact wire map with auth and key', () async {
      late Uri seen;
      late String method;
      late Map<String, String> headers;
      late Map<String, dynamic> body;
      final client = FeedbackClient(
        client: MockClient((request) async {
          seen = request.url;
          method = request.method;
          headers = request.headers;
          body = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response('', 204);
        }),
      );

      final result = await client.submitFeedback(
        rating: FeedbackRating.like,
        targetSavedLookId: _savedId,
        idempotencyKey: 'key-1',
      );

      expect(method, 'POST');
      expect(seen.path, '/v1/feedback');
      expect(headers['Authorization'], 'Bearer dev');
      expect(headers['Content-Type'], 'application/json; charset=UTF-8');
      expect(headers['Idempotency-Key'], 'key-1');
      expect(body, {'rating': 'like', 'targetSavedLookId': _savedId});
      expect(result.sent, isTrue);
      expect(result.status, FeedbackStatus.sent);
    });

    test('submit includes reason and look target when provided', () async {
      late Map<String, dynamic> body;
      final client = FeedbackClient(
        client: MockClient((request) async {
          body = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response('', 204);
        }),
      );

      await client.submitFeedback(
        rating: FeedbackRating.dislike,
        reason: 'Too formal',
        targetLookId: 'structured_goatee',
        idempotencyKey: 'key-2',
      );

      expect(body, {
        'rating': 'dislike',
        'reason': 'Too formal',
        'targetLookId': 'structured_goatee',
      });
    });

    test('submit treats 201 as sent (forward-compatible ack)', () async {
      final client = FeedbackClient(
        client: MockClient((_) async => http.Response('{}', 201)),
      );

      final result = await client.submitFeedback(
        rating: FeedbackRating.like,
        idempotencyKey: 'key-3',
      );

      expect(result.sent, isTrue);
    });

    test('submit maps the frozen error table', () async {
      final cases = {
        401: FeedbackStatus.unauthorized,
        409: FeedbackStatus.conflict,
        422: FeedbackStatus.invalid,
        429: FeedbackStatus.rateLimited,
        500: FeedbackStatus.unknown,
      };
      for (final entry in cases.entries) {
        final client = FeedbackClient(
          client: MockClient((_) async => http.Response('{}', entry.key)),
        );
        final result = await client.submitFeedback(
          rating: FeedbackRating.like,
          targetSavedLookId: _savedId,
          idempotencyKey: 'key-${entry.key}',
        );
        expect(result.sent, isFalse, reason: '${entry.key}');
        expect(result.status, entry.value, reason: '${entry.key}');
      }
    });

    test('network failure maps to offline without throwing', () async {
      final client = FeedbackClient(
        client: MockClient((_) async => throw Exception('down')),
      );

      final result = await client.submitFeedback(
        rating: FeedbackRating.like,
        idempotencyKey: 'key-offline',
      );

      expect(result.sent, isFalse);
      expect(result.status, FeedbackStatus.networkError);
    });

    test('submit without a key fails closed with no network call', () async {
      var calls = 0;
      final client = FeedbackClient(
        client: MockClient((_) async {
          calls += 1;
          return http.Response('', 204);
        }),
      );

      final result = await client.submitFeedback(
        rating: FeedbackRating.like,
        idempotencyKey: '',
      );

      expect(result.sent, isFalse);
      expect(calls, 0);
    });

    test('idempotency keys are fresh per attempt and UUID-shaped', () {
      final first = newFeedbackIdempotencyKey();
      final second = newFeedbackIdempotencyKey();
      final uuid = RegExp(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
      );

      expect(first, isNot(second));
      expect(uuid.hasMatch(first), isTrue);
      expect(uuid.hasMatch(second), isTrue);
    });
  });

  group('FeedbackRepository mapping', () {
    test('repository passes submits through verbatim', () async {
      late Map<String, dynamic> body;
      late String? key;
      final repo = FeedbackRepositoryImpl(
        client: FeedbackClient(
          client: MockClient((request) async {
            body = jsonDecode(request.body) as Map<String, dynamic>;
            key = request.headers['Idempotency-Key'];
            return http.Response('', 204);
          }),
        ),
      );

      final result = await repo.submitFeedback(
        rating: FeedbackRating.dislike,
        targetSavedLookId: _savedId,
        idempotencyKey: 'repo-key-1',
      );

      expect(result.sent, isTrue);
      expect(body['rating'], 'dislike');
      expect(body['targetSavedLookId'], _savedId);
      expect(key, 'repo-key-1');

      final failing = FeedbackRepositoryImpl(
        client: FeedbackClient(
          client: MockClient((_) async => http.Response('{}', 500)),
        ),
      );
      final failed = await failing.submitFeedback(
        rating: FeedbackRating.like,
        idempotencyKey: 'repo-key-2',
      );
      expect(failed.sent, isFalse);
      expect(failed.status, FeedbackStatus.unknown);
    });
  });

  group('wire safety: UUIDs only, feedback path only', () {
    test('submits hit only /v1/feedback with the backend UUID', () async {
      final paths = <String>[];
      late Map<String, dynamic> body;
      final client = FeedbackClient(
        client: MockClient((request) async {
          paths.add(request.url.path);
          body = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response('', 204);
        }),
      );

      await client.submitFeedback(
        rating: FeedbackRating.like,
        targetSavedLookId: _savedId,
        idempotencyKey: 'safety-key',
      );

      expect(paths, ['/v1/feedback']);
      expect(body['targetSavedLookId'], _savedId);
      expect(
        RegExp(r'"targetSavedLookId"\s*:\s*"\d+"').hasMatch(jsonEncode(body)),
        isFalse,
      );
      expect(paths.any((p) => p.contains('wear')), isFalse);
      expect(paths.any((p) => p.contains('signal')), isFalse);
      expect(paths.any((p) => p.contains('saved')), isFalse);
    });
  });
}
