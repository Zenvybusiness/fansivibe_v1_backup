import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/app/router/app_router.dart';
import 'package:fansivibe/app/router/auth_guard.dart';
import 'package:fansivibe/features/auth/auth.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/theme/fansivibe_theme.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:fansivibe/shared/utils/user_session.dart';

/// One consistent unauthenticated state after explicit sign-out.
///
/// Regression suite for the "Profile still sees the old account" bug:
/// Profile keyed its established UI off stale `isReturningUser` +
/// preserved `displayName` while AI Stylist keyed off `AuthSession`,
/// so the two features disagreed. `AuthSession` is now the single
/// authority and logout invalidates the session-derived identity.

String _body(String name, String token) =>
    '{"accessToken":"$token","tokenType":"bearer","expiresIn":3600,'
    '"profile":{"displayName":"$name","styleProfile":{},"preferences":{},'
    '"settings":{},"flags":{},"version":0}}';

Future<void> _initPrefs([Map<String, Object> seed = const {}]) async {
  SharedPreferences.setMockInitialValues(seed);
  LocalStorage.init(prefs: await SharedPreferences.getInstance());
}

/// Mirrors exactly what `SignInScreen._handleAuthSuccess` does on a
/// successful login: persist the session, store the server display name,
/// mark the returning user.
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

Future<void> _signOut() async {
  final client = AuthClient(
    client: MockClient((_) async => http.Response('', 204)),
  );
  expect(await client.logout(), AuthStatus.signedOut);
  client.dispose();
}

/// Drops all in-memory state but keeps the prefs store: a process restart.
Future<void> _simulateRestart() async {
  AuthSession.resetForTest();
  LocalStorage.resetForTest();
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
  });

  tearDown(() async {
    AuthSession.resetForTest();
    await AuthSession.clearSession();
    LocalStorage.resetForTest();
  });

  group('1 + 2. sign-in establishes, sign-out clears', () {
    test('identity lives and dies with the session', () async {
      await _signInAs('Account A', 'tok-a');
      expect(AuthSession.isAuthenticated, isTrue);
      expect(LocalStorage.displayName, 'Account A');
      expect(isGuestUser, isFalse);

      await _signOut();
      expect(AuthSession.isAuthenticated, isFalse);
      expect(AuthSession.token, isNull);
      expect(LocalStorage.displayName, isNull);
      expect(LocalStorage.isReturningUser, isFalse);
    });
  });

  group('3 + 4 + 5. exact bug repro: Profile vs AI Stylist', () {
    testWidgets(
        'post-logout guest sees no previous account anywhere', (
      WidgetTester tester,
    ) async {
      await _signInAs('Account A', 'tok-a');
      final router = _guardedRouter('/profile');
      await tester.pumpWidget(_harness(router));
      await _pump(tester);
      // Signed in: Profile resolves the current account.
      expect(find.text('Account A'), findsOneWidget);

      // Sign out through the real established UI button.
      final signOut = find.text('SIGN OUT');
      await tester.ensureVisible(signOut);
      await tester.pump(const Duration(milliseconds: 300));
      await tester.tap(signOut);
      await _pump(tester);
      expect(AuthSession.isAuthenticated, isFalse);
      expect(find.text('Sign In'), findsOneWidget);

      // Continue through onboarding WITHOUT signing in (guest path).
      LocalStorage.savedLocally = true;
      LocalStorage.vibe = 'Minimal';
      expect(AuthSession.isAuthenticated, isFalse);

      // AI Stylist sees the unauthenticated state.
      router.go('/stylist');
      await _pump(tester);
      expect(isGuestUser, isTrue);
      expect(find.text('Sign In \u2192'), findsWidgets);

      // Profile shows the guest design, never the previous account.
      router.go('/profile');
      await _pump(tester);
      expect(find.text('Account A'), findsNothing);
      expect(find.text('On this device'), findsOneWidget);
    });
  });

  group('6. onboarding cannot restore authentication', () {
    test('guest onboarding leaves the session empty', () async {
      await _signInAs('Account A', 'tok-a');
      await _signOut();
      // Guest onboarding writes journey state only.
      LocalStorage.savedLocally = true;
      LocalStorage.vibe = 'Minimal';
      LocalStorage.onboardingPhotoCaptured = true;
      LocalStorage.onboardingComplete = true;
      expect(AuthSession.isAuthenticated, isFalse);
      expect(AuthSession.token, isNull);
      expect(LocalStorage.displayName, isNull);
      expect(isGuestUser, isTrue);
    });
  });

  group('7 + 8. restart cannot restore the previous account', () {
    testWidgets('kill + reopen stays unauthenticated', (
      WidgetTester tester,
    ) async {
      await _signInAs('Account A', 'tok-a');
      await _signOut();
      LocalStorage.savedLocally = true;
      await _simulateRestart();

      expect(AuthSession.isAuthenticated, isFalse);
      expect(LocalStorage.displayName, isNull);
      expect(LocalStorage.isReturningUser, isFalse);

      final router = _guardedRouter('/stylist');
      await tester.pumpWidget(_harness(router));
      await _pump(tester);
      expect(isGuestUser, isTrue);
      expect(find.text('Sign In \u2192'), findsWidgets);

      router.go('/profile');
      await _pump(tester);
      expect(find.text('Account A'), findsNothing);
      expect(find.text('On this device'), findsOneWidget);
    });
  });

  group('9. multi-account safety: B never inherits A', () {
    test('A out, B in shows only B', () async {
      await _signInAs('Account A', 'tok-a');
      await _signOut();
      await _signInAs('Account B', 'tok-b');
      expect(AuthSession.isAuthenticated, isTrue);
      expect(AuthSession.token, 'tok-b');
      expect(LocalStorage.displayName, 'Account B');
    });
  });

  group('10. one state across Profile, Stylist, router, session', () {
    test('all four agree after logout', () async {
      await _signInAs('Account A', 'tok-a');
      await _signOut();
      LocalStorage.savedLocally = true;
      expect(AuthSession.isAuthenticated, isFalse);
      expect(isGuestUser, isTrue);
      // Router: guests browse the shell, never as the old account.
      expect(authRedirect('/profile', isAuthenticated: false, isGuest: true),
          isNull);
      expect(authRedirect('/stylist', isAuthenticated: false, isGuest: true),
          isNull);
      // No identity left for any feature to resolve.
      expect(LocalStorage.displayName, isNull);
      expect(LocalStorage.isReturningUser, isFalse);
    });
  });
}
