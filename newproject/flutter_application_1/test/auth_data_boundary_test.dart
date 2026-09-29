import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/app/router/app_router.dart';
import 'package:fansivibe/app/router/auth_guard.dart';
import 'package:fansivibe/features/auth/auth.dart';
import 'package:fansivibe/features/home/presentation/first_time_home_screen.dart';
import 'package:fansivibe/features/learning/data/models.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/theme/fansivibe_theme.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:fansivibe/shared/utils/user_session.dart';

/// Authentication/presentation boundary across Home, Discover, Profile.
///
/// Mandatory regression for the demonstrated runtime state:
/// `auth=false` with `displayName/isReturningUser/analysis/prefs/local
/// style data` present. Local data is never proof of authentication —
/// only `AuthSession.isAuthenticated` gates personalized UI. Signing out
/// never deletes the data; screens simply must not expose it.

String _body(String name, String token) =>
    '{"accessToken":"$token","tokenType":"bearer","expiresIn":3600,'
    '"profile":{"displayName":"$name","styleProfile":{},"preferences":{},'
    '"settings":{},"flags":{},"version":0}}';

Future<void> _initPrefs([Map<String, Object> seed = const {}]) async {
  SharedPreferences.setMockInitialValues(seed);
  LocalStorage.init(prefs: await SharedPreferences.getInstance());
}

/// The exact runtime leftovers from the bug report: signed out, but the
/// device still holds the previous identity, history, prefs, and style
/// data (legacy state or an uncleared path — never a session).
void _seedStaleLocalState() {
  LocalStorage.displayName = 'Shivu';
  LocalStorage.isReturningUser = true;
  LocalStorage.savedLocally = true;
  LocalStorage.onboardingPhotoCaptured = true;
  LocalStorage.vibe = 'Minimal';
  LocalStorage.hasSavedWardrobeItem = true;
  final service = LearningService.instance;
  service.addItem(const WardrobeEntry(
    id: 'local-1',
    name: 'Tee',
    category: 'tops',
    color: 'black',
  ));
  service.addSavedLook('Evening Look');
  service.addPreferredOccasion('casual');
  service.recordSignal('analysis_updated', 'label');
  expect(AuthSession.isAuthenticated, isFalse);
}

/// Same screen writes as `SignInScreen._handleAuthSuccess`.
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

  group('HOME boundary (auth=false + stale local data)', () {
    testWidgets('no personal score, no name, New User Home only', (
      WidgetTester tester,
    ) async {
      _seedStaleLocalState();
      await tester.pumpWidget(_harness(_guardedRouter('/home')));
      await _pump(tester);

      // Only two Home experiences exist: signed out (even with stale
      // previous-account leftovers) always renders the New User Home —
      // never the old user's personalized Home, and never the stale name.
      expect(find.byType(FirstTimeHomeScreen), findsOneWidget);
      expect(find.textContaining('Shivu'), findsNothing);
      expect(find.text('Good morning, Shivu'), findsNothing);
      expect(find.text('DEVICE ONLY'), findsNothing);
      expect(find.text('Sign in to sync & back up'), findsNothing);
      expect(find.text('Style Score'), findsNothing);
      expect(find.text('Style Streak'), findsNothing);
      // The New User Home renders its uncalibrated baseline instead.
      expect(find.text("TODAY'S LOOK"), findsOneWidget);
      expect(find.text('STYLE SCORE'), findsOneWidget);
      expect(find.text('Uncalibrated'), findsOneWidget);
    });
  });

  group('DISCOVER boundary (auth=false + stale local data)', () {
    testWidgets('no personalized For You; trending path intact', (
      WidgetTester tester,
    ) async {
      _seedStaleLocalState();
      await tester.pumpWidget(_harness(_guardedRouter('/discover')));
      await _pump(tester);

      expect(find.text('Shivu'), findsNothing);
      await tester.tap(find.text('For You'));
      await _pump(tester);
      // Guest For You hero, never the personalized feed.
      expect(find.text('EXPLORE TRENDING LOOKS →'), findsOneWidget);
      expect(find.text('CURATED FOR YOU'), findsNothing);
      expect(find.text('94% STYLE MATCH'), findsNothing);
    });
  });

  group('PROFILE boundary (auth=false + stale local data)', () {
    testWidgets('guest profile, never the previous account', (
      WidgetTester tester,
    ) async {
      _seedStaleLocalState();
      await tester.pumpWidget(_harness(_guardedRouter('/profile')));
      await _pump(tester);

      expect(find.text('Shivu'), findsNothing);
      expect(find.text('STYLE LEVEL: ADVANCED'), findsNothing);
      expect(find.text('On this device'), findsOneWidget);
    });
  });

  group('opposite: authenticated experience intact', () {
    testWidgets('name, For You, and account profile work', (
      WidgetTester tester,
    ) async {
      await _signInAs('Shivu', 'tok-shivu');
      var router = _guardedRouter('/home');
      await tester.pumpWidget(_harness(router));
      await _pump(tester);
      expect(find.text('Good morning, Shivu'), findsOneWidget);

      router = _guardedRouter('/discover');
      await tester.pumpWidget(_harness(router));
      await _pump(tester);
      await tester.tap(find.text('For You'));
      await _pump(tester);
      expect(find.text('EXPLORE TRENDING LOOKS →'), findsNothing);

      router = _guardedRouter('/profile');
      await tester.pumpWidget(_harness(router));
      await _pump(tester);
      expect(find.text('Shivu'), findsWidgets);
    });
  });

  group('sign-out to guest regression across all three', () {
    testWidgets('Shivu in, out, guest everywhere, Shivu back', (
      WidgetTester tester,
    ) async {
      await _signInAs('Shivu', 'tok-shivu');
      var router = _guardedRouter('/profile');
      await tester.pumpWidget(_harness(router));
      await _pump(tester);
      expect(find.text('Shivu'), findsWidgets);

      await _signOut();
      expect(AuthSession.isAuthenticated, isFalse);
      // Guest onboarding without signing in.
      LocalStorage.savedLocally = true;
      LocalStorage.vibe = 'Minimal';

      router = _guardedRouter('/home');
      await tester.pumpWidget(_harness(router));
      await _pump(tester);
      expect(find.text('Shivu'), findsNothing);
      expect(find.text('DEVICE ONLY'), findsNothing);

      router = _guardedRouter('/discover');
      await tester.pumpWidget(_harness(router));
      await _pump(tester);
      await tester.tap(find.text('For You'));
      await _pump(tester);
      expect(find.text('CURATED FOR YOU'), findsNothing);
      expect(find.text('Shivu'), findsNothing);

      router = _guardedRouter('/profile');
      await tester.pumpWidget(_harness(router));
      await _pump(tester);
      expect(find.text('Shivu'), findsNothing);
      expect(find.text('On this device'), findsOneWidget);

      // Data survived: a new sign-in restores the account experience.
      await _signInAs('Shivu', 'tok-shivu-2');
      router = _guardedRouter('/home');
      await tester.pumpWidget(_harness(router));
      await _pump(tester);
      expect(find.text('Good morning, Shivu'), findsOneWidget);
    });
  });
}
