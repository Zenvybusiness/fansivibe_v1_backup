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
import 'package:fansivibe/shared/auth/secure_token_storage.dart';
import 'package:fansivibe/shared/theme/fansivibe_theme.dart';
import 'package:fansivibe/shared/utils/guest_mode.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:fansivibe/shared/utils/user_session.dart';

/// Global sign-out flow: one authoritative path (`AuthClient.logout` →
/// `AuthSession.clearSession`) must end the session, reset journey flags,
/// and land on onboarding entry with no way back into the shell.

Future<void> _initPrefs([Map<String, Object> seed = const {}]) async {
  SharedPreferences.setMockInitialValues(seed);
  LocalStorage.init(prefs: await SharedPreferences.getInstance());
}

/// Test-local router with the exact production wiring: the real routes,
/// the real guard, and the real session notifier.
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

  group('1 + 2. sign-out clears the session everywhere', () {
    test('token gone from memory and from the persisted store', () async {
      await AuthSession.saveSession('live-token');
      final client = AuthClient(
        client: MockClient((_) async => http.Response('', 204)),
      );
      expect(await client.logout(), AuthStatus.signedOut);
      expect(AuthSession.isAuthenticated, isFalse);
      expect(AuthSession.token, isNull);
      expect(SecureTokenStorage.currentToken, isNull);
      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getString('auth_token'), isNull);
      expect(prefs.containsKey('auth_token'), isFalse);
      client.dispose();
    });

    test('server failure still signs out locally (no stuck session)',
        () async {
      await AuthSession.saveSession('doomed-token');
      final offline = AuthClient(
        client: MockClient((_) async => throw Exception('down')),
      );
      expect(await offline.logout(), AuthStatus.signedOut);
      expect(AuthSession.isAuthenticated, isFalse);
      offline.dispose();
    });
  });

  group('3. session notification fires', () {
    test('authVersion changes on explicit logout', () async {
      await AuthSession.saveSession('notify-token');
      final before = AuthSession.authVersion.value;
      final client = AuthClient(
        client: MockClient((_) async => http.Response('', 204)),
      );
      await client.logout();
      expect(AuthSession.authVersion.value, greaterThan(before));
      client.dispose();
    });
  });

  group('4 + 5 + 9. router after sign-out', () {
    test('shell blocked, onboarding + sign-in reachable', () async {
      await AuthSession.saveSession('router-token');
      expect(authRedirect('/profile', isAuthenticated: true), isNull);
      final client = AuthClient(
        client: MockClient((_) async => http.Response('', 204)),
      );
      await client.logout();
      for (final route in [
        '/home',
        '/discover',
        '/stylist',
        '/wardrobe',
        '/profile',
        '/profile/settings',
      ]) {
        expect(authRedirect(route, isAuthenticated: false), '/entry',
            reason: route);
      }
      expect(authRedirect('/entry', isAuthenticated: false), isNull);
      expect(authRedirect('/sign-in', isAuthenticated: false), isNull);
      client.dispose();
    });
  });

  group('7. restart after sign-out stays signed out', () {
    test('no in-memory or persisted session survives', () async {
      await AuthSession.saveSession('restart-token');
      final client = AuthClient(
        client: MockClient((_) async => http.Response('', 204)),
      );
      await client.logout();
      client.dispose();
      // Simulate process death: drop all memory, keep the prefs store.
      AuthSession.resetForTest();
      LocalStorage.resetForTest();
      LocalStorage.init(prefs: await SharedPreferences.getInstance());
      expect(AuthSession.isAuthenticated, isFalse);
      expect(isGuestUser, isFalse);
    });
  });

  group('11. sign-out ends the session, never deletes user data', () {
    test('journey flags reset; content and ledgers preserved', () async {
      await AuthSession.saveSession('data-token');
      LocalStorage.savedLocally = true;
      LocalStorage.onboardingComplete = true;
      LocalStorage.displayName = 'Alex';
      LocalStorage.isReturningUser = true;
      LocalStorage.vibe = 'Minimal';
      LocalStorage.hasSavedWardrobeItem = true;
      LocalStorage.onboardingPhotoCaptured = true;
      LocalStorage.savedLookIds = ['look-1'];
      LocalStorage.pendingAuthIntent = '{"action":"save"}';
      LocalStorage.migratedGuestIds = ['local-1'];
      final client = AuthClient(
        client: MockClient((_) async => http.Response('', 204)),
      );
      await client.logout();
      client.dispose();
      expect(AuthSession.isAuthenticated, isFalse);
      expect(LocalStorage.savedLocally, isFalse);
      expect(LocalStorage.onboardingComplete, isFalse);
      // Session-derived identity is invalidated with the session.
      expect(LocalStorage.displayName, isNull);
      expect(LocalStorage.isReturningUser, isFalse);
      // The previous account's Home personalization is cleared with the
      // session: the next account to sign in on this device must not
      // inherit its vibe (curated look, journey state).
      expect(LocalStorage.vibe, isNull);
      // User data and preferences survive sign-out.
      expect(LocalStorage.hasSavedWardrobeItem, isTrue);
      expect(LocalStorage.onboardingPhotoCaptured, isTrue);
      expect(LocalStorage.savedLookIds, ['look-1']);
      expect(LocalStorage.pendingAuthIntent, '{"action":"save"}');
      expect(LocalStorage.migratedGuestIds, ['local-1']);
    });
  });

  group('6 + 8 + 10. widget: sign out lands on entry with no way back', () {
    testWidgets(
        'established SIGN OUT button ends at entry; back cannot return',
        (WidgetTester tester) async {
      await AuthSession.saveSession('widget-token');
      UserSession.isReturningUser = true;
      LocalStorage.onboardingComplete = true;
      final router = _guardedRouter('/profile');
      await tester.pumpWidget(_harness(router));
      await tester.pump(const Duration(milliseconds: 300));
      await tester.pump(const Duration(milliseconds: 300));
      expect(AuthSession.isAuthenticated, isTrue);

      final signOut = find.text('SIGN OUT');
      await tester.ensureVisible(signOut);
      await tester.pump(const Duration(milliseconds: 300));
      await tester.tap(signOut);
      await tester.pump(const Duration(milliseconds: 300));
      await tester.pump(const Duration(milliseconds: 1500));
      await tester.pump(const Duration(milliseconds: 500));

      expect(AuthSession.isAuthenticated, isFalse);
      // Onboarding entry renders normally with Sign In available.
      expect(find.text('Sign In'), findsOneWidget);
      expect(find.text('Analyze My Style'), findsOneWidget);
      expect(find.byType(NavigationBar), findsNothing);

      // System back cannot return into the shell.
      final popped = await tester.binding.handlePopRoute();
      expect(popped, isFalse);
      await tester.pump(const Duration(milliseconds: 300));
      expect(find.text('Sign In'), findsOneWidget);
      expect(find.byType(NavigationBar), findsNothing);
    });

    testWidgets('authed route unreachable after sign-out', (
      WidgetTester tester,
    ) async {
      await AuthSession.saveSession('guard-token');
      final router = _guardedRouter('/home');
      await tester.pumpWidget(_harness(router));
      await tester.pump(const Duration(milliseconds: 300));
      await tester.pump(const Duration(milliseconds: 300));
      expect(find.byType(NavigationBar), findsOneWidget);

      final client = AuthClient(
        client: MockClient((_) async => http.Response('', 204)),
      );
      await client.logout();
      client.dispose();
      await tester.pump(const Duration(milliseconds: 300));
      await tester.pump(const Duration(milliseconds: 1500));
      await tester.pump(const Duration(milliseconds: 500));
      expect(find.text('Sign In'), findsOneWidget);

      // A later push at an authed route still lands on entry.
      router.go('/wardrobe');
      await tester.pump(const Duration(milliseconds: 300));
      await tester.pump(const Duration(milliseconds: 300));
      expect(find.text('Sign In'), findsOneWidget);
      expect(find.byType(NavigationBar), findsNothing);
    });
  });
}
