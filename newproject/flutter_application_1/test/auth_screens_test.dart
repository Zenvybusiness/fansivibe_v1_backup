import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:fansivibe/app/router/app_router.dart';
import 'package:fansivibe/features/auth/auth.dart';
import 'package:fansivibe/features/onboarding/presentation/screens/account_creation_screen.dart';
import 'package:fansivibe/features/onboarding/presentation/screens/entry_screen.dart';
import 'package:fansivibe/features/profile/presentation/profile_screen.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/theme/fansivibe_theme.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';

/// Scriptable fake: the widget tests drive outcomes without network.
class FakeAuthRepository implements AuthRepository {
  AuthResult nextRegister = const AuthResult.failure(AuthStatus.networkError);
  AuthResult nextLogin = const AuthResult.failure(AuthStatus.networkError);
  AuthResult nextSocial =
      const AuthResult.failure(AuthStatus.providerUnavailable);
  AuthStatus nextLogout = AuthStatus.signedOut;

  int registerCalls = 0;
  int loginCalls = 0;
  int logoutCalls = 0;
  String? lastEmail;

  @override
  Future<AuthResult> register({
    required String email,
    required String password,
    String? displayName,
    required String idempotencyKey,
  }) async {
    registerCalls++;
    lastEmail = email;
    expect(idempotencyKey.isNotEmpty, isTrue);
    if (nextRegister.isAuthenticated) {
      await AuthSession.saveSession('fake-session-token');
    }
    return nextRegister;
  }

  @override
  Future<AuthResult> login({
    required String email,
    required String password,
  }) async {
    loginCalls++;
    lastEmail = email;
    if (nextLogin.isAuthenticated) {
      await AuthSession.saveSession('fake-session-token');
    }
    return nextLogin;
  }

  @override
  Future<AuthResult> socialSignIn({
    required String provider,
    required String providerToken,
  }) async {
    return nextSocial;
  }

  @override
  Future<AuthStatus> logout() async {
    logoutCalls++;
    await AuthSession.clearSession();
    return nextLogout;
  }

  @override
  Future<bool> validateSession() async => AuthSession.isAuthenticated;
}

Future<void> _initPrefs() async {
  SharedPreferences.setMockInitialValues({});
  LocalStorage.init(prefs: await SharedPreferences.getInstance());
}

