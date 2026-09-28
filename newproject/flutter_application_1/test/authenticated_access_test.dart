import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/app/router/app_router.dart';
import 'package:fansivibe/app/router/auth_guard.dart';
import 'package:fansivibe/features/auth/auth.dart';
import 'package:fansivibe/features/onboarding/presentation/screens/entry_screen.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/theme/fansivibe_theme.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:fansivibe/shared/utils/user_session.dart';

const String _authBody = '{"accessToken":"tok-abc-123","tokenType":"bearer",'
    '"expiresIn":3600,"profile":{"displayName":"Alex","styleProfile":{},'
    '"preferences":{},"settings":{},"flags":{},"version":0}}';

const List<String> _shellRoutes = [
  '/home',
  '/home/daily-outfit',
  '/discover',
  '/discover/look-details',
  '/stylist',
  '/stylist/scan-outfit',
  '/stylist/build-outfit',
  '/stylist/build-outfit/generation',
  '/stylist/build-outfit/generation/recommendation',
  '/stylist/hairstyle',
  '/stylist/hairstyle/processing',
  '/stylist/hairstyle/processing/result',
  '/stylist/grooming',
  '/stylist/grooming/processing',
  '/stylist/grooming/processing/result',
  '/stylist/events',
  '/stylist/events/add',
  '/wardrobe',
  '/wardrobe/add-item',
  '/wardrobe/item-details',
  '/profile',
  '/profile/preferences',
  '/profile/saved-looks',
  '/profile/settings',
];

Future<void> _initPrefs([Map<String, Object> seed = const {}]) async {
  SharedPreferences.setMockInitialValues(seed);
  LocalStorage.init(prefs: await SharedPreferences.getInstance());
}

