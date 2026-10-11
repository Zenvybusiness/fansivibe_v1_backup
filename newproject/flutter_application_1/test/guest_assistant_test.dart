import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/app/app.dart';
import 'package:fansivibe/app/router/app_router.dart';
import 'package:fansivibe/app/router/auth_guard.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/assistant/data/assistant_client.dart';
import 'package:fansivibe/features/assistant/data/models.dart';
import 'package:fansivibe/features/assistant/domain/assistant_service.dart';
import 'package:fansivibe/features/assistant/presentation/assistant_screen.dart';
import 'package:fansivibe/features/assistant/presentation/widgets/outfit_recommendation_card.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:fansivibe/shared/utils/pending_auth_intent.dart';

OutfitIntelligence _sampleOutfit() {
  return const OutfitIntelligence(
    selectedItemIds: ['10', '11'],
    outfitComposition: OutfitComposition(
      topIds: ['10'],
      bottomIds: ['11'],
      outerwearIds: [],
      footwearIds: [],
      accessoryIds: [],
      styleScore: 92,
    ),
    occasion: 'date',
    stylingRationale: 'Great casual combination.',
    compatibilityRationale: 'Colors complement each other well.',
    confidence: 0.88,
    explanation: 'A balanced look.',
    dataAvailability: 'partial',
  );
}

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

  group('Guest AI Chatbot Access & Authentication Gating', () {
    test('1. authRedirect permits guest to access /assistant', () {
      LocalStorage.savedLocally = true;
      expect(isGuestUser, isTrue);

      final redirect = authRedirect(
        '/assistant',
        isAuthenticated: false,
        isGuest: true,
      );
      expect(redirect, isNull);
    });

    testWidgets('2. Guest can open chatbot and sees assistant interface', (
      WidgetTester tester,
    ) async {
      LocalStorage.savedLocally = true;
      expect(isGuestUser, isTrue);

      await tester.pumpWidget(
        FansivibeApp(
          router: GoRouter(
            initialLocation: '/assistant',
            routes: appRoutes,
            redirect: (context, state) => authRedirect(
              state.uri.path,
              isAuthenticated: AuthSession.isAuthenticated,
              isGuest: isGuestUser,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byType(AssistantScreen), findsOneWidget);
      expect(find.text('Your AI stylist'), findsOneWidget);
      expect(find.text('Ask your stylist…'), findsOneWidget);
    });

    testWidgets('3. Guest can open chatbot via floating button from shell tab', (
      WidgetTester tester,
    ) async {
      LocalStorage.savedLocally = true;
      expect(isGuestUser, isTrue);

      await tester.pumpWidget(
        FansivibeApp(
          router: GoRouter(
            initialLocation: '/home',
            routes: appRoutes,
            redirect: (context, state) => authRedirect(
              state.uri.path,
              isAuthenticated: AuthSession.isAuthenticated,
              isGuest: isGuestUser,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final fab = find.byType(FloatingActionButton);
      expect(fab, findsOneWidget);

      await tester.tap(fab);
      await tester.pumpAndSettle();

      expect(find.byType(AssistantScreen), findsOneWidget);
    });

    testWidgets(
      '4. Guest can send a message and receive genuine response without sign-in',
      (WidgetTester tester) async {
        LocalStorage.savedLocally = true;
        expect(isGuestUser, isTrue);

        final mockClient = MockClient((request) async {
          expect(request.url.path, '/v1/assistant/chat');
          return http.Response(
            jsonEncode({
              'intent': 'styling',
              'text': 'A navy blazer with beige chinos would look sharp.',
              'cards': <dynamic>[],
              'clarifications': <dynamic>[],
            }),
            200,
            headers: {'content-type': 'application/json; charset=UTF-8'},
          );
        });

        final service = AssistantService(client: AssistantClient(client: mockClient));

        await tester.pumpWidget(
          MaterialApp(
            home: AssistantScreen(service: service),
          ),
        );
        await tester.pumpAndSettle();

        await tester.enterText(
          find.byType(TextField),
          'What should I wear to a dinner?',
        );
        await tester.tap(find.byIcon(Icons.send_rounded));
        await tester.pumpAndSettle();

        expect(
          find.text('What should I wear to a dinner?'),
          findsOneWidget,
        );
        expect(
          find.text('A navy blazer with beige chinos would look sharp.'),
          findsOneWidget,
        );
        // Not redirected to sign in or entry
        expect(find.byType(AssistantScreen), findsOneWidget);
      },
    );

    testWidgets(
      '5. Guest can continue conversation across multiple messages without being gated',
      (WidgetTester tester) async {
        LocalStorage.savedLocally = true;
        expect(isGuestUser, isTrue);

        var requestCount = 0;
        final mockClient = MockClient((request) async {
          requestCount++;
          final text = requestCount == 1
              ? 'First reply: Try dark jeans.'
              : 'Second reply: Add white sneakers to complete it.';
          return http.Response(
            jsonEncode({
              'intent': 'styling',
              'text': text,
              'cards': <dynamic>[],
              'clarifications': <dynamic>[],
            }),
            200,
            headers: {'content-type': 'application/json; charset=UTF-8'},
          );
        });

        final service = AssistantService(client: AssistantClient(client: mockClient));

        await tester.pumpWidget(
          MaterialApp(
            home: AssistantScreen(service: service),
          ),
        );
        await tester.pumpAndSettle();

        // Message 1
        await tester.enterText(find.byType(TextField), 'First question');
        await tester.tap(find.byIcon(Icons.send_rounded));
        await tester.pumpAndSettle();

        expect(find.text('First reply: Try dark jeans.'), findsOneWidget);

        // Message 2
        await tester.enterText(find.byType(TextField), 'Second question');
        await tester.tap(find.byIcon(Icons.send_rounded));
        await tester.pumpAndSettle();

        expect(
          find.text('Second reply: Add white sneakers to complete it.'),
          findsOneWidget,
        );
        expect(requestCount, equals(2));
        expect(find.byType(AssistantScreen), findsOneWidget);
      },
    );

    testWidgets(
      '6. General fashion question does not trigger authentication',
      (WidgetTester tester) async {
        LocalStorage.savedLocally = true;

        final mockClient = MockClient((request) async {
          return http.Response(
            jsonEncode({
              'intent': 'styling',
              'text': 'Earth tones like olive and terracotta work well together.',
              'cards': <dynamic>[],
              'clarifications': <dynamic>[],
            }),
            200,
            headers: {'content-type': 'application/json; charset=UTF-8'},
          );
        });

        final service = AssistantService(client: AssistantClient(client: mockClient));

        await tester.pumpWidget(
          FansivibeApp(
            router: GoRouter(
              initialLocation: '/assistant',
              routes: [
                GoRoute(
                  path: '/assistant',
                  name: RouteNames.assistant,
                  builder: (context, state) => AssistantScreen(service: service),
                ),
                GoRoute(
                  path: '/sign-in',
                  name: RouteNames.signIn,
                  builder: (context, state) => const Scaffold(body: Text('Sign In Screen')),
                ),
              ],
            ),
          ),
        );
        await tester.pumpAndSettle();

        await tester.enterText(
          find.byType(TextField),
          'What colors go with olive green?',
        );
        await tester.tap(find.byIcon(Icons.send_rounded));
        await tester.pumpAndSettle();

        expect(
          find.text('Earth tones like olive and terracotta work well together.'),
          findsOneWidget,
        );
        expect(find.text('Sign In Screen'), findsNothing);
      },
    );

    testWidgets(
      '7. Guest attempting to save outfit recommendation is redirected to sign-in with intent',
      (WidgetTester tester) async {
        LocalStorage.savedLocally = true;
        expect(isGuestUser, isTrue);

        final mockClient = MockClient((request) async {
          return http.Response(
            jsonEncode({
              'intent': 'outfit',
              'text': 'Here is an outfit for your date.',
              'cards': <dynamic>[],
              'clarifications': <dynamic>[],
              'outfitIntelligence': _sampleOutfit().toJson(),
            }),
            200,
            headers: {'content-type': 'application/json; charset=UTF-8'},
          );
        });

        final service = AssistantService(client: AssistantClient(client: mockClient));

        await tester.pumpWidget(
          FansivibeApp(
            router: GoRouter(
              initialLocation: '/assistant',
              routes: [
                GoRoute(
                  path: '/assistant',
                  name: RouteNames.assistant,
                  builder: (context, state) => AssistantScreen(service: service),
                ),
                GoRoute(
                  path: '/sign-in',
                  name: RouteNames.signIn,
                  builder: (context, state) => const Scaffold(body: Text('Sign In Screen')),
                ),
              ],
            ),
          ),
        );
        await tester.pumpAndSettle();

        await tester.enterText(find.byType(TextField), 'suggest an outfit');
        await tester.tap(find.byIcon(Icons.send_rounded));
        await tester.pumpAndSettle();

        expect(find.text('Here is an outfit for your date.'), findsOneWidget);
        expect(find.byType(OutfitRecommendationCard), findsOneWidget);
        await tester.scrollUntilVisible(
          find.text('Save'),
          100,
          scrollable: find.byType(Scrollable).first,
        );
        final saveButtonFinder = find.text('Save');
        expect(saveButtonFinder, findsOneWidget);

        // Guest taps Save
        await tester.tap(saveButtonFinder);
        await tester.pumpAndSettle();

        // Redirected to sign in
        expect(find.text('Sign In Screen'), findsOneWidget);

        // PendingAuthIntent was recorded with route /assistant
        final intent = takePendingAuthIntent();
        expect(intent, isNotNull);
        expect(intent!.route, equals('/assistant'));
        expect(intent.action, contains('Sign in to save looks'));

        // Post-auth destination resolves back to /assistant
        final destination = resolvePostAuthDestination(intent);
        expect(destination, equals('/assistant'));
      },
    );

    testWidgets(
      '8. Guest tapping Fashion Reasoning button is redirected to sign-in with intent',
      (WidgetTester tester) async {
        LocalStorage.savedLocally = true;
        expect(isGuestUser, isTrue);

        await tester.pumpWidget(
          FansivibeApp(
            router: GoRouter(
              initialLocation: '/assistant',
              routes: [
                GoRoute(
                  path: '/assistant',
                  name: RouteNames.assistant,
                  builder: (context, state) => const AssistantScreen(),
                ),
                GoRoute(
                  path: '/sign-in',
                  name: RouteNames.signIn,
                  builder: (context, state) => const Scaffold(body: Text('Sign In Screen')),
                ),
              ],
            ),
          ),
        );
        await tester.pumpAndSettle();

        final reasoningButton = find.byIcon(Icons.psychology_alt_outlined);
        expect(reasoningButton, findsOneWidget);

        await tester.tap(reasoningButton);
        await tester.pumpAndSettle();

        expect(find.text('Sign In Screen'), findsOneWidget);

        final intent = takePendingAuthIntent();
        expect(intent, isNotNull);
        expect(intent!.route, equals('/assistant'));
        expect(intent.action, contains('Fashion Reasoning'));
      },
    );

    testWidgets(
      '9. Authenticated user can save outfit without being prompted to sign in',
      (WidgetTester tester) async {
        await AuthSession.saveSession('valid-session-jwt');
        LocalStorage.savedLocally = false;
        expect(isGuestUser, isFalse);
        expect(AuthSession.isAuthenticated, isTrue);

        var saveCalled = false;
        final mockClient = MockClient((request) async {
          if (request.url.path == '/v1/looks/saved') {
            saveCalled = true;
            return http.Response(
              jsonEncode({
                'id': 'look-saved-uuid-1',
                'title': 'Date Night',
                'sourceContext': 'outfit',
              }),
              201,
              headers: {'content-type': 'application/json; charset=UTF-8'},
            );
          }
          return http.Response(
            jsonEncode({
              'intent': 'outfit',
              'text': 'Here is an outfit.',
              'cards': <dynamic>[],
              'clarifications': <dynamic>[],
              'outfitIntelligence': _sampleOutfit().toJson(),
            }),
            200,
            headers: {'content-type': 'application/json; charset=UTF-8'},
          );
        });

        final service = AssistantService(client: AssistantClient(client: mockClient));

        await tester.pumpWidget(
          FansivibeApp(
            router: GoRouter(
              initialLocation: '/assistant',
              routes: [
                GoRoute(
                  path: '/assistant',
                  name: RouteNames.assistant,
                  builder: (context, state) => AssistantScreen(service: service),
                ),
                GoRoute(
                  path: '/sign-in',
                  name: RouteNames.signIn,
                  builder: (context, state) => const Scaffold(body: Text('Sign In Screen')),
                ),
              ],
            ),
          ),
        );
        await tester.pumpAndSettle();

        await tester.enterText(find.byType(TextField), 'suggest an outfit');
        await tester.tap(find.byIcon(Icons.send_rounded));
        await tester.pumpAndSettle();

        expect(find.text('Here is an outfit.'), findsOneWidget);
        expect(find.byType(OutfitRecommendationCard), findsOneWidget);
        await tester.scrollUntilVisible(
          find.text('Save'),
          100,
          scrollable: find.byType(Scrollable).first,
        );
        final saveButtonFinder = find.text('Save');
        expect(saveButtonFinder, findsOneWidget);

        await tester.tap(saveButtonFinder);
        await tester.pumpAndSettle();

        // Backend save was called, user stayed on assistant screen
        expect(saveCalled, isTrue);
        expect(find.text('Sign In Screen'), findsNothing);
        expect(find.byType(AssistantScreen), findsOneWidget);
      },
    );

    testWidgets(
      '10. Network failure produces honest offline response with badge rather than fake data',
      (WidgetTester tester) async {
        LocalStorage.savedLocally = true;

        final mockClient = MockClient((request) async {
          throw http.ClientException('Network unreachable');
        });

        final service = AssistantService(client: AssistantClient(client: mockClient));

        await tester.pumpWidget(
          MaterialApp(
            home: AssistantScreen(service: service),
          ),
        );
        await tester.pumpAndSettle();

        await tester.enterText(find.byType(TextField), 'What should I wear?');
        await tester.tap(find.byIcon(Icons.send_rounded));
        await tester.pumpAndSettle();

        // Offline badge is displayed honestly
        expect(find.byKey(const Key('assistant_offline_badge')), findsOneWidget);
        expect(find.text('Offline'), findsOneWidget);
        // Does not show an ungrounded fabricated response or force sign-in
        expect(find.byType(AssistantScreen), findsOneWidget);
      },
    );
  });
}
