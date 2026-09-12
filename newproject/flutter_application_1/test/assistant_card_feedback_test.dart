import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:fansivibe/features/assistant/data/assistant_client.dart';
import 'package:fansivibe/features/assistant/data/models.dart';
import 'package:fansivibe/features/assistant/domain/assistant_service.dart';
import 'package:fansivibe/features/learning/data/models.dart';
import 'package:fansivibe/features/learning/learning_repository.dart';

/// STEP B-A — card-feedback tests (#17 / UC-23).
///
/// Client: exact path/method/auth/body, optional-field serialization,
/// 204-only success, never-throws failure. Service: backend-first with no
/// double counting, local fallback only on failure, existing behavior
/// intact. No network, no backend: `MockClient` + fakes only.
void main() {
  group('AssistantClient.submitCardFeedback', () {
    test('posts opened body to /v1/assistant/feedback with auth', () async {
      final client = AssistantClient(
        client: MockClient((request) async {
          expect(request.method, 'POST');
          expect(request.url.path, '/v1/assistant/feedback');
          expect(request.headers['Authorization'], 'Bearer dev');
          expect(
            request.headers['Content-Type'],
            'application/json; charset=UTF-8',
          );
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          expect(body['interactionType'], 'opened');
          expect(body['cardTitle'], 'Textured Quiff');
          expect(body.containsKey('cardId'), isFalse);
          return http.Response('', 204);
        }),
      );

      expect(
        await client.submitCardFeedback(
          cardTitle: 'Textured Quiff',
          interactionType: 'opened',
        ),
        isTrue,
      );
    });

    test('posts navigated body with card reference', () async {
      final client = AssistantClient(
        client: MockClient((request) async {
          expect(request.url.path, '/v1/assistant/feedback');
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          expect(body['interactionType'], 'navigated');
          expect(body['cardTitle'], 'stylist');
          return http.Response('', 204);
        }),
      );

      expect(
        await client.submitCardFeedback(
          cardTitle: 'stylist',
          interactionType: 'navigated',
        ),
        isTrue,
      );
    });

    test('serializes both optional fields when present', () async {
      final client = AssistantClient(
        client: MockClient((request) async {
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          expect(body['cardId'], 'look_suggestion_04');
          expect(body['cardTitle'], 'Textured Quiff');
          expect(body['interactionType'], 'opened');
          return http.Response('', 204);
        }),
      );

      expect(
        await client.submitCardFeedback(
          cardId: 'look_suggestion_04',
          cardTitle: 'Textured Quiff',
          interactionType: 'opened',
        ),
        isTrue,
      );
    });

    test('omits absent optional fields', () async {
      final client = AssistantClient(
        client: MockClient((request) async {
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          expect(body.keys, ['interactionType']);
          return http.Response('', 204);
        }),
      );

      expect(
        await client.submitCardFeedback(interactionType: 'opened'),
        isTrue,
      );
    });

    test('non-204 is failure without throwing', () async {
      final client = AssistantClient(
        client: MockClient(
          (request) async => http.Response('{"error":{}}', 422),
        ),
      );

      expect(
        await client.submitCardFeedback(interactionType: 'bogus'),
        isFalse,
      );
    });

    test('network failure is failure without throwing', () async {
      final client = AssistantClient(
        client: MockClient(
          (request) async => throw http.ClientException('connection refused'),
        ),
      );

      expect(
        await client.submitCardFeedback(interactionType: 'opened'),
        isFalse,
      );
    });
  });

  group('AssistantService card interaction reporting', () {
    test('backend success records no local signal (no double count)', () async {
      final learning = _RecordingLearningRepository();
      final service = AssistantService(
        client: AssistantClient(
          client: MockClient((request) async => http.Response('', 204)),
        ),
        learning: learning,
      );
      addTearDown(service.dispose);

      service.onCardOpened(
        const SuggestionCard(
          kind: 'tip',
          title: 'Textured Quiff',
          subtitle: 'Volume on top',
        ),
      );
      await Future<void>.delayed(Duration.zero);

      expect(learning.recorded, isEmpty);
    });

    test('backend failure falls back to one local signal', () async {
      final learning = _RecordingLearningRepository();
      final service = AssistantService(
        client: AssistantClient(
          client: MockClient((request) async => http.Response('oops', 500)),
        ),
        learning: learning,
      );
      addTearDown(service.dispose);

      service.onNavigated(
        const NavigationRequest(route: 'stylist', label: 'Stylist'),
      );
      await Future<void>.delayed(Duration.zero);

      expect(learning.recorded, <(String, String)>[('assistant_navigation', 'stylist')]);
    });

    test('offline exception falls back without throwing', () async {
      final learning = _RecordingLearningRepository();
      final service = AssistantService(
        client: AssistantClient(
          client: MockClient(
            (request) async => throw http.ClientException('connection refused'),
          ),
        ),
        learning: learning,
      );
      addTearDown(service.dispose);

      service.onCardOpened(
        const SuggestionCard(
          kind: 'tip',
          title: 'Textured Quiff',
          subtitle: 'Volume on top',
        ),
      );
      await Future<void>.delayed(Duration.zero);

      expect(learning.recorded, <(String, String)>[('suggestion_opened', 'Textured Quiff')]);
    });

    test('existing message-signal behavior is intact', () async {
      final learning = _RecordingLearningRepository();
      final service = AssistantService(
        client: AssistantClient(
          client: MockClient(
            (request) async => http.Response(
              jsonEncode({
                'intent': 'greeting',
                'text': 'Hi',
                'cards': <Map<String, dynamic>>[],
                'clarifications': <Map<String, dynamic>>[],
              }),
              200,
            ),
          ),
        ),
        learning: learning,
      );
      addTearDown(service.dispose);

      await service.send('hello');
      expect(
        learning.recorded.any((entry) => entry.$1 == 'assistant_message'),
        isTrue,
      );
    });
  });
}

class _RecordingLearningRepository implements LearningRepository {
  final List<(String, String)> recorded = [];

  @override
  List<WardrobeEntry> get wardrobe => const [];

  @override
  FaceProfile? get face => null;

  @override
  String? get styleType => null;

  @override
  List<String> get savedLooks => const [];

  @override
  List<String> get preferredOccasions => const [];

  @override
  List<LearningSignal> get signals => const [];

  @override
  int get styleScore => 0;

  @override
  Future<void> load() async {}

  @override
  void addItem(WardrobeEntry item) {}

  @override
  void setFace(FaceProfile face) {}

  @override
  void setStyleType(String value) {}

  @override
  void addSavedLook(String title) {}

  @override
  void addPreferredOccasion(String occasion) {}

  @override
  void recordSignal(String type, String label) {
    recorded.add((type, label));
  }

  @override
  void updateItem(String itemId, WardrobeEntry item) {}
}