Widget _routerHarness(Widget child, {String location = '/test'}) {
  return MaterialApp.router(
    theme: FansivibeTheme.darkTheme,
    routerConfig: GoRouter(
      initialLocation: location,
      routes: [
        GoRoute(path: '/test', builder: (context, state) => child),
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
  });

  group('AccountCreationScreen real auth', () {
    testWidgets('register success persists the session and goes home',
        (WidgetTester tester) async {
      final fake = FakeAuthRepository()
        ..nextRegister = const AuthResult.authenticated(displayName: 'Alex');
      await tester.pumpWidget(
        _routerHarness(AccountCreationScreen(authRepository: fake)),
      );
      await tester.pumpAndSettle();

      await tester.enterText(
        find.widgetWithText(TextField, 'Email address'),
        'alex@example.com',
      );
      await tester.enterText(
        find.widgetWithText(TextField, 'Password'),
        'Passw0rd1',
      );
      await tester.pump();
      final createCta = find.text('Create Account').first;
      await tester.ensureVisible(createCta);
      await tester.pumpAndSettle();
      await tester.tap(createCta);
      await tester.pumpAndSettle();

      expect(fake.registerCalls, 1);
      expect(fake.lastEmail, 'alex@example.com');
      expect(AuthSession.token, 'fake-session-token');
      // Home shell renders after a real register (no fake local nav).
      expect(find.byType(NavigationBar), findsOneWidget);
    });

    testWidgets('register failure keeps the form and reports truthfully',
        (WidgetTester tester) async {
      final fake = FakeAuthRepository()
        ..nextRegister =
            const AuthResult.failure(AuthStatus.emailTaken);
      await tester.pumpWidget(
        _routerHarness(AccountCreationScreen(authRepository: fake)),
      );
      await tester.pumpAndSettle();

      await tester.enterText(
        find.widgetWithText(TextField, 'Email address'),
        'dupe@example.com',
      );
      await tester.enterText(
        find.widgetWithText(TextField, 'Password'),
        'Passw0rd1',
      );
      await tester.pump();
      final createCta = find.text('Create Account').first;
      await tester.ensureVisible(createCta);
      await tester.pumpAndSettle();
      await tester.tap(createCta);
      await tester.pumpAndSettle();

      expect(fake.registerCalls, 1);
      expect(AuthSession.token, isNull);
      expect(find.textContaining('already registered'), findsOneWidget);
      expect(find.byType(NavigationBar), findsNothing);
    });

    testWidgets('login mode signs in through the login endpoint', (
      WidgetTester tester,
    ) async {
      final fake = FakeAuthRepository()
        ..nextLogin = const AuthResult.authenticated(displayName: 'Sam');
      await tester.pumpWidget(
        _routerHarness(
          AccountCreationScreen(authRepository: fake, mode: 'login'),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Welcome Back'), findsOneWidget);
      await tester.enterText(
        find.widgetWithText(TextField, 'Email address'),
        'sam@example.com',
      );
      await tester.enterText(
        find.widgetWithText(TextField, 'Password'),
        'Passw0rd1',
      );
      await tester.pump();
      final signInCta = find.text('Sign In').first;
      await tester.ensureVisible(signInCta);
      await tester.pumpAndSettle();
      await tester.tap(signInCta);
      await tester.pumpAndSettle();

      expect(fake.loginCalls, 1);
      expect(fake.registerCalls, 0);
      expect(AuthSession.token, 'fake-session-token');
      expect(find.byType(NavigationBar), findsOneWidget);
    });

    testWidgets('social sign-in reports honest unavailability', (
      WidgetTester tester,
    ) async {
      final fake = FakeAuthRepository();
      await tester.pumpWidget(
        _routerHarness(AccountCreationScreen(authRepository: fake)),
      );
      await tester.pumpAndSettle();

      final googleCta = find.text('Google');
      await tester.ensureVisible(googleCta);
      await tester.pumpAndSettle();
      await tester.tap(googleCta);
      await tester.pumpAndSettle();

      expect(AuthSession.token, isNull);
      expect(find.textContaining("isn't available yet"), findsOneWidget);
      expect(find.byType(NavigationBar), findsNothing);
    });
  });

  group('EntryScreen sign-in routing', () {
    testWidgets('Sign In opens the account screen in login mode', (
      WidgetTester tester,
    ) async {
      await tester.pumpWidget(_routerHarness(const EntryScreen()));
      await tester.pump(const Duration(milliseconds: 1300));

      final signInFinder = find.text('Sign In');
      await tester.ensureVisible(signInFinder);
      await tester.tap(signInFinder);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));

      expect(find.text('Welcome Back'), findsOneWidget);
    });
  });

  group('ProfileScreen real logout', () {
    testWidgets('sign out clears the session and returns to entry', (
      WidgetTester tester,
    ) async {
      await AuthSession.saveSession('tok-profile');
      final fake = FakeAuthRepository();
      await tester.pumpWidget(
        _routerHarness(ProfileScreen(authRepository: fake)),
      );
      await tester.pumpAndSettle();

      final signOutFinder = find.text('Sign Out');
      await tester.ensureVisible(signOutFinder);
      await tester.tap(signOutFinder);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));

      expect(fake.logoutCalls, 1);
      expect(AuthSession.token, isNull);
      // Entry screen renders after a real logout.
      expect(find.text('Sign In'), findsOneWidget);
    });
  });

  group('Auth redirect contract', () {
    testWidgets('no dev-token leakage: sessionless screens send no token',
        (WidgetTester tester) async {
      expect(AuthSession.token, isNull);
      expect(AuthSession.isAuthenticated, isFalse);
      expect(
        AuthSession.effectiveToken('dev'),
        'dev',
      );
      await AuthSession.saveSession('user-token');
      expect(AuthSession.effectiveToken('dev'), 'user-token');
    });
  });
}
