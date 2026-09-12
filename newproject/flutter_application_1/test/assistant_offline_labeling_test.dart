import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:fansivibe/app/app.dart';
import 'package:fansivibe/app/router/app_router.dart';
import 'package:fansivibe/features/assistant/data/assistant_client.dart';
import 'package:fansivibe/features/assistant/data/models.dart';
import 'package:fansivibe/features/assistant/domain/assistant_service.dart';
import 'package:fansivibe/features/assistant/presentation/widgets/assistant_widgets.dart';

Widget _bubbleHarness({required AssistantMessage message}) {
  return MaterialApp(
    home: Scaffold(
      body: MessageBubble(message: message),
    ),
  );
}

Widget _screenApp({required AssistantService service}) {
  return FansivibeApp(
    router: GoRouter(
      initialLocation: '/assistant',
      routes: appRoutes,
    ),
  );
}

void main() {
  group('P2-4: MessageBubble offline labeling', () {
    testWidgets(
      'displays "Offline" badge when assistant message has isOffline: true',
      (WidgetTester tester) async {
        const offlineMessage = AssistantMessage(
          role: 'assistant',
          text: 'This is offline fallback guidance.',
          isOffline: true,
        );

        await tester.pumpWidget(_bubbleHarness(message: offlineMessage));

        expect(find.byKey(const Key('assistant_offline_badge')), findsOneWidget);
        expect(find.text('Offline'), findsOneWidget);
        expect(find.byIcon(Icons.cloud_off_rounded), findsOneWidget);
        expect(find.text('This is offline fallback guidance.'), findsOneWidget);
      },
    );

    testWidgets(
      'does NOT display "Offline" badge when assistant message has isOffline: false (live backend)',
      (WidgetTester tester) async {
        const liveMessage = AssistantMessage(
          role: 'assistant',
          text: 'This is live backend intelligence.',
          isOffline: false,
        );

        await tester.pumpWidget(_bubbleHarness(message: liveMessage));

        expect(find.byKey(const Key('assistant_offline_badge')), findsNothing);
        expect(find.text('Offline'), findsNothing);
        expect(find.byIcon(Icons.cloud_off_rounded), findsNothing);
        expect(find.text('This is live backend intelligence.'), findsOneWidget);
      },
    );

    testWidgets(
      'does NOT display "Offline" badge on user message even if isOffline is true',
      (WidgetTester tester) async {
        const userMessage = AssistantMessage(
          role: 'user',
          text: 'What should I wear?',
          isOffline: true,
        );

        await tester.pumpWidget(_bubbleHarness(message: userMessage));

        expect(find.byKey(const Key('assistant_offline_badge')), findsNothing);
        expect(find.text('Offline'), findsNothing);
        expect(find.text('What should I wear?'), findsOneWidget);
      },
    );
  });

  group('P2-4: AssistantService data flow', () {
    test(
      'sets isOffline: true when backend returns null (offline fallback)',
      () async {
        final mockHttpClient = MockClient((request) async {
          return http.Response('Server error', 500);
        });
        final client = AssistantClient(client: mockHttpClient);
        final service = AssistantService(client: client);

        await service.send('hello');

        expect(service.messages.length, 2);
        final userMsg = service.messages[0];
        final assistantMsg = service.messages[1];

        expect(userMsg.role, 'user');
        expect(userMsg.text, 'hello');

        expect(assistantMsg.role, 'assistant');
        expect(assistantMsg.isOffline, isTrue);
        expect(assistantMsg.text, isNotEmpty);
      },
    );

    test(
      'sets isOffline: false when backend returns 200 OK (live backend intelligence)',
      () async {
        final liveReplyJson = jsonEncode({
          'intent': 'greeting',
          'text': 'Live backend stylist response.',
          'cards': [],
          'clarifications': [],
        });

        final mockHttpClient = MockClient((request) async {
          if (request.url.path.endsWith('/v1/assistant/chat')) {
            return http.Response(
              liveReplyJson,
              200,
              headers: {'content-type': 'application/json; charset=UTF-8'},
            );
          }
          return http.Response('Not found', 404);
        });

        final client = AssistantClient(client: mockHttpClient);
        final service = AssistantService(client: client);

        await service.send('hello');

        expect(service.messages.length, 2);
        final assistantMsg = service.messages[1];

        expect(assistantMsg.role, 'assistant');
        expect(assistantMsg.isOffline, isFalse);
        expect(assistantMsg.text, 'Live backend stylist response.');
      },
    );
  });

  group('P2-4: AssistantScreen integration', () {
    testWidgets(
      'typing and sending a message with offline fallback shows "Offline" badge',
      (WidgetTester tester) async {
        final mockHttpClient = MockClient((request) async {
          return http.Response('Connection refused', 503);
        });
        final service = AssistantService(
          client: AssistantClient(client: mockHttpClient),
        );

        await tester.pumpWidget(_screenApp(service: service));
        await tester.pump();

        await tester.enterText(find.byType(TextField), 'hello');
        await tester.tap(find.byIcon(Icons.send_rounded));
        await tester.pumpAndSettle();

        expect(find.text('hello'), findsOneWidget);
        expect(find.byKey(const Key('assistant_offline_badge')), findsOneWidget);
        expect(find.text('Offline'), findsOneWidget);
        expect(find.byIcon(Icons.cloud_off_rounded), findsOneWidget);
      },
    );

    testWidgets(
      'typing and sending a message with live backend response does NOT show "Offline" badge',
      (WidgetTester tester) async {
        final liveReplyJson = jsonEncode({
          'intent': 'greeting',
          'text': 'Fresh backend AI response.',
          'cards': [],
          'clarifications': [],
        });

        final mockHttpClient = MockClient((request) async {
          return http.Response(
            liveReplyJson,
            200,
            headers: {'content-type': 'application/json; charset=UTF-8'},
          );
        });
        final service = AssistantService(
          client: AssistantClient(client: mockHttpClient),
        );

        await tester.pumpWidget(_screenApp(service: service));
        await tester.pump();

        await tester.enterText(find.byType(TextField), 'hello');
        await tester.tap(find.byIcon(Icons.send_rounded));
        await tester.pumpAndSettle();

        expect(find.text('hello'), findsOneWidget);
        expect(find.text('Fresh backend AI response.'), findsOneWidget);
        expect(find.byKey(const Key('assistant_offline_badge')), findsNothing);
        expect(find.text('Offline'), findsNothing);
        expect(find.byIcon(Icons.cloud_off_rounded), findsNothing);
      },
    );
  });
}
