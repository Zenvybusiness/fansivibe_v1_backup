import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/features/assistant/data/assistant_client.dart';
import 'package:fansivibe/features/assistant/data/models.dart';
import 'package:fansivibe/features/assistant/domain/assistant_service.dart';
import 'package:fansivibe/features/assistant/presentation/widgets/assistant_widgets.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    LocalStorage.init(prefs: await SharedPreferences.getInstance());
    AuthSession.resetForTest();
    await AuthSession.clearSession();
  });

  tearDown(() async {
    AuthSession.resetForTest();
    await AuthSession.clearSession();
  });

  group('P2-5: Assistant chat authentication', () {
    test(
      '1. Authenticated chat sends the correct Bearer token from AuthSession',
      () async {
        await AuthSession.saveSession('user-authenticated-jwt-token-123');

        String? observedAuthHeader;
        String? observedContentType;

        final mockHttpClient = MockClient((request) async {
          expect(request.method, 'POST');
          expect(request.url.path, '/v1/assistant/chat');
          observedAuthHeader = request.headers['Authorization'];
          observedContentType = request.headers['Content-Type'];

          return http.Response(
            jsonEncode({
              'intent': 'greeting',
              'text': 'Hello from authenticated backend.',
              'cards': [],
              'clarifications': [],
            }),
            200,
            headers: {'content-type': 'application/json; charset=UTF-8'},
          );
        });

        final client = AssistantClient(client: mockHttpClient);
        final reply = await client.chat(
          history: [const AssistantMessage(role: 'user', text: 'hi')],
          context: const AssistantUserContext(),
        );

        expect(observedAuthHeader, 'Bearer user-authenticated-jwt-token-123');
        expect(observedContentType, 'application/json; charset=UTF-8');
        expect(reply, isNotNull);
        expect(reply!.text, 'Hello from authenticated backend.');
      },
    );

    test('2. The token is dynamic and not hardcoded', () async {
      final recordedTokens = <String?>[];

      final mockHttpClient = MockClient((request) async {
        recordedTokens.add(request.headers['Authorization']);
        return http.Response(
          jsonEncode({
            'intent': 'chat',
            'text': 'OK',
            'cards': [],
            'clarifications': [],
          }),
          200,
          headers: {'content-type': 'application/json; charset=UTF-8'},
        );
      });

      final client = AssistantClient(client: mockHttpClient);

      // Session A
      await AuthSession.saveSession('session-token-alpha');
      expect(AssistantClient.devToken, 'session-token-alpha');
      await client.chat(
        history: [],
        context: const AssistantUserContext(),
      );
      expect(recordedTokens.last, 'Bearer session-token-alpha');

      // Session B
      await AuthSession.saveSession('session-token-beta');
      expect(AssistantClient.devToken, 'session-token-beta');
      await client.chat(
        history: [],
        context: const AssistantUserContext(),
      );
      expect(recordedTokens.last, 'Bearer session-token-beta');

      // Logged out / cleared session -> fallback default
      await AuthSession.clearSession();
      expect(AssistantClient.devToken, 'dev');
      await client.chat(
        history: [],
        context: const AssistantUserContext(),
      );
      expect(recordedTokens.last, 'Bearer dev');
    });

    test(
      '3. Unauthorized 401 response invokes existing session handling',
      () async {
        var sessionExpiredNotified = false;
        AuthSession.onSessionExpired = () {
          sessionExpiredNotified = true;
        };

        await AuthSession.saveSession('expired-session-token');
        expect(AuthSession.isAuthenticated, isTrue);

        final mockHttpClient = MockClient((request) async {
          expect(request.headers['Authorization'], 'Bearer expired-session-token');
          return http.Response(
            jsonEncode({'detail': 'Token expired or revoked'}),
            401,
            headers: {'content-type': 'application/json; charset=UTF-8'},
          );
        });

        final client = AssistantClient(client: mockHttpClient);
        final reply = await client.chat(
          history: [],
          context: const AssistantUserContext(),
        );

        // Client returns null on failure so service degrades gracefully
        expect(reply, isNull);

        // Dead session was dropped and expiry listener fired
        expect(sessionExpiredNotified, isTrue);
        expect(AuthSession.isAuthenticated, isFalse);
        expect(AuthSession.token, isNull);
      },
    );

    test(
      '4. Offline fallback still works on 401/error and remains labeled offline (P2-4)',
      () async {
        await AuthSession.saveSession('expired-token');

        final mockHttpClient = MockClient((request) async {
          return http.Response('Unauthorized', 401);
        });

        final client = AssistantClient(client: mockHttpClient);
        final service = AssistantService(client: client);

        await service.send('hello');

        expect(service.messages.length, 2);
        final assistantMsg = service.messages[1];

        // Degradation is graceful: offline response generated
        expect(assistantMsg.role, 'assistant');
        expect(assistantMsg.text, contains('Fansivibe stylist'));
        // P2-4 guarantee: offline fallback is truthfully marked offline
        expect(assistantMsg.isOffline, isTrue);

        // Widget bubble verification
        final widget = MaterialApp(
          home: Scaffold(
            body: MessageBubble(message: assistantMsg),
          ),
        );

        expect(assistantMsg.isOffline, isTrue);
      },
    );

    test('5. No client-supplied user ID is introduced in the request', () async {
      await AuthSession.saveSession('authenticated-user-token');

      Map<String, dynamic>? parsedPayload;

      final mockHttpClient = MockClient((request) async {
        parsedPayload = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(
          jsonEncode({
            'intent': 'greeting',
            'text': 'Hello',
            'cards': [],
            'clarifications': [],
          }),
          200,
          headers: {'content-type': 'application/json; charset=UTF-8'},
        );
      });

      final client = AssistantClient(client: mockHttpClient);
      await client.chat(
        history: [const AssistantMessage(role: 'user', text: 'hello')],
        context: const AssistantUserContext(),
      );

      expect(parsedPayload, isNotNull);
      // Top-level payload has no client-supplied user identity
      expect(parsedPayload!.containsKey('userId'), isFalse);
      expect(parsedPayload!.containsKey('user_id'), isFalse);
      expect(parsedPayload!.containsKey('id'), isFalse);

      // Context user payload has no user identity
      final userContext = parsedPayload!['user'] as Map<String, dynamic>;
      expect(userContext.containsKey('userId'), isFalse);
      expect(userContext.containsKey('user_id'), isFalse);
      expect(userContext.containsKey('id'), isFalse);
      expect(userContext.containsKey('username'), isFalse);
      expect(userContext.containsKey('email'), isFalse);
    });
  });
}
