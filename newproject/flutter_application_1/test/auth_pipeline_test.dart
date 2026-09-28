import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/app/router/app_router.dart';
import 'package:fansivibe/app/router/auth_guard.dart';
import 'package:fansivibe/features/auth/auth.dart';
import 'package:fansivibe/features/events/presentation/event_list_screen.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/features/profile/presentation/saved_looks_screen.dart';
import 'package:fansivibe/features/stylist/presentation/stylist_screen.dart';
import 'package:fansivibe/features/wardrobe/presentation/wardrobe_screen.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/theme/fansivibe_theme.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:fansivibe/shared/utils/user_session.dart';

/// Complete auth pipeline: mounted screens must swap data sources when
/// the session flips, and the A–F lifecycles must hold end to end.
///
/// Screens below are pumped with their live repositories: in widget
/// tests every network call answers 400, so a *server attempt* surfaces
/// as the honest error state while guest/local paths stay offline.

String _body(String name, String token) =>
    '{"accessToken":"$token","tokenType":"bearer","expiresIn":3600,'
    '"profile":{"displayName":"$name","styleProfile":{},"preferences":{},'
    '"settings":{},"flags":{},"version":0}}';

Future<void> _initPrefs([Map<String, Object> seed = const {}]) async {
  SharedPreferences.setMockInitialValues(seed);
  LocalStorage.init(prefs: await SharedPreferences.getInstance());
}

Future<void> _signInAs(String name, String token) async {
  final client = AuthClient(
    client: MockClient((_) async => http.Response(_body(name, token), 200)),
  );
  final result = await client.login(
    email: '${name.replaceAll(' ', '')}@x.co',
    password: 'Passw0rd1',
  );
  expect(result.isAuthenticated, isTrue);
  LocalStorage.displayName = result.displayName;
  UserSession.isReturningUser = true;
  client.dispose();
}

Future<void> _registerAs(String name, String token) async {
  final client = AuthClient(
    client: MockClient((_) async => http.Response(_body(name, token), 201)),
  );
  final result = await client.register(
    email: '${name.replaceAll(' ', '')}@x.co',
    password: 'Passw0rd1',
    displayName: name,
    idempotencyKey: 'pipeline-key-$name',
  );
  expect(result.isAuthenticated, isTrue);
  LocalStorage.displayName = result.displayName ?? name;
  LocalStorage.onboardingComplete = true;
  client.dispose();
}

Future<void> _signOut() async {
  final client = AuthClient(
    client: MockClient((_) async => http.Response('', 204)),
  );
  expect(await client.logout(), AuthStatus.signedOut);
  client.dispose();
}

Future<void> _simulateRestart() async {
  AuthSession.resetForTest();
  LocalStorage.resetForTest();
  LearningService.instance.resetForTest();
  LocalStorage.init(prefs: await SharedPreferences.getInstance());
}

GoRouter _guardedRouter(String location) {
  return GoRouter(
    initialLocation: location,
    refreshListenable: AuthSession.authVersion,
    redirect: (context, state) => authRedirect(
      state.uri.path,
      isAuthenticated: AuthSession.isAuthenticated,
      isGuest:
          !AuthSession.isAuthenticated && LocalStorage.savedLocally,
    ),
    routes: [...appRoutes],
  );
}

Widget _harness(GoRouter router) {
  return MaterialApp.router(
    theme: FansivibeTheme.darkTheme,
    routerConfig: router,
  );
}

Future<void> _pump(WidgetTester tester) async {
  await tester.pump(const Duration(milliseconds: 300));
  await tester.pump(const Duration(milliseconds: 300));
  await tester.pump(const Duration(milliseconds: 1500));
  await tester.pump(const Duration(milliseconds: 500));
}

