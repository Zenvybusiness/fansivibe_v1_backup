import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:fansivibe/app/router/app_router.dart';
import 'package:fansivibe/app/router/route_names.dart';
import 'package:fansivibe/features/home/presentation/first_time_home_screen.dart';
import 'package:fansivibe/features/home/presentation/home_screen.dart';
import 'package:fansivibe/features/learning/domain/learning_service.dart';
import 'package:fansivibe/shared/auth/auth_session.dart';
import 'package:fansivibe/shared/theme/fansivibe_theme.dart';
import 'package:fansivibe/shared/utils/local_storage.dart';
import 'package:fansivibe/shared/utils/user_session.dart';

Widget _buildAppWithRouter(GoRouter router) {
  return MaterialApp.router(
    theme: FansivibeTheme.darkTheme,
    routerConfig: router,
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('HomeScreen Production Route Decision Tests', () {
    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      LocalStorage.init(prefs: await SharedPreferences.getInstance());
      LearningService.instance.resetForTest();
      await AuthSession.clearSession();
      LocalStorage.clear();
      UserSession.hasSavedWardrobeItem = false;
    });

    testWidgets(
      'REAL FIRST-TIME HOME ROUTE: Newly registered authenticated user renders FirstTimeHomeScreen',
      (WidgetTester tester) async {
        // Simulate real registration flow:
        await AuthSession.saveSession('test_jwt_token');
        expect(AuthSession.isAuthenticated, isTrue);

        final router = GoRouter(
          initialLocation: '/home',
          routes: appRoutes,
        );

        // When navigating to /home with onboarding_complete extra (as AccountCreationScreen does)
        await tester.pumpWidget(_buildAppWithRouter(router));
        router.goNamed(
          RouteNames.home,
          extra: {
            'onboarding_complete': true,
            'display_name': 'Alex',
          },
        );
        await tester.pumpAndSettle();

        // Must render FirstTimeHomeScreen with Alex's greeting matching Homes.pdf
        expect(find.byType(FirstTimeHomeScreen), findsOneWidget);
        expect(find.textContaining('Alex'), findsOneWidget);
        expect(find.text("Let's build your style\nprofile."), findsOneWidget);
        expect(find.text("TODAY'S LOOK"), findsOneWidget);
        expect(find.text('INITIAL LOOK'), findsOneWidget);
        expect(find.text('SCAN MY OUTFIT'), findsAtLeastNWidgets(1));
        expect(find.text('STYLE SCORE'), findsOneWidget);
        expect(find.text('0'), findsOneWidget);
        expect(find.text('Your score starts here'), findsOneWidget);
      },
    );

    testWidgets(
      'REAL NEW-USER ROUTE: Guest exploring with vibe renders the single New User Home (FirstTimeHomeScreen)',
      (WidgetTester tester) async {
        // Simulate explore path from VibeSelectScreen:
        LocalStorage.savedLocally = true;
        LocalStorage.vibe = 'Relaxed Streetwear';
        expect(AuthSession.isAuthenticated, isFalse);

        final router = GoRouter(
          initialLocation: '/home',
          routes: appRoutes,
        );

        await tester.pumpWidget(_buildAppWithRouter(router));
        router.goNamed(
          RouteNames.home,
          extra: {'vibe': 'Relaxed Streetwear'},
        );
        await tester.pumpAndSettle();

        // Only two Home experiences exist: guests see the New User Home.
        // (HomeScreen stays in the tree as the /home route shell that
        // selects the experience; FirstTimeHomeScreen is the experience.)
        expect(find.byType(FirstTimeHomeScreen), findsOneWidget);
        expect(find.text("Let's build your style\nprofile."), findsOneWidget);
        expect(find.text("TODAY'S LOOK"), findsOneWidget);
        expect(find.text('CURATED RECOMMENDATION'), findsOneWidget);
        expect(find.text('Relaxed Streetwear'), findsOneWidget);
      },
    );

    testWidgets(
      'REAL FIRST-TIME ROUTE: Subsequent visits before adding wardrobe/scans still render FirstTimeHomeScreen',
      (WidgetTester tester) async {
        // State after registration:
        await AuthSession.saveSession('test_jwt_token');
        LocalStorage.onboardingComplete = true;
        LocalStorage.displayName = 'Jordan';

        final router = GoRouter(
          initialLocation: '/home',
          routes: appRoutes,
        );

        // Cold start or tab switch without extra
        await tester.pumpWidget(_buildAppWithRouter(router));
        await tester.pumpAndSettle();

        expect(find.byType(FirstTimeHomeScreen), findsOneWidget);
        expect(find.textContaining('Jordan'), findsOneWidget);
        expect(find.text("Let's build your style\nprofile."), findsOneWidget);
      },
    );

    testWidgets(
      'ISOLATION: Unreachable backend + device residue resolves neutral error, never Old from leftovers',
      (WidgetTester tester) async {
        await AuthSession.saveSession('test_jwt_token');
        // Device-local history of unknown ownership (may be Account A's).
        // The backend is unreachable in widget tests, so no account-scoped
        // proof exists: neither Home experience may be invented from it.
        UserSession.hasSavedWardrobeItem = true;

        final router = GoRouter(
          initialLocation: '/home',
          routes: appRoutes,
        );

        await tester.pumpWidget(_buildAppWithRouter(router));
        await tester.pumpAndSettle();

        expect(find.byType(FirstTimeHomeScreen), findsNothing);
        expect(find.text('Quick Actions'), findsNothing);
        expect(
          find.text(
            "Couldn't load your Home. Please check your connection.",
          ),
          findsOneWidget,
        );
        expect(find.text('Try Again'), findsOneWidget);
      },
    );

    testWidgets(
      'RETURNING LOGIN with live history renders established HomeScreen',
      (WidgetTester tester) async {
        await AuthSession.saveSession('test_jwt_token');
        // History built live in this onboarding flow belongs to this user.
        UserSession.hasSavedWardrobeItem = true;

        final router = GoRouter(
          initialLocation: '/home',
          routes: appRoutes,
        );

        await tester.pumpWidget(_buildAppWithRouter(router));
        router.goNamed(
          RouteNames.home,
          extra: {
            'display_name': 'ReturningUser',
            'is_login': true,
          },
        );
        await tester.pumpAndSettle();

        expect(find.byType(FirstTimeHomeScreen), findsNothing);
        expect(find.byType(HomeScreen), findsOneWidget);
        expect(find.text('Quick Actions'), findsOneWidget);
      },
    );

    testWidgets(
      'is_login WITHOUT history resolves New User Home (data-empty login)',
      (WidgetTester tester) async {
        // is_login is not an established-account proof: nothing in
        // production passes it, and a data-empty login must never be posed
        // as established. Only account-scoped server history promotes (see
        // learning_summary Q/R).
        await AuthSession.saveSession('test_jwt_token');

        final router = GoRouter(
          initialLocation: '/home',
          routes: appRoutes,
        );

        await tester.pumpWidget(_buildAppWithRouter(router));
        router.goNamed(
          RouteNames.home,
          extra: {
            'display_name': 'ReturningUser',
            'is_login': true,
          },
        );
        await tester.pumpAndSettle();

        expect(find.byType(FirstTimeHomeScreen), findsOneWidget);
      },
    );
  });
}