Widget _entryHarness() {
  return MaterialApp.router(
    theme: FansivibeTheme.darkTheme,
    routerConfig: GoRouter(
      initialLocation: '/test',
      routes: [
        GoRoute(path: '/test', builder: (_, __) => const EntryScreen()),
        ...appRoutes,
      ],
    ),
  );
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

  group('1. fresh unauthenticated launch', () {
    test('sign-in is available; shell redirects to entry', () {
      expect(AuthSession.isAuthenticated, isFalse);
      expect(isGuestUser, isFalse);
      expect(authRedirect('/sign-in', isAuthenticated: false), isNull);
      expect(authRedirect('/create-account', isAuthenticated: false), isNull);
      for (final route in ['/home', '/discover', '/stylist', '/wardrobe', '/profile']) {
        expect(authRedirect(route, isAuthenticated: false), '/entry', reason: route);
      }
    });
  });

  group('2. successful sign-in', () {
    test('session persists, guest UI predicate flips, guard leaves auth routes', () async {
      LocalStorage.savedLocally = true;
      final client = AuthClient(
        client: MockClient((_) async => http.Response(_authBody, 200)),
      );
      final result = await client.login(email: 'a@b.co', password: 'Passw0rd1');
      expect(result.isAuthenticated, isTrue);
      expect(AuthSession.isAuthenticated, isTrue);
      expect(isGuestUser, isFalse);
      expect(LocalStorage.savedLocally, isFalse);
      expect(authRedirect('/sign-in', isAuthenticated: true), '/home');
      expect(authRedirect('/entry', isAuthenticated: true), '/home');
      for (final route in _shellRoutes) {
        expect(authRedirect(route, isAuthenticated: true), isNull, reason: route);
      }
      client.dispose();
    });
  });

  group('3. major tabs after sign-in', () {
    test('no tab redirects an authenticated user to sign-in', () async {
      await AuthSession.saveSession('tab-token');
      for (final route in _shellRoutes) {
        expect(authRedirect(route, isAuthenticated: true), isNull, reason: route);
      }
    });
  });

  group('4. restart with a valid persisted session', () {
    test('session restores; user stays authenticated; no guest UI', () async {
      await _initPrefs(const {'auth_token': 'returning-session-token'});
      expect(AuthSession.isAuthenticated, isTrue);
      expect(isGuestUser, isFalse);
      expect(authRedirect('/home', isAuthenticated: true), isNull);
      expect(authRedirect('/entry', isAuthenticated: true), '/home');
    });

    test('persisted token wins over a stale guest flag', () async {
      await _initPrefs(const {
        'auth_token': 'returning-session-token',
        'saved_locally': true,
      });
      expect(AuthSession.isAuthenticated, isTrue);
      expect(isGuestUser, isFalse);
    });
  });

  group('5. invalid/expired session', () {
    test('401 clears the session and re-opens sign-in', () async {
      await AuthSession.saveSession('dead-token');
      var navigatedToEntry = false;
      AuthSession.onSessionExpired = () => navigatedToEntry = true;
      AuthSession.notifyUnauthorized();
      expect(AuthSession.isAuthenticated, isFalse);
      expect(navigatedToEntry, isTrue);
      expect(authRedirect('/home', isAuthenticated: false), '/entry');
      expect(authRedirect('/sign-in', isAuthenticated: false), isNull);
    });
  });

  group('6. explicit logout', () {
    test('session clears; sign-in becomes available; shell goes to entry', () async {
      await AuthSession.saveSession('live-token');
      final client = AuthClient(
        client: MockClient((_) async => http.Response('', 204)),
      );
      expect(await client.logout(), AuthStatus.signedOut);
      expect(AuthSession.isAuthenticated, isFalse);
      expect(authRedirect('/sign-in', isAuthenticated: false), isNull);
      expect(authRedirect('/profile', isAuthenticated: false), '/entry');
      client.dispose();
    });
  });

  group('7 + 8. new and returning users stay authenticated', () {
    test('new user (register + onboarding) keeps the session', () async {
      final client = AuthClient(
        client: MockClient((_) async => http.Response(_authBody, 201)),
      );
      final result = await client.register(
        email: 'n@ew.co',
        password: 'Passw0rd1',
        idempotencyKey: 'new-user-key',
      );
      expect(result.isAuthenticated, isTrue);
      LocalStorage.onboardingComplete = true;
      expect(AuthSession.isAuthenticated, isTrue);
      expect(isGuestUser, isFalse);
      expect(authRedirect('/sign-in', isAuthenticated: true), '/home');
      client.dispose();
    });

    test('returning user (login + flag) keeps the session', () async {
      final client = AuthClient(
        client: MockClient((_) async => http.Response(_authBody, 200)),
      );
      final result = await client.login(email: 'o@ld.co', password: 'Passw0rd1');
      expect(result.isAuthenticated, isTrue);
      UserSession.isReturningUser = true;
      expect(AuthSession.isAuthenticated, isTrue);
      expect(isGuestUser, isFalse);
      for (final route in ['/home', '/profile', '/wardrobe']) {
        expect(authRedirect(route, isAuthenticated: true), isNull, reason: route);
      }
      client.dispose();
    });
  });

  group('9. initialization race', () {
    test('session transitions notify, so the router cannot stick on guest UI', () async {
      final before = AuthSession.authVersion.value;
      await AuthSession.saveSession('race-token');
      expect(AuthSession.authVersion.value, greaterThan(before));
      // A pre-restoration guard verdict for the shell is entry...
      expect(authRedirect('/home', isAuthenticated: false), '/entry');
      // ...but the post-restoration verdict recovers to the shell.
      expect(authRedirect('/home', isAuthenticated: true), isNull);
      final atClear = AuthSession.authVersion.value;
      await AuthSession.clearSession();
      expect(AuthSession.authVersion.value, greaterThan(atClear));
    });
  });

  group('10. backend authorization intact', () {
    test('failed login persists nothing and authenticates nothing', () async {
      final client = AuthClient(
        client: MockClient((_) async => http.Response('{"error":"nope"}', 401)),
      );
      final result = await client.login(email: 'o@ld.co', password: 'wrong');
      expect(result.isAuthenticated, isFalse);
      expect(AuthSession.isAuthenticated, isFalse);
      client.dispose();
    });

    test('token-less 200 persists nothing (never a fake session)', () async {
      final client = AuthClient(
        client: MockClient(
          (_) async => http.Response(
            jsonEncode(<String, dynamic>{'profile': <String, dynamic>{}}),
            200,
          ),
        ),
      );
      final result = await client.login(email: 'o@ld.co', password: 'Passw0rd1');
      expect(result.isAuthenticated, isFalse);
      expect(AuthSession.isAuthenticated, isFalse);
      client.dispose();
    });
  });

  group('entry screen', () {
    testWidgets('hides Sign In while a session is active', (tester) async {
      await _initPrefs(const {'auth_token': 'entry-session-token'});
      await tester.pumpWidget(_entryHarness());
      await tester.pump(const Duration(milliseconds: 300));
      expect(tester.takeException(), isNull);
      expect(find.text('FANSIVIBE'), findsOneWidget);
      expect(find.text('Sign In'), findsNothing);
      expect(find.text('Already have a Fansivibe account?'), findsNothing);
      // Let the returning-user hop finish: home must show no Sign In either.
      await tester.pump(const Duration(milliseconds: 1500));
      await tester.pump(const Duration(milliseconds: 500));
      expect(tester.takeException(), isNull);
      expect(find.text('Sign In'), findsNothing);
    });

    testWidgets('shows Sign In when signed out', (tester) async {
      await tester.pumpWidget(_entryHarness());
      await tester.pump(const Duration(milliseconds: 300));
      expect(tester.takeException(), isNull);
      expect(find.text('Sign In'), findsOneWidget);
    });
  });
}