void main() {
  setUp(() async {
    await _initPrefs();
    AuthSession.resetForTest();
    LearningService.instance.resetForTest();
  });

  tearDown(() async {
    AuthSession.resetForTest();
    await AuthSession.clearSession();
    LocalStorage.resetForTest();
    LearningService.instance.resetForTest();
  });

  group('mounted data-source swaps (no remount needed)', () {
    testWidgets('Wardrobe guest-local swaps to server on login', (
      WidgetTester tester,
    ) async {
      LocalStorage.savedLocally = true;
      await tester.pumpWidget(
        MaterialApp(theme: FansivibeTheme.darkTheme, home: const WardrobeScreen()),
      );
      await _pump(tester);
      // Guest reads the on-device collection; no server attempt.
      expect(find.text('Merino Crew Neck'), findsWidgets);
      expect(
        find.text('Failed to load wardrobe. Please check your connection.'),
        findsNothing,
      );

      await AuthSession.saveSession('swap-token');
      await _pump(tester);
      // Live backend answers 400 in tests: the honest error proves the
      // server source is now in use (local path would stay empty).
      expect(
        find.text('Failed to load wardrobe. Please check your connection.'),
        findsOneWidget,
      );
    });

    testWidgets('Wardrobe drops server rows on logout', (
      WidgetTester tester,
    ) async {
      await AuthSession.saveSession('swap-token-2');
      await tester.pumpWidget(
        MaterialApp(theme: FansivibeTheme.darkTheme, home: const WardrobeScreen()),
      );
      await _pump(tester);
      expect(
        find.text('Failed to load wardrobe. Please check your connection.'),
        findsOneWidget,
      );

      await _signOut();
      await _pump(tester);
      // Back on local state: on-device rows return, server state gone.
      expect(find.text('Merino Crew Neck'), findsWidgets);
      expect(
        find.text('Failed to load wardrobe. Please check your connection.'),
        findsNothing,
      );
    });

    testWidgets('Stylist event section swaps guest to server on login', (
      WidgetTester tester,
    ) async {
      LocalStorage.savedLocally = true;
      await tester.pumpWidget(
        MaterialApp(theme: FansivibeTheme.darkTheme, home: const StylistScreen()),
      );
      await _pump(tester);
      await tester.scrollUntilVisible(find.text('Sign In \u2192'), 500.0);
      expect(find.text('Sign In \u2192'), findsOneWidget);

      await AuthSession.saveSession('stylist-token');
      await _pump(tester);
      await tester.scrollUntilVisible(find.text('No upcoming events'), 500.0);
      expect(find.text('No upcoming events'), findsOneWidget);
      expect(find.text('Sign In \u2192'), findsNothing);
    });

    testWidgets('SavedLooks reloads instead of staying empty', (
      WidgetTester tester,
    ) async {
      LocalStorage.savedLocally = true;
      await tester.pumpWidget(
        MaterialApp(
          theme: FansivibeTheme.darkTheme,
          home: const SavedLooksScreen(),
        ),
      );
      await _pump(tester);
      expect(find.text('No saved looks yet'), findsOneWidget);

      await AuthSession.saveSession('saves-token');
      await _pump(tester);
      expect(
        find.text('Couldn\'t load saved looks. Please check your connection.'),
        findsOneWidget,
      );
    });

    testWidgets('EventList reloads instead of staying guest', (
      WidgetTester tester,
    ) async {
      LocalStorage.savedLocally = true;
      await tester.pumpWidget(
        MaterialApp(theme: FansivibeTheme.darkTheme, home: const EventListScreen()),
      );
      await _pump(tester);
      expect(find.text('Event Planning'), findsOneWidget);

      await AuthSession.saveSession('events-token');
      await _pump(tester);
      expect(
        find.text('Couldn\'t load your events. Please try again.'),
        findsOneWidget,
      );
    });

    testWidgets('Profile drops stale account on mounted logout', (
      WidgetTester tester,
    ) async {
      await _signInAs('Account A', 'tok-a');
      await tester.pumpWidget(_harness(_guardedRouter('/profile')));
      await _pump(tester);
      expect(find.text('Account A'), findsWidgets);

      await _signOut();
      await _pump(tester);
      expect(AuthSession.isAuthenticated, isFalse);
      expect(find.text('Account A'), findsNothing);
      expect(find.text('Help & Concierge'), findsNothing);
    });
  });

  group('feature auth matrix (unit level)', () {
    test('guard verdicts agree with the session in every state', () async {
      const shell = ['/home', '/discover', '/stylist', '/wardrobe', '/profile'];
      // Authenticated: shell open, auth-only routes bounce home.
      await AuthSession.saveSession('matrix-token');
      expect(AuthSession.isAuthenticated, isTrue);
      expect(isGuestUser, isFalse);
      for (final route in shell) {
        expect(authRedirect(route, isAuthenticated: true), isNull,
            reason: route);
      }
      expect(authRedirect('/entry', isAuthenticated: true), '/home');
      expect(authRedirect('/sign-in', isAuthenticated: true), '/home');

      // Signed out, plain: shell blocked, sign-in open.
      await _signOut();
      expect(AuthSession.isAuthenticated, isFalse);
      expect(isGuestUser, isFalse);
      for (final route in shell) {
        expect(authRedirect(route, isAuthenticated: false), '/entry',
            reason: route);
      }
      expect(authRedirect('/sign-in', isAuthenticated: false), isNull);

      // Signed out, guest: shell browsable, assistant blocked.
      LocalStorage.savedLocally = true;
      expect(isGuestUser, isTrue);
      for (final route in shell) {
        expect(
            authRedirect(route, isAuthenticated: false, isGuest: true),
            isNull,
            reason: route);
      }
      expect(
          authRedirect('/assistant', isAuthenticated: false, isGuest: true),
          '/entry');
    });
  });

  group('Scenario A: register, restart, logout, guest, login', () {
    test('full new-user lifecycle holds', () async {
      await _registerAs('Nia', 'tok-nia');
      expect(AuthSession.isAuthenticated, isTrue);
      await _simulateRestart();
      expect(AuthSession.isAuthenticated, isTrue);
      expect(LocalStorage.displayName, 'Nia');
      await _signOut();
      expect(AuthSession.isAuthenticated, isFalse);
      expect(LocalStorage.displayName, isNull);
      LocalStorage.savedLocally = true;
      expect(isGuestUser, isTrue);
      await _signInAs('Nia', 'tok-nia-2');
      expect(AuthSession.isAuthenticated, isTrue);
      expect(LocalStorage.displayName, 'Nia');
      expect(isGuestUser, isFalse);
    });
  });

  group('Scenario B: logout, guest, restart guest, login', () {
    test('guest survives restart without gaining a session', () async {
      await _signInAs('Shivu', 'tok-shivu');
      await _signOut();
      LocalStorage.savedLocally = true;
      LocalStorage.vibe = 'Minimal';
      await _simulateRestart();
      expect(AuthSession.isAuthenticated, isFalse);
      expect(isGuestUser, isTrue);
      expect(LocalStorage.displayName, isNull);
      await _signInAs('Shivu', 'tok-shivu-2');
      expect(AuthSession.isAuthenticated, isTrue);
      expect(LocalStorage.displayName, 'Shivu');
    });
  });

  group('Scenario C: A out, B in', () {
    test('only B identity remains', () async {
      await _signInAs('Account A', 'tok-a');
      await _signOut();
      await _signInAs('Account B', 'tok-b');
      expect(AuthSession.token, 'tok-b');
      expect(LocalStorage.displayName, 'Account B');
      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getString('auth_token'), 'tok-b');
    });
  });

  group('Scenarios D + E: restart with/without session', () {
    test('valid session restores; signed-out stays out', () async {
      await _signInAs('Dee', 'tok-dee');
      await _simulateRestart();
      expect(AuthSession.isAuthenticated, isTrue);
      await _signOut();
      await _simulateRestart();
      expect(AuthSession.isAuthenticated, isFalse);
      expect(AuthSession.token, isNull);
    });
  });
}
